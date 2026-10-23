# Set-based SQL and the N+1 problem

> **In one sentence:** The N+1 problem is a loop in the application that runs one query to fetch N parent rows and then N more queries to fetch each one's children; the fix is always to let the database do the loop in a single statement, with a join, an array parameter or a window function.

**Why it matters:** It is the most common performance bug in applications that use an ORM, it is invisible in development (N is 3) and expensive in production (N is 3,000), and it reaches the database as thousands of fast queries rather than one slow one, so slow-query logging never catches it. The database-level shape and the fixes are the same whatever framework produced it; JPA's own settings are covered in the Spring domain.

## The idea

The shape, as the server sees it:

```sql
SELECT id, name FROM customer WHERE country = 'NO' AND created_at >= $1;   -- 1 query, 27 rows
SELECT id, total FROM orders WHERE customer_id = $1;                        -- 27 queries, $1 = each id
```

Each child query is fast, but each one is a network round trip, a parse, a plan and an execution, and the connection is held for the whole loop. The cost is proportional to N, dominated by latency rather than by database work, and no single query ever looks slow.

**Spotting it.** With `log_min_duration_statement = 0` the server log shows the pattern directly. This excerpt is from a client using the extended protocol, the way JDBC does; three executions of the same statement within the same millisecond, with consecutive parameters:

```text
LOG:  duration: 0.050 ms  execute <unnamed>: SELECT id, total FROM orders WHERE customer_id = $1
DETAIL:  Parameters: $1 = '42'
LOG:  duration: 0.052 ms  execute <unnamed>: SELECT id, total FROM orders WHERE customer_id = $1
DETAIL:  Parameters: $1 = '43'
LOG:  duration: 0.018 ms  execute <unnamed>: SELECT id, total FROM orders WHERE customer_id = $1
DETAIL:  Parameters: $1 = '44'
```

In production you cannot log every statement, so use `pg_stat_statements`, which aggregates by normalised query text. The N+1 signature is a very high `calls` count with a tiny mean time and few rows per call:

```sql
SELECT calls, round(mean_exec_time::numeric, 3) AS mean_ms, rows / calls AS rows_per_call, query
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 10;
```

**Thinking in sets.** Tell the database which set of rows you want, not how to iterate over it. Four rewrites cover almost every case:

1. **Join.** One statement; the planner does the loop internally and chooses how.
2. **Array parameter.** `WHERE customer_id = ANY($1)` with a single `bigint[]` parameter (`connection.createArrayOf("bigint", ids)` in JDBC). Unlike `IN (?, ?, ?)`, the statement text is the same for any number of ids, so the plan cache and `pg_stat_statements` see one statement rather than one per list length. Batch very large sets in chunks of a few hundred to a few thousand ids.
3. **Window functions** for "the k most recent children of each parent", instead of a `LIMIT k` query per parent.
4. **`GROUP BY`** for "a count or sum per parent", instead of an aggregate query per parent.

The same applies to writes: a loop of single-row `INSERT`s becomes one multi-row `INSERT ... VALUES (...), (...)` or a `COPY`, and a loop of `UPDATE`s becomes one `UPDATE ... FROM (VALUES ...) AS changes (id, value) WHERE ...`.

## Example: the N+1 and its single-query rewrites

A `customer` table (50,000 rows) and an `orders` table (1,000,000 rows) with an index starting with `customer_id`. PostgreSQL 18, planning lines removed.

**The join.** Twenty-seven customers and their 536 orders in one round trip. The `Nested Loop` with `Index Searches: 27` is the application's loop, moved inside the database where it costs no latency:

```sql
SELECT c.id, c.name, o.id, o.total
FROM customer c JOIN orders o ON o.customer_id = c.id
WHERE c.country = 'NO' AND c.created_at >= now() - interval '7 days';
```
```text
Nested Loop (actual rows=536.00 loops=1)
  ->  Seq Scan on customer c (actual rows=27.00 loops=1)
        Filter: ((country = 'NO'::text) AND (created_at >= (now() - '7 days'::interval)))
  ->  Index Scan using orders_customer_status_created_idx on orders o (actual rows=19.85 loops=27)
        Index Cond: (customer_id = c.id)
        Index Searches: 27
```

**The array parameter**, when the ids are already in memory (the second query of a two-step load):

```sql
SELECT customer_id, id, total, created_at
FROM orders
WHERE customer_id = ANY ($1)          -- $1 = '{42,43,44,...}'::bigint[]
ORDER BY customer_id;
```
```text
Bitmap Heap Scan on orders (actual rows=391.00 loops=1)
  Recheck Cond: (customer_id = ANY ('{42,43,...,61}'::integer[]))
  ->  Bitmap Index Scan on orders_customer_status_created_idx (actual rows=432.00 loops=1)
```

Twenty customers' orders in one statement and 383 page accesses, instead of twenty statements.

**The window function**, for the three most recent orders of each customer:

```sql
SELECT customer_id, id, created_at
FROM (
    SELECT o.customer_id, o.id, o.created_at,
           row_number() OVER (PARTITION BY o.customer_id ORDER BY o.created_at DESC, o.id DESC) AS recency_rank
    FROM orders o
    WHERE o.customer_id = ANY ($1)
) ranked
WHERE recency_rank <= 3;
```
```text
 customer_id |   id   |          created_at
-------------+--------+-------------------------------
          42 |  67694 | 2026-08-20 10:23:20.602756+06
          42 | 241607 | 2026-06-10 04:46:58.075028+06
          42 | 368052 | 2026-06-04 09:17:37.141609+06
          43 | 587302 | 2026-09-13 16:32:14.014637+06
          ...
```

The plan shows `WindowAgg` with `Run Condition: (row_number() OVER w1 <= 3)`: PostgreSQL stops numbering a partition once the condition can no longer be met. The aggregate case is plain SQL: `SELECT customer_id, count(*), sum(total) FROM orders WHERE customer_id = ANY ($1) GROUP BY customer_id`.

## Pitfalls

- `IN (?, ?, ?)` with a variable number of placeholders. Every list length is a different statement to the plan cache and to `pg_stat_statements`, and very long lists are slow to parse. Use `= ANY($1)` with an array.
- Fixing the N+1 with a join that multiplies rows. Joining two child collections at once (orders and addresses) returns orders × addresses rows per customer; load each collection with its own `ANY` query instead.
- Moving the loop into memory badly. After loading parents and children in two queries, match them with a map keyed by parent id, not with a nested loop over two lists.
- Running the N queries in parallel to "fix" latency. Now the loop holds N connections instead of one; the pool empties and every other request waits (item 7.5).
- One enormous array. A hundred thousand ids in one `ANY` makes the planner scan and sort the whole table; batch into chunks and keep each statement's result set modest.
- Setting `log_min_duration_statement` to a few hundred milliseconds and concluding that there are no slow queries. The N+1 is below the threshold by construction; look at `calls` in `pg_stat_statements`.

## Check yourself

1. Why does `log_min_duration_statement = 200ms` never report an N+1, and which two columns of `pg_stat_statements` reveal it?
2. What advantage does `WHERE id = ANY($1)` have over `WHERE id IN (?, ?, ?)` beyond saving keystrokes?
3. A page shows twenty customers and the three most recent orders of each. Write the shape of the single query that loads the orders.
4. An import inserts 50,000 order lines in a loop of single-row inserts. Give two set-based alternatives and say when each applies.

## Go deeper

- [Vlad Mihalcea: N+1 query problem](https://vladmihalcea.com/n-plus-1-query-problem/) · the problem from the JPA side, with the ways Hibernate produces it.
- [PostgreSQL: pg_stat_statements](https://www.postgresql.org/docs/current/pgstatstatements.html) · the view's columns and how to enable it.
- [PostgreSQL: Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html) · the tutorial behind the "top k per group" rewrite.
- [Use The Index, Luke: Nested Loops](https://use-the-index-luke.com/sql/join/nested-loops-join-n1-problem) · why the database's own nested loop beats the application's, and how ORMs produce N+1.

---

Part of [Databases](../README.md) · item 4.4
