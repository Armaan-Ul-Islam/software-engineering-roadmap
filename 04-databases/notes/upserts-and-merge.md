# Upserts, MERGE and bulk loading

> **In one sentence:** `INSERT ... ON CONFLICT` turns "insert, or if the key already exists, do nothing or update" into one atomic, race-free statement that needs a unique index on the conflict columns; `MERGE` expresses a whole source-to-target synchronisation with inserts, updates and deletes in one statement; and `COPY` is how rows get into PostgreSQL in bulk.

**Why it matters:** Every consumer of a message queue or a webhook is handed the same event twice sooner or later, and "check whether it exists, then insert" is a race that produces duplicate-key errors under load and duplicate rows without a constraint. The upsert is the idempotent write primitive that makes at-least-once delivery safe. Knowing where `ON CONFLICT` stops and `MERGE` begins, and why a loop of inserts is far slower than `COPY`, is the difference between an ingestion pipeline that works and one that pages you.

## The idea

**`ON CONFLICT` needs a unique index.** `INSERT ... ON CONFLICT (columns) DO ...` requires a unique index or constraint whose columns match the conflict target exactly (an exclusion constraint also works for `DO NOTHING`); otherwise the statement fails with `there is no unique or exclusion constraint matching the ON CONFLICT specification`, whether or not a conflict occurs. The target can also be `ON CONSTRAINT name`, or carry a `WHERE` predicate to match a partial unique index. `ON CONFLICT DO NOTHING` without a target catches a violation of any unique constraint.

**`DO NOTHING` versus `DO UPDATE`.** `DO NOTHING` skips the row silently (`INSERT 0 0`) and `RETURNING` returns nothing for it. `DO UPDATE SET ...` updates the existing row; in the `SET` list and in an optional `WHERE`, `EXCLUDED` is the row that was proposed for insertion and the table name is the row already there. That `WHERE` is how an update is refused conditionally, for example when the incoming event is older than the stored one, which makes the statement safe against redelivery and reordering at once.

**Why it is race-free.** PostgreSQL inserts the row speculatively, checks the unique index, and if another transaction is inserting the same key at that moment, waits for it to finish and then takes the conflict path. There is no window between "check" and "insert", which is exactly the window a `SELECT` followed by an `INSERT` leaves open. Under Read Committed the outcome is always an insert or an update; under Repeatable Read or Serializable, a conflict with a row your snapshot cannot see is a serialization failure to retry (item 5.4).

**Idempotent writes for at-least-once consumers.** Give every event a stable identifier assigned by the producer, make it the primary key of the table that records events, and insert with `ON CONFLICT (event_id) DO NOTHING`. A redelivery becomes a no-op. When the consumer also maintains derived state, a "current value" table, update it with `DO UPDATE ... WHERE EXCLUDED.occurred_at > current.occurred_at`, and run both statements in one transaction. Item 5.6 covers idempotency keys for request-level deduplication.

**`RETURNING`.** `INSERT`, `UPDATE`, `DELETE` and, from PostgreSQL 17, `MERGE` can return columns of the affected rows, which saves a round trip for generated keys and shows which rows an upsert touched. With `DO UPDATE`, `RETURNING (xmax = 0) AS inserted` distinguishes inserts from updates; it is a widely used idiom that relies on a system column rather than on a documented guarantee.

**`MERGE`** (PostgreSQL 15 or later). `MERGE INTO target USING source ON condition`, followed by `WHEN MATCHED [AND ...] THEN UPDATE | DELETE | DO NOTHING` and `WHEN NOT MATCHED THEN INSERT ...` clauses. They are tried in order, the first whose condition holds wins, and a row that matches no clause is left alone. PostgreSQL 17 adds `WHEN NOT MATCHED BY SOURCE` (target rows absent from the source, usually to delete them) and `RETURNING` with `merge_action()`. `MERGE` is the tool for synchronising a table with a feed; it is not a concurrent upsert. It does not use speculative insertion, so two sessions merging the same new key can end with a unique-violation error in one of them, and it needs no unique index at all.

**Bulk loading.** `COPY table FROM STDIN WITH (FORMAT csv, HEADER)` streams rows in one statement, with no per-row parsing, planning or round trip; `psql`'s `\copy` does the same from the client's file system, and the JDBC driver exposes it as `CopyManager`. The robust pattern is `COPY` into a staging table (unlogged or temporary), then `INSERT INTO target SELECT ... FROM staging ON CONFLICT DO NOTHING`, or a `MERGE`, so that validation, deduplication and type conversion happen in SQL. From PostgreSQL 17, `COPY ... WITH (ON_ERROR ignore)` skips rows that fail type conversion instead of aborting the load, and `LOG_VERBOSITY verbose` names each skipped row.

## Example: an idempotent event ingest

```sql
CREATE TABLE reading (
    id          bigint GENERATED ALWAYS AS IDENTITY,
    event_id    uuid PRIMARY KEY,                 -- assigned by the producer
    device_id   text NOT NULL,
    occurred_at timestamptz NOT NULL,
    temperature numeric(5,2) NOT NULL
);
CREATE TABLE device_state (
    device_id   text PRIMARY KEY,
    last_seen   timestamptz NOT NULL,
    temperature numeric(5,2) NOT NULL,
    updates     int NOT NULL DEFAULT 1
);
```

The consumer runs two statements per event, in one transaction:

```sql
INSERT INTO reading (event_id, device_id, occurred_at, temperature)
VALUES ('0190a1b2-0000-7000-8000-000000000001', 'sensor-7', '2026-10-24 10:00+02', 21.50)
ON CONFLICT (event_id) DO NOTHING;
-- INSERT 0 1 the first time; INSERT 0 0 when the broker redelivers it

INSERT INTO device_state (device_id, last_seen, temperature)
VALUES ('sensor-7', '2026-10-24 10:00+02', 21.50)
ON CONFLICT (device_id) DO UPDATE
    SET last_seen = EXCLUDED.last_seen, temperature = EXCLUDED.temperature, updates = device_state.updates + 1
    WHERE EXCLUDED.last_seen > device_state.last_seen
RETURNING *;
```

The second statement, for three deliveries in a row (PostgreSQL 18, session time zone `Europe/Oslo`):

```text
 device_id |       last_seen        | temperature | updates
-----------+------------------------+-------------+---------
 sensor-7  | 2026-10-24 10:00:00+02 |       21.50 |       1       first event: inserted
 sensor-7  | 2026-10-24 10:05:00+02 |       21.75 |       2       a newer event: updated
(0 rows)                                                            a late event from 09:55: refused by the WHERE
```

The identity column shows a side effect: after the redelivery, the next distinct event gets `id = 3`, not 2, because an identity value is consumed even when the conflict path is taken. Sequences guarantee uniqueness, not contiguity.

Two errors you will meet:

```sql
INSERT INTO device_state (device_id, last_seen, temperature) VALUES ('sensor-9', now(), 20.00)
ON CONFLICT (temperature) DO NOTHING;
-- ERROR:  there is no unique or exclusion constraint matching the ON CONFLICT specification

INSERT INTO device_state (device_id, last_seen, temperature)
VALUES ('sensor-9', '2026-10-24 10:00+02', 20.00), ('sensor-9', '2026-10-24 10:01+02', 20.50)
ON CONFLICT (device_id) DO UPDATE SET last_seen = EXCLUDED.last_seen, temperature = EXCLUDED.temperature;
-- ERROR:  ON CONFLICT DO UPDATE command cannot affect row a second time
-- HINT:  Ensure that no rows proposed for insertion within the same command have duplicate constrained values.
```

The second one reaches every batch consumer eventually: the same device twice in one batch. Deduplicate the batch first, `SELECT DISTINCT ON (device_id) ... ORDER BY device_id, last_seen DESC`, and upsert the result.

## Example: a `MERGE` that inserts, updates and deletes in one statement

A product table synchronised with a supplier feed (PostgreSQL 17 or later for `NOT MATCHED BY SOURCE` and `RETURNING`):

```sql
CREATE TABLE product      (sku text PRIMARY KEY, name text NOT NULL, price numeric(10,2) NOT NULL);
CREATE TABLE product_feed (sku text PRIMARY KEY, name text NOT NULL, price numeric(10,2) NOT NULL,
                           discontinued boolean NOT NULL);
INSERT INTO product      VALUES ('W-1', 'Widget', 9.99), ('G-7', 'Gadget', 24.50), ('C-2', 'Cable', 3.00);
INSERT INTO product_feed VALUES ('W-1', 'Widget', 10.49, false), ('G-7', 'Gadget', 24.50, true),
                                ('B-3', 'Bracket', 5.00, false);

MERGE INTO product
USING product_feed AS feed ON product.sku = feed.sku
WHEN MATCHED AND feed.discontinued THEN DELETE
WHEN MATCHED AND (product.price, product.name) IS DISTINCT FROM (feed.price, feed.name) THEN
    UPDATE SET price = feed.price, name = feed.name
WHEN NOT MATCHED BY TARGET THEN
    INSERT (sku, name, price) VALUES (feed.sku, feed.name, feed.price)
WHEN NOT MATCHED BY SOURCE THEN DELETE
RETURNING merge_action() AS action, product.sku, product.price;
```
```text
 action | sku | price
--------+-----+-------
 UPDATE | W-1 | 10.49       price changed
 DELETE | G-7 | 24.50       discontinued in the feed
 DELETE | C-2 |  3.00       missing from the feed
 INSERT | B-3 |  5.00       new in the feed
```

A matched product whose price and name are unchanged hits no clause and is not written at all, which keeps the writes (and the WAL) proportional to the real changes.

## Example: `COPY`, then upsert from staging

```sql
CREATE TABLE reading_staging (event_id uuid, device_id text, occurred_at timestamptz, temperature numeric(5,2));
\copy reading_staging FROM 'readings.csv' WITH (FORMAT csv, HEADER)
-- COPY 200000      Time: 338.732 ms

INSERT INTO reading (event_id, device_id, occurred_at, temperature)
SELECT event_id, device_id, occurred_at, temperature FROM reading_staging
ON CONFLICT (event_id) DO NOTHING;
-- INSERT 0 200000  about 2 s; run it again: INSERT 0 0 in about 1.2 s, and nothing has changed
```

For comparison, 20,000 single-row `INSERT` statements in one transaction over the same local connection took 3.0 s: a tenth of the rows in nine times the time. And a bad row in the file:

```sql
\copy reading_staging FROM 'readings_bad.csv' WITH (FORMAT csv, HEADER)
-- ERROR:  invalid input syntax for type uuid: "not-a-uuid"
-- CONTEXT:  COPY reading_staging, line 3, column event_id: "not-a-uuid"
\copy reading_staging FROM 'readings_bad.csv' WITH (FORMAT csv, HEADER, ON_ERROR ignore, LOG_VERBOSITY verbose)
-- NOTICE:  skipping row due to data type incompatibility at line 3 for column "event_id": "not-a-uuid"
-- NOTICE:  1 row was skipped due to data type incompatibility
-- COPY 2
```

## Pitfalls

- "Check, then insert" in application code. Two requests pass the check at the same moment; one gets a duplicate-key exception, or without a constraint you get two rows. `ON CONFLICT` with a unique constraint is the race-free version (item 8.3).
- A conflict target that does not match a unique index exactly. The statement fails at execution even when there is no conflict; a non-unique index does not count.
- The same key twice in one multi-row statement. `cannot affect row a second time`; deduplicate the batch with `DISTINCT ON`.
- `DO UPDATE` without a guard. A redelivered or reordered event overwrites the current state with older data; compare timestamps or versions in the `WHERE`.
- Expecting `DO NOTHING` to report anything. It returns no row; use `DO UPDATE ... RETURNING` with the `xmax = 0` idiom, or check the row count of the event-table insert.
- `MERGE` as a concurrent upsert. Two sessions merging the same new key can get a unique violation; `MERGE` is for batch synchronisation, `ON CONFLICT` for concurrent single-row upserts.
- Loading millions of rows through an ORM. One statement per row, often one flush per row; `COPY` into staging and one set-based statement instead. From Java, `CopyManager`, or a JDBC batch with `reWriteBatchedInserts=true` (item 10.1).

## Check yourself

1. Why is `INSERT ... ON CONFLICT DO NOTHING` safe against two consumers inserting the same event at the same moment, while `SELECT` followed by `INSERT` is not?
2. A "current value" table is maintained with `DO UPDATE SET temperature = EXCLUDED.temperature`. An old event is redelivered. What goes wrong, and which single clause fixes it?
3. You must delete the products that disappeared from the supplier feed as well as insert and update the rest. Which statement expresses that, and which PostgreSQL version do you need for it?
4. A nightly import of five million rows runs one `INSERT` per row inside a transaction. Name the two changes you would make and describe how the data flows afterwards.

## Go deeper

- [PostgreSQL: INSERT](https://www.postgresql.org/docs/current/sql-insert.html) · the `ON CONFLICT` clause in full: conflict targets, `EXCLUDED`, the partial-index predicate and `RETURNING`.
- [PostgreSQL: MERGE](https://www.postgresql.org/docs/current/sql-merge.html) · syntax, clause evaluation order and the concurrency notes.
- [PostgreSQL: COPY](https://www.postgresql.org/docs/current/sql-copy.html) · formats, `ON_ERROR`, `LOG_VERBOSITY` and the file-permission rules.
- [PostgreSQL: Populating a Database](https://www.postgresql.org/docs/current/populate.html) · the official bulk-loading advice: `COPY`, dropping indexes during the load, `maintenance_work_mem`, `ANALYZE` afterwards.
- [Brandur: Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys) · the request-level version of the same idea (item 5.6).

---

Part of [Databases](../README.md) · item 1.5
