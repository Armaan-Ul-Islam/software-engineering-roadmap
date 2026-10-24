# Finding slow queries with pg_stat_statements

> **In one sentence:** `pg_stat_statements` keeps one row per normalised statement with how often it ran, how long it took in total and on average, and how many rows and pages it touched, so sorting it by total time shows which statement actually costs the server its time; `log_min_duration_statement` and `auto_explain` then capture individual slow executions with their plans, and the tuning loop is measure, fix the top entry, verify, repeat.

**Why it matters:** The query a developer thinks is slow is rarely the one the database spends its time on. A 30 ms query called 400 times a minute costs more than a 2 s report run once an hour, and only aggregated statistics show that. Being able to say "this statement is 80% of the load, here is its plan, here is the index, here is the before and after" is most of practical database tuning, and it is what a senior engineer is expected to do in the first hour of a performance incident.

## The idea

**Enabling it.** `pg_stat_statements` is a contrib module that must be preloaded: `shared_preload_libraries = 'pg_stat_statements'` in `postgresql.conf` (a restart), then `CREATE EXTENSION pg_stat_statements` in the database you query it from. It tracks every database on the server, so filter by `dbid`. Settings that matter: `pg_stat_statements.max` (5,000 distinct statements by default; when the table is full the least-used entries are evicted, and `pg_stat_statements_info.dealloc` counts how often), `pg_stat_statements.track` (`top` for top-level statements only, `all` to include statements inside functions) and `track_io_timing = on`, which adds the time spent waiting for I/O. Managed services usually ship the extension preloaded.

**Normalisation.** Constants are replaced by `$1`, `$2`, so `WHERE id = 42` and `WHERE id = 43` are one row with `calls = 2`. Statements that differ in text stay separate: `IN (?, ?)` and `IN (?, ?, ?)`, or SQL with values concatenated into it, produce one row per variant and flood the table (item 4.4 explains why `= ANY($1)` fixes this). Since PostgreSQL 14 the `queryid` is computed by the server itself (`compute_query_id`), and the same id appears in `pg_stat_activity.query_id` and in `EXPLAIN (VERBOSE)`, which links a live session to its statistics.

**The columns that matter.**

| Column | The question it answers |
|---|---|
| `calls` | How often? A huge count with a tiny mean is an N+1 or a missing cache. |
| `total_exec_time`, `mean_exec_time` | Where does the server's time go? Sort by total; the mean tells you whether the fix is "run it less" or "make it faster". |
| `rows` | Rows returned or affected in total; `rows / calls` in the millions for a listing is a missing `LIMIT`. |
| `shared_blks_hit`, `shared_blks_read` | Pages served from the buffer pool and from the operating system; their sum per call is the I/O footprint, which is more stable than time. |
| `shared_blks_dirtied`, `wal_bytes` | Write cost; large values on a `SELECT` are hint bits being set after a bulk load, large `wal_bytes` on an `UPDATE` means wide rows or many indexes. |
| `temp_blks_written` | Sorts and hashes that spilled to disk: `work_mem` is too small for this statement. |
| `stddev_exec_time`, `max_exec_time` | A fast mean with a huge maximum is lock waits, or a plan that flips (item 3.5). |
| `stats_since` | When the counters started; `pg_stat_statements_reset()` restarts them. |

**The top-by-total-time query:**

```sql
SELECT calls,
       round(total_exec_time::numeric, 0) AS total_ms,
       round(mean_exec_time::numeric, 2)  AS mean_ms,
       round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 1) AS pct,
       rows,
       shared_blks_hit + shared_blks_read AS blocks,
       temp_blks_written AS temp,
       left(regexp_replace(query, '\s+', ' ', 'g'), 70) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 10;
```

`ORDER BY calls DESC` finds the N+1 shape, `ORDER BY shared_blks_read DESC` what is churning the cache, `ORDER BY temp_blks_written DESC` the spilling sorts.

**Individual executions: `log_min_duration_statement` and `auto_explain`.** The statistics say *which statement*; the log says *which execution*, with its parameters. `log_min_duration_statement = '500ms'` (settable globally, per role with `ALTER ROLE ... SET`, or per session) writes every statement that takes longer, with its duration. `auto_explain`, also preloaded through `shared_preload_libraries`, logs the *plan* of such a statement; with `auto_explain.log_analyze = on` and `auto_explain.log_buffers = on` the logged plan carries actual row and page counts, which you need and cannot reproduce the next morning because the data and the cache have changed. `log_analyze` adds timing overhead to every statement whether or not it is logged, so on busy servers set `auto_explain.sample_rate` below 1, use `auto_explain.log_timing = off`, or enable it per session.

**Sequential scans on big tables.** `pg_stat_user_tables` counts `seq_scan` and `seq_tup_read` (table scans and the rows they read), `idx_scan`, and `n_live_tup`. A large table whose `seq_scan` keeps growing while `seq_tup_read / seq_scan` is close to `n_live_tup` is being read in full, repeatedly: a missing index, or a query written so that the index cannot be used (item 3.5). Small tables are scanned sequentially on purpose; ignore them.

**A repeatable method.**

1. Make sure the window is representative: compare `stats_since` with the time of the batch jobs, or `pg_stat_statements_reset()` and wait a full cycle.
2. Take the top entry by `total_exec_time`. From `calls`, `mean_ms` and `blocks` per call, decide whether it is one slow statement or a frequent cheap one.
3. Get the plan of a real execution: `auto_explain` output from the log, or `EXPLAIN (ANALYZE, BUFFERS)` with representative parameters (item 4.1).
4. Fix the plan: an index (items 3.1 to 3.4), a rewrite that lets the index be used (item 3.5), a set-based rewrite (item 4.4), `ANALYZE` (item 4.3), or running the statement less often (item 9.2).
5. Verify in the same view: the entry's `mean_ms` and `blocks` per call must drop and its share of total time must move elsewhere. If the row improved but the server did not, you fixed the wrong thing.
6. Repeat with the new top entry, and stop when the top entries are work the application genuinely has to do.

## Example: one workload, measured, fixed, verified

About 3,500 statements against the `event` and `product` tables of item 3.4 (PostgreSQL 18, `track_io_timing = on`). The view afterwards:

```text
 calls | total_ms | mean_ms | pct  | rows | blocks  | temp |                               query
-------+----------+---------+------+------+---------+------+-------------------------------------------------------------------
   400 |    13386 |   33.46 | 80.0 |  400 | 5607600 |    0 | SELECT count(*) FROM event WHERE device_id = $1
   150 |     2786 |   18.57 | 16.7 |  150 |  960750 |    0 | SELECT count(*) FROM product WHERE attributes ->> $1 = $2
     5 |      233 |   46.53 |  1.4 |    5 |   70400 |    0 | SELECT count(*) FROM event_shuffled WHERE occurred_at >= $1 AND occurr
     1 |      222 |  222.32 |  1.3 |    1 |   18126 |    0 | SELECT count(*) FROM (SELECT DISTINCT device_id, occurred_at FROM even
  3000 |       92 |    0.03 |  0.5 | 3000 |   12003 |    0 | SELECT id, attributes FROM product WHERE id = $1
```

The slowest single statement (222 ms) is 1.3% of the load, and the 3,000 primary-key lookups together are 0.5%. What matters is a 33 ms count run 400 times: 80% of all execution time and 5.6 million page reads, about 14,000 pages per call. `pg_stat_user_tables` tells the same story from the table's side:

```text
    relname     | seq_scan | seq_tup_read | idx_scan | n_live_tup | total_size | rows_per_seq_scan
----------------+----------+--------------+----------+------------+------------+-------------------
 event          |      401 |    601500000 |        1 |    1500000 | 142 MB     |           1500000
```

Four hundred full scans of a table of 1.5 million rows. A session with `SET log_min_duration_statement = '10ms'`, `SET auto_explain.log_min_duration = '10ms'`, `log_analyze = on` and `log_buffers = on` puts the plan of one real execution in the server log:

```text
LOG:  duration: 86.392 ms  plan:
	Query Text: SELECT count(*) FROM event WHERE device_id = 42;
	Aggregate  (cost=32772.72..32772.73 rows=1 width=8) (actual time=86.374..86.374 rows=1.00 loops=1)
	  Buffers: shared hit=12515 read=1504
	  ->  Seq Scan on event  (cost=0.00..32769.00 rows=1489 width=0) (actual time=0.062..86.238 rows=1561.00 loops=1)
	        Filter: (device_id = 42)
	        Rows Removed by Filter: 1498439
	        Buffers: shared hit=12515 read=1504
LOG:  duration: 88.250 ms  statement: SELECT count(*) FROM event WHERE device_id = 42;
```

1,561 rows wanted, 1,498,439 read and discarded: a missing index. The fix, built without blocking writers (item 3.6), then `pg_stat_statements_reset()` and the same 400 calls:

```sql
CREATE INDEX CONCURRENTLY event_device_id_idx ON event (device_id);
```
```text
 calls | total_ms | mean_ms | rows | blocks |                      query
-------+----------+---------+------+--------+-------------------------------------------------
   400 |       78 |    0.19 |  400 |   2063 | SELECT count(*) FROM event WHERE device_id = $1
```

33.46 ms to 0.19 ms per call, about 14,000 pages to 5; the plan is now an `Index Only Scan using event_device_id_idx` with `Buffers: shared hit=5`. The new top entry is the `attributes ->> 'color'` count, which wants an expression index (item 3.5), and the loop continues.

## Pitfalls

- Sorting by `mean_exec_time`. It finds the rare heavy report and hides the frequent cheap statement that is most of the load. Sort by total, then read `calls` and the mean to decide the kind of fix.
- Judging from a short or unrepresentative window. The counters describe the time since `stats_since`; a view reset ten minutes ago knows nothing about the nightly batch.
- `log_min_duration_statement = 0` in production. Every statement is logged and the log can saturate the disk the database runs on. Use a threshold, `log_min_duration_sample` with `log_statement_sample_rate`, or per-role settings.
- `auto_explain.log_analyze` on everything. The timing overhead applies to every statement, logged or not; use `sample_rate`, `log_timing = off`, or a session.
- Statements that cannot be normalised. Values concatenated into SQL and `IN` lists of varying length give one row per variant, exhaust `pg_stat_statements.max` (`dealloc` grows) and hide the aggregate cost. Bind parameters and use arrays (items 1.7 and 4.4).
- Fixing without verifying. An index the planner ignores (item 3.5) leaves the row unchanged; `blocks` per call before and after is the proof that the fix landed.
- Forgetting the application's side. A statement with 3,000 calls and a 0.03 ms mean costs the database nothing and the application 3,000 round trips; the fix is in the code, and only `calls` reveals it.

## Check yourself

1. One statement runs once an hour and takes 4 s; another runs 50 times a second and takes 5 ms. Which one does the server spend more time on, and which column shows it?
2. The top entry has a `mean_exec_time` of 0.2 ms and `calls` in the millions. What shape of problem is that, and where is the fix?
3. Why do you want `auto_explain` with `log_analyze` and `log_buffers` in the log, rather than running `EXPLAIN ANALYZE` yourself the next morning?
4. A table of 50 million rows shows `seq_scan` climbing by 200 an hour. Name the two most likely causes and what in the plan tells them apart.

## Go deeper

- [PostgreSQL: pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) · every column, the normalisation rules and the configuration parameters.
- [PostgreSQL: auto_explain](https://www.postgresql.org/docs/current/auto-explain.html) · all `auto_explain.*` settings, including `sample_rate` and `log_nested_statements`.
- [PostgreSQL: Error Reporting and Logging](https://www.postgresql.org/docs/current/runtime-config-logging.html) · `log_min_duration_statement`, `log_min_duration_sample` and the sampling parameters.
- [PostgreSQL: The Cumulative Statistics System](https://www.postgresql.org/docs/current/monitoring-stats.html) · `pg_stat_user_tables`, `pg_stat_user_indexes` and the other views.
- [Use The Index, Luke](https://use-the-index-luke.com/) and [SQL Performance Explained](https://sql-performance-explained.com/) · what to do with the statement once you have found it.

---

Part of [Databases](../README.md) · items 4.5, 4.6
