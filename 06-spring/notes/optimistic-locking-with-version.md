# Optimistic locking with @Version

> **In one sentence:** A `@Version` column makes every `UPDATE` conditional on the row still having the version the transaction read, so a concurrent change turns the lost update into an `ObjectOptimisticLockingFailureException` at commit, which you handle by retrying the whole transaction from outside it.

**Why it matters:** Any load-modify-save sequence under Read Committed is a lost update waiting for traffic (see the Databases domain on isolation levels). `@Version` is the cheapest correct fix for JPA entities, and it is also the one people implement half-way: they add the annotation, see the exception in the logs, and catch it inside the transactional method where it cannot be recovered from. Getting the retry in the right place is the whole skill.

## The idea

Add one field:

```java
@Version
private long version;
```

Hibernate manages it; never set it yourself. On every `UPDATE` or `DELETE` of that entity Hibernate appends the version it loaded to the `WHERE` clause and increments it:

```sql
update stock set available=?, version=? where id=? and version=?
-- binds: [7, 4, 42, 3]
```

JDBC reports how many rows the statement changed. One means nobody touched the row since you read it. Zero means another transaction committed a newer version in between, and Hibernate throws `StaleObjectStateException`, which the JPA layer wraps as `jakarta.persistence.OptimisticLockException`, which Spring's exception translation turns into `org.springframework.orm.ObjectOptimisticLockingFailureException`. It is a `RuntimeException`, so the transaction rolls back.

Two details decide where you can handle it.

1. **The check happens at flush**, which for most code means at commit, after your method has returned and while the `TransactionInterceptor` is committing. A `try`/`catch` inside the method never sees it. Even if you `flush()` manually and catch the exception, the persistence context is now inconsistent and the JPA specification marks the transaction for rollback; nothing you do inside it will commit.
2. **The retry must re-read.** The point of the exception is that your in-memory state is stale. A correct retry starts a new transaction, loads the row again, applies the business operation to the fresh state and tries to commit again. That is only safe if the operation is a function of the current state ("reserve 2 units if available"), not a replay of stale values ("set available to 7").

So the retry loop lives in a caller that is not inside the transaction, and the transactional method lives on another bean so the call goes through the proxy (item 4.3).

**Beyond a single row.** `LockModeType.OPTIMISTIC_FORCE_INCREMENT` on the aggregate root bumps its version whenever a child changes, so two transactions adding different lines to the same order conflict even though they touched different rows. That is how an aggregate's invariant ("at most ten lines") is protected with optimistic locking alone.

**The pessimistic alternative.** `LockModeType.PESSIMISTIC_WRITE` becomes `select ... for update` in PostgreSQL: the second transaction blocks until the first commits, then reads the new state. No exception, no retry, but a held lock for the duration of the transaction and the possibility of deadlocks when two transactions lock rows in different orders. Choose it for hot rows where retries would mostly fail (a popular product's inventory, a counter), and keep the locked section short. Set a timeout with the `jakarta.persistence.lock.timeout` hint: `0` gives `NOWAIT`, and Hibernate maps `-2` to `SKIP LOCKED`, the building block for picking jobs from a table.

## Example: a retry wrapper around a transactional service

```java
@Service
public class StockService {

    private final StockRepository stockRepository;

    public StockService(StockRepository stockRepository) {
        this.stockRepository = stockRepository;
    }

    @Transactional
    public void reserve(Long productId, int quantity) {
        Stock stock = stockRepository.findById(productId).orElseThrow();
        stock.reserve(quantity);
    }
}
```

No `save` is needed: `stock` is managed and dirty checking writes the `UPDATE ... where id=? and version=?` at commit (item 5.1). The wrapper is a separate bean:

```java
@Service
public class ReserveStockUseCase {

    private static final int MAX_ATTEMPTS = 3;

    private final StockService stockService;

    public ReserveStockUseCase(StockService stockService) {
        this.stockService = stockService;
    }

    public void reserve(Long productId, int quantity) {
        for (int attempt = 1; ; attempt++) {
            try {
                stockService.reserve(productId, quantity);
                return;
            } catch (ObjectOptimisticLockingFailureException exception) {
                if (attempt == MAX_ATTEMPTS) {
                    throw exception;
                }
            }
        }
    }
}
```

Each iteration is a complete transaction: open, `SELECT`, change, `UPDATE` with version check, commit. If two requests reserve the same product at once, one commits with version 3 to 4 and the other's `UPDATE ... and version=3` matches zero rows, rolls back, re-reads version 4 and succeeds on the second attempt with whatever is actually available. Add a short randomised sleep between attempts when contention is expected, so the retries do not collide again.

With Spring Retry on the classpath the loop becomes `@Retryable(retryFor = ObjectOptimisticLockingFailureException.class, maxAttempts = 3)` on `ReserveStockUseCase.reserve`, plus `@EnableRetry`. Spring Framework 7 ships the same idea in core as `@Retryable` under `org.springframework.resilience.annotation`, enabled with `@EnableResilientMethods`. In both cases the annotation must sit on a method that is outside the transaction, for the same proxy reasons.

The pessimistic version of the same operation, for comparison:

```java
public interface StockRepository extends JpaRepository<Stock, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints(@QueryHint(name = "jakarta.persistence.lock.timeout", value = "0"))
    Optional<Stock> findWithLockById(Long id);
}
```

```sql
select s1_0.id,s1_0.available,s1_0.version from stock s1_0 where s1_0.id=? for update nowait
```

PostgreSQL has no per-statement wait limit for row locks other than `NOWAIT` and `SKIP LOCKED`, so a positive millisecond value in that hint is ignored there; without the hint the statement waits until the holder commits or `lock_timeout` fires.

## Pitfalls

- Catching the exception inside the `@Transactional` method. It is thrown at commit, outside the method body, so the catch block is never reached; and if you force a flush to reach it, the transaction is already doomed.
- Retrying from the same bean. `this.reserve(...)` bypasses the proxy, so the "retry" runs inside the original, now rolled-back transaction. The retry loop and the transactional method belong on different beans.
- Retrying an operation that replays stale values. Loading the row, computing `available - 2` in the first attempt and writing that number on the second attempt loses the update you were protecting against. Recompute from the fresh row each time.
- Letting the version leak out of the server without using it. For a REST edit flow, the client must send back the version it displayed (for example as an `ETag` and `If-Match`), and the server must compare it; otherwise each request reads the current row and two users still overwrite each other, now with matching versions.
- A `@Version` on an `Integer` or `Long` that is set from a DTO. Hibernate treats an entity with a non-null version as existing; mapping a client-supplied version onto a new entity makes `save` call `merge` and issue a pointless `SELECT`, or fail.
- Pessimistic locks held across remote calls. The row stays locked while you wait for the payment provider; every other request for that product queues behind it until the pool is empty.

## Check yourself

1. Why can the `catch` for `ObjectOptimisticLockingFailureException` not be inside `StockService.reserve`, and what two properties must the method that contains it have?
2. Two transactions each add a line to the same order, touching different rows. How do you make them conflict with optimistic locking, and why would you want to?
3. When would you choose `PESSIMISTIC_WRITE` over `@Version`, and what new failure mode does it introduce?
4. A web form shows a product's price, the user edits it, and the request carries only the new price. Does `@Version` on the entity prevent two users from overwriting each other? What is missing?

## Go deeper

- [Baeldung: Optimistic Locking in JPA](https://www.baeldung.com/jpa-optimistic-locking) · the lock modes and the exceptions, with examples.
- [Baeldung: Pessimistic Locking in JPA](https://www.baeldung.com/jpa-pessimistic-locking) · `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE`, `FORCE_INCREMENT` and timeouts.
- [Spring Data JPA: Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html) · `@Lock` on repository methods.
- [Vlad Mihalcea: Lost update](https://vladmihalcea.com/a-beginners-guide-to-database-locking-and-the-lost-update-phenomena/) · the anomaly this note prevents, from the database side.

---

Part of [Spring](../README.md) · item 5.8
