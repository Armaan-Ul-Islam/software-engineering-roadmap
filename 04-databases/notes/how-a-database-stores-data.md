# How a database stores data: pages, the buffer pool and the write-ahead log

> **In one sentence:** PostgreSQL keeps every table as a file of fixed 8 kB pages, moves those pages between disk and a shared buffer pool, and makes a commit durable by flushing a small write-ahead log record rather than the pages themselves.

**Why it matters:** Every performance question eventually comes down to pages: how many had to be read, whether they were already in memory, and how many were dirtied. `EXPLAIN (ANALYZE, BUFFERS)` reports exactly that, and it only makes sense once you know what a page and a buffer are. The same model explains why a commit is fast yet survives a crash, and what you give up when you turn `synchronous_commit` off.

## The idea

**Pages and heap files.** A PostgreSQL table is a heap: an unordered file of 8 kB pages (`block_size`), stored under the data directory as `base/<database oid>/<relfilenode>`. Each page has a small header, an array of line pointers growing from the front, and the tuples (row versions) growing from the back; the gap between them is the page's free space. A row is addressed by its `ctid`, the pair (page number, line pointer). Indexes are separate files of 8 kB pages with their own layout.

The page is the unit of I/O. To return one 64-byte row the server reads the whole 8 kB page it lives on; to change one column it eventually writes the whole page back. A table of a million 64-byte rows is about 8,400 pages with roughly 120 rows each, so a query that touches 2% of the rows at random can still touch most of the pages.

**The buffer pool.** No query reads a file directly. It asks the buffer manager for a page; if the page is in `shared_buffers` (128 MB by default, 16,384 pages) that is a *hit*, otherwise the manager evicts a rarely used buffer using a clock-sweep algorithm and *reads* the page from the operating system, which may serve it from its own page cache without touching the disk. Writers only modify the copy in the buffer pool and mark it dirty; the background writer and the checkpointer write dirty pages later, in bulk. Large sequential scans use a small ring of buffers so that one reporting query does not evict everyone else's working set.

**The write-ahead log.** Before a dirty page may be written to its file, every change made to it must be recorded in the WAL (`pg_wal/`), an append-only sequence of records addressed by a log sequence number (LSN). Committing appends a commit record and, with `synchronous_commit = on`, calls `fsync` on the WAL file before the client sees `COMMIT`. The data pages are not written at commit time at all; they may stay dirty in memory for minutes.

**Checkpoints and recovery.** Every `checkpoint_timeout` (5 minutes by default) or `max_wal_size` (1 GB) of WAL, the checkpointer writes all dirty pages and records a redo point. After a crash, recovery replays the WAL from the last redo point, bringing pages up to date with every committed change and ignoring transactions that have no commit record. Because a crash can tear an 8 kB page in the middle of a write, `full_page_writes` logs the whole page the first time it changes after each checkpoint.

So **"committed" means**: the commit record is on durable storage in the WAL. Nothing more, and nothing less.

## Example: hits, reads and pages in `EXPLAIN (ANALYZE, BUFFERS)`

A table `orders` with a million rows and a primary key (PostgreSQL 18; older versions print no `Index Searches` line).

```sql
SELECT pg_relation_filepath('orders'), pg_relation_size('orders') / 8192 AS pages;
--  base/208902/209807 | 8382

SELECT ctid, id FROM orders WHERE id IN (1, 120, 121, 500000);
--  (0,1)     | 1         first row of page 0
--  (0,120)   | 120       page 0 holds 120 rows
--  (1,1)     | 121       row 121 opens page 1
--  (4190,90) | 500000
```

```sql
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING OFF) SELECT * FROM orders WHERE id = 500000;
```

```text
Index Scan using orders_pkey on orders (actual rows=1.00 loops=1)
  Index Cond: (id = 500000)
  Index Searches: 1
  Buffers: shared read=4        -- cold: root, internal and leaf page of the index, then one heap page
```

Run it again and the last line becomes `Buffers: shared hit=4`: the four pages are now in the buffer pool. One row cost four page accesses, because the index is three levels deep and the row lives on a fifth page.

A sequential scan shows the other extreme:

```text
Aggregate (actual time=81.313..81.313 rows=1.00 loops=1)
  Buffers: shared read=8382
  ->  Seq Scan on orders (actual time=1.379..81.194 rows=2004.00 loops=1)
        Filter: (total > '499'::numeric)
        Rows Removed by Filter: 997996
```

All 8,382 pages were read to find 2,004 rows. Running it again still shows `shared hit=94 read=8288` and the same 81 ms: the table (65 MB) is larger than a quarter of `shared_buffers`, so the scan used the ring buffer and did not keep its pages, and the operating system served the "reads" from its cache. `read` means "PostgreSQL asked the OS", not "the disk was touched".

The WAL side of one insert:

```sql
SELECT pg_current_wal_lsn();                                  -- 0/75F26CD8
INSERT INTO orders (customer_id, status, total, created_at) VALUES (1, 'pending', 10.00, now());
SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/75F26CD8');   -- 256
```

A row, its primary-key entry and the commit record are 256 bytes of sequential WAL. The 8 kB heap page and the 8 kB index leaf it dirtied will be written by a later checkpoint.

## Pitfalls

- Reading `shared read` as disk I/O. It is a request to the OS; set `track_io_timing = on` to get an `I/O Timings` line and learn whether the request was slow.
- Confusing `fsync = off` with `synchronous_commit = off`. The first risks a corrupt cluster after a crash; the second only risks losing the last few hundred milliseconds of commits (at most three times `wal_writer_delay`, which is 200 ms by default) while the database stays consistent. The second is a legitimate setting for data you can replay.
- Expecting a commit to write the table. It writes the WAL. A crash a millisecond after `COMMIT` loses nothing; recovery replays the record.
- Checkpoint storms. A small `max_wal_size` on a write-heavy server means frequent checkpoints, each followed by a burst of full-page writes that inflates WAL volume. Watch `pg_stat_checkpointer`: `num_requested` growing faster than `num_timed` means checkpoints are forced by WAL volume.
- Benchmarking with a warm cache and deploying to a cold one. The first execution reads, the next hits; measure both, and use the `pg_buffercache` extension to see what is resident.
- Wide rows. Fewer rows per page means more pages per query; a table with a dozen rarely used `text` columns makes every scan of the hot columns slower. TOAST only moves values out of line when a row exceeds about 2 kB (see item 2.4).

## Check yourself

1. A query returns one row and reports `Buffers: shared hit=4`. Where did each of the four page accesses go?
2. After `COMMIT` returns, the server loses power before the next checkpoint. Which file contains the committed row, and how does it reappear in the table?
3. Why does the second run of a large sequential scan still report `read` instead of `hit`, and why is it not slower?
4. `synchronous_commit = off` is set for a session that records analytics events. What exactly can be lost, and what cannot?

## Go deeper

- [The Internals of PostgreSQL: Database Cluster, Databases, and Tables](https://www.interdb.jp/pg/pgsql01.html) · the file layout and page structure with diagrams.
- [The Internals of PostgreSQL: Buffer Manager](https://www.interdb.jp/pg/pgsql08.html) · how pages move in and out of `shared_buffers`, including the ring buffers.
- [The Internals of PostgreSQL: Write Ahead Logging](https://www.interdb.jp/pg/pgsql09.html) · WAL records, checkpoints and recovery step by step.
- [PostgreSQL: Reliability and the Write-Ahead Log](https://www.postgresql.org/docs/current/wal-intro.html) · what the server promises and which settings weaken it.
- [PostgreSQL: Database Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html) · the exact layout behind `ctid`, line pointers and free space.
- [CMU 15-445: Database Systems](https://15445.courses.cs.cmu.edu/) · the storage and buffer pool lectures generalise this to every database.

---

Part of [Databases](../README.md) · items 2.1, 2.2
