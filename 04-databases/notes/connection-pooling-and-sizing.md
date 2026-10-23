# Connection pooling and sizing

> **In one sentence:** Every PostgreSQL connection is an operating-system process with its own memory, so applications keep a small, fixed pool of long-lived connections and queue requests for them; a pool sized to the database server's cores rather than to the application's threads is almost always faster, and pool exhaustion is nearly always a symptom of transactions that hold a connection while doing something else.

**Why it matters:** "Connection is not available, request timed out" is one of the most common production incidents in Spring applications, and the reflex response, raising the pool size, usually makes it worse. Sizing a pool from first principles and reading the exhaustion symptoms correctly are expected of any backend developer, and they come up in interviews because the intuitive answer is wrong.

## The idea

**Why connections are expensive.** PostgreSQL forks a backend process for each connection. On the server, `ps` shows them individually, each with its own memory:

```text
  PID    RSS COMMAND
94952   9824 postgres: armaan roadmap_notes_scratch [local] SELECT
94953   9888 postgres: armaan roadmap_notes_scratch [local] SELECT
```

Opening one means a TCP handshake, usually TLS, authentication, the fork, and then a cold catalog cache that warms up over the first queries. `max_connections` (default 100, a few of them reserved for superusers) is a hard limit; beyond it the server answers `FATAL: sorry, too many clients already`. A thousand idle connections also cost memory and bookkeeping on every snapshot the server takes.

**Why fewer connections are faster.** A server with C cores and one storage device can make progress on roughly C queries at once. More active connections than that do not add throughput; they add context switches, contention on shared memory structures and `work_mem` multiplied by the number of concurrent sorts. The sizing rule in HikariCP's wiki, taken from the PostgreSQL wiki, is:

```text
connections = (core_count × 2) + effective_spindle_count
```

For an 8-core database server on SSDs that is about 16 to 20 connections, in total, shared by every instance of every application that talks to it. Requests beyond that wait a few milliseconds in the pool's in-process queue instead of competing inside the database, and the whole system finishes sooner. Divide the total by the number of application instances to get each pool's size, and leave headroom for migrations, monitoring and administrators.

**HikariCP settings that matter.** `maximumPoolSize` (default 10) and `minimumIdle` (defaults to the maximum; keep them equal for a fixed-size pool that never pays connection setup under load). `connectionTimeout` (default 30 s) is how long a thread waits for a connection before failing; lower it so that an exhausted pool fails fast instead of piling up threads. `maxLifetime` (default 30 minutes) retires connections; it must be shorter than any idle timeout imposed by the server, a proxy or a cloud network path. `leakDetectionThreshold` logs the stack trace of any connection held longer than the given milliseconds, which is how leaks are found. In Spring Boot these are `spring.datasource.hikari.*` properties:

```properties
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=10
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.max-lifetime=1200000
spring.datasource.hikari.leak-detection-threshold=10000
```

**Pool exhaustion.** The symptom in the application is `SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms`, with request latency climbing to the timeout for every endpoint that touches the database, including the healthy ones. The causes, in order of likelihood:

1. Transactions that hold a connection while waiting on something else: an HTTP call to another service, a message broker, a lock, a slow external API, or user think time. Ten such requests and a pool of ten is empty.
2. Leaks: a connection obtained outside try-with-resources and never closed, or an `EntityManager` kept open for the life of a thread. The pool shrinks permanently until restart.
3. Too many instances: twenty pods with a pool of twenty each is 400 connections against `max_connections = 100`; the symptom then appears on the server as "too many clients" and in the pool as failures to open connections.
4. One slow query multiplied by concurrency. Fifty requests per second running a 500 ms query need 25 connections just for that query.

The diagnostic query on the server:

```sql
SELECT state, count(*), max(now() - xact_start) AS longest_transaction
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state;
```

Many `idle in transaction` rows with a long `longest_transaction` is cause 1. Setting `idle_in_transaction_session_timeout` on the server turns a leak or a forgotten transaction into an error you will see, instead of a connection you will not get back.

**PgBouncer.** A lightweight proxy that accepts thousands of client connections and multiplexes them over a few dozen server connections. Its `pool_mode` decides what a client holds: `session` (a server connection for the client's whole session, which saves only connection setup), `transaction` (a server connection for the duration of each transaction, the mode that makes a thousand application connections fit in fifty server ones) and `statement` (per statement, no multi-statement transactions). Transaction mode breaks anything that assumes session state survives between transactions: `SET` without `LOCAL`, temporary tables, `LISTEN`/`NOTIFY`, session-level advisory locks and holdable cursors. Server-side prepared statements, which JDBC drivers use heavily, are supported in transaction mode since PgBouncer 1.21 with `max_prepared_statements`. PgBouncer helps when many application instances or serverless functions would otherwise exceed `max_connections`; it does not change the sizing rule for the server side.

## Example: watching a pool run dry

A service with `maximumPoolSize = 10` calls a payment provider inside its `@Transactional` method. The provider slows to 5 s. Within a second, ten requests hold all ten connections while waiting on HTTP; the eleventh request, a read-only product listing, blocks in `HikariPool.getConnection` for `connectionTimeout` and fails. On the server, `pg_stat_activity` shows ten `idle in transaction` sessions each with a `longest_transaction` approaching 5 s and no active query at all: the database is idle while the application reports a database outage. Raising the pool to 50 lets fifty requests wait on the provider instead of ten and moves the failure to `max_connections`. The fix is to call the provider outside the transaction, or to make the transaction wait for nothing but the database (item 5.5).

## Pitfalls

- Raising `maximumPoolSize` when the pool is exhausted. It hides the long transaction for a while and makes the database slower for everyone; find the holder with `pg_stat_activity` or `leakDetectionThreshold` instead.
- Sizing per instance and forgetting the total. Autoscaling multiplies pools; the server's limit does not scale with it.
- `maxLifetime` longer than the network's idle timeout. Cloud load balancers and NAT gateways drop idle TCP connections silently; the pool then hands out dead connections and the first use fails with a connection reset.
- Leaving `connectionTimeout` at 30 s. Thirty seconds of blocked request threads is how a slow database becomes a dead application.
- Session state behind PgBouncer in transaction mode. `SET search_path`, `pg_advisory_lock` and temporary tables leak across clients; use `SET LOCAL`, the `_xact_` advisory functions and ordinary tables.
- Judging pool size by the number of application threads. Two hundred Tomcat threads do not need two hundred connections; they need the few the database can actually serve, and a queue.

## Check yourself

1. A 4-core database server on SSDs serves eight application instances. Roughly how large should each instance's pool be, and what would you measure to confirm the number?
2. Requests fail with "Connection is not available" while `pg_stat_activity` shows the database almost idle. What is the most likely cause, and which column of `pg_stat_activity` confirms it?
3. Why must `maxLifetime` be shorter than every idle timeout between the application and the server, and what symptom appears if it is not?
4. Which three features of a PostgreSQL session stop working behind PgBouncer in transaction mode, and what replaces each?

## Go deeper

- [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · the formula, the reasoning and a benchmark showing a smaller pool outperforming a larger one.
- [HikariCP](https://github.com/brettwooldridge/HikariCP) · the README documents every setting and its default.
- [PgBouncer](https://www.pgbouncer.org/) · the [features page](https://www.pgbouncer.org/features.html) lists exactly what each pooling mode supports.
- [PostgreSQL: Connections and Authentication](https://www.postgresql.org/docs/current/runtime-config-connection.html) · `max_connections`, reserved connections and the related timeouts.
- [Marco Behler: JDBC guide](https://www.marcobehler.com/guides/jdbc) · where a pool fits in the JDBC picture, and how connections are obtained and released.

---

Part of [Databases](../README.md) · item 7.5
