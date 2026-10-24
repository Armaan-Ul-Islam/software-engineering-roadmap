# SQL joins explained: inner, outer, semi, anti and the fan-out bug

> **In one sentence:** A join pairs rows from two tables by a condition; the join type decides what happens to rows that find no partner (inner drops them, outer keeps them with NULLs), `EXISTS` asks whether a partner exists without producing the pairs, and summing after a join to a one-to-many table silently multiplies your numbers.

**Why it matters:** Almost every report query, API listing and ORM-generated statement is a join, and the three classic mistakes produce plausible wrong numbers rather than errors: an outer join turned back into an inner one by a `WHERE` condition, a `NOT IN` that returns nothing because the subquery contains a NULL, and a total that doubles after a second join. Interviewers ask about semi joins and `HAVING` because the answers show whether you think in sets or in loops.

## The idea

**A join is a filter over all pairs.** Conceptually, `customer JOIN orders ON orders.customer_id = customer.id` forms every (customer, order) pair, the cross product, and keeps the pairs for which the `ON` condition is true. `CROSS JOIN` is that product with no condition, occasionally what you want (every customer for every month of a report) and otherwise a sign of a missing `ON`.

**The four main types** differ only in what they do with rows that found no partner:

| Join | Keeps | Unmatched side |
|---|---|---|
| `INNER JOIN` (`JOIN`) | pairs that match | dropped |
| `LEFT JOIN` | all left rows, plus matching right rows | right columns are NULL |
| `RIGHT JOIN` | all right rows, plus matching left rows | left columns are NULL; same as `LEFT JOIN` with the tables swapped |
| `FULL JOIN` | everything from both sides | NULLs on whichever side is missing |

**Semi and anti joins.** "Customers who have at least one order" is not a join: you want each customer once, not once per order. `WHERE EXISTS (SELECT FROM orders WHERE orders.customer_id = customer.id)` is a *semi join*. It tests for a partner and never produces the pairs, so there are no duplicates to remove. `NOT EXISTS` is the *anti join*: customers with no partner at all. PostgreSQL recognises both and plans them as `Semi Join` and `Anti Join` nodes.

**Why `NOT IN` is a trap.** `id NOT IN (1, 2, NULL)` means `id <> 1 AND id <> 2 AND id <> NULL`, and `id <> NULL` is not false but *unknown*. `true AND unknown` is unknown, and `WHERE` keeps only rows whose condition is true, so the row is dropped. One NULL in the subquery's column makes `NOT IN` return no rows at all, without an error. `IN` is safe, because a single true wins; `NOT IN` is safe only when the column is `NOT NULL`. Use `NOT EXISTS`.

**`ON` versus `WHERE` with outer joins.** For an inner join the two places are interchangeable. For an outer join they are not: a condition in `ON` decides which right rows *match*, and left rows without a match are still kept; a condition in `WHERE` runs after the join, when unmatched rows carry NULLs on the right, so `WHERE orders.placed_on >= ...` is unknown for them and they vanish. The one `WHERE` test that belongs on the nullable side is `IS NULL`, which turns a `LEFT JOIN` into an anti join.

**`GROUP BY` and `HAVING`.** `GROUP BY` collapses the rows that share the grouping columns into one row per group; the select list may then contain only grouping columns and aggregates (PostgreSQL also accepts other columns of a table whose primary key is grouped, so `GROUP BY customer.id` lets you select `customer.name`). `WHERE` filters rows before grouping; `HAVING` filters groups after it, which is why a condition on an aggregate can only live in `HAVING`. After a `LEFT JOIN`, `count(*)` counts the NULL-filled row of an unmatched customer and `count(orders.id)` does not.

**The fan-out bug.** Joining a table to a one-to-many child repeats each parent row once per child. Join to *two* children and each parent row appears (lines × payments) times. Every `sum` or `count` over such a result is multiplied, and the numbers look plausible. The fix is to aggregate each child down to the parent's grain first, in a derived table or CTE with its own `GROUP BY`, and join the aggregates, so that every join is one-to-one again.

## Example: one schema, every join

```sql
CREATE TABLE customer (id int PRIMARY KEY, name text NOT NULL, country text NOT NULL);
CREATE TABLE orders (
    id           int PRIMARY KEY,
    customer_id  int REFERENCES customer (id),      -- NULL for guest checkouts
    placed_on    date NOT NULL,
    shipping_fee numeric(6,2) NOT NULL
);
CREATE TABLE order_line (
    order_id   int REFERENCES orders (id), line_number int, product text NOT NULL,
    quantity   int NOT NULL, unit_price numeric(8,2) NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
CREATE TABLE payment (id int PRIMARY KEY, order_id int NOT NULL REFERENCES orders (id), amount numeric(8,2) NOT NULL);

INSERT INTO customer VALUES (1, 'Alice', 'NO'), (2, 'Bob', 'SE'), (3, 'Carol', 'NO');
INSERT INTO orders VALUES (101, 1, '2026-09-14', 5.00), (102, 1, '2026-10-02', 0.00),
                          (103, 2, '2026-09-30', 5.00), (104, NULL, '2026-10-05', 5.00);
INSERT INTO order_line VALUES (101, 1, 'Widget', 2, 9.99), (101, 2, 'Gadget', 1, 24.50), (102, 1, 'Widget', 1, 9.99),
                              (103, 1, 'Gadget', 2, 24.50), (103, 2, 'Cable', 3, 3.00), (104, 1, 'Widget', 1, 9.99);
INSERT INTO payment VALUES (1, 101, 20.00), (2, 101, 24.48), (3, 102, 9.99), (4, 103, 58.00), (5, 104, 9.99);
```

Carol has no orders and order 104 has no customer. `SELECT customer.name, orders.id FROM customer FULL JOIN orders ON orders.customer_id = customer.id` returns every row below; `INNER` returns only the first three, `LEFT` adds Carol, `RIGHT` adds order 104, and `CROSS JOIN` returns 12 rows:

```text
 name  | order_id
-------+----------
 Alice |      101
 Alice |      102
 Bob   |      103
 Carol |
       |      104
```

**Semi, anti and the NULL trap:**

```sql
SELECT name FROM customer WHERE EXISTS (SELECT FROM orders WHERE orders.customer_id = customer.id);
-- Alice, Bob                      (customer JOIN orders would return Alice twice)
SELECT name FROM customer WHERE NOT EXISTS (SELECT FROM orders WHERE orders.customer_id = customer.id);
-- Carol
SELECT name FROM customer WHERE id NOT IN (SELECT customer_id FROM orders);
-- (0 rows)                        order 104's NULL customer_id poisons the whole list
SELECT 3 NOT IN (1, 2, NULL);      -- NULL, not false
```

`EXPLAIN (COSTS OFF)` on PostgreSQL 18 shows how differently the server treats them. The `NOT EXISTS` is a `Hash Right Anti Join` with `Hash Cond: (orders.customer_id = customer.id)`. The `NOT IN` is a `Seq Scan on customer` with `Filter: (NOT (ANY (id = (hashed SubPlan 1).col1)))`: a subplan that must preserve the NULL semantics and is not a join, and when its result is too large to hash in memory it is re-executed for every outer row.

**`ON` versus `WHERE`.** Customers and their orders placed in October, keeping customers who placed none:

```sql
SELECT customer.name, orders.id
FROM customer LEFT JOIN orders ON orders.customer_id = customer.id
                              AND orders.placed_on >= date '2026-10-01';
--  Alice | 102
--  Bob   |
--  Carol |
```

Move the date condition into `WHERE` and only `Alice | 102` remains: the NULL `placed_on` of Bob's and Carol's rows fails the test, and the outer join has become an inner join.

**`GROUP BY`, `HAVING` and the two counts:**

```sql
SELECT customer.name, count(*) AS rows_in_group, count(orders.id) AS orders
FROM customer LEFT JOIN orders ON orders.customer_id = customer.id
GROUP BY customer.id                 -- name may be selected: it depends on the primary key
ORDER BY customer.id;
--  Alice | 2 | 2
--  Bob   | 1 | 1
--  Carol | 1 | 0                      count(*) counts the NULL-filled row; count(orders.id) does not
```

Add `HAVING count(orders.id) >= 2` and only Alice remains. The same condition in `WHERE` is an error, because the count does not exist until the groups do.

**The fan-out bug.** Goods total and amount paid per order:

```sql
SELECT orders.id, sum(order_line.quantity * order_line.unit_price) AS goods, sum(payment.amount) AS paid
FROM orders
JOIN order_line ON order_line.order_id = orders.id
JOIN payment    ON payment.order_id = orders.id
GROUP BY orders.id ORDER BY orders.id;
--  101 | 88.96 |  88.96               both doubled: 2 lines × 2 payments = 4 joined rows
--  102 |  9.99 |   9.99
--  103 | 58.00 | 116.00               paid doubled: 2 lines × 1 payment
--  104 |  9.99 |   9.99
```

Order 101 is really 44.48 of goods, paid in full; the one-line, one-payment orders are right by luck. The fix aggregates each child to the order grain before joining:

```sql
SELECT orders.id, line_total.goods, paid.amount AS paid
FROM orders
JOIN (SELECT order_id, sum(quantity * unit_price) AS goods FROM order_line GROUP BY order_id) AS line_total
     ON line_total.order_id = orders.id
LEFT JOIN (SELECT order_id, sum(amount) AS amount FROM payment GROUP BY order_id) AS paid
     ON paid.order_id = orders.id
ORDER BY orders.id;
--  101 | 44.48 | 44.48
--  103 | 58.00 | 58.00
```

The detection habit: count the rows of the driving table (4 orders), then of each join (6 rows after `order_line`, 8 after `payment`). A join that increases the count has fanned out, and nothing summed after it can be trusted. The `LEFT JOIN` on the payment aggregate keeps unpaid orders in the result with a NULL `paid`.

## Pitfalls

- Filtering the nullable side in `WHERE`. The report silently loses the customers with zero activity, which are exactly the rows the `LEFT JOIN` was added for.
- `NOT IN` against a nullable column. Zero rows, no error, and it passes every test until the first NULL appears in production. `<> ALL (subquery)` has the same problem; `NOT EXISTS` does not.
- `JOIN` plus `DISTINCT` to express "has at least one". It computes every pair and then removes the duplicates, and the `DISTINCT` also hides fan-outs you did not know about. `EXISTS` never creates the duplicates.
- Summing after joining two children. If a query joins more than one one-to-many relationship and aggregates, assume the numbers are multiplied until you have compared the row counts.
- `count(*)` after an outer join. It counts the NULL-filled rows; count the column that is NULL when unmatched.
- `NATURAL JOIN`. It joins on every column name the two tables share, so adding a `created_at` column to both tables changes the result of an existing query. Name the columns with `ON` or `USING`.
- Trusting an ORM's generated join. Fetching two collections of an entity in one query is the fan-out in disguise; load each collection with its own query (item 4.4).

## Check yourself

1. A `LEFT JOIN` from `customer` to `orders` with `WHERE orders.status = 'paid'` returns fewer customers than the table holds. Explain why, and name the one-word change that fixes it.
2. `SELECT id FROM customer WHERE id NOT IN (SELECT customer_id FROM orders)` returns nothing although many customers have no orders. What must be in `orders`, and what are two rewrites that work?
3. You join `orders` to `order_line` and to `shipment`, then sum the line amounts. The sum is too high for some orders and correct for others. Which orders are correct, and how do you restructure the query?
4. Why can a condition on `count(*)` not be written in `WHERE`, and why does a condition on a plain column belong in `WHERE` even though `HAVING` would accept it?

## Go deeper

- [PostgreSQL: Joined Tables](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-JOIN) · the exact semantics of every join type, including `USING` and `NATURAL`.
- [PostgreSQL: Subquery Expressions](https://www.postgresql.org/docs/current/functions-subquery.html) · `EXISTS`, `IN`, `NOT IN`, `ANY` and `ALL`, with the NULL rules spelled out.
- [Use The Index, Luke: The Join Operation](https://use-the-index-luke.com/sql/join) · how nested loops, hash joins and merge joins execute what you wrote (the plans are item 4.2).
- [PostgreSQL Exercises](https://pgexercises.com/) · the joins and aggregates sections make this automatic.
- [SQLBolt](https://sqlbolt.com/) · interactive lessons on joins and grouping if you are starting from zero.

---

Part of [Databases](../README.md) · item 1.2
