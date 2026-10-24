# JDBC fundamentals

> **In one sentence:** JDBC is the thin layer every Java database access goes through: a `DataSource` hands out pooled connections, a `PreparedStatement` sends SQL with bound parameters (in batches when there are many rows), a `ResultSet` streams rows back in fetch-size chunks when autocommit is off, and transactions, timeouts and closing are your responsibility unless a framework does them for you, which is why you must know what the framework is doing.

**Why it matters:** Every JPA, Hibernate, jOOQ or Spring `JdbcClient` call ends as these few JDBC calls, and the production failures they cause are JDBC failures in a framework's clothes: a pool that runs dry, an `OutOfMemoryError` on an export, an import that is a hundred thousand round trips, a request that hangs forever because no timeout was set. Interviewers ask about autocommit, batching and fetch size because the answers separate people who have run an import or an export from people who have only written CRUD.

## The idea

**`DriverManager` versus `DataSource`.** `DriverManager.getConnection(url, user, password)` opens a new physical connection every time: TCP, often TLS, authentication, a server process (item 7.5). `javax.sql.DataSource` is the abstraction whose `getConnection()` may do that or may hand out a connection from a pool; application code depends on `DataSource` and never on the driver. In practice the `DataSource` is HikariCP (Spring Boot's default) wrapping the driver. `close()` on a pooled connection returns it to the pool, which is why every connection must be closed on every path, and try-with-resources is the only reliable way to do that.

**`PreparedStatement`.** SQL with `?` placeholders and parameters bound by position with typed setters: `setLong`, `setString`, `setBigDecimal`, `setObject` for `java.time` types (`OffsetDateTime` for `timestamptz`, `LocalDate` for `date`). The driver sends the SQL and the values separately, so a value can never be read as SQL (item 1.7), and the server can reuse the plan; the PostgreSQL driver switches to a named server-side prepared statement after `prepareThreshold` (5) executions on a connection, with the generic-plan consequences of item 3.5. Bind the right Java type: a `BigDecimal` bound against a `bigint` column defeats the index (item 3.5).

**Batching.** `addBatch()` collects parameter sets and `executeBatch()` sends them in one network round trip. With `reWriteBatchedInserts=true` in the URL, the PostgreSQL driver also rewrites a batch of `INSERT ... VALUES (?, ?, ?)` into multi-row statements, so the server parses and plans a few statements instead of thousands. Execute batches in chunks of a few hundred to a few thousand rows inside one transaction; a batch of millions holds them all in client memory and keeps the transaction open for its whole duration.

**Fetch size and large results.** By default the PostgreSQL driver reads the *entire* result into memory before `executeQuery()` returns, so a million-row query is an `OutOfMemoryError` waiting for production data. `setFetchSize(n)` makes the driver open a server-side cursor and fetch `n` rows at a time, but only when autocommit is off (the cursor lives inside a transaction), the result set is `TYPE_FORWARD_ONLY` and the statement is a single query; in autocommit mode the setting is silently ignored. Use it for exports, migrations and streaming responses, and keep that transaction read-only and as short as the stream (it pins a snapshot, item 6.5).

**Autocommit and transactions.** A connection starts in autocommit mode: every statement is its own transaction. For a unit of work, `setAutoCommit(false)`, run the statements, `commit()`, and `rollback()` on the exception path. HikariCP rolls back a connection that is returned with an open transaction and restores autocommit, so a forgotten commit loses the work rather than leaking it to the next borrower. Autocommit traps: a read followed by a write is two transactions and a lost update in waiting (item 5.2); `setFetchSize` does nothing; and a `@Transactional` that never started a transaction (item 5.5) leaves every statement in autocommit. After any error inside a transaction PostgreSQL rejects further statements until rollback (item 5.1); catching the exception and carrying on fails with `current transaction is aborted`.

**Timeouts, three of them.** `Statement.setQueryTimeout(seconds)` makes the driver cancel the statement from a timer thread; the server reports `canceling statement due to user request`, SQLState `57014`. The server-side `statement_timeout` (per role, per session, or `options=-c statement_timeout=5000` in the URL) cancels on the server with `canceling statement due to statement timeout`, including statements waiting on a lock. `socketTimeout` in the URL abandons a connection whose server has stopped answering (a crashed or partitioned server); without it a thread can wait forever. `connectTimeout` covers the handshake, and the pool's `connectionTimeout` covers waiting for a free connection (item 7.5). Set all of them.

**How JPA sits on top.** Hibernate takes a `Connection` from the `DataSource` when the transaction starts, generates SQL, runs it through `PreparedStatement`s and maps `ResultSet` rows to entities. Its settings are JDBC settings under other names: `hibernate.jdbc.batch_size` is `addBatch` (with `hibernate.order_inserts` so that statements of one kind are adjacent), `hibernate.jdbc.fetch_size` is `setFetchSize`, `jakarta.persistence.query.timeout` is `setQueryTimeout`, `@Transactional` is `setAutoCommit(false)` plus `commit` or `rollback`, and the flush is the moment the buffered statements are sent. A SQL log full of single-row inserts means batching is off at this layer (an `IDENTITY` id generator forces it off, because Hibernate needs the generated key after each insert); an export that dies with `OutOfMemoryError` means the fetch size was never set and every entity was also kept in the persistence context. Spring's `JdbcTemplate` and `JdbcClient` are the same calls with the closing and the exception translation done for you.

## Example: a complete method with batching, and a streaming read

PostgreSQL JDBC driver 42.7, HikariCP 7, Java 21. The `reading` table is the one from item 1.5; `event` is the 1.5 million row table from item 3.4.

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import javax.sql.DataSource;

public final class JdbcFundamentals {

    public static void main(String[] arguments) throws SQLException {
        int fetchSize = arguments.length > 0 ? Integer.parseInt(arguments[0]) : 1000;
        HikariConfig configuration = new HikariConfig();
        configuration.setJdbcUrl("jdbc:postgresql://localhost:5432/app?reWriteBatchedInserts=true&socketTimeout=30");
        configuration.setUsername("app");
        configuration.setPassword("secret");
        configuration.setMaximumPoolSize(4);
        try (HikariDataSource dataSource = new HikariDataSource(configuration)) {
            insertReadingsInBatches(dataSource, 100_000);
            long rowCount = streamReadings(dataSource, fetchSize);
            System.out.println("rows read: " + rowCount);
        }
    }

    static void insertReadingsInBatches(DataSource dataSource, int rowCount) throws SQLException {
        String sql = "INSERT INTO reading (device_id, occurred_at, temperature) VALUES (?, ?, ?)";
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement insert = connection.prepareStatement(sql)) {
                OffsetDateTime firstReading = OffsetDateTime.of(2026, 10, 1, 0, 0, 0, 0, ZoneOffset.UTC);
                for (int index = 0; index < rowCount; index++) {
                    insert.setString(1, "sensor-" + (index % 500));
                    insert.setObject(2, firstReading.plusSeconds(index * 7L));
                    insert.setBigDecimal(3, BigDecimal.valueOf(1500 + index % 1500, 2));
                    insert.addBatch();
                    if ((index + 1) % 1000 == 0) {
                        insert.executeBatch();
                    }
                }
                insert.executeBatch();
                connection.commit();
            } catch (SQLException exception) {
                connection.rollback();
                throw exception;
            }
        }
    }

    static long streamReadings(DataSource dataSource, int fetchSize) throws SQLException {
        long rowCount = 0;
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);                       // the cursor lives inside this transaction
            try (PreparedStatement select = connection.prepareStatement(
                     "SELECT id, occurred_at, device_id, payload FROM event ORDER BY id")) {
                select.setFetchSize(fetchSize);
                try (ResultSet resultSet = select.executeQuery()) {
                    while (resultSet.next()) {
                        rowCount++;                                // one row at a time: write it to the response here
                    }
                }
            }
            connection.commit();
        }
        return rowCount;
    }
}
```

Run with a 64 MB heap (`java -Xmx64m ... JdbcFundamentals 1000`), then with fetch size 0:

```text
inserted 100000 rows in batches of 1000 in 317 ms
streamed 1500000 rows with fetchSize=1000 in 1329 ms, heap in use 35 MB

Exception in thread "main" java.lang.OutOfMemoryError: Java heap space        <- fetchSize=0: the whole result in memory
```

What the server saw, from `pg_stat_statements` (item 4.5): with `reWriteBatchedInserts=true`, each batch of 1,000 rows arrived as six statements of 512, 256, 128, 64, 32 and 8 rows (`calls = 100` for each shape); without the flag the same program sent `calls = 100000` single-row inserts and took 523 ms over a local socket, and over a real network the difference is proportional to the latency. Two more measurements from the same session: opening 20 connections through `DriverManager` took 125 ms, borrowing 20 from the pool 4 ms; and `statement.setQueryTimeout(1)` on `SELECT pg_sleep(10)` failed after 1,010 ms with `SQLState 57014, ERROR: canceling statement due to user request`.

## Pitfalls

- Streaming with autocommit on. `setFetchSize` is ignored, the driver buffers the entire result, and the export that worked on test data dies in production with `OutOfMemoryError`.
- Batching without `reWriteBatchedInserts`. The round trips are saved, but the server still executes one statement per row; `pg_stat_statements` shows `calls` equal to the row count.
- No timeouts. A statement waiting on a lock or a server that stopped answering holds the thread and the pooled connection indefinitely; the pool empties and every endpoint fails (item 7.5).
- Leaked connections and result sets. A `ResultSet` or `Connection` not in a try-with-resources header leaks on the exception path; HikariCP's `leakDetectionThreshold` prints the stack trace of the borrower.
- `java.sql.Timestamp` with `setTimestamp` for `timestamptz`. The conversion goes through the JVM's default time zone; bind `OffsetDateTime` or `Instant` with `setObject` instead (item 1.4).
- Catching `SQLException` and continuing in the same transaction. PostgreSQL has aborted it; every further statement fails until `rollback()`.
- Building SQL with string concatenation because "the value comes from our own code". Values travel as parameters, always (item 1.7).
- Holding the connection while calling another service. The transaction and the pooled connection wait for the remote call (item 5.5).

## Check yourself

1. Why does `setFetchSize(1000)` have no effect in autocommit mode with the PostgreSQL driver, and what happens to a query returning ten million rows in that mode?
2. A batch of 100,000 inserts takes 0.3 s against a local database and 40 s against one in another region. Where does the time go, and which two settings change it?
3. Name the three timeouts a well-configured JDBC setup sets and the failure each one prevents.
4. `hibernate.jdbc.batch_size=50` is set, yet the SQL log shows single inserts and the server shows 50 statements per flush. Give one reason for each observation.

## Go deeper

- [Marco Behler: JDBC guide](https://www.marcobehler.com/guides/jdbc) · connections, statements, result sets and pools from first principles.
- [PostgreSQL JDBC Driver: Issuing a Query and Processing the Result](https://jdbc.postgresql.org/documentation/query/) · the cursor-based fetch rules and the batching notes.
- [PostgreSQL JDBC Driver: Connecting to the Database](https://jdbc.postgresql.org/documentation/use/) · every URL parameter, including `reWriteBatchedInserts`, `socketTimeout` and `prepareThreshold`.
- [HikariCP](https://github.com/brettwooldridge/HikariCP) · the pool's settings and defaults, with the sizing wiki linked from the README.
- [Java SE 21: java.sql](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html) · the API itself; `Connection`, `PreparedStatement` and `ResultSet` are short reads.
- [High-Performance Java Persistence](https://vladmihalcea.com/books/high-performance-java-persistence/) · Vlad Mihalcea on JDBC batching, fetching and how Hibernate maps onto them (paid).

---

Part of [Databases](../README.md) · item 10.1
