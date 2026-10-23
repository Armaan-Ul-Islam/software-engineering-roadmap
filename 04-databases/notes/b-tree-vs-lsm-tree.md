# B-trees vs LSM-trees: two ways to organise data on disk

> **In one sentence:** A B-tree keeps data sorted in fixed pages that are updated in place, which favours reads; an LSM-tree collects writes in memory and appends them as sorted, immutable files that are merged in the background, which favours writes; every storage engine pays for its choice as read, write or space amplification.

**Why it matters:** The structure under a database decides what it is good at long before you tune anything. Knowing that PostgreSQL and InnoDB are B-tree engines while RocksDB and Cassandra are LSM engines tells you why one absorbs a flood of inserts gracefully and the other answers point lookups with predictable latency. Interviewers ask this to see whether you reason about trade-offs rather than product names.

## The idea

**B-tree.** A balanced tree of fixed-size pages (8 kB in PostgreSQL, 16 kB in InnoDB). Internal pages hold separator keys; leaf pages hold the keys in sorted order with either a pointer to the row (a PostgreSQL index) or the row itself (InnoDB's clustered index). A lookup descends from the root to one leaf, three or four page reads for hundreds of millions of keys, and a range scan walks the linked leaves in order. A write finds the leaf, modifies it in place and splits the page if it is full. The price is paid on writes: changing a 100-byte row dirties an 8 kB page that must eventually be written in full, random keys dirty random pages, and the write-ahead log is written as well.

**LSM-tree (log-structured merge tree).** A write is appended to a log for durability and inserted into an in-memory sorted structure, the memtable. When the memtable is full it is written out sequentially as an immutable sorted file (an SSTable). A read checks the memtable, then the SSTables from newest to oldest, using a bloom filter per file to skip those that cannot contain the key. Background *compaction* merges SSTables, dropping overwritten values and deleted keys (tombstones) and keeping the number of files a read must consult bounded. Writes are sequential and batched, so write throughput is excellent; the costs move to reads, which may consult several files, to compaction, which rewrites data repeatedly, and to disk space, which holds obsolete versions until compaction removes them.

**The three amplifications.** Write amplification is bytes written to disk per byte the application wrote; read amplification is pages read per logical read; space amplification is bytes on disk per byte of live data. No structure minimises all three. A B-tree spends write amplification to keep read amplification at one descent. An LSM-tree with levelled compaction rewrites each byte up to once per level as it moves down (the level size ratio, 10 by default in RocksDB, bounds how often) to keep space overhead small; size-tiered compaction rewrites less but can need up to twice the live data's space while merging.

| | B-tree | LSM-tree |
|---|---|---|
| Write path | Find the leaf, modify the page in place, split when full | Append to log and memtable, flush sorted files, compact later |
| Read path | One root-to-leaf descent, then neighbouring leaves | Memtable, then each level's files (bloom filters skip most) |
| Write amplification | Whole pages for small changes; random keys hurt most | Each byte rewritten roughly once per level during compaction |
| Read amplification | Low and predictable | Higher; grows with the number of files per level |
| Space amplification | Pages typically 70 to 90% full; dead versions until vacuum | Obsolete versions until compaction; small with levelled, large with size-tiered |
| Latency profile | Steady; occasional page splits | Steady until compaction falls behind, then write stalls |
| Deletes | Remove the entry | Write a tombstone; the data is gone only after compaction |
| Used by | PostgreSQL, MySQL InnoDB, SQLite, Oracle, SQL Server | RocksDB (MyRocks, CockroachDB, TiKV), LevelDB, Cassandra, ScyllaDB, HBase |

**How to choose.** You rarely pick the structure; you pick a database, and the structure comes with it. Reach for an LSM-backed store when writes dominate and arrive fast (events, metrics, messaging state, time series), when the working set exceeds memory so that sequential writes matter, and when somewhat higher and more variable read latency is acceptable. Stay with a B-tree engine when reads dominate, when point and range lookups need steady latency, when rows are updated in place many times (an LSM-tree turns each update into a new version plus compaction work), and when you want mature transactional semantics on top. Most business systems are read-heavy with moderate write rates, which is why the relational B-tree engines remain the default.

## Example: B-tree write amplification you can measure

Insert 10,000 rows into three PostgreSQL tables that differ only in their primary key, each already holding a million rows (`EXPLAIN (ANALYZE, BUFFERS)` on the `INSERT`, PostgreSQL 18):

```text
key_uuid4  (random UUID v4):       Buffers: shared hit=38933 read=1231 dirtied=1473 written=1391
key_uuid7  (time-ordered UUID v7): Buffers: shared hit=20356 dirtied=102 written=204
key_bigint (identity column):      Buffers: shared hit=30265 read=5 dirtied=85 written=167
```

The random keys landed on 1,473 different leaf pages to store 10,000 keys of 16 bytes: about 12 MB of pages dirtied for 160 kB of key data, and each of those pages will also be logged in full after the next checkpoint. The time-ordered keys went to the right edge of the tree and dirtied 102 pages. This is the B-tree's write amplification, and it is exactly what an LSM-tree avoids by never updating a page in place: the same 10,000 random keys would be sorted in memory and written once, sequentially.

The LSM-tree's bill arrives later. With a size ratio of 10 and five levels, a key written once is rewritten roughly once per level as compaction pushes it down, and a point read that misses the memtable may probe a file at each level (bloom filters make most probes a memory check rather than a disk read).

## Pitfalls

- "LSM means fast writes, full stop." Compaction is deferred work. If it cannot keep up, RocksDB and Cassandra throttle or stall writes; sizing compaction threads and disk bandwidth is part of running them.
- Forgetting that a delete is a write. Tombstones must be read and skipped until compaction removes them; deleting or expiring many rows in one partition is a classic Cassandra performance problem.
- Measuring read performance with everything in RAM. A B-tree with its pages cached has almost no read amplification; the differences appear when data is larger than memory.
- Treating PostgreSQL's MVCC as "append-only like an LSM". New row versions are written, but into heap pages that are updated in place and cleaned by `VACUUM` (see item 6.5); the trade-offs are B-tree trade-offs.
- Random UUID primary keys in a B-tree engine. The measurement above is the cost; time-ordered keys (sequences, UUID v7) avoid it (see item 8.2).

## Check yourself

1. A workload updates the same 10,000 rows thousands of times per hour. Which structure handles it with less total disk writing, and why does the answer differ from a workload that only inserts new rows?
2. Why does an LSM-tree need bloom filters while a B-tree does not?
3. Explain in one sentence each what levelled and size-tiered compaction optimise for.
4. A colleague proposes Cassandra for a system whose main operation is "read one customer with all their orders, update two fields, save". What questions would you ask before agreeing?

## Go deeper

- [Designing Data-Intensive Applications, chapter 3](https://dataintensive.net/) · the clearest explanation of both structures and of the amplification trade-offs.
- [Database Internals](https://www.databass.dev/) · part one covers B-tree variants and LSM-trees at implementation level (paid).
- [RocksDB wiki: Leveled Compaction](https://github.com/facebook/rocksdb/wiki/Leveled-Compaction) · how a production LSM engine organises its levels and what that costs.
- [CMU 15-445: Database Systems](https://15445.courses.cs.cmu.edu/) · the tree index and storage lectures, with the trade-offs made explicit.

---

Part of [Databases](../README.md) · item 2.3
