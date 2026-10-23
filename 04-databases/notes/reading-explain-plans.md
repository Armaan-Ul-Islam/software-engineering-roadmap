# Reading EXPLAIN plans

> **In one sentence:** An `EXPLAIN (ANALYZE, BUFFERS)` plan is a tree of operations executed from the leaves up, and reading it means checking three things at each node: which access or join method was chosen, how far the estimated row count is from the actual one, and how many pages the node touched.

**Why it matters:** The plan is the only honest account of what the database did with your query; everything else is guesswork. The habit that separates people who fix slow queries from people who add indexes at random is to find the node where estimated and actual rows diverge, because that is where the planner was misled.

## The idea

**Shape.** Each line is a node; indentation shows which nodes feed which. Inner nodes run first and parents pull rows from their children. For every node:

```text
Hash Join  (cost=1246.71..22270.95 rows=85940 width=9) (actual time=4.355..100.876 rows=84390.00 loops=1)
```

1. `cost=startup..total`: the planner's estimate in abstract units (a sequential page read is 1.0), used only to compare alternatives.
2. `rows`: how many rows the planner expected this node to emit *per loop*; `width`: estimated bytes per row.
3. `actual time=first..last` in milliseconds and `actual rows`, also per loop; multiply by `loops` for totals.
4. `Buffers: shared hit=... read=... dirtied=...`: pages found in the buffer pool, fetched from the operating system, or modified; a parent's figures include its children's.

**Scan nodes.** `Seq Scan` reads every page and applies a `Filter`; `Rows Removed by Filter` shows the waste. `Index Scan` walks the index and fetches each row's heap page as it goes, good for few rows or when the index order matches `ORDER BY`. `Index Only Scan` answers from the index alone, with `Heap Fetches` counting rows whose pages were not marked all-visible. `Bitmap Index Scan` plus `Bitmap Heap Scan` collect matching row addresses first and visit heap pages in physical order, the planner's choice for medium selectivity; `Heap Blocks: exact=` says how many pages that was.

**Join nodes.** PostgreSQL has three algorithms and chooses by the estimated sizes of the two inputs:

| Algorithm | How it works | When the planner picks it | What to look for |
|---|---|---|---|
| Nested Loop | For each outer row, find the matching inner rows, ideally through an index | A small outer input and an index on the inner join column | Inner `loops=` equals the outer row count; cheap until the outer estimate is wrong |
| Hash Join | Build a hash table from the smaller input, probe it with the larger | Equality joins with a large input; no ordering needed | `Batches: 1` fitted in `work_mem`; `Batches: 8` spilled to temporary files |
| Merge Join | Sort both inputs on the join key (or read them in index order) and merge | Both inputs large and already sorted, or the output order is needed anyway | `Sort` nodes feeding it, or index scans in key order |

**Estimates and statistics.** The planner never looks at the data at plan time. It uses statistics gathered by `ANALYZE` (run by autovacuum when enough rows change): row and page counts, the most common values with their frequencies, a histogram of the rest, the number of distinct values and the physical correlation of each column, all visible in `pg_stats`. From those it estimates how many rows each condition passes, and from the estimates it picks scan and join methods. When the statistics are stale, or conditions are correlated in ways they cannot describe, the estimate is wrong, the method is wrong, and the query is slow although every step works as designed.

## Example: one plan, line by line

Order count and revenue for Norwegian customers, on a million orders and 50,000 customers (PostgreSQL 18; `SET max_parallel_workers_per_gather = 0` keeps the tree small).

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.country, count(*) AS order_count, sum(o.total) AS revenue
FROM customer c JOIN orders o ON o.customer_id = c.id
WHERE c.country = 'NO'
GROUP BY c.country;
```

```text
GroupAggregate  (cost=1246.71..22700.66 rows=1 width=43) (actual time=105.344..105.347 rows=1.00 loops=1)
  Buffers: shared hit=1579 read=7388
  ->  Hash Join  (cost=1246.71..22270.95 rows=85940 width=9) (actual time=4.355..100.876 rows=84390.00 loops=1)
        Hash Cond: (o.customer_id = c.id)
        Buffers: shared hit=1579 read=7388
        ->  Seq Scan on orders o  (cost=0.00..18399.01 rows=1000001 width=14) (actual time=0.040..39.187 rows=1000001.00 loops=1)
              Buffers: shared hit=1011 read=7388
        ->  Hash  (cost=1193.00..1193.00 rows=4297 width=11) (actual time=4.300..4.303 rows=4228.00 loops=1)
              Buckets: 8192  Batches: 1  Memory Usage: 263kB
              Buffers: shared hit=568
              ->  Seq Scan on customer c  (cost=0.00..1193.00 rows=4297 width=11) (actual time=0.008..3.889 rows=4228.00 loops=1)
                    Filter: (country = 'NO'::text)
                    Rows Removed by Filter: 45772
                    Buffers: shared hit=568
Planning Time: 1.234 ms
Execution Time: 105.407 ms
```

From the inside out:

1. `Seq Scan on customer c`: all 568 pages read, 45,772 rows discarded by the filter, 4,228 kept; estimated 4,297, because the statistics know roughly one customer in twelve is Norwegian.
2. `Hash`: the 4,228 rows became a 263 kB hash table in one batch. This is the build side; the planner builds from the input it believes is smaller.
3. `Seq Scan on orders o`: every order, 8,399 pages, mostly `read` because the table is larger than the buffer ring keeps. With no condition on orders, one sequential pass is the cheapest way to see them all.
4. `Hash Join`: each order probed the hash table; 84,390 matched against an estimate of 85,940.
5. `GroupAggregate`: one group, one row. 105 ms in total, 39 ms of it reading orders and most of the rest probing.

Would an index on `orders (customer_id)` help? No. 8.4% of all orders match, far too many for 84,390 index lookups to beat one sequential pass. The plan is right; if it is too slow, the question is whether the aggregate can be maintained incrementally, not which index is missing.

## Example: a wrong estimate chooses the wrong plan

A table `event` was analysed when it held one row, then loaded with a million rows without `ANALYZE`:

```text
Hash Join  (cost=6513.32..7832.52 rows=6370 width=3) (actual time=150.455..324.080 rows=1000001.00 loops=1)
  Hash Cond: (c.id = e.customer_id)
  ->  Seq Scan on customer c  (cost=0.00..1068.00 rows=50000 width=11) (actual ... rows=50000.00 loops=1)
  ->  Hash  (cost=6433.70..6433.70 rows=6370 width=8) (actual time=149.934..149.934 rows=1000001.00 loops=1)
        Buckets: 262144 (originally 8192)  Batches: 8 (originally 1)  Memory Usage: 6907kB
        Buffers: shared hit=6370, temp written=2989
        ->  Seq Scan on event e  (cost=0.00..6433.70 rows=6370 width=8) (actual time=0.009..61.112 rows=1000001.00 loops=1)
```

The planner expected 6,370 events (it scales the stale row count by the file's current size, so it was off by a factor of 157 rather than a million) and built the hash table from the "small" side, which was the large one: the table was resized at run time, spilled into 8 batches of temporary files, and the query took 415 ms. After `ANALYZE event` the node reads `rows=1000001`, the hash is built from the 50,000 customers in one batch, and the same query takes 280 ms. The gap between `rows=6370` and `rows=1000001.00` was the whole story.

## Pitfalls

- Reading `rows` as a total when `loops` is greater than one. An inner index scan showing `rows=19.85 loops=27` returned 536 rows.
- Running `EXPLAIN` without `ANALYZE` and trusting the costs. Costs are estimates; only `ANALYZE` shows actual rows and times. `EXPLAIN ANALYZE` executes the statement, so wrap `INSERT`, `UPDATE` and `DELETE` in a transaction and roll back.
- Looking at the top node only. The expensive step is often deep in the tree; subtract children's times from parents', or paste the plan into explain.depesz.com, which does that for you.
- Misreading parallel plans. Under a `Gather` node with `Workers Planned: 2`, the children's actual rows and times are per worker; read the totals at `Gather`.

## Check yourself

1. In the first plan, how would the tree change if the condition became `WHERE c.email = 'customer42@example.com'`, and why?
2. A node shows `rows=1` estimated and `rows=48000` actual, and its parent is a Nested Loop. What is the likely consequence, and what is the first command you run?
3. Why does the planner build the hash table from the smaller input, and what in the plan tells you it guessed the sides wrong?
4. Give one reason a Merge Join might be chosen over a Hash Join even when both inputs fit in memory.

## Go deeper

- [PostgreSQL: Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) · the official walk-through, with the exact meaning of every field.
- [PostgreSQL: Statistics Used by the Planner](https://www.postgresql.org/docs/current/planner-stats.html) · what `ANALYZE` collects and how to read `pg_stats`.
- [PostgreSQL: Planner/Optimizer](https://www.postgresql.org/docs/current/planner-optimizer.html) · how plans are generated and the three join strategies.
- [pgMustard: EXPLAIN glossary](https://www.pgmustard.com/docs/explain) · a reference for every node type and plan field.
- [explain.depesz.com](https://explain.depesz.com/) · paste a plan and get the per-node exclusive times highlighted.
- [CMU 15-445 lectures](https://15445.courses.cs.cmu.edu/) · the join algorithm and query optimisation lectures explain why the planner behaves as it does.

---

Part of [Databases](../README.md) · items 4.1, 4.2, 4.3
