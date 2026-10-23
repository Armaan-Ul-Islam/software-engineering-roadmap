# Transaction isolation levels and the anomalies they prevent

> **In one sentence:** An isolation level is a choice of which concurrency anomalies you are willing to tolerate in exchange for throughput, and the level names mean different things in different databases.

**Why it matters:** Most "impossible" data corruption in production is not a bug in a SQL statement. It is a lost update or a write skew that happened under Read Committed, the default in PostgreSQL and the level most Spring applications run at without knowing it. Interviewers ask about this because it separates people who have read the definitions from people who have debugged the consequences.

## The idea

Transactions run concurrently. Without isolation, their reads and writes would interleave arbitrarily and the result could be something no serial execution could produce. The strongest guarantee, **serializable**, says the outcome equals *some* serial order of the transactions. Everything weaker permits specific anomalies in return for less locking and fewer aborts.

The SQL standard defines four levels by three anomalies (dirty read, non-repeatable read, phantom read). That list is incomplete. The anomalies that bite in real systems are these six:

| Anomaly | What happens | Everyday shape |
|---|---|---|
| Dirty read | You read a row another transaction has written but not committed. | Report counts an order that is rolled back a second later. |
| Non-repeatable read | You read a row twice in one transaction and get different values. | Price checked at the start differs from the price used at the end. |
| Phantom read | You run the same `WHERE` query twice and rows appear or disappear. | "Count seats, then insert booking" admits one seat too many. |
| Lost update | Two transactions read a value, each computes a new one, and the second write overwrites the first. | Two withdrawals from the same balance; one vanishes. |
| Read skew | You read two related rows while another transaction commits a change between the reads. | Account A plus account B does not sum to the total. |
| Write skew | Two transactions read overlapping data, then make disjoint writes that together violate a rule. | Both on-call doctors go off duty at the same time. |

What each PostgreSQL level actually prevents (not the standard's table, the real behaviour):

| Level in PostgreSQL | Dirty | Non-repeatable | Phantom | Lost update | Read skew | Write skew |
|---|---|---|---|---|---|---|
| Read Uncommitted (behaves as Read Committed) | prevented | allowed | allowed | allowed | allowed | allowed |
| Read Committed (default) | prevented | allowed | allowed | allowed | allowed | allowed |
| Repeatable Read (snapshot isolation) | prevented | prevented | prevented | detected, aborts | prevented | allowed |
| Serializable (SSI) | prevented | prevented | prevented | detected, aborts | prevented | detected, aborts |

Two things in that table surprise people. PostgreSQL's Repeatable Read prevents phantoms even though the standard allows them, because it is really snapshot isolation: every statement sees the database as of the transaction's first query. And Repeatable Read still allows write skew, which is why Serializable exists.

MySQL's InnoDB also defaults to Repeatable Read, but implements it with a mix of snapshots and next-key locks, so its behaviour differs in the details. Always read the engine's own documentation rather than the standard.

## Example: reproduce a lost update, then fix it four ways

Open two `psql` sessions against the same database.

```sql
-- once, in either session
CREATE TABLE account (id int PRIMARY KEY, balance numeric NOT NULL);
INSERT INTO account VALUES (1, 100);
```

Session A:

```sql
BEGIN;
SELECT balance FROM account WHERE id = 1;   -- 100
```

Session B:

```sql
BEGIN;
SELECT balance FROM account WHERE id = 1;   -- 100
UPDATE account SET balance = 100 - 30 WHERE id = 1;
COMMIT;
```

Session A, continuing with the value it read earlier:

```sql
UPDATE account SET balance = 100 - 50 WHERE id = 1;
COMMIT;
SELECT balance FROM account WHERE id = 1;   -- 50. The 30 withdrawal is gone.
```

This is exactly what an application does when it loads an entity, changes a field in Java, and saves it. Four fixes, from cheapest to most general:

1. **Make the read and the write one statement.** `UPDATE account SET balance = balance - 50 WHERE id = 1 AND balance >= 50;` Under Read Committed, PostgreSQL waits for B's lock, re-reads the row, and applies the arithmetic to the committed value. Prefer this whenever the new value is a function of the old one.
2. **Lock first.** `SELECT balance FROM account WHERE id = 1 FOR UPDATE;` in session A blocks session B's `UPDATE` until A commits. Pessimistic, simple, and fine for low-contention rows.
3. **Optimistic locking.** Add a `version` column and write `UPDATE account SET balance = 50, version = version + 1 WHERE id = 1 AND version = 7;`. If the update count is 0, somebody else won; reload and retry or report a conflict. This is what JPA's `@Version` does for you.
4. **Raise the isolation level.** Under `REPEATABLE READ`, session A's `UPDATE` fails with `ERROR: could not serialize access due to concurrent update`. Correct, but now every client must catch that error and retry the whole transaction.

## Example: write skew survives Repeatable Read

```sql
CREATE TABLE on_call (doctor text PRIMARY KEY, shift date NOT NULL, on_duty boolean NOT NULL);
INSERT INTO on_call VALUES ('alice', '2026-11-01', true), ('bob', '2026-11-01', true);
```

Rule: at least one doctor must stay on duty. Both doctors try to leave at the same time, each in a `REPEATABLE READ` transaction:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM on_call WHERE shift = '2026-11-01' AND on_duty;   -- 2 in both sessions
UPDATE on_call SET on_duty = false WHERE doctor = 'alice';            -- 'bob' in the other session
COMMIT;                                                                -- both succeed
```

Nobody is on duty. The two transactions wrote different rows, so snapshot isolation has nothing to detect. Under `SERIALIZABLE`, PostgreSQL notices the read-write dependency and aborts one transaction with `could not serialize access due to read/write dependencies among transactions`. Without Serializable, you must materialise the conflict yourself: lock a single row that represents the shift with `FOR UPDATE`, or enforce the rule with a constraint trigger.

## Pitfalls

- Trusting the default. Read Committed allows every anomaly except dirty reads. Any load-modify-save sequence in application code is a lost update waiting for traffic.
- Checking a condition in code and then writing. Any rule that spans rows ("at most N", "at least one", "unique unless cancelled") is a write-skew candidate; it belongs in a constraint, a lock, or a Serializable transaction.
- Switching to Serializable without a retry loop. Serialization failures are normal operation, not bugs; the application must retry the whole transaction, and the retry must be idempotent.
- Memorising the SQL standard's table as if it described your database. PostgreSQL's Repeatable Read is snapshot isolation; MySQL's is something else again.
- Long transactions under Repeatable Read or Serializable. They pin old row versions, so `VACUUM` cannot reclaim them and tables bloat (see item 6.5).
- Letting the ORM hide the problem. Hibernate's dirty checking writes whatever changed, last writer wins. Add `@Version` to entities that are updated concurrently.

## Check yourself

1. Why does `UPDATE account SET balance = balance - 50` avoid lost updates under Read Committed, while reading the balance into Java and writing it back does not?
2. Which anomaly can still happen under PostgreSQL's Repeatable Read, and what are two ways to prevent it without Serializable?
3. A colleague says "we run Repeatable Read, so phantoms cannot happen". For which database is that correct reasoning?
4. What must every caller of a Serializable transaction implement, and what property must the transaction have for that to be safe?

## Go deeper

- [PostgreSQL: Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) · the precise behaviour of each level, including the error messages above.
- [Designing Data-Intensive Applications, chapter 7](https://dataintensive.net/) · the clearest treatment of weak isolation and the anomalies, with the on-call doctors example.
- [Hermitage](https://github.com/ept/hermitage) · scripts that reproduce every anomaly against PostgreSQL, MySQL, Oracle and others; run them yourself.
- [A Critique of ANSI SQL Isolation Levels](https://arxiv.org/abs/cs/0701157) · the 1995 paper that showed the standard's definitions are incomplete and defined snapshot isolation.
- [Vlad Mihalcea: Lost update](https://vladmihalcea.com/a-beginners-guide-to-database-locking-and-the-lost-update-phenomena/) and [Read and write skew](https://vladmihalcea.com/a-beginners-guide-to-read-and-write-skew-phenomena/) · the same anomalies from the JPA side.

---

Part of [Databases](../README.md) · items 5.2, 5.3, 5.4
