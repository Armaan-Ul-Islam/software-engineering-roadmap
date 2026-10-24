# JdbcClient, JdbcTemplate and the connection pool underneath

> **In one sentence:** Boot wires a HikariCP pool from `spring.datasource.*`, `JdbcTemplate` and the fluent `JdbcClient` run the SQL you write against it with connections borrowed and returned and exceptions translated for you, and both join whatever `@Transactional` transaction is open, which makes plain SQL a first-class citizen next to JPA rather than a fallback.

**Why it matters:** The connection pool is the narrowest point in most Spring services and the least understood: ten connections, a thirty-second wait, and a stack trace saying `Connection is not available` long after the real cause. On the query side, the reporting screen, the bulk import and the `ON CONFLICT` upsert do not want an ORM, and teams who equate Spring with JPA either bend Hibernate into shape or drop to raw JDBC with try-finally everywhere. `JdbcClient` is the ten-minute answer to the second problem, and the pool's metrics are the answer to the first.

## The idea

**The pool.** With `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa` on the classpath, `DataSourceAutoConfiguration` builds a `HikariDataSource` from `spring.datasource.url`, `username` and `password`; the driver is inferred from the URL. Everything else lives under `spring.datasource.hikari.*`, and these are the settings that matter:

| Property | Default | What it decides |
|---|---|---|
| `maximum-pool-size` | 10 | Concurrent database operations for the whole instance. Raising it rarely helps: the database has a fixed number of cores and the pool is a queue in front of them |
| `connection-timeout` | 30000 ms | How long a thread waits for a free connection before `SQLTransientConnectionException: ... Connection is not available, request timed out after 30000ms`. Lower it to fail fast under overload |
| `max-lifetime` | 1800000 ms | Connections are retired after this; keep it shorter than any idle limit in the database, PgBouncer or a cloud load balancer in between |
| `keepalive-time` | 0 (off) | Pings idle connections so firewalls do not drop them silently |
| `leak-detection-threshold` | 0 (off) | Logs a stack trace when a connection is held longer than this; 20000 ms finds the long transactions nobody admitted to |
| `minimum-idle` | same as maximum | Leave it; a fixed-size pool is what HikariCP recommends |

Hikari's numeric values are milliseconds. The meters Boot binds (`hikaricp.connections.active`, `idle`, `pending`, `timeout`, `acquire`, `usage`) tell the story under load: `pending` above zero means threads are waiting, `timeout` counting up means they gave up, and `usage` is how long each connection is held, which is the number to shrink (item 8.1). HikariCP's own pool-sizing page is counter-intuitive and worth reading once: a pool of ten beats a pool of a hundred on most hardware.

**`JdbcTemplate`** wraps the JDBC ceremony: borrow a connection, prepare and bind a statement, iterate the `ResultSet`, close everything, and translate `SQLException` into Spring's `DataAccessException` hierarchy (`DuplicateKeyException`, `DataIntegrityViolationException`, `EmptyResultDataAccessException`). It uses `?` placeholders; `NamedParameterJdbcTemplate` adds `:name` parameters. Boot auto-configures both and applies `spring.jdbc.template.query-timeout`, `fetch-size` and `max-rows`.

**`JdbcClient`** (Spring Framework 6.1, auto-configured since Boot 3.2) is a fluent facade over the same machinery. `sql(...)` takes the statement, `param(...)` binds by name or position, `paramSource(record)` binds every component of a record or bean by name, `query(Class)` maps rows onto a record or a simple type, `query(RowMapper)` takes your own mapper, `update()` returns the row count and `update(KeyHolder)` captures generated keys. Column names map onto record components with underscores converted to camel case (`customer_email` to `customerEmail`), which needs the constructor parameter names at runtime; the Boot build plugins compile with `-parameters`, so this works out of the box. `JdbcClient` has no batch method in Spring 6.x, so batches still go through `JdbcTemplate.batchUpdate`.

**Transactions.** Both borrow connections through `DataSourceUtils`, which returns the connection bound to the current thread when a transaction is active. So `@Transactional` on the service covers `JdbcClient` calls exactly as it covers repositories, and without a transaction each statement runs in its own autocommit connection. With JPA present, `JpaTransactionManager` exposes the same connection to JDBC code, so an `EntityManager` and a `JdbcClient` share one transaction. The trap is flush order: Hibernate queues writes until flush, so a JDBC query in the same transaction does not see them until you call `entityManager.flush()`.

**When plain SQL wins.** Reports and aggregates, bulk writes, database-specific features (`ON CONFLICT`, window functions, `jsonb`, recursive CTEs), read models that return exactly the columns a screen needs, and anything where you want to read the SQL that will run. JPA wins when an aggregate has a lifecycle, dirty checking saves you writing a hundred `update` statements, and the object graph is the model. They coexist well: one `DataSource`, one transaction manager, JPA for the aggregates that are modified, `JdbcClient` for what is only read or written in bulk (item 5.10). Spring Data JDBC sits between the two (item 5.11).

## Example: a repository written with JdbcClient

```sql
CREATE TABLE product (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku     text NOT NULL UNIQUE,
    name    text NOT NULL,
    price   numeric(12, 2) NOT NULL,
    active  boolean NOT NULL DEFAULT true
);
```

An identity column is fine here; the batching problem with `IDENTITY` belongs to Hibernate, not to JDBC (item 5.7).

```java
public record Product(Long id, String sku, String name, BigDecimal price, boolean active) {
}

public record NewProduct(String sku, String name, BigDecimal price) {
}
```

```java
@Repository
public class ProductRepository {

    private final JdbcClient jdbcClient;
    private final JdbcTemplate jdbcTemplate;

    public ProductRepository(JdbcClient jdbcClient, JdbcTemplate jdbcTemplate) {
        this.jdbcClient = jdbcClient;
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<Product> findBySku(String sku) {
        return jdbcClient.sql("select id, sku, name, price, active from product where sku = :sku")
                .param("sku", sku)
                .query(Product.class)
                .optional();
    }

    public List<Product> findActiveCheaperThan(BigDecimal maxPrice, int limit) {
        return jdbcClient.sql("""
                select id, sku, name, price, active
                from product
                where active and price < :maxPrice
                order by price, id
                limit :limit
                """)
                .param("maxPrice", maxPrice)
                .param("limit", limit)
                .query(Product.class)
                .list();
    }

    public long insert(NewProduct newProduct) {
        return jdbcClient.sql("""
                insert into product (sku, name, price)
                values (:sku, :name, :price)
                returning id
                """)
                .paramSource(newProduct)
                .query(Long.class)
                .single();
    }

    public int deactivate(long id) {
        return jdbcClient.sql("update product set active = false where id = :id and active")
                .param("id", id)
                .update();
    }

    public void insertAll(List<NewProduct> newProducts) {
        jdbcTemplate.batchUpdate(
                "insert into product (sku, name, price) values (?, ?, ?)",
                newProducts,
                500,
                (preparedStatement, newProduct) -> {
                    preparedStatement.setString(1, newProduct.sku());
                    preparedStatement.setString(2, newProduct.name());
                    preparedStatement.setBigDecimal(3, newProduct.price());
                });
    }
}
```

Three details carry the design. `insert` uses PostgreSQL's `RETURNING` instead of a `GeneratedKeyHolder`: it is one statement, and it avoids the surprise that the PostgreSQL driver reports every column as a generated key, which makes `keyHolder.getKey()` throw unless you name the key column in `update(keyHolder, "id")`. `deactivate` returns the row count so the service can tell "already inactive" from "unknown id". `insertAll` sends 500 rows per round trip, and with `reWriteBatchedInserts=true` in the JDBC URL the PostgreSQL driver also rewrites each batch into multi-row `INSERT` statements, usually another large speed-up. A duplicate `sku` surfaces as `DuplicateKeyException` from either insert method, because the template translates the `SQLException` on the way out.

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/shop?reWriteBatchedInserts=true
spring.datasource.username=shop
spring.datasource.password=${DB_PASSWORD}
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=5000
spring.datasource.hikari.max-lifetime=1500000
spring.datasource.hikari.keepalive-time=300000
spring.datasource.hikari.leak-detection-threshold=20000
spring.jdbc.template.query-timeout=10s
```

To watch the statements, `logging.level.org.springframework.jdbc.core=DEBUG` prints `Executing prepared SQL statement [select id, sku, ...]` for every call, and `logging.level.org.springframework.jdbc.core.StatementCreatorUtils=TRACE` adds each bound value with its type.

## Pitfalls

- `queryForObject` or `single()` for a lookup that may find nothing. Zero rows is `EmptyResultDataAccessException`, not `null`; use `optional()`.
- Building SQL by concatenating values. Injection, a different plan per value, and no help from exception translation. Bind everything, including `limit`.
- Holding the connection across a remote call. A `@Transactional` method that calls a partner API keeps one of ten connections busy for the whole call (item 4.3); `leak-detection-threshold` is how you find these.
- Growing the pool to cure `Connection is not available`. When `usage` is high because transactions are long or queries slow, more connections add contention at the database and the timeout moves instead of disappearing.
- Expecting a `JdbcClient` query to see an entity persisted a line earlier in the same transaction. Hibernate has not flushed; call `flush()` first or keep the use case in one technology.
- A `@Transactional` method with `JdbcClient` calls that is invoked from the same class. The proxy is bypassed (item 4.3), so each statement autocommits and a failure half-way leaves the first rows in place.
- Mapping records with `query(Class)` in a build that does not pass `-parameters`. The constructor parameter names are missing, so columns cannot be matched. Boot's plugins set the flag; hand-written Maven or Gradle configuration may not.

## Check yourself

1. Hikari reports `pending=40`, `active=10` and `usage` averaging 800 ms for a query that takes 5 ms in `psql`. What is probably holding the connections, and which property would have shown you the stack trace?
2. Why does `insert ... returning id` with `query(Long.class).single()` avoid a problem that `GeneratedKeyHolder` has on PostgreSQL?
3. A `@Transactional` service persists an `Order` entity and then runs a `JdbcClient` count on the `orders` table. The count excludes the new row. Why, and what are two fixes?
4. A monthly revenue report grouped by customer and a "change order status" use case: which API for each, and what decides it?

## Go deeper

- [Spring: JdbcClient](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html#jdbc-JdbcClient) · the fluent API, parameter binding and row mapping rules, next to the `JdbcTemplate` chapter it sits in.
- [Spring Boot: SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html) · `DataSource` auto-configuration, the Hikari properties and the `JdbcTemplate` settings.
- [Marco Behler: JDBC guide](https://www.marcobehler.com/guides/jdbc) · raw JDBC first, then what the templates remove; the foundation this note assumes.
- [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · why small pools win, with the formula and the video demonstration.
- [HikariCP](https://github.com/brettwooldridge/HikariCP) · every configuration knob with its default, in the README.
- [PostgreSQL JDBC Driver: Initializing the Driver](https://jdbc.postgresql.org/documentation/use/) · the connection parameters, including `reWriteBatchedInserts`.

---

Part of [Spring](../README.md) · items 4.1, 4.2
