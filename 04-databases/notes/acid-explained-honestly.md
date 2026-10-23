# ACID explained honestly

> **In one sentence:** Atomicity, consistency, isolation and durability are four separate promises with different owners: the database guarantees atomicity outright, durability to the extent you configure it, isolation to the level you choose, and consistency only for the rules you declare as constraints; the rest of consistency is your code.

**Why it matters:** "The database is ACID" is used to end discussions it should start. Lost updates under the default isolation level, committed rows missing after a failover, and "consistent" meaning two unrelated things in ACID and in CAP are each a place where someone trusted the acronym instead of the configuration. Interviewers like this topic because the honest answer requires knowing what the server actually does.

## The idea

| Letter | What PostgreSQL guarantees | What it does not cover | What controls it |
|---|---|---|---|
| **Atomicity** | A transaction's writes become visible all together at `COMMIT` or not at all. Any error aborts the whole transaction, not just the failing statement. | Effects outside the database (emails, HTTP calls, messages). A client that crashes after sending `COMMIT` but before reading the reply does not know the outcome. | Always on. Savepoints (`SAVEPOINT`, `ROLLBACK TO`) give partial rollback inside a transaction. |
| **Consistency** | Every declared constraint holds after every statement (or at commit, if deferred): `NOT NULL`, `CHECK`, `UNIQUE`, foreign keys, exclusion constraints. | Rules you did not declare. "Total of order lines equals order total" or "at least one doctor on call" are invariants the database knows nothing about. | Your DDL (item 8.3), plus isolation or locking for rules that span rows. |
| **Isolation** | Concurrent transactions do not see each other's uncommitted changes, and at stronger levels behave as if they ran one at a time. | The default, Read Committed, permits lost updates, non-repeatable reads, phantoms and write skew. | `default_transaction_isolation`, or `BEGIN ISOLATION LEVEL ...` per transaction (items 5.2 to 5.4). |
| **Durability** | Once `COMMIT` returns, the transaction survives a crash or power loss of the server, because its WAL record was flushed to disk first (item 2.2). | Loss of the disk itself, and anything a replica has not received yet. | `fsync` (never off), `synchronous_commit`, `full_page_writes`, and `synchronous_standby_names` for durability on more than one machine. |

Three misreadings account for most ACID arguments:

1. **Consistency in ACID versus consistency in CAP.** In ACID it means "constraints hold". In CAP (and in Jepsen's hierarchy) it means linearizability: every read sees the latest committed write across all nodes. A PostgreSQL primary with an asynchronous replica is ACID-consistent and not CAP-consistent, and nothing is wrong with it.
2. **Durability versus replication.** With the default `synchronous_commit = on` and no synchronous standby, a commit is durable on the primary's disk only. If the primary is lost and a replica is promoted, committed transactions the replica had not received are gone. Durability on two machines requires `synchronous_standby_names` plus `synchronous_commit` at `on` or `remote_apply`, and costs a network round trip on every commit (item 7.1).
3. **"ACID means no concurrency bugs."** Isolation is a dial, and the default position allows the anomalies that corrupt data in real systems. Atomicity says your two `UPDATE`s commit together; it says nothing about the `SELECT` you did a moment earlier being stale.

`synchronous_commit` deserves its own line, because it is the one durability setting worth changing on purpose. Its values are `off`, `local`, `remote_write`, `on` and `remote_apply`. `off` returns `COMMIT` before the WAL is flushed; a crash in the next few hundred milliseconds (at most three times `wal_writer_delay`) loses those commits but never corrupts the database. It can be set per transaction, so an analytics insert can be fast while a payment stays safe.

## Example: atomicity and consistency in one transaction

```sql
CREATE TABLE account (
    id      int PRIMARY KEY,
    balance numeric(12,2) NOT NULL CHECK (balance >= 0)
);
INSERT INTO account VALUES (1, 100.00), (2, 0.00);

BEGIN;
UPDATE account SET balance = balance + 150 WHERE id = 2;
UPDATE account SET balance = balance - 150 WHERE id = 1;
```
```text
ERROR:  new row for relation "account" violates check constraint "account_balance_check"
DETAIL:  Failing row contains (1, -50.00).
```
```sql
SELECT * FROM account;
```
```text
ERROR:  current transaction is aborted, commands ignored until end of transaction block
```
```sql
COMMIT;      -- the server answers ROLLBACK
SELECT * FROM account ORDER BY id;
```
```text
 id | balance
----+---------
  1 |  100.00
  2 |    0.00
```

The constraint (consistency, declared) rejected the second update; the abort (atomicity) took the first update with it, even though that statement had succeeded; and `COMMIT` on an aborted transaction is a rollback. PostgreSQL differs here from databases that roll back only the failing statement: after any error you must `ROLLBACK`, or `ROLLBACK TO` a savepoint you set earlier.

Durability per transaction:

```sql
BEGIN;
SET LOCAL synchronous_commit = off;
INSERT INTO page_view (url, viewed_at) VALUES ('/pricing', now());
COMMIT;    -- returns without waiting for the WAL flush; the setting reverts after COMMIT
```

A rule the schema cannot express, such as "the sum of all account balances never changes", is left to isolation: under Read Committed two concurrent transfers can still interleave into a lost update (item 5.2), and the constraint above will cheerfully accept the result.

## Pitfalls

- Catching the exception and continuing in the same transaction. Every further statement fails with "current transaction is aborted"; ORMs that swallow a constraint violation and keep going produce exactly this. Use a savepoint when a failure is expected, otherwise let the transaction fail.
- Checking an invariant in code and trusting it. Between your `SELECT` and your `UPDATE` another transaction can change the rows; multi-row rules need a constraint, a lock or Serializable (item 5.4).
- Treating a committed write as replicated. Reading from an asynchronous replica right after a commit can miss the write (item 7.2).
- Turning `fsync` off for speed. That trades durability for the risk of an unrecoverable cluster; `synchronous_commit = off` is the setting that trades only recent commits.
- Confusing an ORM flush with a commit. Flushed statements are in the transaction, not durable; nothing is promised until `COMMIT` returns.
- Expecting atomicity across services. A database transaction plus an HTTP call is not atomic; use the transactional outbox or an idempotent retry (item 5.6).

## Check yourself

1. A colleague says the system is "strongly consistent because PostgreSQL is ACID". Which two meanings of consistency are being merged, and which one does PostgreSQL alone give you?
2. `COMMIT` returned, then the data centre lost power and the asynchronous replica was promoted. Is the transaction durable? What single setting would have changed the answer, and at what cost?
3. Why does a `CHECK (balance >= 0)` constraint not prevent two concurrent withdrawals from overdrawing an account under Read Committed?
4. In PostgreSQL, what must the application do after a statement in a transaction fails, and how does that differ from statement-level rollback in other databases?

## Go deeper

- [Vlad Mihalcea: A beginner's guide to ACID](https://vladmihalcea.com/a-beginners-guide-to-acid-and-database-transactions/) · each property with examples from the application side.
- [Designing Data-Intensive Applications, chapter 7](https://dataintensive.net/) · the "meaning of ACID" section is the best short treatment of what the letters do and do not promise.
- [PostgreSQL: Reliability](https://www.postgresql.org/docs/current/wal-reliability.html) · what durability depends on, from `fsync` down to disk write caches.
- [PostgreSQL: Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) · the I in detail.
- [Jepsen: Consistency Models](https://jepsen.io/consistency) · the CAP side of the word "consistency", mapped against isolation levels.

---

Part of [Databases](../README.md) · item 5.1
