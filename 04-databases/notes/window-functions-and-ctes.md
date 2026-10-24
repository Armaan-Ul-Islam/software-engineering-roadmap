# Window functions, CTEs and LATERAL joins

> **In one sentence:** A window function computes a value for each row from a set of related rows (its window) without collapsing them the way `GROUP BY` does; a CTE names a subquery so a statement reads top to bottom and, with `RECURSIVE`, can walk a tree; and `LATERAL` lets a subquery in `FROM` see the row before it, which is the natural way to fetch the top N per group.

**Why it matters:** Running totals, "compared with the previous row", rankings and top-N-per-group are the questions reports and dashboards actually ask, and without window functions they become self-joins or application loops (item 4.4). Interviewers like the topic because the syntax is small while the frame semantics are subtle: the default frame produces running totals that are wrong by exactly one duplicate.

## The idea

**Window functions.** `function(...) OVER (PARTITION BY ... ORDER BY ... frame)` is evaluated after `WHERE`, `GROUP BY` and `HAVING`, once per output row. `PARTITION BY` splits the rows into independent groups (like `GROUP BY`, but the rows survive); `ORDER BY` orders the rows inside each partition, which ranking and offset functions need; the *frame* says which rows of the partition an aggregate sees for the current row.

| Family | Functions | `ORDER BY` in the window |
|---|---|---|
| Ranking | `row_number()`, `rank()`, `dense_rank()`, `ntile(n)` | required |
| Offset | `lag(column, n)`, `lead(column, n)`, `first_value`, `last_value`, `nth_value` | required |
| Aggregates as windows | `sum`, `count`, `avg`, `min`, `max`, `array_agg`, ... | absent: whole partition; present: running |

**Frames, the subtle part.** With an `ORDER BY` and no explicit frame, the frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, and `RANGE` includes every *peer* of the current row (rows equal under the `ORDER BY`). A running total over `ORDER BY placed_on` therefore gives two orders from the same day the same total. Either add a unique tiebreaker to the `ORDER BY` or write `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Moving windows are explicit frames: `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` for a seven-row moving average, `RANGE BETWEEN INTERVAL '7 days' PRECEDING AND CURRENT ROW` for a time-based one.

**Ranking and ties.** `row_number()` numbers rows 1, 2, 3 even when they tie, so without a unique `ORDER BY` the numbering is arbitrary and can change between executions. `rank()` gives tied rows the same number and skips (1, 2, 2, 4); `dense_rank()` does not skip (1, 2, 2, 3). Which of them is "top 3" is a business decision, not a syntax one.

**Common table expressions.** `WITH name AS (SELECT ...)` names a subquery for the rest of the statement. Use CTEs to give each step of a long query a name, to reuse one result twice, and for data-modifying statements (`WITH moved AS (DELETE ... RETURNING *) INSERT INTO archive SELECT * FROM moved`). Since PostgreSQL 12 a CTE that is referenced once, is not recursive and has no side effects is inlined into the main query, so the planner can push conditions into it and use indexes; a CTE referenced more than once is materialised (computed once). `AS MATERIALIZED` forces materialisation, which makes the CTE an optimisation fence; `AS NOT MATERIALIZED` forces inlining even for repeated references.

**Recursive CTEs.** `WITH RECURSIVE tree AS (anchor UNION ALL step)`, where `step` selects from `tree`: the anchor runs once, then the step runs repeatedly on the rows produced by the previous round until it returns none. That walks an adjacency list (categories, organisation charts, bills of materials) of any depth in one statement. Carry a depth counter and a path array along. From PostgreSQL 14, `CYCLE id SET is_cycle USING path` stops the recursion if the data contains a loop.

**`LATERAL`.** A subquery in `FROM` normally cannot see the other `FROM` items. `LATERAL` lets it reference the rows of the items before it, so it runs once per such row, like a correlated loop the database controls. With an index on `(customer_id, total DESC)`, each iteration of "top three orders of this customer" reads exactly three index entries. `CROSS JOIN LATERAL` drops rows for which the subquery returns nothing; `LEFT JOIN LATERAL ... ON true` keeps them.

## Example: top 3 orders per customer, three ways

```sql
CREATE TABLE customer (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int NOT NULL REFERENCES customer (id),
                     placed_on date NOT NULL, total numeric(8,2) NOT NULL);
INSERT INTO customer VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Carol');
INSERT INTO orders VALUES
    (1, 1, '2026-09-01', 120.00), (2, 1, '2026-09-05', 80.00), (3, 1, '2026-09-05', 45.00),
    (4, 1, '2026-09-20', 200.00), (5, 1, '2026-10-02', 60.00),
    (6, 2, '2026-09-03', 50.00),  (7, 2, '2026-09-10', 50.00), (8, 2, '2026-09-11', 50.00),
    (9, 2, '2026-10-01', 90.00),  (10, 3, '2026-09-07', 30.00);
CREATE INDEX orders_customer_total_idx ON orders (customer_id, total DESC, id);
```

**Way 1, `row_number()` with a tiebreaker** (exactly three per customer, deterministic):

```sql
SELECT customer_id, id, total
FROM (
    SELECT customer_id, id, total,
           row_number() OVER (PARTITION BY customer_id ORDER BY total DESC, id) AS position
    FROM orders
) AS ranked
WHERE position <= 3
ORDER BY customer_id, position;
```
```text
 customer_id | id | total
-------------+----+--------
           1 |  4 | 200.00
           1 |  1 | 120.00
           1 |  2 |  80.00
           2 |  9 |  90.00
           2 |  6 |  50.00
           2 |  7 |  50.00
           3 | 10 |  30.00
```

Bob's orders 6, 7 and 8 all cost 50.00; the tiebreaker `id` decided that 8 is out. **Way 2** replaces `row_number()` with `rank() OVER (PARTITION BY customer_id ORDER BY total DESC)`: the three tied orders all get rank 2, so Bob gets four rows. Both are one pass over the data; the plan shows `WindowAgg` with `Run Condition: (row_number() OVER w1 <= 3)`, which stops numbering a partition once the condition can no longer hold.

**Way 3, `LATERAL`:**

```sql
SELECT customer.name, top_orders.id, top_orders.total
FROM customer
CROSS JOIN LATERAL (
    SELECT id, total
    FROM orders
    WHERE orders.customer_id = customer.id
    ORDER BY total DESC, id
    LIMIT 3
) AS top_orders;
```

The same seven rows. Replace `LIMIT 3` with `FETCH FIRST 3 ROWS WITH TIES` (PostgreSQL 13 or later) and the subquery behaves like `rank()`, returning Bob's four. The two shapes scale differently. On a table of 300,000 orders for 1,000 customers with the index above, the `LATERAL` plan is a `Nested Loop` over the customers whose inner side is an `Index Only Scan` with `actual rows=3.00 loops=1000` and `Index Searches: 1000`, 4 ms; the window plan is one `Index Only Scan` over all 300,000 entries feeding the `WindowAgg`, 25 ms. The window must read every order to number it; the lateral probe jumps straight to the top three of each customer. With few orders per customer and many customers the balance tips the other way, so read the plan. For "top 3 for *this* customer", `LATERAL` or a plain `LIMIT 3` is the only sensible shape.

**Running totals, frames and `lag`:**

```sql
SELECT id, placed_on, total,
       sum(total) OVER (PARTITION BY customer_id ORDER BY placed_on) AS running_range,
       sum(total) OVER (PARTITION BY customer_id ORDER BY placed_on, id) AS running_rows,
       placed_on - lag(placed_on) OVER (PARTITION BY customer_id ORDER BY placed_on, id) AS days_since_previous
FROM orders WHERE customer_id = 1 ORDER BY placed_on, id;
```
```text
 id | placed_on  | total  | running_range | running_rows | days_since_previous
----+------------+--------+---------------+--------------+---------------------
  1 | 2026-09-01 | 120.00 |        120.00 |       120.00 |
  2 | 2026-09-05 |  80.00 |        245.00 |       200.00 |                   4
  3 | 2026-09-05 |  45.00 |        245.00 |       245.00 |                   0
  4 | 2026-09-20 | 200.00 |        445.00 |       445.00 |                  15
  5 | 2026-10-02 |  60.00 |        505.00 |       505.00 |                  12
```

Orders 2 and 3 are peers under `ORDER BY placed_on`, so the default `RANGE` frame gives both the total *including* each other (245.00). With `id` as a tiebreaker every row is its own peer group and the total runs row by row.

**A recursive CTE over a category tree:**

```sql
CREATE TABLE category (id int PRIMARY KEY, parent_id int REFERENCES category (id), name text NOT NULL);
INSERT INTO category VALUES (1, NULL, 'Electronics'), (2, 1, 'Computers'), (3, 2, 'Laptops'),
                            (4, 2, 'Monitors'), (5, 1, 'Phones'), (6, NULL, 'Home'), (7, 6, 'Kitchen');

WITH RECURSIVE subtree AS (
    SELECT id, parent_id, name, 0 AS depth, ARRAY[name] AS path
    FROM category
    WHERE id = 1
  UNION ALL
    SELECT category.id, category.parent_id, category.name, subtree.depth + 1, subtree.path || category.name
    FROM category
    JOIN subtree ON category.parent_id = subtree.id
)
SELECT id, depth, array_to_string(path, ' > ') AS path
FROM subtree
ORDER BY path;
```
```text
 id | depth |                path
----+-------+------------------------------------
  1 |     0 | Electronics
  2 |     1 | Electronics > Computers
  3 |     2 | Electronics > Computers > Laptops
  4 |     2 | Electronics > Computers > Monitors
  5 |     1 | Electronics > Phones
```

Swap the join condition to `category.id = subtree.parent_id` and the same shape walks *up* from a leaf to produce a breadcrumb. If a bad update makes Electronics a child of Laptops, this query never terminates; add `CYCLE id SET is_cycle USING visited` after the CTE body and the row that closes the loop comes back flagged `is_cycle = t` with `visited = {(1),(2),(3),(1)}` instead.

**`MATERIALIZED` as a fence.** On the 300,000-row table, `WITH recent AS (SELECT ... WHERE placed_on >= '2026-10-01') SELECT count(*), sum(total) FROM recent WHERE customer_id = 42` is inlined: the plan is a `Bitmap Heap Scan` with `Recheck Cond: (customer_id = 42)` touching 295 pages. With `AS MATERIALIZED` the plan reads all 1,920 pages in a `Seq Scan` (`Rows Removed by Filter: 272321`), materialises 27,679 rows and filters them in a `CTE Scan`. Write the keyword only when you want the fence: a CTE with a volatile function, or one that must be computed exactly once.

## Pitfalls

- Running totals without a tiebreaker. Peers share the total under the default `RANGE` frame; the symptom is a cumulative column that repeats a value and then jumps.
- `row_number()` without a unique `ORDER BY`. Which tied row is "third" is undefined and can differ between executions; tests on small data never notice.
- Filtering on a window function in `WHERE`. Window functions are evaluated after `WHERE`, so `WHERE row_number() OVER (...) <= 3` fails with `window functions are not allowed in WHERE`; wrap the query in a subquery or CTE and filter the alias.
- `last_value()` with the default frame. The frame ends at the current row, so `last_value` returns the current row's value; use `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`, or `first_value` with the `ORDER BY` reversed.
- Assuming a CTE is an optimisation fence, or assuming it is not. It depends on the server version and on how many times the CTE is referenced; read the plan, and write `MATERIALIZED` or `NOT MATERIALIZED` when it matters.
- Recursive CTEs over data that can contain a cycle. Without `CYCLE` or a check against the path array, the query runs until it exhausts memory or you cancel it.

## Check yourself

1. Two orders share the same `placed_on`. Explain why `sum(total) OVER (ORDER BY placed_on)` gives them the same running total, and give two fixes.
2. For "the three most expensive orders of each of these five customers" and for "the three most expensive orders of every one of a million customers", which shape would you write, and what in the plan confirms the choice?
3. `rank()`, `dense_rank()` and `row_number()` over `ORDER BY total DESC` produce different "top 3" sets when there are ties. Describe the difference and a business case where each is the correct answer.
4. Why must the recursive part of a `WITH RECURSIVE` query reference the CTE itself, and what happens when the table contains a cycle and the query has no `CYCLE` clause?

## Go deeper

- [PostgreSQL: Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html) · the tutorial, then [Window Function Calls](https://www.postgresql.org/docs/current/sql-expressions.html#SYNTAX-WINDOW-FUNCTIONS) for the exact frame rules.
- [PostgreSQL: Window Functions reference](https://www.postgresql.org/docs/current/functions-window.html) · every ranking and offset function with its definition.
- [PostgreSQL: WITH Queries](https://www.postgresql.org/docs/current/queries-with.html) · CTEs, `RECURSIVE`, `CYCLE`, `SEARCH` and the materialisation rules.
- [PostgreSQL: LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL) · the semantics and the top-N example.
- [Modern SQL](https://modern-sql.com/) · Markus Winand's reference on window functions, `WITH`, `FETCH FIRST ... WITH TIES` and which databases support each.

---

Part of [Databases](../README.md) · item 1.3
