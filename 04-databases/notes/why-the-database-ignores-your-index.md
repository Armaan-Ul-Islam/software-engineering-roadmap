# Why the database ignores your index

> **In one sentence:** The planner can use a B-tree index only when the query compares the indexed expression, in the indexed type and collation, against something it can turn into a slice of the sorted entries; a function on the column, an implicit cast, a leading wildcard, an `OR` it cannot split, a value that matches most of the table, or statistics that are out of date each break that rule.

**Why it matters:** "There is an index on that column" is the most common wrong answer to "why is this query slow". The index exists; the query is written so that it cannot be used. Each cause has a visible signature in `EXPLAIN` and a mechanical fix, and several are introduced by application code rather than SQL: the ORM wraps the column in a function, or the JDBC parameter arrives with the wrong type.

## The idea

A B-tree over `email` is sorted by `email`. The planner can descend it for `email = $1` or `email > $1` because those conditions describe a contiguous slice of the sorted entries. It cannot descend it for `lower(email) = $1`: the entries are not sorted by `lower(email)`, so the only option is to compute the function for every row. The same reasoning covers every case below.

1. **A function or cast on the column.** `lower(email) = ...`, `created_at::date = ...`, `substring(code, 1, 3) = ...`, `id::text = ...`. Signature: `Seq Scan` with the expression in `Filter`. Fix: rewrite so the column stands alone (`created_at >= date '2026-10-01' AND created_at < date '2026-10-02'`), or create an expression index on exactly that expression, or store the normalised value in its own column.
2. **A parameter of a different type.** When no operator exists for `bigint = numeric`, PostgreSQL casts the *column*, and the index is lost: `Filter: ((customer_id)::numeric = 42.0)`. This happens with the literal `42.0`, with `setBigDecimal` or `setDouble` on a `bigint` column from JDBC, and with `double precision` parameters from some ORMs. Comparing a `bigint` to a `varchar` parameter fails loudly instead (`operator does not exist: bigint = character varying`) unless the connection sets `stringtype=unspecified`, in which case the server infers the type and the index works. MySQL is more dangerous here: comparing a string column with a number silently converts every row.
3. **`LIKE` with a leading wildcard.** `email LIKE '%@example.com'` has no prefix to descend to. And under a non-C collation such as `en_US.UTF-8`, even `LIKE 'customer42%'` cannot use an ordinary B-tree, because the collation's sort order is not byte order; the index needs the `text_pattern_ops` operator class or a `COLLATE "C"` column. For suffix and infix search use a `pg_trgm` GIN index, or an expression index on `reverse(email)` for suffixes.
4. **`OR` across columns.** PostgreSQL can combine two indexes with a `BitmapOr`, but only if every branch is indexable; one non-indexed branch forces a sequential scan for the whole condition. The optional-parameter idiom `($1 IS NULL OR email = $1)` is the worst case: once the server switches to a generic plan (after five executions of a prepared statement, if the generic plan does not look costlier), it cannot know that `$1` is not null and scans the table. Fix: build the SQL conditionally, or `UNION ALL` the branches.
5. **Low selectivity.** The value matches most of the table, so the planner correctly prefers a sequential scan (`status = 'shipped'` for 70% of rows). No rewrite helps; a partial index for the rare values might (item 3.3).
6. **Stale statistics.** The planner thinks the table is small or the value rare, and picks the plan that would be right for that table. Signature: estimated rows far from actual rows. Fix: `ANALYZE`, run explicitly after bulk loads instead of waiting for autovacuum (item 4.3).

## Example: two cases, before and after

A `customer` table with 50,000 rows and `CREATE INDEX customer_email_idx ON customer (email)`; PostgreSQL 18, planning lines removed.

**Case 1, function on the column.**

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF)
SELECT id FROM customer WHERE lower(email) = 'customer42@example.com';
```
```text
Seq Scan on customer (actual rows=1.00 loops=1)
  Filter: (lower(email) = 'customer42@example.com'::text)
  Rows Removed by Filter: 49999
  Buffers: shared hit=568
```

```sql
CREATE INDEX customer_email_lower_idx ON customer (lower(email));
ANALYZE customer;
```
```text
Index Scan using customer_email_lower_idx on customer (actual rows=1.00 loops=1)
  Index Cond: (lower(email) = 'customer42@example.com'::text)
  Buffers: shared hit=1 read=3
```

568 pages down to 4. The expression in the index must match the query's expression exactly; `lower(email)` does not serve `upper(email)` or `lower(trim(email))`.

**Case 2, parameter type from the driver.** `PREPARE` reproduces what a JDBC driver sends, type and all:

```sql
PREPARE by_customer_numeric (numeric) AS SELECT * FROM orders WHERE customer_id = $1;
EXPLAIN (COSTS OFF) EXECUTE by_customer_numeric (42);
```
```text
Seq Scan on orders
  Filter: ((customer_id)::numeric = '42'::numeric)
```

```sql
PREPARE by_customer_bigint (bigint) AS SELECT * FROM orders WHERE customer_id = $1;
EXPLAIN (COSTS OFF) EXECUTE by_customer_bigint (42);
```
```text
Bitmap Heap Scan on orders
  Recheck Cond: (customer_id = '42'::bigint)
  ->  Bitmap Index Scan on orders_customer_status_created_idx
        Index Cond: (customer_id = '42'::bigint)
```

The fix is in Java, not SQL: bind the parameter as `long` (`setLong`, or a `Long` entity attribute) rather than `BigDecimal` or `Double`. In Hibernate, compare each attribute's Java type with the column type; a `BigDecimal` attribute mapped to a `bigint` column produces exactly this plan on every lookup.

To diagnose any of the cases, read the `Filter` or `Index Cond` line: a cast such as `(customer_id)::numeric` or a function wrapped around the column name says the index could not be applied to the column as stored.

## Pitfalls

- Trusting that the ORM compares columns the way you wrote the entity. Case-insensitive lookups, date truncation and `COALESCE` defaults often arrive wrapped around the column. Log the SQL, or use `auto_explain` (item 4.5).
- Testing `LIKE 'prefix%'` on a database created with the `C` locale and shipping to one created with `en_US.UTF-8`. Check `SELECT datcollate FROM pg_database`.
- Creating an expression index that almost matches. `lower(email)`, `lower(email::text)` and `lower(trim(email))` are three different indexes.
- Fixing a type mismatch with a cast on the column (`customer_id::numeric = ?`). That is case 1 wearing a different hat; cast the parameter instead.
- Blaming the planner for case 5 or 6. Compare estimated to actual rows before touching the query; if they agree and the plan is a sequential scan, the scan is probably the right plan.
- Relying on the five-execution custom-plan window. The same prepared statement can be fast in a test (custom plans) and slow in production (generic plan). `plan_cache_mode = force_custom_plan` is a diagnostic, not a fix.

## Check yourself

1. `WHERE date_trunc('day', created_at) = date '2026-10-01'` is slow despite an index on `created_at`. Give two different fixes and say which you would choose.
2. A Spring application maps an order id as `BigDecimal`. The query uses the index in `psql` but not from the application. Why, and how do you confirm it from the server side?
3. Why can `WHERE email LIKE 'alice%'` use a B-tree in one database and not in another with the same schema?
4. A search endpoint has six optional filters implemented as `($n IS NULL OR column = $n)`. What plan will it eventually get, and what would you do instead?

## Go deeper

- [Use The Index, Luke: Function-Based Indexes](https://use-the-index-luke.com/sql/where-clause/functions) · case 1 in depth, then [Obfuscated Conditions](https://use-the-index-luke.com/sql/where-clause/obfuscation) for dates, numeric strings and "smart logic".
- [PostgreSQL: Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) · what the server requires of an expression index.
- [PostgreSQL: Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html) · `text_pattern_ops`, and why collation decides whether `LIKE` can use an index.
- [PostgreSQL: pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html) · indexing `LIKE '%infix%'` with trigrams.
- [PostgreSQL: PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html) · the generic-versus-custom plan rules behind case 4.
- [PostgreSQL JDBC Driver: Using the Driver](https://jdbc.postgresql.org/documentation/use/) · connection parameters, including `stringtype`.

---

Part of [Databases](../README.md) · item 3.5
