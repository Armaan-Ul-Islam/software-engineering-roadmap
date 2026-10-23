# Zero-downtime deployments and expand-contract database changes

> **In one sentence:** Every zero-downtime strategy runs two versions of the application against the same database at the same time, so a schema change has to be split into steps that both versions can live with: expand first, migrate the data, switch the code, and only then contract.

**Why it matters:** Rolling deploys are the default in Kubernetes, so the window in which old code runs against a new schema exists on every deploy whether you planned for it or not. The classic outage is `ERROR: column "phone" does not exist` from the Pods that have not been replaced yet, or an `ALTER TABLE` that waits for a lock while every request queues behind it. "Rename a column without downtime" is a favourite interview question because it tests exactly this.

## The idea

**Deployment strategies.**

| Strategy | How | Rollback | Price | Versions coexist |
|---|---|---|---|---|
| Rolling | replace Pods a few at a time (item 4.6) | `rollout undo`, minutes | nothing extra | for minutes, on every deploy |
| Blue/green | a second full environment; switch the router | switch back, seconds | double capacity during the switch | while green warms up and while blue waits as the rollback target |
| Canary | a small share of traffic to the new version, watch the SLIs, ramp up (Argo Rollouts, Flagger) | drop the canary | tooling and metrics discipline | for hours or days |
| Shadow | mirror live traffic to the new version, discard its responses | none needed | side effects must be suppressed | the shadow must not write |

Whatever the strategy, versions N and N+1 share the database for a while, and rolling back the code must work against the schema that N+1 already applied, because database rollbacks mean restoring a backup and losing data (item 6.4).

**Expand-contract (parallel change).** Split a breaking change into releases that are each backwards compatible:

1. Expand: add the new structure beside the old one (a nullable column, a new table). Both versions still work.
2. Migrate: backfill existing rows in batches, and keep old and new in sync while both are written: dual writes in the application, or a database trigger.
3. Switch: the new release reads and writes the new structure.
4. Contract: remove the old structure once no running version touches it.

Each step is its own release, and a step's migration must be compatible with the *previous* release's code, because it runs while that code is still serving.

**Flyway.** Versioned migrations `V<n>__<description>.sql` run in order, each in its own transaction (PostgreSQL DDL is transactional), and are recorded in `flyway_schema_history` with a checksum, so an applied migration is immutable. Spring Boot runs pending migrations at start-up, before the application accepts traffic, and Flyway takes a lock so that only one of several starting Pods applies them. A migration that fails leaves a failed entry that `flyway repair` removes before the retry. Flyway runs a migration containing statements that cannot run in a transaction, such as `CREATE INDEX CONCURRENTLY`, without a transaction; mixing those with ordinary statements in one file needs the `mixed` setting, so keep them in a file of their own.

**Lock-safe DDL in PostgreSQL.** Every `ALTER TABLE` takes an `ACCESS EXCLUSIVE` lock, which waits for every running transaction on the table and makes everything behind it wait too, so start with `SET LOCAL lock_timeout = '5s'` and retry rather than queue. What is cheap and what is not:

- `ADD COLUMN`, nullable or with a constant default, is a metadata change since PostgreSQL 11; `DROP COLUMN` likewise. The lock is brief.
- `CREATE INDEX CONCURRENTLY` builds without blocking writes; plain `CREATE INDEX` blocks them for the whole build. A failed concurrent build leaves an `INVALID` index to drop.
- Constraints: `ADD CONSTRAINT ... NOT VALID` takes the brief lock and checks only new rows; `VALIDATE CONSTRAINT` then scans with a `SHARE UPDATE EXCLUSIVE` lock that allows reads and writes. For `NOT NULL`, PostgreSQL 12 and later accepts a validated `CHECK (column IS NOT NULL)` as proof, so `SET NOT NULL` skips the table scan.
- Transactions hold locks until commit. Flyway wraps a migration in one transaction, so `NOT VALID` and `VALIDATE` in the same file hold the exclusive lock for the whole scan. Put them in separate migrations.
- Renaming a column is instant, and breaks the old code instantly. That is why it takes three releases.

## Example: renaming `customer.phone` to `phone_number` in three releases

**Release 1, expand.** Add the column and a trigger that keeps both columns equal whichever one a writer uses. No code change.

```sql
-- V12__add_phone_number.sql
SET LOCAL lock_timeout = '5s';

ALTER TABLE customer ADD COLUMN phone_number text;

CREATE OR REPLACE FUNCTION customer_sync_phone() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.phone_number IS NULL THEN
            NEW.phone_number := NEW.phone;
        ELSIF NEW.phone IS NULL THEN
            NEW.phone := NEW.phone_number;
        END IF;
    ELSIF NEW.phone IS DISTINCT FROM OLD.phone THEN
        NEW.phone_number := NEW.phone;
    ELSIF NEW.phone_number IS DISTINCT FROM OLD.phone_number THEN
        NEW.phone := NEW.phone_number;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER customer_sync_phone
BEFORE INSERT OR UPDATE ON customer
FOR EACH ROW EXECUTE FUNCTION customer_sync_phone();
```

Once release 1 is fully rolled out, backfill in batches from a job or a script, one transaction per batch, advancing the id range until `max(id)` and pausing if replication lag grows:

```sql
UPDATE customer SET phone_number = phone
WHERE id > 0 AND id <= 5000 AND phone_number IS NULL;
```

A single `UPDATE customer SET phone_number = phone` inside a Flyway migration would hold row locks on the whole table for the duration, bloat it, and keep the first new Pod from starting until it finished.

**Release 2, switch.** The entity maps the new column; nothing else changes.

```java
@Column(name = "phone_number")
private String phoneNumber;
```

During this rollout, release-1 Pods still write `phone` and the trigger fills `phone_number`; release-2 Pods write `phone_number` and the trigger fills `phone`. Both read consistent data. If `phone` was `NOT NULL`, carry the constraint over now, in three separate migrations so no lock is held during the scan:

```sql
-- V13__phone_number_not_null_check.sql
ALTER TABLE customer ADD CONSTRAINT customer_phone_number_not_null
    CHECK (phone_number IS NOT NULL) NOT VALID;

-- V14__phone_number_validate.sql
ALTER TABLE customer VALIDATE CONSTRAINT customer_phone_number_not_null;

-- V15__phone_number_set_not_null.sql
ALTER TABLE customer ALTER COLUMN phone_number SET NOT NULL;
ALTER TABLE customer DROP CONSTRAINT customer_phone_number_not_null;
```

**Release 3, contract.** Release-2 Pods never touch `phone`, so dropping it while they are still running is safe.

```sql
-- V16__drop_phone.sql
SET LOCAL lock_timeout = '5s';
DROP TRIGGER customer_sync_phone ON customer;
DROP FUNCTION customer_sync_phone();
ALTER TABLE customer DROP COLUMN phone;
```

Without the trigger, the application dual-writes instead: release 1 writes both columns, release 2 reads the new one, release 3 stops writing the old one, and only release 4 may drop it, because during the rollout of release 3 the release-2 Pods still write `phone`. The checklist for every release is the same three questions: does the migration work with the previous release's code, does this code work if the migration is rolled back, and does the previous code work against the new schema if we roll back?

## Pitfalls

- Rename, drop or change a type in one step during a rolling deploy. The old Pods fail with `column does not exist` until they are replaced, and `rollout undo` brings them back against the new schema.
- `ALTER TABLE` without `lock_timeout` behind a long-running transaction. The migration waits, every new query on the table waits behind it, and the whole application stalls until something times out.
- Backfilling millions of rows in one statement inside a migration. Start-up hangs, replicas lag, the table bloats, and if it fails Flyway needs `repair` before anything else can deploy.
- `CREATE INDEX` without `CONCURRENTLY` on a large table, or `CONCURRENTLY` in the same file as transactional statements.
- `SET NOT NULL` without the validated check constraint (or on PostgreSQL before 12): a full scan under an exclusive lock.
- `spring.jpa.hibernate.ddl-auto=update` in production. The schema becomes whatever Hibernate guesses, with no history and no review.
- Planning to "roll back the database". A restore is data loss; design every change so that the fix goes forward.

## Check yourself

1. Why does the trigger version need exactly three releases, and where does the dual-write version need a fourth?
2. What goes wrong if V13, V14 and V15 are one migration file?
3. During the rollout of release 2, a release-1 Pod inserts a customer with only `phone` set. Trace the row through the trigger; which columns are set when the transaction commits, and does the `NOT NULL` constraint from V15 get in the way?
4. A migration file contains both `CREATE INDEX CONCURRENTLY` and an `ALTER TABLE`. What does Flyway do, and how do you restructure it?

## Go deeper

- [Martin Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html) · expand, migrate, contract as a general refactoring pattern.
- [Flyway documentation](https://documentation.red-gate.com/flyway) and [Flyway: Migration transaction handling](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/migration-transaction-handling) · versioned migrations, and how non-transactional statements are treated.
- [PostgreSQL: ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) · which forms rewrite the table, which only touch metadata, and the `NOT VALID` and `VALIDATE` forms.
- [PostgreSQL: Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) · the lock modes each DDL statement takes and which ones conflict.
- [PostgreSQL: Building indexes concurrently](https://www.postgresql.org/docs/current/sql-createindex.html#SQL-CREATEINDEX-CONCURRENTLY) · the exact semantics and failure modes of `CONCURRENTLY`.
- [Martin Fowler: Blue Green Deployment](https://martinfowler.com/bliki/BlueGreenDeployment.html) and [Canary Release](https://martinfowler.com/bliki/CanaryRelease.html) · the two strategies and their database caveats.

---

Part of [DevOps & Delivery](../README.md) · items 6.1, 6.2
