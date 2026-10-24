# PostgreSQL data types that matter, and modelling the hard things

> **In one sentence:** Use `numeric` for money, `text` for strings, `timestamptz` for instants, `date` for dates, `uuid` for UUIDs, `jsonb` rather than `json`, arrays and ranges where they match the domain, and a `CHECK` or lookup table rather than an enum you will need to change; every wrong choice has a specific failure you can reproduce.

**Why it matters:** A column type is the one decision every row, index and query inherits, and the failures are quiet: a float total that is off by a cent, a timestamp that moves an hour when a server's time zone changes, a status enum nobody can remove a value from. "`timestamp` or `timestamptz`?" and "how do you store money?" are near-certain interview questions, and soft deletes, audit trails and hierarchies are where otherwise clean schemas go wrong.

## The idea

| Need | Use | Not | What goes wrong otherwise |
|---|---|---|---|
| Money and anything that must add up | `numeric(14,2)` plus a currency column (or integer minor units) | `float8`, `real`, `money` | binary floats cannot represent 0.1; `money` is formatted by the server's `lc_monetary` |
| Strings | `text`, with a `CHECK` on length if the business has one | `varchar(255)`, `char(n)` | an arbitrary limit fails loudly years later; `char(n)` pads with spaces |
| A point in time | `timestamptz` | `timestamp` | `timestamp` is a wall-clock reading with no zone; its meaning depends on who reads it |
| A calendar date | `date` | `timestamp` at midnight | daylight-saving arithmetic |
| External identifiers | `uuid` | `text` or `varchar(36)` | 16 bytes against 40, and no validation |
| Small fixed set of codes | `text` with `CHECK (status IN (...))`, or a lookup table and a foreign key | `enum` | values cannot be dropped; a new value cannot be used in the transaction that adds it |
| Several values per row | an array such as `text[]`, indexed with GIN | comma-separated text | `LIKE '%new%'` matches `renewal` |
| Semi-structured attributes | `jsonb` | `json`, or a `text` column | `json` keeps duplicate keys and whitespace and cannot be indexed |
| Periods | `daterange` or `tstzrange` with an exclusion constraint | two columns and `BETWEEN` | `BETWEEN` includes both ends, so adjacent periods overlap on the boundary day |

**Floats and money.** `float8` stores base-2 fractions; 0.1 is already an approximation and the errors accumulate. `numeric` is exact decimal arithmetic at any scale. Keep a currency code beside every amount, because amounts in different currencies do not add.

**`text`, `varchar(n)` and `char(n)`.** PostgreSQL stores all three the same way and the documentation is explicit that there is no performance difference. `varchar(n)` only adds a rejection at n characters, and `char(n)` pads with spaces that it then ignores in comparisons and strips on conversion. Use `text` and express a real business limit as a constraint, which also says *why* the limit exists.

**`timestamptz` is an instant, not "a timestamp with a zone".** It stores a point on the UTC timeline; the input is interpreted using the explicit offset or the session's `timezone`, and the output is formatted in the session's zone. `timestamp` stores the digits you typed and never converts them, so every client and server that touches the column must agree on a zone that is written down nowhere. Record instants as `timestamptz`. For a future appointment at a local wall-clock time, store the local time and the IANA zone name (`Europe/Oslo`) and compute the instant when needed, because the zone's rules may change before the date arrives. `interval '1 day'` follows the calendar across a daylight-saving change; `interval '24 hours'` does not.

**`uuid`.** Sixteen bytes, validated on input; the text form is 40 bytes including the header and compares slower. Generate with `uuidv7()` (PostgreSQL 18; `gen_random_uuid()` gives a random v4 on older versions). Item 8.2 explains why time-ordered UUIDs are kinder to indexes.

**Enums.** Compact, and sorted in declaration order rather than alphabetically, which makes `ORDER BY status` meaningful. But values can be added (`ALTER TYPE ... ADD VALUE`, which must be committed before the value is used) and renamed, never dropped, and the set of values lives in the type rather than in data. Use them for sets that genuinely never change; otherwise `text` with a `CHECK`, or a lookup table when the codes carry attributes such as a label or a sort order.

**Arrays, `jsonb` and ranges.** Arrays suit tags and short lists queried with `@>` or `= ANY` and indexed with GIN (item 3.4), not relationships you join on. `jsonb` is parsed, de-duplicated and indexable; `->` returns `jsonb` and `->>` returns `text`, so compare numbers as numbers (item 8.6 is about when `jsonb` belongs in a schema at all). A range carries its bounds (`[)` by default), `@>` tests containment, `&&` overlap, and an exclusion constraint forbids overlapping rows (item 8.3).

**Modelling the hard things.**

1. **Time.** Instants as `timestamptz`, dates as `date`, `created_at timestamptz NOT NULL DEFAULT now()`. Inside a transaction `now()` is the transaction's start time; `clock_timestamp()` is the current time.
2. **Money.** `numeric` plus currency, or integer minor units when fractions of a cent must be impossible. Round once, where the business rule says, and store the rounded result.
3. **Soft deletes versus archival.** A `deleted_at timestamptz` keeps history and makes undelete trivial, but every query must filter on it, uniqueness needs a partial unique index `WHERE deleted_at IS NULL`, and foreign keys still point at deleted rows. Archiving moves rows to a separate table in one statement (`WITH moved AS (DELETE ... RETURNING *) INSERT INTO ..._archive SELECT * FROM moved`) and keeps the live table honest. Soft delete when undelete is a feature; archive when retention is the requirement.
4. **Audit trails.** An append-only table with who, when, the old row and the new row as `jsonb`, written by a trigger (catches every writer) or by the application (knows the business reason). Never update an audit row; prune by time, ideally with partitioning (item 7.4).
5. **Hierarchies.** An adjacency list (`parent_id`) with a recursive CTE (item 1.3) covers most cases; a materialised path (`ltree`) when subtree reads dominate; a closure table when both ancestor and descendant queries must be fast and writes are rare.
6. **Many-to-many.** An association table with a composite primary key `(order_id, product_id)`, an index on the second column, and the attributes of the relationship (quantity) stored in it.

## Example: the anomalies, reproduced

PostgreSQL 18, session time zone `Europe/Oslo` unless stated.

```sql
SELECT 0.1::float8 + 0.2::float8 = 0.3 AS float_equal,      -- f
       sum(0.10::float8) AS float_total,                     -- 0.9999999999999999
       sum(0.10::numeric) AS numeric_total                   -- 1.00
FROM generate_series(1, 10);
SELECT 19.999::numeric(14,2);                                -- 20.00, rounded silently
```

```sql
CREATE TABLE t (naive timestamp, instant timestamptz);
INSERT INTO t VALUES ('2026-10-24 12:00', '2026-10-24 12:00');
SET timezone = 'America/New_York';
SELECT * FROM t;
--  2026-10-24 12:00:00 | 2026-10-24 06:00:00-04      same instant, correctly shown; the naive value just sits there
SET timezone = 'Europe/Oslo';
SELECT timestamptz '2026-03-28 12:00' + interval '1 day', timestamptz '2026-03-28 12:00' + interval '24 hours';
--  2026-03-29 12:00:00+02 | 2026-03-29 13:00:00+02      daylight saving started that night
SELECT timestamp '2026-03-29 02:30';                     -- accepted, although that local time never existed in Oslo
```

```sql
CREATE TYPE order_status AS ENUM ('pending', 'paid', 'shipped');
ALTER TYPE order_status DROP VALUE 'shipped';
-- ERROR:  dropping an enum value is not implemented
BEGIN;
ALTER TYPE order_status ADD VALUE 'refunded';
INSERT INTO t_enum VALUES ('refunded');
-- ERROR:  unsafe use of new value "refunded" of enum type order_status
-- HINT:  New enum values must be committed before they can be used.
```

```sql
SELECT '{"price": 10}'::jsonb ->> 'price' > '9' AS as_text,              -- f: '10' < '9' as strings
       ('{"price": 10}'::jsonb ->> 'price')::numeric > 9 AS as_number;   -- t
SELECT 'renewal,sale' LIKE '%new%' AS csv_match, ARRAY['renewal', 'sale'] @> ARRAY['new'] AS array_match;   -- t | f
SELECT date '2026-02-01' BETWEEN date '2026-01-01' AND date '2026-02-01' AS in_january,
       date '2026-02-01' BETWEEN date '2026-02-01' AND date '2026-03-01' AS in_february;                    -- t | t
SELECT daterange('2026-01-01', '2026-02-01') @> date '2026-02-01';                                         -- f
```

Soft delete with the partial unique index:

```sql
CREATE TABLE account (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, email text NOT NULL, deleted_at timestamptz);
CREATE UNIQUE INDEX account_live_email_idx ON account (email) WHERE deleted_at IS NULL;
INSERT INTO account (email) VALUES ('alice@example.com');
UPDATE account SET deleted_at = now() WHERE email = 'alice@example.com';
INSERT INTO account (email) VALUES ('alice@example.com');       -- ok: Alice registers again
INSERT INTO account (email) VALUES ('alice@example.com');
-- ERROR:  duplicate key value violates unique constraint "account_live_email_idx"
```

## Example: a DDL that gets each choice right

```sql
CREATE TABLE currency (code text PRIMARY KEY CHECK (code ~ '^[A-Z]{3}$'), minor_units int NOT NULL);

CREATE TABLE purchase (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    public_id     uuid NOT NULL DEFAULT uuidv7() UNIQUE,
    customer_id   bigint NOT NULL,
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    amount        numeric(14,2) NOT NULL CHECK (amount >= 0),
    currency_code text NOT NULL REFERENCES currency (code),
    tags          text[] NOT NULL DEFAULT '{}',
    attributes    jsonb NOT NULL DEFAULT '{}',
    placed_at     timestamptz NOT NULL DEFAULT now(),
    delivery_date date,
    deleted_at    timestamptz,
    CHECK (deleted_at IS NULL OR status = 'cancelled')
);
CREATE INDEX purchase_tags_idx ON purchase USING gin (tags);

CREATE TABLE purchase_audit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purchase_id bigint NOT NULL,
    changed_at  timestamptz NOT NULL DEFAULT now(),
    changed_by  text NOT NULL DEFAULT current_user,
    old_row     jsonb,
    new_row     jsonb
);

CREATE TABLE price_list (
    product_id bigint NOT NULL,
    valid      daterange NOT NULL,
    price      numeric(12,2) NOT NULL,
    EXCLUDE USING gist (product_id WITH =, valid WITH &&)       -- needs CREATE EXTENSION btree_gist
);
INSERT INTO price_list VALUES (1, daterange('2026-01-01', '2026-07-01'), 99.00),
                              (1, daterange('2026-07-01', NULL), 109.00);
INSERT INTO price_list VALUES (1, daterange('2026-06-01', '2026-08-01'), 104.00);
-- ERROR:  conflicting key value violates exclusion constraint "price_list_product_id_valid_excl"
SELECT price FROM price_list WHERE product_id = 1 AND valid @> date '2026-10-24';    -- 109.00
```

The status is a `CHECK` rather than an enum, so adding `refunded` is `ALTER TABLE ... DROP CONSTRAINT` and `ADD CONSTRAINT` in one ordinary migration. The audit table is filled by a trigger or by the service that changes a purchase; the price list cannot contain two prices for the same day.

## Pitfalls

- `timestamp` because "we store everything in UTC anyway". The agreement lives in people's heads; the first client with a different JVM or session time zone writes values an hour off and nothing complains.
- `numeric(14,2)` rounding on insert. `19.999` becomes `20.00` without an error; round deliberately in the statement or the application and treat the column's scale as a safety net.
- Enum migrations in one transaction. `ALTER TYPE ... ADD VALUE` followed by an `UPDATE` that uses the value fails with `unsafe use of new value`; split them into two migrations, or use `text` with a `CHECK`.
- Soft deletes without the partial unique index. Either a deleted user can never register again or two live rows share an email; and one forgotten `WHERE deleted_at IS NULL` leaks deleted data.
- `BETWEEN` on timestamps. `BETWEEN '2026-10-01' AND '2026-10-31'` loses the whole last day except midnight; use `>= start AND < next_start`, or a range.

## Check yourself

1. Ten rows of `0.10` sum to `0.9999999999999999` as `float8` and to `1.00` as `numeric`. Explain why, and state the general rule for choosing between them.
2. An application in Oslo writes `2026-10-24 12:00` into a `timestamp` column and a report server in New York reads it. What time does each believe the event happened, and how does `timestamptz` change that?
3. A migration runs `ALTER TYPE ... ADD VALUE 'refunded'` and then `UPDATE ... SET status = 'refunded'` in one transaction. What happens, and what are two ways out?
4. A soft-deleted `account` row shares its email with a new live account. Which constraint allows that while still forbidding two live accounts with the same email, and what else must every query on the table remember?

## Go deeper

- [PostgreSQL: Data Types](https://www.postgresql.org/docs/current/datatype.html) · the chapter; read Numeric Types and Character Types in full.
- [PostgreSQL: Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html) · exactly how `timestamptz` input and output are converted, and the `interval` rules.
- [PostgreSQL: Range Types](https://www.postgresql.org/docs/current/rangetypes.html) · bounds, operators and the exclusion-constraint example.
- [PostgreSQL: Enumerated Types](https://www.postgresql.org/docs/current/datatype-enum.html) · ordering, `ADD VALUE` and its restrictions.
- [PostgreSQL: JSON Types](https://www.postgresql.org/docs/current/datatype-json.html) · `json` versus `jsonb` and the operators.
- [PostgreSQL wiki: Don't Do This](https://wiki.postgresql.org/wiki/Don%27t_Do_This) · the anti-pattern list, with the reasoning behind each row of the table above.

---

Part of [Databases](../README.md) · items 1.4, 8.4
