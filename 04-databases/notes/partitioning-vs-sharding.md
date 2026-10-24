# Partitioning vs sharding

> **In one sentence:** Partitioning splits one table into smaller tables inside a single PostgreSQL server so that queries skip the partitions they do not need and old data is dropped in milliseconds; sharding splits the data across several servers to get more hardware than one machine has, and pays for it with a shard key every query must know, cross-shard joins and transactions that stop being cheap, and rebalancing when a shard runs hot.

**Why it matters:** "Should we partition or shard this table?" arrives as soon as a table approaches hundreds of gigabytes, and the two are routinely confused although they solve different problems: partitioning is a storage layout you can set up in an afternoon and undo; sharding is an architecture decision that changes how every query is written. Interviewers ask about shard keys and hot shards because that choice cannot be fixed later without moving data.

## The idea

**Declarative partitioning.** A partitioned table is a parent with no storage of its own and a set of child tables, each holding the rows whose partition key falls in its range (`RANGE`, usually time), its list of values (`LIST`, regions or tenants) or its hash bucket (`HASH`, to spread rows evenly when nothing natural divides them). Rows are routed on insert; a row that matches no partition is an error unless a `DEFAULT` partition exists. An index created on the parent is created on every partition, including ones added later.

**Pruning.** When the `WHERE` clause constrains the partition key, the planner removes the partitions that cannot match: at plan time for constants, at run time (`Subplans Removed` in the plan) for parameters and for stable functions such as `now()`. Pruning needs the key compared directly; `occurred_at::date = ...` or `date_trunc('day', occurred_at) = ...` disables it, exactly as a function on a column disables an index (item 3.5). A query without the key visits every partition, with an `Append` over one subplan each.

**Dropping old data.** `DROP TABLE event_2026_09`, or `ALTER TABLE event DETACH PARTITION event_2026_09` followed by a drop, removes a month in milliseconds and frees its space at once. `DELETE FROM event WHERE occurred_at < ...` writes a dead tuple per row, logs every one of them to the WAL and leaves the space to `VACUUM` (item 6.5). `DETACH PARTITION ... CONCURRENTLY` (PostgreSQL 14 or later) avoids the `ACCESS EXCLUSIVE` lock on the parent that the plain form takes, but refuses to run while a `DEFAULT` partition exists. `ATTACH PARTITION` scans a pre-filled table to validate its bounds unless the table already carries a matching `CHECK` constraint. `pg_partman` creates future partitions and drops expired ones on a schedule.

**The unique-key constraint.** Each partition has its own indexes and nothing checks across them, so a unique constraint on a partitioned table must include the partition key: `PRIMARY KEY (id)` on a table partitioned by `occurred_at` fails with `unique constraint on partitioned table must include all partitioning columns`. The primary key becomes `(id, occurred_at)`, foreign keys from other tables must reference both columns, and "globally unique id" is guaranteed only by how ids are generated, not by a constraint.

**When it helps, and when not.** Partitioning helps when data has a lifecycle (retention by time), when queries nearly always include the key, when the table and its indexes dwarf memory (the hot partition's indexes are small enough to stay cached), and when maintenance (`VACUUM`, `REINDEX`, `CREATE INDEX`) must happen piecewise. It does not make a point lookup faster (an index does that), each partition is a relation with its own locks, statistics and planning cost (hundreds are fine, tens of thousands are not), and every unique constraint needs the key. A table of a few tens of gigabytes rarely benefits.

**Sharding.** Partitioning stays on one server and inherits its limits: one primary for writes, one machine's memory, CPU and disks. Sharding places the pieces on different servers. Each row lives on exactly one shard, chosen by the **shard key**; a query that knows the key goes to one shard, one that does not is sent to all of them and merged (scatter-gather). A good key has high cardinality, spreads load evenly and appears in nearly every query; in a multi-tenant system that is usually the tenant id, with the tenant's related tables **co-located** on the same shard so their joins stay local. **Hot shards** appear when one tenant or one celebrity exceeds a shard's capacity; the remedies are a compound key (`tenant_id, hash(id)`), isolating the hot tenant on its own shard, or caching. **Cross-shard queries and transactions**: joins across shards move data over the network, aggregates run per shard and are merged, and a transaction touching two shards needs two-phase commit or a saga; the invariants a single database checked for free now span machines. **Rebalancing**: adding a shard means moving data, which is why hash placement into many small logical shards (Citus creates 32 by default) is preferred over one shard per server: a whole logical shard can be moved without rehashing everything; consistent hashing serves the same purpose in application-level designs.

**Citus versus application-level sharding.** Citus is a PostgreSQL extension that makes a cluster of PostgreSQL servers behave as one distributed database: `SELECT create_distributed_table('event', 'device_id')` shards a table, `create_reference_table` replicates a small lookup table to every node, a coordinator routes single-shard queries and parallelises multi-shard ones, cross-shard transactions use two-phase commit transparently, and a rebalancer moves shards online. Joins between tables distributed on different keys are restricted or expensive. Application-level sharding (the service picks a database connection from a directory table or a hash of the key) needs no extension and is simple to reason about, but every cross-shard concern (joins, uniqueness, transactions, rebalancing, running migrations across N databases) becomes code you write and operate. In either case, exhaust vertical scaling, read replicas (item 7.1), connection pooling (item 7.5) and partitioning first; most systems never need to shard.

## Example: a time-partitioned events table

```sql
CREATE TABLE event (
    id          bigint GENERATED ALWAYS AS IDENTITY,
    occurred_at timestamptz NOT NULL,
    device_id   int NOT NULL,
    payload     jsonb NOT NULL,
    PRIMARY KEY (id, occurred_at)                       -- must include the partition key
) PARTITION BY RANGE (occurred_at);
CREATE TABLE event_2026_09 PARTITION OF event FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE event_2026_10 PARTITION OF event FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE event_2026_11 PARTITION OF event FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE event_default PARTITION OF event DEFAULT;
CREATE INDEX event_occurred_idx ON event (occurred_at);
CREATE INDEX event_device_occurred_idx ON event (device_id, occurred_at);
-- 1,000,000 rows spread over September to November
SELECT tableoid::regclass AS partition, count(*) FROM event GROUP BY 1 ORDER BY 1;
--  event_2026_09 | 329662
--  event_2026_10 | 340897
--  event_2026_11 | 329441
```

With `PRIMARY KEY (id)` the `CREATE TABLE` fails: `unique constraint on partitioned table must include all partitioning columns`.

**Pruning at plan time** (PostgreSQL 18, `EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF, SUMMARY OFF)`):

```sql
SELECT count(*) FROM event WHERE occurred_at >= '2026-10-10 00:00+00' AND occurred_at < '2026-10-11 00:00+00';
```
```text
Aggregate (actual rows=1.00 loops=1)
  Buffers: shared hit=1 read=33
  ->  Index Only Scan using event_2026_10_occurred_at_idx on event_2026_10 event (actual rows=11033.00 loops=1)
        Index Cond: ((occurred_at >= '2026-10-10 00:00:00+00'::timestamp with time zone) AND (occurred_at < ...))
```

No `Append` at all: the other partitions were removed before execution and only October's index was opened. **At run time**, `WHERE occurred_at >= now() - interval '1 day' AND occurred_at < now()` keeps an `Append` node and reports `Subplans Removed: 2` above the one remaining `Index Only Scan`, because `now()` is only known when the query runs. **Without the key**, `WHERE device_id = 42` is an `Append` of a `Bitmap Heap Scan` on each of the four partitions through its own `event_2026_xx_device_id_occurred_at_idx`. And `WHERE occurred_at::date = date '2026-10-10'` is an `Append` of four `Seq Scan`s with `Filter: ((occurred_at)::date = '2026-10-10'::date)`: the cast defeated pruning and the index together.

**Dropping a month, detaching one, adding one:**

```sql
ALTER TABLE event DETACH PARTITION event_2026_09 CONCURRENTLY;
-- ERROR:  cannot detach partitions concurrently when a default partition exists
DROP TABLE event_2026_09;                                          -- Time: 12.098 ms; 329,662 rows and their indexes gone
DROP TABLE event_default;
ALTER TABLE event DETACH PARTITION event_2026_11 CONCURRENTLY;     -- Time: 2.395 ms; event_2026_11 is now an ordinary table

CREATE TABLE event_2026_12 (LIKE event INCLUDING INDEXES INCLUDING CONSTRAINTS);
ALTER TABLE event_2026_12 ADD CONSTRAINT event_2026_12_range
    CHECK (occurred_at >= '2026-12-01' AND occurred_at < '2027-01-01');
ALTER TABLE event ATTACH PARTITION event_2026_12 FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');   -- Time: 1.873 ms
INSERT INTO event (occurred_at, device_id, payload) VALUES ('2026-12-24 10:00+00', 1, '{}') RETURNING tableoid::regclass;
--  event_2026_12
```

**List and hash partitions:**

```sql
CREATE TABLE customer_by_region (id bigint, region text NOT NULL, name text NOT NULL, PRIMARY KEY (id, region))
    PARTITION BY LIST (region);
CREATE TABLE customer_eu PARTITION OF customer_by_region FOR VALUES IN ('NO', 'SE', 'DK', 'DE');
CREATE TABLE customer_us PARTITION OF customer_by_region FOR VALUES IN ('US', 'CA');
INSERT INTO customer_by_region VALUES (3, 'BR', 'Carol');
-- ERROR:  no partition of relation "customer_by_region" found for row
-- DETAIL:  Partition key of the failing row contains (region) = (BR).

CREATE TABLE session (id uuid PRIMARY KEY, data jsonb NOT NULL) PARTITION BY HASH (id);
CREATE TABLE session_p0 PARTITION OF session FOR VALUES WITH (MODULUS 4, REMAINDER 0);   -- and p1, p2, p3
-- 10,000 sessions landed as 2528 | 2491 | 2491 | 2490; WHERE id = $1 is pruned to one partition
```

## Pitfalls

- Partitioning by a column the queries do not filter on. Every query becomes an `Append` over every partition, slower than the unpartitioned table. Partition by what you filter and expire on.
- A function or cast on the key. `date_trunc`, `::date`, `extract` and `AT TIME ZONE` on the partition column disable pruning; compare the column to a range.
- Keeping a `DEFAULT` partition "just in case". It silently collects every row with an out-of-range key, blocks `DETACH ... CONCURRENTLY`, and has to be scanned when a new partition is attached.
- `CREATE TABLE ... (LIKE parent INCLUDING ALL)` for a new partition. It copies the identity column and `ATTACH` fails with `table being attached contains an identity column`; copy indexes and constraints only.
- Assuming uniqueness that no constraint enforces. Without the key in every unique constraint, duplicates of a non-key column can exist in different partitions.
- Thousands of partitions. Planning time and lock counts grow with the number of partitions touched; monthly or weekly ranges are the usual sweet spot.
- Sharding by a low-cardinality or skewed key. Country, status or plan tier produce a handful of giant shards; time as a shard key sends every write to the newest shard.
- Sharding before exhausting a single node. A bigger server, replicas for reads, pooling and partitioning carry most systems further, with none of the cross-shard costs.

## Check yourself

1. Why must the primary key of a table partitioned by `occurred_at` include `occurred_at`, and what does that mean for a table that references it with a foreign key?
2. A plan shows `Append` over 36 partitions for a query that filters on `date_trunc('day', occurred_at)`. Why, and what is the fix?
3. A multi-tenant SaaS has 5,000 tenants and one of them generates 40% of the traffic. What shard key would you choose, and what would you do about that tenant?
4. Compare removing 100 million old events with `DELETE` and with dropping a partition, in terms of WAL written, dead tuples, locks and elapsed time.

## Go deeper

- [PostgreSQL: Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html) · declarative partitioning, pruning, the limitations and the best-practice section on partition counts.
- [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) · `ATTACH PARTITION`, `DETACH PARTITION ... CONCURRENTLY` and what each locks.
- [pg_partman](https://github.com/pgpartman/pg_partman) · the extension that automates creating and dropping time-based partitions.
- [Citus documentation](https://docs.citusdata.com/en/stable/) · distributed tables, reference tables, co-location and the shard rebalancer.
- [Designing Data-Intensive Applications, chapter 6](https://dataintensive.net/) · partitioning by key range and by hash, hot spots, rebalancing and request routing, independent of any product.

---

Part of [Databases](../README.md) · item 7.4
