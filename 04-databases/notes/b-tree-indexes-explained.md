# B-tree indexes explained: walking the tree and designing the key

> **In one sentence:** A B-tree index is a sorted copy of some columns with a pointer to each row, so a lookup is a short descent from the root to one leaf followed by a walk along the leaves, and the index helps only when the query's conditions match the order the index is sorted in.

**Why it matters:** Most slow queries in a transactional system are either missing an index or have one whose column order does not fit the query. The planner's choices (`Index Scan`, `Bitmap Heap Scan`, `Index Only Scan`, or a `Seq Scan` despite your index) all follow from how the tree is walked and how many table pages must be visited afterwards. "Why does column order in a composite index matter" is a standard interview question because the answer shows whether you have read a plan.

## The idea

**Anatomy.** A B-tree index is a balanced tree of 8 kB pages. The root and internal pages hold separator keys; the leaf pages hold every indexed key in sorted order with the `ctid` (page, item) of its row, and are linked to their neighbours. On a million-row `orders` table, an index on `(customer_id, status, created_at)` is 4,980 pages and three levels deep (`bt_metap` reports `level 2`), so any key is reached in three page reads.

**Equality lookup.** `WHERE id = 500000` descends root, internal and leaf page, finds the entry, then fetches the heap page it points to: `Buffers: shared hit=4` in `EXPLAIN (ANALYZE, BUFFERS)`.

**Range lookup.** `WHERE created_at >= X` descends to the first matching leaf entry and walks right along the leaf chain until an entry fails the condition; the cost grows with the matching entries and the heap pages they point to.

**Reaching the table.** For a few rows the planner uses an **Index Scan**, fetching each row as its entry is found. For many rows it uses a **Bitmap Index Scan** to collect all matching `ctid`s and a **Bitmap Heap Scan** to visit the heap pages in physical order, each once. When the index holds every column the query needs, an **Index Only Scan** skips the heap, except for visibility: the *visibility map* marks heap pages whose rows are all visible to every transaction, and for any other page the scan fetches the heap page anyway (`Heap Fetches` in the plan). `VACUUM` maintains the map, so index-only scans degrade on tables that are updated and not vacuumed.

**Composite indexes.** The index is sorted by the first column, then by the second within equal first values, and so on, like a phone book sorted by surname and then first name. Two rules follow:

1. **Leftmost prefix.** A query must constrain the first column or the tree cannot be descended; `WHERE status = 'cancelled'` cannot use `(customer_id, status, created_at)`. (PostgreSQL 18 adds a skip scan that helps only when the missing leading column has very few distinct values; with 48,000 customers it does not apply.)
2. **Equality first, then range.** Once a column is used with a range condition, the entries matching the remaining columns are no longer contiguous, so those columns can only filter entries, not narrow the walk. Put the columns compared with `=` first and the range column last.

**Variants.** A *covering* index adds payload columns with `INCLUDE (total)` so more queries become index-only without widening the key; a *partial* index covers only the rows matching a `WHERE` clause; a *unique* index enforces primary keys and `UNIQUE` constraints; an *expression* index indexes `lower(email)` rather than a column (item 3.5).

## Example: one table, five queries, the index that serves each

```sql
CREATE TABLE orders (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customer (id),
    status      text NOT NULL,
    total       numeric(12,2) NOT NULL,
    created_at  timestamptz NOT NULL
);
-- 1,000,000 rows, 50,000 customers; status: 70% shipped, 20% paid, 8% pending, 2% cancelled
CREATE INDEX orders_customer_status_created_idx ON orders (customer_id, status, created_at);
```

**Q1, a customer's shipped orders in a period** uses all three columns (PostgreSQL 18, planning lines removed):

```text
Bitmap Heap Scan on orders (actual rows=2.00 loops=1)
  Recheck Cond: ((customer_id = 42) AND (status = 'shipped'::text) AND (created_at >= ...))
  Buffers: shared hit=5
  ->  Bitmap Index Scan on orders_customer_status_created_idx (actual rows=2.00 loops=1)
        Index Cond: ((customer_id = 42) AND (status = 'shipped'::text) AND (created_at >= ...))
```

**Q2, cancelled orders of the last 30 days** has no `customer_id`, so the composite index is useless and the planner reads all 8,382 pages (`Seq Scan ... Rows Removed by Filter: 999189`). Two candidate indexes, with the query written as `SELECT count(*)` so that both plans are index-only:

```text
Index Only Scan using orders_status_created_idx    -- (status, created_at)    Buffers: shared hit=1 read=7
Index Only Scan using orders_created_status_idx    -- (created_at, status)    Buffers: shared hit=4 read=162
```

Both plans list both conditions under `Index Cond` and both return 812 rows, but equality-then-range reads 8 pages where range-then-equality reads 166: the second index had to walk every entry of the last 30 days and discard the 98% that were not cancelled.

**Q3, index-only scans and the visibility map:**

```sql
EXPLAIN (ANALYZE, BUFFERS) SELECT status, created_at FROM orders WHERE customer_id = 42;
--  Index Only Scan ... Heap Fetches: 0
UPDATE orders SET total = total + 0 WHERE customer_id = 42;
--  Index Only Scan ... Heap Fetches: 27      the pages holding those rows lost their all-visible bit
VACUUM orders;
--  Index Only Scan ... Heap Fetches: 0
```

**Q4, the pending-orders queue** `WHERE status = 'pending' ORDER BY created_at LIMIT 100` is served by a partial index 17 times smaller than the equivalent full index (1,768 kB against 30 MB), which therefore stays in cache:

```sql
CREATE INDEX orders_pending_created_idx ON orders (created_at) WHERE status = 'pending';
```

**Q5, when the index does not help.** For `status = 'shipped'` (70% of rows) the planner ignores `(status, created_at)` and scans the table, correctly: an index pays off only when it expects few enough rows that the index path beats reading everything. Less obviously, `status = 'cancelled'` matches only 2% of rows, yet the bitmap plan touched 7,632 of the 8,382 heap pages (`Heap Blocks: exact=7632`). With 120 rows per page, nearly every page holds a cancelled order, so the index saved almost nothing. Selectivity is about pages, not rows.

**The cost of carrying indexes.** Inserting 1,000 rows with the two secondary indexes present dirtied 921 pages; with only the primary key, 12. Every index is maintained on every insert and delete and on every update of an indexed column, and such an update also loses the heap-only-tuple optimisation that would otherwise keep the new row version on the same page. `idx_scan = 0` in `pg_stat_user_indexes` after weeks of production traffic marks an index you pay for and never use.

## Pitfalls

- Indexing every column separately. Three single-column indexes are not `(customer_id, status, created_at)`; the planner can combine their bitmaps, but slower, and the equality-then-range benefit is lost.
- Putting the range column first because "we always filter by date". That index serves `WHERE created_at BETWEEN ...` alone and walks far too much for every query that also has an equality.
- Expecting index-only scans on a busy table without vacuum. `Heap Fetches` climbs as pages lose their all-visible bit; autovacuum must be allowed to keep up (see item 6.5).
- Ignoring `ORDER BY`. An index in the same order as `ORDER BY created_at DESC` lets the planner stop after `LIMIT n` rows instead of sorting everything (the basis of keyset pagination, item 1.6).

## Check yourself

1. Why can `(customer_id, status, created_at)` not serve `WHERE status = 'cancelled' AND created_at > now() - interval '30 days'`, and which single index would serve both that query and `WHERE status = 'pending' ORDER BY created_at`?
2. Two indexes contain the same two columns in different orders and both show both conditions under `Index Cond`. How do you tell from the plan which one is doing the real work?
3. An index-only scan reports `Heap Fetches: 4000` on a table that was vacuumed last week. What happened in between, and what would you check?
4. A searched value occurs in 1% of rows, spread evenly over pages of 120 rows. Roughly what fraction of pages does an index scan touch, and what does that imply for the plan?

## Go deeper

- [Use The Index, Luke: Anatomy of an SQL Index](https://use-the-index-luke.com/sql/anatomy) · the tree, the leaf chain and why lookups are logarithmic, in plain language.
- [Use The Index, Luke: Concatenated Indexes](https://use-the-index-luke.com/sql/where-clause/the-equals-operator/concatenated-keys) · column order with the phone-book picture, then [Searching for Ranges](https://use-the-index-luke.com/sql/where-clause/searching-for-ranges) for equality before range.
- [PostgreSQL: Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) and [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html) · the precise rules, including the visibility map.
- [PostgreSQL: Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) · when a partial index is right, and the common mistakes.
- [The Internals of PostgreSQL: HOT and Index-Only Scans](https://www.interdb.jp/pg/pgsql07.html) · why updates of indexed columns are expensive and how the visibility map works.

---

Part of [Databases](../README.md) · items 3.1, 3.2, 3.3
