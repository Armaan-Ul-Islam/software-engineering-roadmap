# Optimistic vs pessimistic locking

> **In one sentence:** Pessimistic locking takes the row lock before reading, so nobody can change the row until you commit; optimistic locking reads without a lock and makes the write conditional on the row being unchanged since the read, failing fast if someone got there first; choose by how likely a conflict is and how long you hold the data.

**Why it matters:** Both prevent the lost update (item 5.2), but they fail in opposite ways: pessimistic locking turns contention into waiting and deadlocks, optimistic locking turns it into retries and "someone else changed this record" errors. The wrong choice gives you a system that is slow under load or unusable under conflict. JPA offers both through `@Version` and `LockModeType`, so every Spring developer makes this choice whether or not they notice.

## The idea

**Pessimistic.** Inside the transaction, read the row with `SELECT ... FOR UPDATE` (or `FOR NO KEY UPDATE` when you will not change key columns, item 6.2), compute, `UPDATE`, `COMMIT`. Between the read and the write no other transaction can modify the row; anyone who tries waits for your commit. The guarantee is absolute and the code is simple. The costs: the lock is held for the whole transaction, so the transaction must be short; waiting transactions hold their own connections and locks, so contention spreads; and lock order must be consistent or deadlocks follow. It cannot span user think time, because a database transaction cannot wait for a human.

**Optimistic.** Read the row and its `version` without locking. When writing, include the version you read in the `WHERE` clause and bump it:

```sql
UPDATE account SET balance = $1, version = version + 1 WHERE id = $2 AND version = $3;
```

If the update reports one row, nobody changed it in between. If it reports zero rows, someone did: reload, re-apply the change to the fresh data, and try again, or tell the user. The read and the write may be in different transactions, even different HTTP requests, because the version travels with the data (in a form field, a DTO or an `ETag`). The costs: conflicts waste the work done before them, every caller needs a retry or an error path, and the retry must be idempotent.

**When each wins.**

| | Pessimistic | Optimistic |
|---|---|---|
| Conflict probability | High: the same rows are contended constantly | Low: conflicts are the exception |
| Transaction length | Short, no remote calls | Any; the lock-free read can be minutes before the write |
| User think time | Impossible to cover | Natural fit (edit form, save later) |
| Cost of a conflict | A wait, occasionally a deadlock to retry | Lost work plus a retry, or a user-facing conflict |
| Typical use | Batch jobs, inventory decrements, queue claims (item 6.6) | Editing records in a UI, REST APIs, most CRUD |
| Hot counters | Neither: use `UPDATE ... SET n = n + 1`, a single atomic statement | |

**Retry semantics.** An optimistic failure means re-executing the whole unit of work from the read onwards: reload, re-validate the business rule against the new state (the rule may now fail), re-apply, retry the write. Cap the number of attempts; a row that fails three times in a row is contended and wants the pessimistic path. For human edits, do not retry silently: show both versions and let the person decide. Pessimistic locking has its own retries: `lock_timeout` expiry and deadlock errors (`40P01`) also require rerunning the transaction.

**In JPA, briefly.** A `@Version` attribute makes Hibernate add `AND version = ?` to every `UPDATE` and `DELETE` of the entity and throw `OptimisticLockException` when zero rows are affected (Spring translates it to `ObjectOptimisticLockingFailureException`). `LockModeType.PESSIMISTIC_WRITE` on a query or `find` appends `FOR UPDATE`, `PESSIMISTIC_READ` appends `FOR SHARE`, and `OPTIMISTIC_FORCE_INCREMENT` bumps the version even without a change, to serialise edits of a parent when its children change. Details, including lock timeouts and `SKIP LOCKED` through Hibernate, are in the Spring domain.

## Example: both strategies on the same table

```sql
CREATE TABLE account (
    id      int PRIMARY KEY,
    balance numeric(12,2) NOT NULL,
    version int NOT NULL DEFAULT 0
);
INSERT INTO account VALUES (1, 100.00, 0);
```

**Optimistic.** Sessions A and B both load the row, A withdraws 30 and B withdraws 50:

```sql
-- A and B, each:
SELECT id, balance, version FROM account WHERE id = 1;     --  1 | 100.00 | 0

-- A writes 100 - 30 against the version it read:
UPDATE account SET balance = 70.00, version = version + 1 WHERE id = 1 AND version = 0;
-- UPDATE 1

-- B writes 100 - 50 against the version it read:
UPDATE account SET balance = 50.00, version = version + 1 WHERE id = 1 AND version = 0;
-- UPDATE 0                                        conflict: nothing written, nothing lost

-- B reloads and retries against the current state:
SELECT id, balance, version FROM account WHERE id = 1;     --  1 | 70.00 | 1
UPDATE account SET balance = 70.00 - 50.00, version = version + 1 WHERE id = 1 AND version = 1
RETURNING id, balance, version;                            --  1 | 20.00 | 2
```

Without the version check, B's first update would have written 50.00 and the 30 withdrawal would have vanished. The application must check the row count; a zero that goes unnoticed is a silent lost update of a different kind.

**Pessimistic.** Same starting state, A holds the row for two seconds:

```sql
-- session A                                             -- session B
BEGIN;                                                   BEGIN;
SELECT balance FROM account WHERE id = 1 FOR UPDATE;
--  100.00                                               SELECT balance FROM account WHERE id = 1 FOR UPDATE;
SELECT pg_sleep(2);                                      -- ... waits ...
UPDATE account SET balance = balance - 30 WHERE id = 1;
COMMIT;                                                  --  70.00   (returned after 1.49 s of waiting)
                                                         UPDATE account SET balance = balance - 50 WHERE id = 1;
                                                         COMMIT;    -- balance is 20.00
```

B's `SELECT ... FOR UPDATE` blocked until A committed and then saw A's result, so its arithmetic was based on the real balance. No retry logic, at the price of B's request taking as long as A's transaction. Note that `SELECT balance ... ` without `FOR UPDATE`, followed by an `UPDATE` in the same transaction, is neither strategy: under Read Committed it is the lost update itself.

## Pitfalls

- Reading without `FOR UPDATE` and updating later in the same transaction, and calling it pessimistic. Nothing was locked at read time; this is the classic lost update.
- Checking `@Version` only in the ORM. A migration script, a batch `UPDATE` or another service that writes the table without bumping `version` defeats the mechanism. Either every writer bumps it, or a trigger does.
- Retrying optimistic failures forever. On a hot row the retry storm is worse than a lock; cap attempts and switch strategies for that row.
- Retrying a non-idempotent unit of work. If the retried code also sent an email or charged a card, the conflict just duplicated a side effect.
- Pessimistic locks across remote calls or user think time. The lock lives as long as the transaction and the transaction lives as long as the connection; pools empty quickly (item 7.5).
- `FOR UPDATE` in read paths "to be safe". It serialises every reader of a popular row and blocks foreign-key inserts on it (item 6.2).
- Using either strategy for a counter. `UPDATE ... SET hits = hits + 1 WHERE id = ?` is atomic on its own and never conflicts.

## Check yourself

1. Two users open the same customer record in a web form, edit different fields and save ten minutes apart. Which strategy applies, and what should the second user see?
2. An inventory service decrements stock for 200 concurrent orders of the same product. Which strategy applies, and what single-statement alternative beats both?
3. Why must the unit of work that wraps an optimistic update be idempotent, and what exactly is repeated on a retry?
4. A JPA entity has `@Version`, yet lost updates still occur. Name two ways this can happen.

## Go deeper

- [Baeldung: Optimistic Locking in JPA](https://www.baeldung.com/jpa-optimistic-locking) and [Pessimistic Locking in JPA](https://www.baeldung.com/jpa-pessimistic-locking) · the `@Version` and `LockModeType` mechanics with examples.
- [Vlad Mihalcea: Lost update](https://vladmihalcea.com/a-beginners-guide-to-database-locking-and-the-lost-update-phenomena/) · the anomaly both strategies prevent, shown at each isolation level.
- [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) · what `FOR UPDATE` and `FOR NO KEY UPDATE` lock and how they conflict.

---

Part of [Databases](../README.md) · item 6.4
