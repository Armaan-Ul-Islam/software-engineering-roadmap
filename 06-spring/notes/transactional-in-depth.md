# @Transactional in depth

> **In one sentence:** `@Transactional` is a proxy that opens a transaction before your method and commits or rolls back after it, so it only works when the call passes through the proxy, and by default it only rolls back for unchecked exceptions.

**Why it matters:** The two most common transaction bugs in Spring applications are a `@Transactional` method that silently runs without a transaction (self-invocation) and a checked exception that silently commits half the work. Both pass every unit test and fail in production. Understanding the proxy mechanism also explains propagation, why `readOnly` is a hint, and where transaction boundaries belong.

## The idea

When a bean has a `@Transactional` method, Spring does not change the bean. It wraps it in a proxy and injects the proxy everywhere the bean is used. A call goes:

```
caller  -->  proxy (TransactionInterceptor)  -->  your bean
                 |                                   |
                 |  1. begin or join a transaction   |
                 |  2. invoke the real method  ----->|
                 |  3. commit, or roll back on a     |
                 |     matching exception            |
```

Step 1 is governed by **propagation**. `REQUIRED` (the default) joins an existing transaction if the calling thread has one, otherwise starts one and binds the JDBC connection to the thread. `REQUIRES_NEW` suspends the outer transaction and starts an independent one on a second connection. `MANDATORY` fails if there is none; `SUPPORTS`, `NOT_SUPPORTED` and `NEVER` behave as their names say; `NESTED` uses a JDBC savepoint.

Step 3 is governed by the **rollback rules**. By default Spring rolls back for `RuntimeException` and `Error` and commits for checked exceptions. That default comes from EJB, not from good sense; override it with `rollbackFor = Exception.class` or use unchecked exceptions for failures.

Two attributes only take effect when the method *starts* a transaction: `isolation` and `timeout`. If the method joins an existing transaction, they are ignored (Spring can be told to complain via `validateExistingTransaction`). `readOnly = true` is a hint: with Hibernate it disables flushing, so modified entities are not written, and the PostgreSQL driver marks the connection read-only.

## Example: the three classic bugs

```java
@Service
public class ImportService {

    private final RowRepository rowRepository;

    public ImportService(RowRepository rowRepository) {
        this.rowRepository = rowRepository;
    }

    public void importAll(List<Row> rows) {
        for (Row row : rows) {
            importOne(row);                       // bug 1
        }
    }

    @Transactional
    public void importOne(Row row) {
        rowRepository.save(row);
    }

    @Transactional
    public void transfer(Account from, Account to, Money amount) throws InsufficientFundsException {
        from.debit(amount);                       // bug 2
        if (from.isOverdrawn()) {
            throw new InsufficientFundsException();
        }
        to.credit(amount);
    }

    @Transactional
    public void importWithRecovery(List<Row> rows) {
        for (Row row : rows) {
            try {
                rowService.importOne(row);       // another bean, REQUIRED
            } catch (RuntimeException exception) {
                log.warn("skipping row", exception);   // bug 3
            }
        }
    }
}
```

**Bug 1, self-invocation.** `importAll` calls `importOne` through `this`, not through the proxy, so no transaction starts and each `save` runs in its own autocommit statement. Fix: move `importOne` to another bean, or annotate `importAll` instead, or (rarely) inject the bean into itself through `ObjectProvider<ImportService>` and call through that.

**Bug 2, checked exception.** `InsufficientFundsException` is checked, so the transaction commits with the debit applied and no credit. Fix: `@Transactional(rollbackFor = Exception.class)`, or make the exception extend `RuntimeException`.

**Bug 3, swallowed rollback.** `rowService.importOne` joined the outer transaction. When it threw, the interceptor on *that* method marked the shared transaction rollback-only. Catching the exception does not undo that. At the end of `importWithRecovery` the commit fails with `UnexpectedRollbackException: Transaction silently rolled back because it has been marked as rollback-only`. Fix: give `importOne` `REQUIRES_NEW` so each row is its own transaction, or validate rows before writing instead of catching.

To see what is really happening, turn on the interceptor's log:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
```

You will see `Getting transaction for [ImportService.importOne]` and `Completing transaction for [...]` only for calls that actually went through the proxy. In code, `TransactionSynchronizationManager.isActualTransactionActive()` answers the same question.

## Where the boundary belongs

Put `@Transactional` on the application-service method that implements one use case ("place order", "import file"). Not on controllers, which would keep the connection open while serialising the response, and not on individual repository calls, which are too small to express a business invariant. Keep remote calls (HTTP, message brokers, email) outside the transaction or after it: a transaction holding a pooled connection while waiting on a 2-second HTTP call is how connection pools run dry. If the database write and the message send must both happen, use the transactional outbox pattern rather than hoping.

## Pitfalls

- Non-public methods. Private methods are never intercepted. Since Spring Framework 6, class-based proxies honour `protected` and package-private methods; before that only `public` worked. Keep transactional methods public to avoid the question.
- Annotating interfaces. With CGLIB class proxies, annotations on interface methods are not seen; annotate the concrete class.
- `@Async` and new threads. The transaction is bound to the calling thread; code running on another thread, including `CompletableFuture.supplyAsync`, is outside it.
- `REQUIRES_NEW` as a "save progress" hack. It uses a second connection while the first stays open, which halves your effective pool size and can deadlock when the inner transaction waits on a row the outer one locked.
- `readOnly = true` on a method that modifies entities. Hibernate will not flush, and the change is lost without an error.
- `@Transactional` on tests. The test transaction rolls back at the end and keeps the session open, which hides `LazyInitializationException` and flush-time constraint violations that production will hit.
- Messaging inside the transaction. A Kafka send inside `@Transactional` is not rolled back with the database; the consumer may receive an event about data that was never committed.

## Check yourself

1. A `@Transactional` method calls another `@Transactional(propagation = REQUIRES_NEW)` method on the same bean. How many transactions run?
2. Your service throws a checked `IOException` after inserting two rows. What is in the database afterwards, and what single change fixes it?
3. Why is `UnexpectedRollbackException` thrown at the outer method rather than at the line that failed?
4. Where would you draw the transaction boundary for "create order, charge the card, send a confirmation email", and what pattern makes the event publication reliable?

## Go deeper

- [Spring Framework: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) · the reference, including the propagation and rollback-rule sections.
- [Spring Framework: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) · why self-invocation bypasses the proxy, with a diagram.
- [Marco Behler: Spring Transaction Management, an unconventional guide](https://www.marcobehler.com/guides/spring-transaction-management) · builds the mental model from plain JDBC up to `@Transactional`.
- [Vlad Mihalcea: Spring transaction best practices](https://vladmihalcea.com/spring-transaction-best-practices/) · the data-access side: read-only transactions, connection acquisition, and avoiding long transactions.

---

Part of [Spring](../README.md) · items 1.4, 4.3
