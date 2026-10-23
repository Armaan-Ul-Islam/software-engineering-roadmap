# Replication lag and read-your-writes

> **In one sentence:** A PostgreSQL replica replays the primary's write-ahead log and is therefore always some distance behind; asynchronous replication keeps commits fast and accepts that distance, synchronous replication makes every commit wait for the replica, and an application that reads from replicas must either tolerate the gap or route around it.

**Why it matters:** Read replicas are the first scaling step most teams take, and the first bug they get is a user who saves a form and sees the old value on the next page. The same lag decides how many committed transactions a failover loses. "A user updates their profile and the next request shows the old data; what happened?" is a question every backend developer should be able to answer in one breath.

## The idea

**Streaming replication.** The WAL (item 2.2) is already a complete record of every change, so a standby is built by taking a base backup (`pg_basebackup`) and then receiving WAL continuously over a replication connection: the primary's *walsender* streams records, the standby's *walreceiver* writes and flushes them, and the standby's startup process replays them into its own pages. With `hot_standby = on` (the default) the standby answers read-only queries while replaying. Logical replication is a different tool: it decodes WAL into row changes for selected tables and can cross versions, at the cost of not copying everything.

**Measuring lag.** The primary's `pg_stat_replication` shows, for each standby, how far the stream has got: `sent_lsn`, `write_lsn`, `flush_lsn` and `replay_lsn`, with `write_lag`, `flush_lag` and `replay_lag` as times. On the standby, `pg_last_wal_receive_lsn()`, `pg_last_wal_replay_lsn()` and `pg_last_xact_replay_timestamp()` give the same picture from the other side. Lag in bytes (an LSN difference) is always meaningful; lag in seconds is only meaningful while the primary is writing.

**Asynchronous versus synchronous.** By default a commit waits only for the primary's own WAL flush; the standby catches up when it can. If the primary is lost and the standby is promoted, transactions the standby had not received are gone, although they were durable on the primary (item 5.1). Setting `synchronous_standby_names` makes the commit also wait for one or more standbys, and `synchronous_commit` chooses how far they must have got: `remote_write` (received and handed to the standby's operating system), `on` (flushed to the standby's disk) or `remote_apply` (replayed, so a query on the standby sees the commit). The price is a network round trip plus standby I/O on every commit, and a dependency: if the only synchronous standby disappears, commits hang until it returns or the configuration changes, which is why production setups name several candidates (`FIRST 1 (a, b)` or `ANY 1 (a, b)`).

**The anomalies.** With asynchronous replicas, a read routed to a standby sees a past state of the database. Two guarantees break in ways users notice: *read-your-writes* (you save, then read from a replica that has not replayed your commit) and *monotonic reads* (two consecutive reads hit two replicas with different lag, so the second shows an older state than the first). Both are "session guarantees" in the consistency literature: nobody expects a replica to be current, but everybody expects their own session to make sense.

**Routing reads safely.** The strategies, from simplest to most precise:

1. Send only known-safe queries to replicas: reports, search, dashboards, pages where seconds of staleness are harmless. Every write, and every read in the same request as a write, goes to the primary.
2. Stick a session to the primary for a short window after it writes (a flag with a timestamp in the session or a cookie), chosen to be longer than the lag you normally observe.
3. Carry an LSN token: after a commit, record `pg_current_wal_lsn()`; a replica is safe for that session once `pg_last_wal_replay_lsn()` on it is at least the token, otherwise wait briefly or use the primary. This is exact, not a guess.
4. Route a given session to the same replica for monotonic reads.
5. Use `synchronous_commit = remote_apply` with a synchronous standby when every read anywhere must see every committed write, and accept the commit latency.

## Example: a local replica, a stale read, and the token check

A streaming replica built with `pg_basebackup -R` from a PostgreSQL 18 primary and started on another port.

```sql
-- primary
SELECT state, sent_lsn, replay_lsn, write_lag, flush_lag, replay_lag, sync_state FROM pg_stat_replication;
--  streaming | 0/A404C8C0 | 0/A404C8C0 | 00:00:00.000113 | 00:00:00.000114 | 00:00:00.000137 | async

CREATE TABLE replica_demo (id int PRIMARY KEY, note text NOT NULL);
INSERT INTO replica_demo VALUES (1, 'first');
SELECT pg_current_wal_lsn();                       -- 0/A4053EC0

-- replica, a moment later
SELECT * FROM replica_demo;                        -- 1 | first
SELECT pg_last_wal_replay_lsn();                   -- 0/A4053EC0: caught up
INSERT INTO replica_demo VALUES (2, 'x');          -- ERROR:  cannot execute INSERT in a read-only transaction
```

To make the lag visible, pause replay on the replica (`SELECT pg_wal_replay_pause();`), then write on the primary:

```sql
-- primary
UPDATE replica_demo SET note = 'second' WHERE id = 1;
SELECT pg_current_wal_lsn();                       -- 0/A405FB58   the token the application would keep

-- replica
SELECT * FROM replica_demo;                        -- 1 | first    a read-your-writes violation
SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn(), now() - pg_last_xact_replay_timestamp();
--  0/A405FB58 | 0/A4053EC0 | 00:00:02.19               received everything, replayed nothing new
SELECT pg_last_wal_replay_lsn() >= '0/A405FB58'::pg_lsn AS safe_to_read,
       pg_wal_lsn_diff('0/A405FB58', pg_last_wal_replay_lsn()) AS bytes_behind;
--  f | 48280
```

The token check says exactly what a routing layer needs to know: this replica is 48 kB behind the session's last commit, so send the read elsewhere. After `pg_wal_replay_resume()` the same check returns `t` and the row reads `second`. A paused replica is an artificial case; a replica under heavy write load, a long-running query on the standby delaying replay, or a network hiccup produce the same picture without anyone asking for it.

## Pitfalls

- Measuring lag only as `now() - pg_last_xact_replay_timestamp()`. On a quiet primary it grows without bound while nothing is behind; compare LSNs, or check that the primary has written anything recently.
- One synchronous standby and no fallback. When it goes down, every commit on the primary hangs. Name several standbys, and know how to change `synchronous_standby_names` under pressure.
- Routing by statement type. "All `SELECT`s to replicas" sends the `GET` after a `POST` redirect to a stale node; route by request context, not by SQL verb.
- `hot_standby_feedback`. Off (the default), long queries on the standby are cancelled when replay needs to remove rows they can still see (`canceling statement due to conflict with recovery`, after `max_standby_streaming_delay`, 30 s). On, the standby pins the primary's vacuum horizon and the primary bloats (item 6.5). Choose knowingly.
- Treating the replica as a backup. A `DROP TABLE` replicates within milliseconds. Backups and point-in-time recovery are a separate discipline (item 7.6).
- Load balancers that hide which node served a request. Monotonic reads become impossible to reason about, and lag incidents impossible to debug; log the node.

## Check yourself

1. A commit returned on the primary and the asynchronous replica crashed a second later. Did the data survive? Now reverse it: the primary crashed and the replica was promoted. What decides whether the data survived?
2. Explain the difference between `remote_write`, `on` and `remote_apply`, and which one is needed so that a read on the standby immediately after a commit sees it.
3. A user saves a profile and the next page shows the old data. List three different mechanisms that would have prevented it, and the cost of each.
4. Why is `replay_lag` in seconds misleading on a primary that writes nothing at night, and what should the alert be based on?

## Go deeper

- [PostgreSQL: High Availability, Load Balancing, and Replication](https://www.postgresql.org/docs/current/high-availability.html) · the official chapter; the [Synchronous Replication](https://www.postgresql.org/docs/current/warm-standby.html#SYNCHRONOUS-REPLICATION) section explains `synchronous_standby_names` precisely.
- [PostgreSQL: pg_stat_replication](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-REPLICATION-VIEW) · every column used above.
- [The Internals of PostgreSQL: Streaming Replication](https://www.interdb.jp/pg/pgsql11.html) · walsender, walreceiver and the LSN handshake, with diagrams.
- [Designing Data-Intensive Applications, chapter 5](https://dataintensive.net/) · replication lag, read-your-writes and monotonic reads as general problems, not PostgreSQL ones.
- [Jepsen: Consistency Models](https://jepsen.io/consistency) · where read-your-writes and monotonic reads sit in the hierarchy of guarantees.

---

Part of [Databases](../README.md) · items 7.1, 7.2
