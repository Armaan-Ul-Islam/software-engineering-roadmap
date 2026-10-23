# The JPA persistence context and the entity lifecycle

> **In one sentence:** The persistence context is a per-transaction map of managed entities that guarantees one Java object per database row, remembers how each object looked when it was loaded, and at flush time writes exactly the differences, which is why changes to managed entities are saved without `save` and changes to detached ones are not saved at all.

**Why it matters:** "I called `setStatus` and nothing was written" and "it updated the row and I never called `save`" are the two most common JPA questions, and both are the same concept seen from two sides. The persistence context also decides when SQL runs, which is why a constraint violation appears at commit rather than at the line that caused it, and why bulk jobs run out of memory.

## The idea

Every `@Transactional` method gets an `EntityManager` whose persistence context lives as long as the transaction (unless Open Session in View extends it to the whole request, see item 5.5). An entity instance is always in one of four states relative to that context:

| State | Meaning | How you get there |
|---|---|---|
| Transient (new) | A plain object the context has never seen. No row. | `new Customer(...)` |
| Managed | Tracked by the context; has an id; changes are written at flush. | `persist`, `find`, any query result, the return value of `merge` |
| Detached | Was managed; the context closed or let it go. Changes are ignored. | transaction ended, `detach`, `clear`, `close` |
| Removed | Scheduled for `DELETE` at flush. | `remove` on a managed entity |

Three guarantees follow from the context being a map keyed by entity class and id.

**Identity.** `find` for an id already in the context returns the same instance without SQL. This is the first-level cache; it is per context, never shared across transactions, and cannot be turned off. A JPQL query always hits the database, but rows whose id is already managed are resolved to the existing instance, so the object you hold keeps its in-memory state even if the row changed underneath (call `refresh` if you need the database's version).

**Dirty checking.** When an entity is loaded, Hibernate keeps a snapshot of its column values. At flush it compares every managed entity with its snapshot and emits an `UPDATE` for each that differs. By default the statement lists all columns, so the same prepared statement is reused; `@DynamicUpdate` writes only changed columns. No `save` call is involved, and the cost grows with the number of managed entities, which is why a bulk job that loads a million rows into one context slows down and then dies.

**Flush timing.** Flushing is when the queued `INSERT`, `UPDATE` and `DELETE` statements are sent. With `FlushModeType.AUTO`, the default, that happens at commit and before any JPQL or Criteria query whose result could be affected by pending changes (and, when Hibernate is bootstrapped through JPA as in Spring Boot, before every native query, because Hibernate cannot tell which tables a native string touches). `FlushModeType.COMMIT` flushes only at commit, so a query in the middle of the transaction can return stale results. Hibernate's own `MANUAL` mode is what Spring sets for `@Transactional(readOnly = true)`: nothing is ever flushed, which is why a modification inside a read-only transaction vanishes silently (item 4.3). Call `entityManager.flush()` to force the SQL out early, for example to surface a unique-constraint violation at a line you can catch.

`persist` and `merge` differ in what they do with the object you pass. `persist(entity)` makes that instance managed; the `INSERT` is queued (or, with `IDENTITY` ids, executed immediately to obtain the key). `merge(entity)` copies the state of the argument onto a managed instance, loading it first if necessary, and returns the managed copy; the argument stays detached. Spring Data's `save` is `persist` if the entity looks new (null id, or `Persistable.isNew()` says so) and `merge` otherwise, so calling `save` on an entity that is already managed is a harmless no-op, and calling it on a detached object with an assigned id costs an extra `SELECT`.

## Example: eight steps and the SQL each one emits

`Customer` has a `SEQUENCE`-generated id. Logging is `logging.level.org.hibernate.SQL=DEBUG` plus `logging.level.org.hibernate.orm.jdbc.bind=TRACE` for the parameter values.

```java
@Transactional
public void walkThroughTheLifecycle() {
    Customer customer = new Customer("Ada");                                      // 1
    entityManager.persist(customer);                                              // 2
    customer.setName("Ada Lovelace");                                             // 3
    Customer sameInstance = entityManager.find(Customer.class, customer.getId()); // 4
    List<Customer> matches = entityManager
            .createQuery("select c from Customer c where c.name like 'Ada%'", Customer.class)
            .getResultList();                                                     // 5
    entityManager.detach(customer);
    customer.setName("A. L.");                                                    // 6
    Customer merged = entityManager.merge(customer);                              // 7
}                                                                                 // 8: commit
```

| Step | State of `customer` | SQL emitted |
|---|---|---|
| 1 | transient | none |
| 2 | managed, id assigned | `select nextval('customer_seq')` (once per block of ids, item 5.2); no `INSERT` yet |
| 3 | managed, dirty | none |
| 4 | managed | none; `sameInstance == customer` is `true` |
| 5 | managed | AUTO flush first: `insert into customer (name,id) values (?,?)`, then `select c1_0.id,c1_0.name from customer c1_0 where c1_0.name like ?` |
| 6 | detached | none, now or later |
| 7 | `customer` detached, `merged` managed | `select c1_0.id,c1_0.name from customer c1_0 where c1_0.id=?` (the row is re-read because `detach` evicted it), then the detached state is copied onto `merged` |
| 8 | | `update customer set name=? where id=?` with `A. L.`, because `merged` differs from its snapshot |

Step 3 produced no SQL; step 5 wrote the row only because the query needed a consistent view; step 6 is the "I set a field and nothing happened" bug in miniature, and step 7 shows that the fix is to work with the object `merge` returns.

Now the two classic reports:

1. **"I called the setter but nothing was written."** The entity was detached when you changed it. Typical cause: a `@Service` method without `@Transactional` calls `orderRepository.findById(...)`, whose own transaction ends when it returns, then modifies the result. Other causes: a `readOnly = true` transaction, a rollback, or modifying the argument of `merge` instead of its return value. Fix: load and modify inside one `@Transactional` method.
2. **"It updated the database and I never called `save`."** The entity was managed and the transaction committed; dirty checking did its job. If the write was unwanted, you mutated an entity you meant as read-only data. Map to a DTO for display, or make the transaction `readOnly`.

## Pitfalls

- Reading entities in one transaction and modifying them in another, with `merge` in between to "reattach". Every merge re-reads the row and overwrites it with whatever the detached copy held, including fields someone else changed since. Pair it with `@Version` (item 5.8) or restructure so the use case is one transaction.
- Catching a `DataIntegrityViolationException` around `repository.save(...)`. With a queued `INSERT`, the violation surfaces at flush or commit, outside your `try`. Call `flush()` where you want the error, or validate first.
- Loading a large result set in one transaction and updating as you go. Dirty checking compares every managed entity at every flush. Process in pages and call `flush()` then `clear()` per page (item 5.7).
- Assuming `find` after an `update` query returns the new values. A bulk JPQL `UPDATE` bypasses the context; entities already managed keep their old state. Use `@Modifying(clearAutomatically = true)` or `refresh` (item 5.10).
- Keeping entities in an HTTP session or a static cache. They are detached the moment the transaction ends; every lazy access is a `LazyInitializationException` (item 5.4) and every `merge` is a blind overwrite.
- Relying on `spring.jpa.show-sql=true`. It prints to standard output without parameters or timestamps. Use the two loggers above.

## Check yourself

1. In the example, why does step 5 emit an `INSERT` before the `SELECT`, and what would change under `FlushModeType.COMMIT`?
2. A controller calls `customerRepository.findById(id).orElseThrow()`, then `customer.setEmail(newEmail)`, then returns. Nothing is written. Explain why and give two fixes.
3. `entityManager.merge(detachedOrder)` returns an instance. You then modify `detachedOrder`. What is persisted?
4. Why is calling `save` on a managed entity harmless, and when does `save` cost an extra `SELECT`?

## Go deeper

- [Vlad Mihalcea: First-level cache](https://vladmihalcea.com/jpa-hibernate-first-level-cache/) · identity guarantee, write-behind and flush, with the SQL traces.
- [Vlad Mihalcea: JPA persist and merge](https://vladmihalcea.com/jpa-persist-and-merge/) · exactly what each operation does to the object you pass in.
- [Baeldung: JPA/Hibernate Persistence Context](https://www.baeldung.com/jpa-hibernate-persistence-context) · the state diagram in words, including transaction-scoped versus extended contexts.
- [Hibernate ORM documentation](https://hibernate.org/orm/documentation/) · the user guide's "Persistence Context" and "Flushing" chapters are the primary source for everything above.

---

Part of [Spring](../README.md) · item 5.1
