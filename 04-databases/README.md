# Databases

> Relational databases from the inside out: SQL that scales, storage engines, indexes, query planning, transactions and isolation, MVCC and locking, replication, partitioning, connection pooling, schema design, and when NoSQL fits. PostgreSQL first, with MySQL differences noted.

**Prerequisites:** [Foundations](../01-foundations/README.md)

**Done when you can:**

- Write and read SQL with joins, aggregates, window functions and CTEs, and explain the plan the database chose.
- Design indexes for a given query mix and predict which queries they will and will not help.
- Name the isolation anomalies, say which PostgreSQL isolation level prevents each, and reproduce one in two `psql` sessions.
- Explain MVCC, why readers do not block writers, and why long transactions and table bloat are related.
- Choose between optimistic and pessimistic locking for a concrete use case and implement it correctly.
- Explain replication lag, failover and read-your-writes, and size a connection pool from first principles.

## Roadmap

### 1. The relational model and SQL

- [ ] 1.1 Relations, keys, constraints, and `NULL` with its three-valued logic · [PostgreSQL Tutorial: The SQL Language](https://www.postgresql.org/docs/current/tutorial-sql.html) · [Modern SQL](https://modern-sql.com/)
- [ ] 1.2 Joins (inner, left, full, cross, semi and anti joins with `EXISTS`), grouping, aggregates, `HAVING` · [notes](notes/sql-joins-explained.md) · [SQLBolt](https://sqlbolt.com/) · [PostgreSQL Exercises](https://pgexercises.com/)
- [ ] 1.3 Window functions, common table expressions, recursive queries, `LATERAL` joins · [notes](notes/window-functions-and-ctes.md) · [PostgreSQL: Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html) · [PostgreSQL: WITH Queries](https://www.postgresql.org/docs/current/queries-with.html)
- [ ] 1.4 Data types that matter: `numeric` for money, `text`, `timestamptz` vs `timestamp`, `uuid`, `jsonb`, arrays, enums · [notes](notes/postgresql-data-types-that-matter.md) · [PostgreSQL: Data Types](https://www.postgresql.org/docs/current/datatype.html) · [PostgreSQL wiki: Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This)
- [ ] 1.5 Upserts with `INSERT ... ON CONFLICT`, `MERGE`, `RETURNING`, bulk loading with `COPY` · [notes](notes/upserts-and-merge.md) · [PostgreSQL: INSERT](https://www.postgresql.org/docs/current/sql-insert.html) · [PostgreSQL: MERGE](https://www.postgresql.org/docs/current/sql-merge.html)
- [ ] 1.6 Pagination done right: keyset (seek) pagination instead of `OFFSET` · [notes](notes/keyset-pagination.md) · [Use The Index, Luke: We need tool support for keyset pagination](https://use-the-index-luke.com/no-offset)
- [ ] 1.7 Parameterised queries and why string concatenation is an injection (details in Security) · [OWASP: SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

### 2. Storage engines: how data is stored

- [ ] 2.1 Pages, heap files, tuples and the buffer pool; why all I/O happens in pages · [notes](notes/how-a-database-stores-data.md) · [The Internals of PostgreSQL: Database Cluster, Databases, and Tables](https://www.interdb.jp/pg/pgsql01.html) · [CMU 15-445: Database Systems](https://15445.courses.cs.cmu.edu/)
- [ ] 2.2 Write-ahead logging, checkpoints, `fsync` and crash recovery; what "committed" physically means · [notes](notes/how-a-database-stores-data.md) · [PostgreSQL: Reliability and the Write-Ahead Log](https://www.postgresql.org/docs/current/wal-intro.html) · [The Internals of PostgreSQL: Write Ahead Logging](https://www.interdb.jp/pg/pgsql09.html)
- [ ] 2.3 B-trees vs LSM-trees: read vs write amplification; where each is used (PostgreSQL, InnoDB vs RocksDB, Cassandra) · [notes](notes/b-tree-vs-lsm-tree.md) · [Database Internals](https://www.databass.dev/) · [Designing Data-Intensive Applications, ch. 3](https://dataintensive.net/)
- [ ] 2.4 Heap tables vs clustered (index-organised) tables: PostgreSQL vs InnoDB; TOAST for large values · [MySQL: Clustered and Secondary Indexes](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html) · [PostgreSQL: TOAST](https://www.postgresql.org/docs/current/storage-toast.html)

### 3. Indexing

- [ ] 3.1 B-tree index anatomy: how equality and range lookups walk the tree; index-only scans and the visibility map · [notes](notes/b-tree-indexes-explained.md) · [Use The Index, Luke: Anatomy of an SQL Index](https://use-the-index-luke.com/sql/anatomy)
- [ ] 3.2 Composite indexes and column order: the leftmost-prefix rule and "equality first, then range" · [notes](notes/b-tree-indexes-explained.md) · [Use The Index, Luke: Concatenated Indexes](https://use-the-index-luke.com/sql/where-clause/the-equals-operator/concatenated-keys)
- [ ] 3.3 Covering, partial, expression and unique indexes; selectivity; when an index makes things slower · [notes](notes/b-tree-indexes-explained.md) · [PostgreSQL: Indexes](https://www.postgresql.org/docs/current/indexes.html) · [PostgreSQL: Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)
- [ ] 3.4 Beyond B-trees: hash, GIN (for `jsonb` and full-text), GiST, BRIN; what each is for · [notes](notes/gin-gist-brin-and-other-index-types.md) · [PostgreSQL: Index Types](https://www.postgresql.org/docs/current/indexes-types.html)
- [ ] 3.5 How to make the database ignore your index: functions on columns, implicit casts, leading-wildcard `LIKE`, `OR`, type mismatches · [notes](notes/why-the-database-ignores-your-index.md) · [Use The Index, Luke: Function-Based Indexes](https://use-the-index-luke.com/sql/where-clause/functions)
- [ ] 3.6 Index cost: write amplification, bloat, `REINDEX`, `CREATE INDEX CONCURRENTLY` and its failure modes · [notes](notes/gin-gist-brin-and-other-index-types.md) · [PostgreSQL: Building Indexes Concurrently](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY)

### 4. Query planning and performance

- [ ] 4.1 Reading `EXPLAIN (ANALYZE, BUFFERS)`: sequential, index and bitmap scans; estimated vs actual rows; loops · [notes](notes/reading-explain-plans.md) · [PostgreSQL: Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) · [explain.depesz.com](https://explain.depesz.com/) · [pgMustard: EXPLAIN glossary](https://www.pgmustard.com/docs/explain)
- [ ] 4.2 Join algorithms: nested loop, hash join, merge join; why the planner picks each · [notes](notes/reading-explain-plans.md) · [PostgreSQL: Planner/Optimizer](https://www.postgresql.org/docs/current/planner-optimizer.html) · [CMU 15-445 lectures](https://15445.courses.cs.cmu.edu/)
- [ ] 4.3 Statistics and `ANALYZE`; estimation errors; why a query is fast in development and slow in production · [notes](notes/reading-explain-plans.md) · [PostgreSQL: Statistics Used by the Planner](https://www.postgresql.org/docs/current/planner-stats.html)
- [ ] 4.4 The N+1 problem and ORM-generated SQL; set-based thinking and batching (JPA specifics in Spring) · [notes](notes/set-based-sql-and-the-n-plus-one-problem.md) · [Vlad Mihalcea: N+1 query problem](https://vladmihalcea.com/n-plus-1-query-problem/)
- [ ] 4.5 Finding slow queries: `pg_stat_statements`, `log_min_duration_statement`, `auto_explain` · [notes](notes/finding-slow-queries-with-pg-stat-statements.md) · [PostgreSQL: pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html)
- [ ] 4.6 A tuning method: measure, take the top query by total time, fix the plan, verify, repeat · [notes](notes/finding-slow-queries-with-pg-stat-statements.md) · [Use The Index, Luke](https://use-the-index-luke.com/) · [SQL Performance Explained](https://sql-performance-explained.com/)

### 5. Transactions

- [ ] 5.1 ACID honestly: what each letter guarantees, what it does not, and what depends on configuration · [notes](notes/acid-explained-honestly.md) · [Vlad Mihalcea: A beginner's guide to ACID](https://vladmihalcea.com/a-beginners-guide-to-acid-and-database-transactions/) · [Designing Data-Intensive Applications, ch. 7](https://dataintensive.net/)
- [ ] 5.2 Anomalies: dirty read, non-repeatable read, phantom read, lost update, read skew, write skew · [notes](notes/transaction-isolation-levels-and-anomalies.md) · [Vlad Mihalcea: Lost update](https://vladmihalcea.com/a-beginners-guide-to-database-locking-and-the-lost-update-phenomena/) · [Vlad Mihalcea: Read and write skew](https://vladmihalcea.com/a-beginners-guide-to-read-and-write-skew-phenomena/) · [A Critique of ANSI SQL Isolation Levels](https://arxiv.org/abs/cs/0701157)
- [ ] 5.3 Isolation levels: Read Uncommitted, Read Committed, Repeatable Read (snapshot), Serializable; what PostgreSQL and MySQL actually implement · [notes](notes/transaction-isolation-levels-and-anomalies.md) · [PostgreSQL: Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) · [Hermitage](https://github.com/ept/hermitage) · [Kleppmann: Hermitage, testing the "I" in ACID](https://martin.kleppmann.com/2014/11/25/hermitage-testing-the-i-in-acid.html)
- [ ] 5.4 Serializable in practice: PostgreSQL's SSI, serialization failures, and the retry loop every client needs · [notes](notes/transaction-isolation-levels-and-anomalies.md) · [PostgreSQL: Serializable Isolation Level](https://www.postgresql.org/docs/current/transaction-iso.html#XACT-SERIALIZABLE) · [PostgreSQL wiki: SSI](https://wiki.postgresql.org/wiki/SSI)
- [ ] 5.5 Transaction boundaries in application code: keep them short, no remote calls inside, read-only hints, autocommit traps · [Vlad Mihalcea: Spring transaction best practices](https://vladmihalcea.com/spring-transaction-best-practices/)
- [ ] 5.6 Idempotency and "exactly-once effects" with transactions: idempotency keys, the transactional outbox · [Brandur: Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys)

### 6. Concurrency control: MVCC and locking

- [ ] 6.1 MVCC: tuple versions, snapshots, `xmin`/`xmax`, why readers never block writers · [notes](notes/mvcc-how-it-works.md) · [PostgreSQL: Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) · [Vlad Mihalcea: How does MVCC work](https://vladmihalcea.com/how-does-mvcc-multi-version-concurrency-control-work/) · [The Internals of PostgreSQL: Concurrency Control](https://www.interdb.jp/pg/pgsql05.html)
- [ ] 6.2 Row and table locks: `SELECT ... FOR UPDATE` / `FOR SHARE` / `SKIP LOCKED` / `NOWAIT`; lock modes and the conflict matrix · [notes](notes/row-locks-select-for-update-and-deadlocks.md) · [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [ ] 6.3 Deadlocks in the database: how they arise, how they are detected, and ordering updates to avoid them · [notes](notes/row-locks-select-for-update-and-deadlocks.md) · [PostgreSQL: Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS)
- [ ] 6.4 Optimistic vs pessimistic locking: version columns, compare-and-set updates, retry semantics, choosing per use case · [notes](notes/optimistic-vs-pessimistic-locking.md) · [Baeldung: Optimistic Locking in JPA](https://www.baeldung.com/jpa-optimistic-locking) · [Baeldung: Pessimistic Locking in JPA](https://www.baeldung.com/jpa-pessimistic-locking)
- [ ] 6.5 `VACUUM`, dead tuples, bloat, transaction ID wraparound; why one long-running transaction hurts everyone · [notes](notes/mvcc-how-it-works.md) · [PostgreSQL: Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [ ] 6.6 Advisory locks and queue tables with `SKIP LOCKED` as building blocks for jobs and schedulers · [notes](notes/row-locks-select-for-update-and-deadlocks.md) · [PostgreSQL: Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) · [What is SELECT SKIP LOCKED for?](https://www.2ndquadrant.com/en/blog/what-is-select-skip-locked-for-in-postgresql-9-5/)

### 7. Replication, availability and scaling

- [ ] 7.1 Replication: WAL shipping, streaming replication, synchronous vs asynchronous, logical replication · [notes](notes/replication-lag-and-read-your-writes.md) · [PostgreSQL: High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/current/high-availability.html) · [Designing Data-Intensive Applications, ch. 5](https://dataintensive.net/)
- [ ] 7.2 Replication lag and its anomalies: read-your-writes, monotonic reads; routing reads to replicas safely · [notes](notes/replication-lag-and-read-your-writes.md) · [Jepsen: Consistency Models](https://jepsen.io/consistency)
- [ ] 7.3 Failover, split brain and fencing; what managed services (RDS, Aurora, Azure Database for PostgreSQL) automate · [Patroni](https://patroni.readthedocs.io/)
- [ ] 7.4 Partitioning (range, list, hash) vs sharding; choosing a shard key; cross-shard queries and rebalancing · [notes](notes/partitioning-vs-sharding.md) · [PostgreSQL: Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) · [Citus documentation](https://docs.citusdata.com/en/stable/)
- [ ] 7.5 Connection pooling: why connections are expensive, pool sizing, HikariCP, PgBouncer, pool-exhaustion symptoms · [notes](notes/connection-pooling-and-sizing.md) · [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · [PgBouncer](https://www.pgbouncer.org/)
- [ ] 7.6 Backups and restores: logical vs physical, point-in-time recovery, and actually testing a restore · [PostgreSQL: Backup and Restore](https://www.postgresql.org/docs/current/backup.html)

### 8. Schema design and evolution

- [ ] 8.1 Normalisation (1NF to BCNF) as a tool, and deliberate denormalisation with its maintenance cost · [notes](notes/schema-design-keys-and-constraints.md) · [Database normalization](https://en.wikipedia.org/wiki/Database_normalization)
- [ ] 8.2 Keys: natural vs surrogate; sequences and identity columns vs UUIDs (v4 vs v7) and what they do to your indexes · [notes](notes/schema-design-keys-and-constraints.md) · [Vlad Mihalcea: The best UUID type for a database primary key](https://vladmihalcea.com/uuid-database-primary-key/)
- [ ] 8.3 Constraints as the last line of defence: `NOT NULL`, `CHECK`, foreign keys, `UNIQUE`, exclusion constraints · [notes](notes/schema-design-keys-and-constraints.md) · [PostgreSQL: Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [ ] 8.4 Modelling the hard things: time and time zones, money, soft deletes, audit trails, hierarchies, many-to-many · [notes](notes/postgresql-data-types-that-matter.md) · [PostgreSQL wiki: Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This)
- [ ] 8.5 Migrations: Flyway and Liquibase, versioned vs repeatable, expand-contract for zero-downtime changes, locks taken by DDL · [Flyway documentation](https://documentation.red-gate.com/flyway) · [PostgreSQL at Scale: Database Schema Changes Without Downtime](https://medium.com/paypal-tech/postgresql-at-scale-database-schema-changes-without-downtime-20d3749ed680)
- [ ] 8.6 `jsonb` in a relational schema: when it is right, and when it is a schema you have not designed yet · [PostgreSQL: JSON Types](https://www.postgresql.org/docs/current/datatype-json.html)

### 9. Beyond relational

- [ ] 9.1 The NoSQL landscape: key-value, document, wide-column, graph, search, time-series; what each trades away · [notes](notes/choosing-a-database.md) · [Designing Data-Intensive Applications, ch. 2](https://dataintensive.net/) · [Martin Fowler: NoSQL Distilled](https://martinfowler.com/books/nosql.html)
- [ ] 9.2 Redis as a cache and data-structure server: data types, TTLs, eviction policies, persistence, and the classic mistakes · [notes](notes/redis-as-a-cache.md) · [Redis documentation](https://redis.io/docs/latest/) · [Redis: Data types](https://redis.io/docs/latest/develop/data-types/)
- [ ] 9.3 Document stores (MongoDB): when the document model fits, embedding vs referencing · [MongoDB: Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/)
- [ ] 9.4 Search: inverted indexes and relevance; Elasticsearch/OpenSearch vs PostgreSQL full-text search · [PostgreSQL: Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) · [Elasticsearch](https://www.elastic.co/elasticsearch)
- [ ] 9.5 Choosing a database: a checklist (consistency needs, access patterns, scale, operations maturity, team skills) · [notes](notes/choosing-a-database.md) · [Things I Wished More Developers Knew About Databases](https://rakyll.medium.com/things-i-wished-more-developers-knew-about-databases-2d0178464f78)

### 10. Databases from Java

- [ ] 10.1 JDBC fundamentals: drivers, connections, prepared statements, result sets, batching, fetch size, autocommit · [notes](notes/jdbc-fundamentals.md) · [Marco Behler: JDBC guide](https://www.marcobehler.com/guides/jdbc)
- [ ] 10.2 The ORM trade-off: the impedance mismatch, what JPA/Hibernate buys and costs (deep dive in Spring) · [Marco Behler: Java & Databases](https://www.marcobehler.com/guides/java-databases)
- [ ] 10.3 Testing against a real database with Testcontainers instead of H2 · [Testcontainers: PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/)

## Resources

### Start here

- [CMU 15-445/645: Database Systems](https://15445.courses.cs.cmu.edu/) · Andy Pavlo's course; the lectures are on YouTube. The best explanation of storage, indexes, query execution and concurrency control available anywhere.
- [Use The Index, Luke](https://use-the-index-luke.com/) · Markus Winand's free book on indexing; every backend developer should finish it.
- [PostgreSQL documentation](https://www.postgresql.org/docs/current/) · unusually well written. The chapters on MVCC, indexes and `EXPLAIN` are required reading.
- [Designing Data-Intensive Applications](https://dataintensive.net/) · chapters 2, 3, 5 and 7 cover data models, storage, replication and transactions.
- [Vlad Mihalcea's blog](https://vladmihalcea.com/blog/) · transactions, locking and JPA/Hibernate explained with runnable examples.

### Books

- [Designing Data-Intensive Applications](https://dataintensive.net/) · Martin Kleppmann (paid). A second edition is being published; the first remains excellent.
- [Database Internals](https://www.databass.dev/) · Alex Petrov. Storage engines and distributed databases in depth (paid).
- [PostgreSQL 17 Internals](https://postgrespro.com/community/books/internals) · Egor Rogov. Free PDF; MVCC, vacuum, locks, buffers and WAL explained precisely.
- [SQL Performance Explained](https://sql-performance-explained.com/) · Markus Winand. The printed version of Use The Index, Luke (paid).
- [High-Performance Java Persistence](https://vladmihalcea.com/books/high-performance-java-persistence/) · Vlad Mihalcea. JDBC, JPA and Hibernate performance (paid).
- [The Art of PostgreSQL](https://theartofpostgresql.com/) · Dimitri Fontaine. Using SQL and PostgreSQL features instead of application code (paid).

### Courses and videos

- [CMU Database Group on YouTube](https://www.youtube.com/@CMUDatabaseGroup) · full lecture recordings of 15-445 every year.
- [Hussein Nasser](https://www.youtube.com/@hnasr) · practical videos on indexes, transactions, pooling and database internals.
- [Postgres FM](https://postgres.fm/) · weekly podcast on PostgreSQL operations and performance.

### References

- [The Internals of PostgreSQL](https://www.interdb.jp/pg/) · Hironobu Suzuki's free, detailed walkthrough of the storage, MVCC, WAL and planner internals.
- [PostgreSQL wiki: Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) · the anti-pattern list to read before designing a schema.
- [Jepsen: Consistency Models](https://jepsen.io/consistency) · the map of isolation and consistency levels and how they relate.
- [roadmap.sh: SQL](https://roadmap.sh/sql) and [roadmap.sh: PostgreSQL DBA](https://roadmap.sh/postgresql-dba) · visual overviews.
- [GeeksforGeeks: DBMS](https://www.geeksforgeeks.org/dbms/) · broad coverage of textbook topics; cross-check against the PostgreSQL docs.
- [PostgreSQL Exercises](https://pgexercises.com/) and [SQLBolt](https://sqlbolt.com/) · hands-on SQL practice.
