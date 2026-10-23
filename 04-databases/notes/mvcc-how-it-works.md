# MVCC: how PostgreSQL lets readers and writers ignore each other

> **In one sentence:** Every update in PostgreSQL writes a new row version instead of overwriting the old one, each version carries the transaction that created it (`xmin`) and the one that deleted it (`xmax`), and every statement sees only the versions its snapshot says were committed when it started; the price is dead versions that `VACUUM` must remove before they bloat the table or exhaust the transaction ID space.

**Why it matters:** MVCC is why a long report does not block the checkout path, and also why one forgotten open transaction can make every table in the database grow. Bloat, autovacuum tuning and the wraparound emergency all follow from the same design, and "why does an idle connection slow down an unrelated table" separates people who know the model from people who know the acronym.

## The idea

**Versions.** A table page holds tuples, and each tuple is one version of a row. Its header records `xmin`, the ID of the transaction that inserted it, and `xmax`, the ID of the transaction that deleted or updated it (zero while the version is live). An `UPDATE` does not change the old tuple's data: it writes a new tuple with `xmin` set to the current transaction and sets `xmax` on the old one, which now points to its successor. A `DELETE` only sets `xmax`.

**Snapshots.** When a statement starts (Read Committed) or a transaction starts (Repeatable Read and Serializable), it takes a snapshot: the lowest transaction ID still in progress, the next ID to be assigned, and the IDs in progress between them. A tuple is visible if its `xmin` committed before the snapshot and its `xmax` is zero, aborted, or still in progress according to the snapshot. Nothing is locked to read: the reader consults the snapshot and the commit log, and the writer leaves the old version in place for readers that still need it. Writers wait only for other writers of the *same row*, because `xmax` doubles as the row lock.

**Dead tuples and vacuum.** A version whose `xmax` committed before every current snapshot is dead: no transaction can ever see it again. Dead tuples stay in the page until `VACUUM` removes them, records the freed space in the free space map and marks fully visible pages in the visibility map (which index-only scans depend on, item 3.1). Autovacuum runs it once a table has changed by `autovacuum_vacuum_threshold` plus `autovacuum_vacuum_scale_factor` times its row count (50 rows plus 20% by default). `VACUUM` makes space reusable inside the table but does not shrink the file, except for empty pages at the very end; only `VACUUM FULL` (a rewrite under an exclusive lock) or an online tool such as `pg_repack` returns space to the operating system.

**Bloat.** Dead space that `VACUUM` has not reclaimed, or has reclaimed but the file never shrank. A heavily updated, rarely vacuumed table can be many times its live size, and its indexes bloat too, since every non-HOT update adds index entries. Updates that change no indexed column and find room on the same page take the heap-only-tuple path (HOT) and skip the indexes entirely, which is why a `fillfactor` below 100 helps hot tables.

**Transaction ID wraparound.** Transaction IDs are 32-bit and compared in a circle: an ID counts as "in the past" if it is within two billion of the current one. A tuple whose `xmin` fell two billion transactions behind would suddenly look like it was written in the future and vanish. `VACUUM` prevents this by *freezing* old tuples, marking them visible to everyone regardless of ID. When a table's oldest unfrozen ID approaches `autovacuum_freeze_max_age` (200 million), autovacuum forces a vacuum whether you like it or not; if even that cannot finish, the server eventually refuses new writes. `age(datfrozenxid)` in `pg_database` says how close you are.

**Why one long transaction hurts everyone.** `VACUUM` may remove a dead tuple only when no snapshot can still see it, and that horizon is set by the oldest running transaction in the database (`backend_xmin` in `pg_stat_activity`). A session that opened a transaction an hour ago and went idle pins the horizon for every table: dead tuples accumulate everywhere, index-only scans start fetching heap pages, and freezing cannot advance. The culprit is usually a connection left `idle in transaction` by an application.

## Example: versions, dead tuples and a blocked vacuum

PostgreSQL 18 with the `pageinspect` and `pgstattuple` extensions; autovacuum disabled on the table so that only our commands change it.

```sql
CREATE TABLE account (id int PRIMARY KEY, balance numeric NOT NULL) WITH (autovacuum_enabled = off);
INSERT INTO account VALUES (1, 100), (2, 100);
UPDATE account SET balance = balance - 30 WHERE id = 1;

SELECT ctid, xmin, xmax, id, balance FROM account ORDER BY id;
--  (0,3) | 60840 |    0 |  1 |      70        the new version, written by transaction 60840
--  (0,2) | 60839 |    0 |  2 |     100

SELECT lp, t_xmin, t_xmax, t_ctid FROM heap_page_items(get_raw_page('account', 0));
--   1 |  60839 |  60840 | (0,3)      the old version of row 1: xmax set, pointing at its successor
--   2 |  60839 |      0 | (0,2)
--   3 |  60840 |      0 | (0,3)
```

Now session 2 opens a transaction, reads row 1 (70) and goes idle. Session 1 runs a thousand single-statement updates on the row, then looks around:

```sql
SELECT pg_current_snapshot();                       -- 61841:61841:   nothing in progress from our side
SELECT pid, state, backend_xmin FROM pg_stat_activity WHERE backend_xmin IS NOT NULL;
--  12806 | active | 60841                            session 2 still holds a snapshot from before the updates
SELECT n_live_tup, n_dead_tup, n_tup_hot_upd FROM pg_stat_user_tables WHERE relname = 'account';
--           2 |       1000 |          996
SELECT pg_size_pretty(pg_relation_size('account'));  -- 48 kB: six pages for two live rows

VACUUM (VERBOSE) account;
--  tuples: 0 removed, 1002 remain, 1000 are dead but not yet removable
--  removable cutoff: 60841, which was 1000 XIDs old when operation ended
```

Session 2 reads row 1 again inside its transaction and still sees 70; after it commits it sees 1070. Then:

```sql
VACUUM (VERBOSE) account;
--  tuples: 1000 removed, 2 remain, 0 are dead but not yet removable
--  visibility map: 6 pages set all-visible
SELECT pg_size_pretty(pg_relation_size('account'));  -- still 48 kB; space is reusable, not returned
VACUUM FULL account;
SELECT pg_size_pretty(pg_relation_size('account'));  -- 8192 bytes
```

The thousand dead versions were untouchable for as long as one idle transaction could, in principle, still need them. Multiply by every table in a busy database and an afternoon.

## Pitfalls

- Connections left `idle in transaction`. An ORM that opens a transaction for a read and never commits, or a developer's `psql` with a forgotten `BEGIN`, pins the horizon. Set `idle_in_transaction_session_timeout` in production.
- Throttling autovacuum on a hot table because "it uses I/O". The I/O is deferred, not saved, and the eventual vacuum is larger; instead make it more aggressive per table, `ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = 0.01)` for tables with millions of rows.
- Expecting `DELETE` to free disk space. It creates dead tuples; `VACUUM` makes the space reusable; only `VACUUM FULL` or `pg_repack` shrinks the file.
- Running long reports on the primary to spare the replicas. They pin the horizon just like any other transaction; and a replica with `hot_standby_feedback = on` passes its own horizon back to the primary (item 7.1).
- Ignoring wraparound warnings in the log. "Database must be vacuumed within N transactions" is the last warning before the server stops accepting writes.

## Check yourself

1. Why does a `SELECT` in one session never wait for an `UPDATE` in another, and what is the one situation in which two sessions do wait for each other?
2. A table has 2 million live rows and 30 million dead ones, and `VACUUM VERBOSE` says they are "dead but not yet removable". Which view and column identify the cause?
3. After deleting 90% of a large table and running `VACUUM`, the file is the same size. Why, and what are the two ways to shrink it?
4. What does freezing a tuple do, and why does the database stop accepting writes if freezing cannot keep up?

## Go deeper

- [PostgreSQL: Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html) · the official model, short and precise.
- [PostgreSQL: Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) · dead tuples, the visibility map, freezing and wraparound, with the settings that control them.
- [The Internals of PostgreSQL: Concurrency Control](https://www.interdb.jp/pg/pgsql05.html) · tuple headers, snapshots and visibility rules with diagrams, then [Vacuum Processing](https://www.interdb.jp/pg/pgsql06.html) for what `VACUUM` actually does to a page.
- [Vlad Mihalcea: How does MVCC work](https://vladmihalcea.com/how-does-mvcc-multi-version-concurrency-control-work/) · the same ideas from the application side.
- [PostgreSQL: pageinspect](https://www.postgresql.org/docs/current/pageinspect.html) · the extension used above to look at raw tuple headers.

---

Part of [Databases](../README.md) · items 6.1, 6.5
