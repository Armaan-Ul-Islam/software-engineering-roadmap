# Row locks, SELECT FOR UPDATE and deadlocks

> **In one sentence:** PostgreSQL locks a row whenever a transaction updates, deletes or explicitly locks it, holds the lock until commit, queues other writers behind it, detects a cycle in that queue after one second and aborts one participant; `NOWAIT`, `SKIP LOCKED`, `lock_timeout`, consistent ordering and advisory locks are the tools for deciding who waits for whom.

**Why it matters:** Lock waits and deadlocks are the production failures that never appear in a single-user test. Knowing exactly which statements take which locks lets you order them so that deadlocks cannot form, and `SKIP LOCKED` turns a plain table into a safe multi-worker job queue without adding a message broker.

## The idea

**Row lock modes.** There are four, from weakest to strongest: `FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE` and `FOR UPDATE`. Statements take them implicitly: an `UPDATE` that does not touch a unique-key column takes `FOR NO KEY UPDATE`; a `DELETE`, or an `UPDATE` that changes a key column, takes `FOR UPDATE`; inserting or updating a row with a foreign key takes `FOR KEY SHARE` on the referenced parent row. `SELECT ... FOR <mode>` takes one explicitly. Row locks are stored in the tuple header, so locking a million rows costs no lock memory, but they show up in `pg_locks` only when someone is waiting.

| Requested \ held by another transaction | KEY SHARE | SHARE | NO KEY UPDATE | UPDATE |
|---|---|---|---|---|
| `FOR KEY SHARE` | ok | ok | ok | waits |
| `FOR SHARE` | ok | ok | waits | waits |
| `FOR NO KEY UPDATE` | ok | waits | waits | waits |
| `FOR UPDATE` | waits | waits | waits | waits |

The practical consequence of the two weakest modes: a plain `UPDATE` on a customer does not block inserting that customer's orders, but `SELECT ... FOR UPDATE` on the customer does.

**Waiting.** A transaction that needs a locked row waits for the holder's transaction to end, in a fair queue; the server reports `wait_event_type = Lock`, and `pg_blocking_pids(pid)` names the blocker. `lock_timeout` bounds the wait and fails with `canceling statement due to lock timeout`; `NOWAIT` fails immediately with `could not obtain lock on row`; `SKIP LOCKED` silently leaves locked rows out of the result.

**Deadlocks.** Transaction A holds row 1 and wants row 2; B holds row 2 and wants row 1. Neither can finish. After a waiter has waited `deadlock_timeout` (1 s) PostgreSQL searches the wait graph for a cycle and aborts one of the transactions with `ERROR: deadlock detected` (SQLSTATE `40P01`); the other proceeds. Deadlocks are not bugs in the database, they are a property of taking locks in different orders. The cure is ordering: lock rows in a consistent order (by primary key, `UPDATE ... WHERE id IN (SELECT id FROM ... ORDER BY id FOR UPDATE)`), take the strongest lock you will need first, keep transactions short, and retry on `40P01`.

**Advisory locks.** Application-defined locks on a 64-bit key that the database does not interpret: `pg_advisory_xact_lock(key)` waits, `pg_try_advisory_xact_lock(key)` returns `false` instead of waiting, and both release at transaction end. Use them for "only one instance of this job may run", with `hashtext('nightly-report')` as the key. The session-level variants (`pg_advisory_lock`, `pg_advisory_unlock`) outlive transactions and are dangerous behind connection poolers.

## Example: a deadlock, with the error text

Two `psql` sessions, `account` rows 1 and 2.

```sql
-- session A                                          -- session B
BEGIN;                                                BEGIN;
UPDATE account SET balance = balance - 10 WHERE id = 1;
                                                      UPDATE account SET balance = balance - 10 WHERE id = 2;
                                                      UPDATE account SET balance = balance + 10 WHERE id = 1;   -- waits for A
UPDATE account SET balance = balance + 10 WHERE id = 2;    -- waits for B: cycle
```

One second later, session B receives:

```text
ERROR:  deadlock detected
DETAIL:  Process 17588 waits for ShareLock on transaction 61870; blocked by process 17586.
Process 17586 waits for ShareLock on transaction 61871; blocked by process 17588.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (0,4) in relation "account"
```

Session A's second update then completes and A commits. B's transaction is gone and must be retried from the beginning. Had both sessions updated the rows in id order (1 then 2), B would simply have waited for A and the deadlock could not have formed.

While a session waits, a third session can see who is blocking whom:

```sql
SELECT pid, pg_blocking_pids(pid) AS blocked_by, wait_event_type, wait_event, left(query, 40)
FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;
--  17415 | {17412} | Lock | transactionid | UPDATE account SET balance = balance + 5
```

## Example: a job queue with `SKIP LOCKED`

```sql
CREATE TABLE job (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    state      text NOT NULL DEFAULT 'queued',
    payload    jsonb NOT NULL
);
CREATE INDEX job_queued_idx ON job (created_at, id) WHERE state = 'queued';
```

Each worker claims the oldest unclaimed job inside its own transaction:

```sql
BEGIN;
UPDATE job SET state = 'running'
WHERE id = (
    SELECT id FROM job
    WHERE state = 'queued'
    ORDER BY created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
RETURNING id, payload;
-- ... do the work ...
UPDATE job SET state = 'done' WHERE id = $1;
COMMIT;
```

Three workers started half a second apart, each holding its transaction open while "working", received jobs 1, 2 and 3 respectively: the second worker's subquery skipped job 1 because it was locked, rather than waiting for it, and so on. Without `SKIP LOCKED` every worker would queue up behind the first on the same row. The partial index keeps the queued set tiny no matter how many finished jobs accumulate. If the worker's transaction aborts, the row lock is released and the job becomes `queued` again automatically, because the state change was never committed.

For a scheduler that must run on exactly one of several application instances:

```sql
SELECT pg_try_advisory_xact_lock(hashtext('nightly-report'));   -- true on one instance, false on the others
```

## Pitfalls

- `SELECT ... FOR UPDATE` on a parent row to "protect" it while inserting children. The children's foreign-key checks need `FOR KEY SHARE`, which conflicts with `FOR UPDATE`: inserting an order waited 1.5 s behind such a lock on the customer, and 3 ms behind `FOR NO KEY UPDATE`. Use the weaker mode unless you change the key.
- Locking in application order instead of key order. "Debit the payer, then credit the payee" deadlocks the moment two transfers cross; sort the two ids first.
- Holding row locks across user think time or remote calls. A web request that locks a row, calls a payment provider and then commits holds the lock for the provider's latency; everyone else queues (item 5.5).
- Not retrying `40P01`. The server resolved the deadlock by aborting you; the application must rerun the whole transaction, which must therefore be safe to repeat.
- Queue tables without `ORDER BY` and an index on the queue predicate, or without a lease. A worker that crashes mid-job releases the lock, but a worker that hangs keeps the row `running` forever; add a `locked_until` column and reclaim expired leases.
- Session-level advisory locks with a transaction-mode pooler. The lock belongs to the server connection, which the pooler hands to another client at the next transaction. Use the `_xact_` variants.
- Reading `pg_locks` to find row locks. Uncontended row locks are in the tuples, not in `pg_locks`; look for `granted = false` rows and use `pg_blocking_pids`.

## Check yourself

1. Why does inserting an order block when another transaction holds `FOR UPDATE` on the customer, but not when it holds `FOR NO KEY UPDATE`?
2. Two transactions each update rows 7 and 12. Describe the interleaving that deadlocks and the one-line change that makes it impossible.
3. What happens to a job's row if the worker that claimed it with `FOR UPDATE SKIP LOCKED` crashes before committing, and what happens if it hangs instead?
4. Why is `pg_advisory_lock` risky behind PgBouncer in transaction mode, and which function should be used instead?

## Go deeper

- [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) · the table-level and row-level lock modes with the full conflict matrices, including the [Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS) and [Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) sections.
- [PostgreSQL: SELECT, The Locking Clause](https://www.postgresql.org/docs/current/sql-select.html#SQL-FOR-UPDATE-SHARE) · exact semantics of `FOR UPDATE`, `NOWAIT` and `SKIP LOCKED`.
- [What is SELECT SKIP LOCKED for?](https://www.2ndquadrant.com/en/blog/what-is-select-skip-locked-for-in-postgresql-9-5/) · the queue pattern explained by the people who added the feature.
- [Vlad Mihalcea: Lost update](https://vladmihalcea.com/a-beginners-guide-to-database-locking-and-the-lost-update-phenomena/) · the anomaly that explicit locking exists to prevent.

---

Part of [Databases](../README.md) · items 6.2, 6.3, 6.6
