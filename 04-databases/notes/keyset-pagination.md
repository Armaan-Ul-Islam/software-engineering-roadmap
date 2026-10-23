# Keyset pagination

> **In one sentence:** `OFFSET n` makes the database fetch and discard n rows before returning a page, so deep pages cost more the deeper they are and shift under concurrent writes; keyset (seek) pagination instead remembers the sort key of the last row shown and asks for the rows after it, which an index answers in constant time at any depth.

**Why it matters:** "The last pages of the list time out" and "items appear twice or go missing while paging" are both `OFFSET`. Every API that returns a `next` cursor instead of a page number is doing keyset pagination, and every infinite-scroll feed that does not is a latent incident. It also exercises the two indexing rules that matter most: matching the index to the `ORDER BY`, and making the sort key unique.

## The idea

**Why `OFFSET` degrades.** `ORDER BY created_at DESC LIMIT 20 OFFSET 100000` is executed exactly as written: walk the index (or sort the table) in order, skip 100,000 rows, return 20. The skipped rows are read from disk, checked for visibility and thrown away, so page 5,001 costs 5,000 times more than page 1. And because the skip is counted in rows, an insert between two requests pushes every later row down by one: the last item of page 7 reappears as the first of page 8, and a delete makes a row disappear from both.

**The seek method.** Sort by a key that is total and stable, remember the key of the last row on the current page, and ask for rows beyond it:

```sql
SELECT id, created_at, total
FROM orders
WHERE (created_at, id) < ($1, $2)          -- the last row of the previous page
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The row-value comparison `(created_at, id) < ($1, $2)` means "comes after this row in the sort order", including the rows that share the same `created_at` but have a smaller `id`. PostgreSQL turns it into a single index condition, descends the index straight to the boundary, and reads 20 entries. The cost is the same on page 1 and page 50,000, and a row inserted meanwhile simply appears in its proper place without shifting anything already shown.

**The tiebreaker.** Timestamps collide, and a sort key with duplicates is not a position. If two orders share a `created_at` on the page boundary, `WHERE created_at < $1` skips one and `WHERE created_at <= $1` repeats one. Adding a unique column (`id`) as the last sort key makes every key unique and the boundary exact. Any unique column works, but it must be in both the `ORDER BY` and the comparison.

**The index.** It must match the sort columns in order, `(created_at, id)`; PostgreSQL scans it backwards for `DESC`, or declare the columns `DESC` to scan forwards. Any equality filter the page always has, such as `WHERE customer_id = $3`, goes in front: `(customer_id, created_at, id)`. Without a matching index the planner sorts the whole result set for every page and the method gains nothing.

**Trade-offs.** No "jump to page 50": the client can go to the next page, and to the previous page by reversing the comparison and the sort and then re-sorting the 20 rows. No total count comes for free; count separately, or estimate. Mixed directions (`created_at DESC, id ASC`) cannot use the row-value form and need the expanded `OR` form with an index declared in matching directions. Nullable sort columns need `NULLS LAST` and a comparison that handles the null boundary, or a non-null column instead. In return: constant cost, stable pages, and a cursor that can be handed to a client as an opaque token.

## Example: the same page two ways

A million orders with `CREATE INDEX orders_created_at_id_idx ON orders (created_at, id)`. PostgreSQL 18, `EXPLAIN (ANALYZE, BUFFERS)`, planning lines removed.

**`OFFSET`, page 5,001:**

```sql
SELECT id, created_at, total FROM orders
ORDER BY created_at DESC, id DESC LIMIT 20 OFFSET 100000;
```
```text
Limit (actual time=70.083..70.092 rows=20.00 loops=1)
  Buffers: shared hit=93282 read=7108
  ->  Index Scan Backward using orders_created_at_id_idx on orders (actual time=0.009..67.153 rows=100020.00 loops=1)
```

The index scan produced 100,020 rows and touched 100,390 pages so that `Limit` could keep 20. Page 1 of the same query took 0.9 ms and 23 pages.

**Keyset, the same 20 rows** (the cursor is the key of row 100,000, `2026-08-12 04:22:35.421993+06` and `272622`):

```sql
SELECT id, created_at, total FROM orders
WHERE (created_at, id) < ('2026-08-12 04:22:35.421993+06', 272622)
ORDER BY created_at DESC, id DESC LIMIT 20;
```
```text
Limit (actual time=0.011..0.017 rows=20.00 loops=1)
  Buffers: shared hit=22 read=1
  ->  Index Scan Backward using orders_created_at_id_idx on orders (actual time=0.010..0.015 rows=20.00 loops=1)
        Index Cond: (ROW(created_at, id) < ROW('2026-08-12 04:22:35.421993+06'::timestamp with time zone, '272622'::bigint))
```

Twenty rows, 23 pages, 0.017 ms against 70 ms; the two queries return exactly the same rows (checked with `EXCEPT`). The condition appears as `Index Cond`, which is the proof that the index did the seeking.

**The expanded form is not equivalent to the planner.** Writing the same predicate as `created_at < $1 OR (created_at = $1 AND id < $2)` is logically identical, but PostgreSQL does not derive an index range from the `OR`:

```text
Limit (actual time=34.425..34.434 rows=20.00 loops=1)
  Buffers: shared hit=100390
  ->  Index Scan Backward using orders_created_at_id_idx on orders (actual time=34.424..34.432 rows=20.00 loops=1)
        Filter: ((created_at < ...) OR ((created_at = ...) AND (id < '272622'::bigint)))
        Rows Removed by Filter: 100000
```

It walked 100,000 entries and filtered them: as expensive as `OFFSET`. Use the row-value form whenever the sort directions agree.

## Pitfalls

- No tiebreaker. Works in testing, where timestamps are distinct, then skips or repeats rows in production at exactly the moment two orders are created in the same millisecond.
- The `OR` form. Correct results, `OFFSET` performance; check for `Index Cond` versus `Filter` in the plan.
- Sorting by a column that changes. `ORDER BY updated_at` moves rows between pages while the user is paging; sort by something immutable, or accept the movement knowingly.
- A cursor that is a row number in disguise. If the token encodes "100000", it is `OFFSET` with extra steps; the token must carry the sort key values of the last row.
- Mixing directions and using the row-value comparison anyway. `(created_at, id) < ($1, $2)` is wrong for `created_at DESC, id ASC`; use the expanded form with an index declared `(created_at DESC, id ASC)`.
- Keeping the `count(*)` of the whole table on every page. The seek is constant time; the count is a full scan. Estimate it, cache it, or drop it from the design.

## Check yourself

1. Why does `OFFSET 100000` read 100,020 index entries even though an index exists on the sort column, and why does the keyset query read 20?
2. Two orders share the same `created_at`, one on each side of a page boundary. Describe what `WHERE created_at < $1` and `WHERE created_at <= $1` each get wrong, and what the fix is.
3. The planner shows the keyset predicate under `Filter` instead of `Index Cond`. What was written, and how should it be rewritten?
4. Which features of a traditional paginated UI does keyset pagination give up, and how would you provide the "previous page" link?

## Go deeper

- [Use The Index, Luke: We need tool support for keyset pagination](https://use-the-index-luke.com/no-offset) · the manifesto, with the argument against `OFFSET` in one page.
- [Use The Index, Luke: Fetching The Next Page](https://use-the-index-luke.com/sql/partial-results/fetch-next-page) · the seek method with the row-value syntax and its per-database caveats.
- [PostgreSQL: Row Constructor Comparison](https://www.postgresql.org/docs/current/functions-comparisons.html#ROW-WISE-COMPARISON) · the exact semantics of `(a, b) < (x, y)`.
- [PostgreSQL: LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html) · the documentation's own warning that rows skipped by `OFFSET` still have to be computed.

---

Part of [Databases](../README.md) · item 1.6
