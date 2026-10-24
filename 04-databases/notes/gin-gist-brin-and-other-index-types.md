# GIN, GiST, BRIN and hash: the other index types and what they cost

> **In one sentence:** A B-tree answers equality and range questions about whole values; GIN indexes the elements inside a value (the keys of a `jsonb` document, the members of an array, the words of a text), GiST answers "overlaps, contains, is near" for ranges and geometry and backs exclusion constraints, BRIN stores only a minimum and maximum per block range and is therefore tiny but useful only when the table's physical order follows the column, and hash indexes do equality alone; every one of them is paid for on every write, so build and rebuild them `CONCURRENTLY` and watch for the invalid index a failed build leaves behind.

**Why it matters:** `WHERE attributes @> '{"color": "red"}'` and `WHERE tags @> '{sale}'` cannot use a B-tree at all, and a B-tree on the timestamp of a terabyte of append-only events costs tens of gigabytes that a BRIN index replaces with kilobytes. Choosing the index type is half of indexing `jsonb`, arrays, ranges and time series. The other half is operational: `CREATE INDEX CONCURRENTLY` can fail and leave an index the planner ignores but every write maintains, and a bloated index never shrinks on its own.

## The idea

| Type | Serves | Typical use | Cost profile |
|---|---|---|---|
| B-tree | `=`, `<`, `>`, `BETWEEN`, `LIKE 'prefix%'`, `ORDER BY` | nearly everything (items 3.1 to 3.3) | one entry per row |
| Hash | `=` only | equality on long values (URLs, tokens) | a 4-byte hash per row, so small for long keys; no ordering, no `UNIQUE` |
| GIN | `@>`, `?`, `&&`, `@@` (full text), trigram `LIKE '%x%'` | `jsonb`, arrays, `tsvector`, `pg_trgm` | one entry per element; slow to update, so new entries are buffered in a pending list |
| GiST | `&&`, `@>`, `<@`, `<->` (nearest), geometry | ranges, exclusion constraints, PostGIS | lossy, so matches are rechecked against the heap |
| BRIN | `=`, `<`, `>` | huge tables whose physical order follows the column | kilobytes; near-zero write cost; useless without correlation |

**GIN** (generalised inverted index) keeps, for every element, a list of the rows that contain it, which is why it can answer containment. For `jsonb`, the default `jsonb_ops` class indexes every key and value and serves `@>`, `?`, `?|`, `?&` and the jsonpath operators `@?` and `@@`; `jsonb_path_ops` indexes hashes of complete paths, is smaller and faster for `@>`, and cannot answer key-existence questions. Neither serves `attributes ->> 'color' = 'red'`; that is an ordinary B-tree on the expression `(attributes ->> 'color')`. Because inserting one row can mean updating hundreds of posting lists, GIN buffers new entries in a pending list (`fastupdate`, up to `gin_pending_list_limit`, 4 MB by default) that `VACUUM` merges into the main structure; every query has to scan the pending list too, so a table with many inserts and no vacuum gets slower reads as well as slower writes.

**GiST** is a balanced tree in which each inner entry holds a predicate covering its subtree, such as a bounding box or a range. It serves `&&` (overlaps), `@>` and `<@` on ranges and geometry, nearest-neighbour search with `ORDER BY location <-> point`, and it is the structure behind `EXCLUDE USING gist` (item 8.3); `btree_gist` adds scalar equality so that a constraint can combine `room_id WITH =` and `during WITH &&`. `pg_trgm` offers both GIN and GiST classes: GIN for `LIKE '%infix%'` lookups, GiST when you also want ordering by similarity.

**BRIN** (block range index) stores the minimum and maximum of the column for each range of 128 pages (`pages_per_range`). A query reads that summary, skips the ranges that cannot match, and scans the rest page by page, rechecking every row. It works when `pg_stats.correlation` for the column is near 1 or -1: append-only tables written in time order. Updates and out-of-order inserts widen the ranges until every range matches everything, and then the planner stops using it. New pages are summarised by `VACUUM` or `brin_summarize_new_values()`, not at insert time.

**Hash** indexes store a 4-byte hash per entry regardless of key length, so they are much smaller than a B-tree on long text; they serve only `=`, cannot enforce uniqueness, cannot be multi-column and have been crash-safe since PostgreSQL 10.

**What every index costs.** Each insert writes every index; each update of an indexed column writes every index and loses the heap-only-tuple shortcut (item 6.5). Deleting or updating leaves dead entries that `VACUUM` removes, but a leaf page that is 10% full stays 10% full: that is bloat, measured with `pgstatindex(...).avg_leaf_density`, and only `REINDEX` compacts it. `REINDEX INDEX CONCURRENTLY` (PostgreSQL 12 or later) builds a replacement, swaps it in and drops the old one without blocking writes.

**`CREATE INDEX CONCURRENTLY`.** A plain `CREATE INDEX` blocks every write to the table for the whole build. `CONCURRENTLY` scans the table twice, waits for transactions that might still see rows it has not indexed, and lets writes continue; it takes longer, it cannot run inside a transaction block (so a migration tool must run it outside one), and it waits for long-running transactions to finish before it can complete. If it fails, because a `UNIQUE` build finds a duplicate, because it is cancelled, or because of a deadlock, the index stays in the catalog marked `INVALID`: the planner never uses it, every write still maintains it, and a second `CREATE INDEX` with the same name fails because it exists. The fix is `DROP INDEX CONCURRENTLY` and a retry, or `REINDEX INDEX CONCURRENTLY`. `pg_stat_progress_create_index` shows how far a build has got.

## Example: `jsonb` containment before and after a GIN index

A `product` table with 300,000 rows (PostgreSQL 18), each with `{"color": ..., "size": ..., "weight_g": ..., "brand": "brand-N"}` and two tags:

```sql
CREATE TABLE product (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, attributes jsonb NOT NULL, tags text[] NOT NULL);
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF, SUMMARY OFF)
SELECT id FROM product WHERE attributes @> '{"brand": "brand-17", "color": "red"}';
```
```text
Seq Scan on product (actual rows=160.00 loops=1)
  Filter: (attributes @> '{"brand": "brand-17", "color": "red"}'::jsonb)
  Rows Removed by Filter: 299840
  Buffers: shared read=6212
```

```sql
CREATE INDEX product_attributes_gin ON product USING gin (attributes);
```
```text
Bitmap Heap Scan on product (actual rows=160.00 loops=1)
  Recheck Cond: (attributes @> '{"brand": "brand-17", "color": "red"}'::jsonb)
  Heap Blocks: exact=160
  Buffers: shared hit=191 read=151
  ->  Bitmap Index Scan on product_attributes_gin (actual rows=160.00 loops=1)
        Index Cond: (attributes @> '{"brand": "brand-17", "color": "red"}'::jsonb)
        Buffers: shared hit=182
```

6,212 pages became 342, and the warm query takes 1.8 ms. The sizes: table 49 MB, `jsonb_ops` index 5,640 kB, the same index with `jsonb_path_ops` 4,320 kB, the primary key's B-tree 6,600 kB. Two limits showed up in the same session. `WHERE attributes ->> 'color' = 'red'` still produced a `Seq Scan` with the GIN index present. And a GIN index on `tags` answered `tags @> ARRAY['tag-7']` from 6 index pages, but the 11,770 matching rows were spread over 5,334 of the table's 6,212 heap pages, so the index saved almost nothing: selectivity is about pages, not rows (item 3.1).

## Example: BRIN on a timestamped events table

1,500,000 events inserted in time order, 110 MB:

```sql
CREATE TABLE event (id bigint GENERATED ALWAYS AS IDENTITY, occurred_at timestamptz NOT NULL, device_id int NOT NULL, payload text NOT NULL);
SELECT correlation FROM pg_stats WHERE tablename = 'event' AND attname = 'occurred_at';   -- 1
CREATE INDEX event_occurred_brin  ON event USING brin (occurred_at);
CREATE INDEX event_occurred_btree ON event (occurred_at);
SELECT pg_size_pretty(pg_relation_size('event_occurred_brin')), pg_size_pretty(pg_relation_size('event_occurred_btree'));
--  24 kB | 32 MB
```

One day of events (17,280 rows) through the BRIN index:

```text
Bitmap Heap Scan on event (actual rows=17280.00 loops=1)
  Recheck Cond: ((occurred_at >= '2026-02-10 00:00:00+00'::timestamp with time zone) AND (occurred_at < ...))
  Rows Removed by Index Recheck: 10112
  Heap Blocks: lossy=256
  Buffers: shared hit=261
  ->  Bitmap Index Scan on event_occurred_brin (actual rows=2560.00 loops=1)
        Buffers: shared hit=5
```

Two block ranges, 256 pages, read in full and rechecked; the B-tree answered the same query from 213 pages. A thousandth of the size for a fifth more I/O. Then the same data copied in random order (`CREATE TABLE event_shuffled AS SELECT * FROM event ORDER BY random()`), correlation -0.005: with a BRIN index on it the planner chose a `Seq Scan` over all 14,080 pages, because every block range now spans the whole three months.

## Example: hash, an invalid index, and bloat

300,000 URLs of about a hundred characters: the B-tree on `url` is 49 MB, the hash index 8,208 kB, `WHERE url = $1` uses the hash index (`Bitmap Index Scan on link_url_hash`) and `WHERE url > $1` cannot (`Seq Scan`).

```sql
CREATE UNIQUE INDEX CONCURRENTLY account_email_key ON account (email);
-- ERROR:  could not create unique index "account_email_key"
-- DETAIL:  Key (email)=(user1@example.com) is duplicated.
\d account
--     "account_email_key" UNIQUE, btree (email) INVALID
EXPLAIN (COSTS OFF) SELECT id FROM account WHERE email = 'user5@example.com';
--  Seq Scan on account
DROP INDEX CONCURRENTLY account_email_key;
BEGIN;
CREATE INDEX CONCURRENTLY account_email_idx ON account (email);
-- ERROR:  CREATE INDEX CONCURRENTLY cannot run inside a transaction block
```

```sql
SELECT leaf_pages, avg_leaf_density FROM pgstatindex('account_pkey');   --  274 | 89.78     2208 kB
DELETE FROM account WHERE id % 10 <> 0;
VACUUM account;
SELECT leaf_pages, avg_leaf_density FROM pgstatindex('account_pkey');   --  274 | 9.2       2208 kB
REINDEX INDEX CONCURRENTLY account_pkey;
SELECT leaf_pages, avg_leaf_density FROM pgstatindex('account_pkey');   --   28 | 87.86      240 kB
```

Ninety percent of the rows were deleted and vacuumed, and the index kept all 274 leaf pages at 9% density until the rebuild.

## Pitfalls

- GIN for `->>` equality. The index is there, the plan says `Seq Scan`; the operator is not one GIN supports. Index the expression with a B-tree, or rewrite the condition as containment.
- `jsonb_path_ops` when you need `?`. Smaller and faster for `@>`, but a key-existence query cannot use it.
- BRIN on a table that is updated or loaded out of order. Check `pg_stats.correlation` before creating it and after a bulk load, and expect `Rows Removed by Index Recheck` to be large even when it works.
- Forgetting that an `INVALID` index exists. Writes pay for it indefinitely; look for `indisvalid = false` in `pg_index` after any failed or cancelled concurrent build, and in migration logs.
- `CREATE INDEX CONCURRENTLY` inside a migration transaction. It refuses to run; the migration tool must execute it outside a transaction, and the build then waits for every long-running transaction in the database.
- Trusting `VACUUM` to shrink an index. It frees entries, not pages; a mostly-deleted or heavily updated index needs `REINDEX INDEX CONCURRENTLY`.
- Indexing a GIN-heavy table and then loading it in bulk. Drop the GIN index, load, recreate: building once is far cheaper than maintaining the pending list through millions of inserts.

## Check yourself

1. Which index type serves `WHERE attributes @> '{"brand": "x"}'`, why can the same index not serve `WHERE attributes ->> 'brand' = 'x'`, and what index would?
2. A 2 TB events table receives rows in time order and is queried by day. Compare a B-tree and a BRIN index on `occurred_at` in size, I/O per query and what happens after a bulk backfill of old data.
3. A deployment ran `CREATE UNIQUE INDEX CONCURRENTLY`, which failed on a duplicate. What state is the table in now, what does it cost, and what are the two ways to fix it?
4. `pgstatindex` reports `avg_leaf_density` of 12% on a primary key after a large purge. What happened, why did `VACUUM` not help, and which command fixes it without blocking writers?

## Go deeper

- [PostgreSQL: Index Types](https://www.postgresql.org/docs/current/indexes-types.html) · the operators each type supports, in one page.
- [PostgreSQL: GIN Indexes](https://www.postgresql.org/docs/current/gin.html), [GiST Indexes](https://www.postgresql.org/docs/current/gist.html) and [BRIN Indexes](https://www.postgresql.org/docs/current/brin.html) · the internals chapters, including the GIN pending list and BRIN summarisation.
- [PostgreSQL: jsonb Indexing](https://www.postgresql.org/docs/current/datatype-json.html#JSON-INDEXING) · `jsonb_ops` versus `jsonb_path_ops` with examples of which queries each serves.
- [PostgreSQL: Building Indexes Concurrently](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY) · the exact procedure, the invalid-index failure mode and its remedies.
- [PostgreSQL: REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) · `CONCURRENTLY`, what it locks and what it leaves behind if interrupted.
- [PostgreSQL: pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) · `pgstatindex` and the other functions used to measure bloat.

---

Part of [Databases](../README.md) · items 3.4, 3.6
