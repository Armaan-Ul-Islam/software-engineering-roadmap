# Hibernate write performance and JDBC batching

> **In one sentence:** Hibernate writes nothing until flush, and at flush it can hand inserts and updates to the driver in JDBC batches of `hibernate.jdbc.batch_size` statements, but only if the identifier does not force an immediate insert (`IDENTITY` does, `SEQUENCE` with the pooled optimiser does not), the statements are grouped by entity (`order_inserts`, `order_updates`), and the persistence context is flushed and cleared often enough that dirty checking and memory do not grow with the job.

**Why it matters:** The same import takes thirty seconds or three minutes depending on five configuration lines and the choice of id generator, and nothing in the code tells you which case you are in: `saveAll` looks identical either way. Teams discover this when a nightly job starts missing its window or an `OutOfMemoryError` appears once the data has grown. Knowing how to verify that batching happened turns a guess into a measurement.

## The idea

**Write-behind.** `persist` and dirty checking queue SQL; the statements are sent at flush, which happens at commit, before a query that needs consistent results, or when you call `flush()` (item 5.1). Batching is a property of that flush: Hibernate groups consecutive statements with the same SQL into one JDBC batch and calls `executeBatch` once per group, so a thousand inserts into one table can become twenty round trips.

**The settings.**

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

`batch_size` turns batching on (it is off by default) and caps a batch. `order_inserts` sorts the queued inserts by entity type so that an `Order, OrderLine, Order, OrderLine` sequence becomes all orders, then all lines; without it Hibernate must close the batch every time the statement changes, and a parent-child import batches almost nothing. `order_updates` does the same for updates. `hibernate.jdbc.batch_versioned_data` has defaulted to `true` since Hibernate 5, so entities with `@Version` batch too. On PostgreSQL, `reWriteBatchedInserts=true` in the JDBC URL additionally lets the driver rewrite a batch into multi-row `INSERT` statements.

**Why `IDENTITY` kills insert batching.** With an identity column the database assigns the id during the insert, and Hibernate needs the id when `persist` returns so that the entity can be managed by its key. It therefore executes the `INSERT` immediately, one statement per `persist`, outside any batch, and no setting changes that. `SEQUENCE` with `allocationSize = 50` and the default pooled optimiser fetches fifty ids per `select nextval(...)` and leaves the inserts to flush time, where they batch (item 5.2). Switching an existing table is a migration (drop the identity, create the sequence, start it past the current maximum), and it pays for itself on any table that receives bulk inserts.

**`persist`, `merge` and Spring Data `save`.** `persist` queues an insert and costs nothing else. `merge` loads the row first (one `SELECT`), copies the state over and returns the managed copy. Spring Data's `save` calls `persist` when the entity is new and `merge` otherwise, and "new" means the id is `null`, or the `@Version` attribute is `null`, or `Persistable.isNew()` returns true. An import that assigns ids itself (external keys, UUIDs generated in Java) therefore pays one `SELECT` per row before the insert; the fix is a `@Version` field, or implementing `Persistable` with a transient `isNew` flag cleared in `@PostPersist` and `@PostLoad`. `saveAll` is a loop over `save` inside one transaction, nothing more; it batches at flush exactly as well or as badly as the settings allow.

**Flush and clear in bulk jobs.** Dirty checking compares every managed entity with its snapshot at every flush, and every entity stays in the context until the transaction ends. A job that persists a million rows in one context gets slower per row and eventually exhausts the heap. Call `entityManager.flush()` and then `entityManager.clear()` every `batch_size` entities: flush sends one full batch, clear drops the references. This is about memory and dirty-checking cost; batching itself would also happen with a single flush at commit.

**`@DynamicUpdate`.** By default an `UPDATE` lists every column, so one prepared statement serves every update of that entity and batching works. `@DynamicUpdate` generates a statement with only the changed columns, which helps wide tables with large, rarely changed columns and reduces the chance that two concurrent updates of different columns overwrite each other, at the cost of a statement shape per combination of changed columns, which fragments batches. Decide per entity.

**Bulk JPQL.** `update Product p set p.active = false where p.updatedAt < :cutoff` is one statement for any number of rows and the right tool when no per-row logic is needed. It bypasses the persistence context: entities already loaded keep their old state and `@Version` is not incremented. With Spring Data, `@Modifying(clearAutomatically = true, flushAutomatically = true)` deals with the context (item 5.10). Likewise `deleteAll()` loads and removes entities one by one, while `deleteAllInBatch()` and `deleteAllByIdInBatch(ids)` issue one statement.

**Verifying.** Set `spring.jpa.properties.hibernate.generate_statistics=true` and Hibernate logs a `Session Metrics` block at the end of each session; `spent executing N JDBC batches` is the line to watch, and `N JDBC statements` next to it shows how many statements were prepared. For a per-batch view, Hibernate 6.2 and later log through `org.hibernate.orm.jdbc.batch` (set it to `TRACE`), and a JDBC proxy such as datasource-proxy shows each `executeBatch` call with its size.

## Example: a 10,000-row import, slowly and then correctly

The slow version: identity ids, no batch settings, one `saveAll`.

```java
@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private BigDecimal price;

    @Column(nullable = false)
    private boolean active = true;
}
```

```java
@Transactional
public void importSlowly(List<ProductRow> rows) {
    productRepository.saveAll(rows.stream().map(Product::from).toList());
}
```

With `logging.level.org.hibernate.SQL=DEBUG` the log is ten thousand of these, each one a round trip executed inside `persist`, while every entity stays in the persistence context until commit:

```text
insert into product (active,name,price,sku) values (?,?,?,?)
insert into product (active,name,price,sku) values (?,?,?,?)
insert into product (active,name,price,sku) values (?,?,?,?)
...
```

`Session Metrics` reports `10000 JDBC statements` and `0 JDBC batches`.

The correct version: a sequence with a matching allocation size, the three properties above, `persist` through the `EntityManager`, and a flush-and-clear per batch.

```java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "product_seq")
@SequenceGenerator(name = "product_seq", sequenceName = "product_seq", allocationSize = 50)
private Long id;
```

```sql
CREATE SEQUENCE product_seq START WITH 1 INCREMENT BY 50;
```

```java
@Service
public class ProductImporter {

    private static final int BATCH_SIZE = 50;

    private final EntityManager entityManager;

    public ProductImporter(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public void importInBatches(List<ProductRow> rows) {
        int persisted = 0;
        for (ProductRow row : rows) {
            entityManager.persist(Product.from(row));
            persisted++;
            if (persisted % BATCH_SIZE == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }
    }
}
```

`BATCH_SIZE` matches `hibernate.jdbc.batch_size` so that every flush is exactly one full batch. The log now has the shape of one `nextval` and one insert per fifty rows:

```text
select nextval('product_seq')
insert into product (active,name,price,sku,id) values (?,?,?,?,?)
select nextval('product_seq')
insert into product (active,name,price,sku,id) values (?,?,?,?,?)
...
```

The insert appears once per batch because the statement is prepared once and executed with fifty parameter sets. `Session Metrics` shows `200 JDBC batches`, and `org.hibernate.orm.jdbc.batch` at `TRACE` shows each batch of fifty being executed. The round trips fell from 10,000 to about 400 (around 200 sequence calls plus 200 batches); with `reWriteBatchedInserts=true` each batch is one multi-row statement on the wire. The persistence context never holds more than fifty entities, so the last row costs the same as the first.

## Pitfalls

- Setting `batch_size` and concluding that batching works. With `IDENTITY` ids nothing changes. Verify with statistics, not faith.
- Importing parents and children without `order_inserts`. Every alternation closes the batch, and the statistics show nearly as many batches as rows.
- `saveAll` on entities whose ids are assigned in code, without `@Version` or `Persistable`. Every row costs a `SELECT` before its `INSERT`; the code gives no hint.
- One persistence context for the whole job. Dirty checking cost grows with every flush and the heap fills. Flush and clear per batch, or process in pages with a transaction per page.
- `clear()` while holding references you still need. Everything is detached afterwards; modifying it does nothing, and `merge` costs a `SELECT`. Reload by id or arrange the loop so that nothing crosses a batch boundary.
- Bulk JPQL updates followed by reads of already-loaded entities. They show stale values, and a later dirty check can write the old state back over the bulk update (item 5.10).
- `@DynamicUpdate` on every entity "to be safe". It fragments update batches and defeats the prepared statement cache; use it for the wide tables that need it.
- Trusting `spring.jpa.show-sql=true`. It prints statements, not batches; only `generate_statistics` or a JDBC proxy tells you what actually went over the wire.

## Check yourself

1. A colleague sets `hibernate.jdbc.batch_size=100` on an `IDENTITY`-keyed table and reports no improvement. Explain why, and say what the `Session Metrics` block will show.
2. Importing 10,000 orders with three lines each, why does the batch count stay close to 40,000 without `order_inserts`, and what does it become with it?
3. `saveAll` on 5,000 entities whose UUIDs are generated in the constructor is twice as slow as expected. What is the extra statement per row, and what are two ways to remove it?
4. After a bulk `update Product p set p.active = false`, an entity loaded earlier in the same transaction still reports `active == true`, and after commit the row is `true` in the database as well. Explain both observations.

## Go deeper

- [Vlad Mihalcea: Batch processing with JPA and Hibernate](https://vladmihalcea.com/the-best-way-to-do-batch-processing-with-jpa-and-hibernate/) · flush, clear and transaction-per-batch, measured.
- [Vlad Mihalcea: How to batch INSERT and UPDATE statements with Hibernate](https://vladmihalcea.com/how-to-batch-insert-and-update-statements-with-hibernate/) · the three properties and the SQL logs that prove they work.
- [Vlad Mihalcea: Identity, sequence and table generators](https://vladmihalcea.com/hibernate-identity-sequence-and-table-sequence-generator/) · why `IDENTITY` disables batching and what the pooled optimiser does.
- [Vlad Mihalcea: JPA persist and merge](https://vladmihalcea.com/jpa-persist-and-merge/) · the extra `SELECT` behind `merge`, and therefore behind `save` on an entity with an assigned id.
- [Hibernate ORM documentation](https://hibernate.org/orm/documentation/) · the user guide's "Batching" chapter is the primary source for the settings above.
- [PostgreSQL JDBC Driver: Initializing the Driver](https://jdbc.postgresql.org/documentation/use/) · `reWriteBatchedInserts` and the other connection parameters.

---

Part of [Spring](../README.md) · item 5.7
