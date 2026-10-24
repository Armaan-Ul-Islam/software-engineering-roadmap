# CQRS and event sourcing, honestly

> **In one sentence:** CQRS means using a different model to update data than to read it, which can be as small as a few denormalised read tables; event sourcing means storing the sequence of events that happened as the source of truth and deriving current state from it; each buys specific things (read models shaped for screens, a complete history, replay) at a steady price (eventual consistency, schema that lives forever, projection plumbing), and most systems should pay neither.

**Why it matters:** These two patterns are the ones most often adopted for the wrong reason and regretted a year later, when the team is maintaining upcasters for events nobody reads and explaining to users why their change is not visible yet. They are also exactly right for ledgers, audit-heavy domains and systems that must answer "what did this look like on 3 March". Knowing the difference, and the simple versions that deliver most of the value, is the honest form of the knowledge.

## The idea

**CQRS: separate read and write models.** Command Query Responsibility Segregation starts from the observation that the model that is good for enforcing business rules on a write (an `Order` aggregate that checks stock, limits and state transitions) is a poor model for a screen that needs an order list joined with customer names and shipment status. So use two: commands go to the write model, which validates and persists; queries go to read models, each shaped for one view. The simple version uses one database: the write model owns the normalised tables, and the read models are SQL views, materialised views, or denormalised tables updated in the same transaction or by a trigger. The fuller version keeps read models in separate stores (Elasticsearch for search, Redis for a dashboard, a replica for reports) fed asynchronously from the write side's events. Fowler's warning stands: CQRS fits a bounded context with a real mismatch between how data is changed and how it is viewed, and applying it everywhere adds complexity for nothing.

**Event sourcing: events as the source of truth.** Instead of storing the current state of an account and overwriting it, store `AccountOpened`, `MoneyDeposited`, `MoneyWithdrawn` as an append-only stream per aggregate. Current state is a fold over the stream: load the events, apply them in order, decide whether the new command is allowed, append the new event. Nothing is ever updated or deleted. Four mechanisms make it workable:

1. Projections: consumers that read the events and maintain read models (a balance table, a monthly statement, a search index). This is where CQRS and event sourcing meet, because an event-sourced write model has no queryable current state without projections.
2. Snapshots: a stored state at version N so that loading an aggregate with 200,000 events replays only the events after the snapshot. An optimisation, not a source of truth; it can always be rebuilt.
3. Replay: rebuild any projection from scratch by reading the stream from the beginning, which fixes projection bugs, creates new read models retroactively, and makes "what was the state at time T" a question with an answer.
4. Optimistic concurrency: the append carries the version the writer expected; a uniqueness constraint on `(stream_id, version)` rejects a concurrent writer, with no locks.

**What they buy.** A complete, trustworthy history (the audit log *is* the data, not a side effect that can be out of step). Temporal queries and retroactive read models. Read models per screen, in whatever store suits each, scaled independently of writes. A write model that only handles commands and invariants. Debugging by replaying production events against a fix. Natural fit for domains that are already event-shaped: ledgers, bookings, trading, inventory movements, anything a regulator may ask about.

**What they cost.** Eventual consistency between the write side and every asynchronous read model, which users see as "I saved it and the list does not show it" unless you handle read-your-writes (see item 3.3). Event schemas that can never be changed, only versioned and upcast, because the old events are the data. No ad-hoc queries over current state without a projection. Deletion is hard (a right-to-erasure request against an immutable log means encrypting personal data per subject and discarding the key, called crypto-shredding). Getting aggregate boundaries wrong is expensive, because splitting a stream means migrating history. Operational tooling you must build or buy: replay, projection rebuild, idempotent projectors (see item 3.8), monitoring of projection lag. And the learning curve: every developer on the team must think in events.

**When neither is justified.** A CRUD domain with forms over tables, no audit requirement beyond "who changed it last", one team, and read shapes close to write shapes. There, a relational schema with a few views is CQRS enough, and an `updated_by, updated_at` pair plus a history table where it matters is event sourcing enough. The honest signals that the full patterns pay for themselves: a legal or financial need for the complete history; frequent questions about past states; several read models with very different shapes and loads; a collaborative domain where detecting conflicting concurrent changes matters; or a domain whose experts already talk in events. One of these is a reason to consider it; none is a reason not to.

## Example: a small event-sourced account

The event store as a PostgreSQL table, with the version in the primary key for optimistic concurrency:

```sql
CREATE TABLE event (
    stream_id       text        NOT NULL,
    version         int         NOT NULL,
    event_type      text        NOT NULL,
    schema_version  int         NOT NULL DEFAULT 1,
    payload         jsonb       NOT NULL,
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (stream_id, version)
);

INSERT INTO event (stream_id, version, event_type, schema_version, payload) VALUES
    ('acc-1', 1, 'AccountOpened',  1, '{"owner": "Ada", "currency": "EUR"}'),
    ('acc-1', 2, 'MoneyDeposited', 1, '{"amount": "100.00"}'),
    ('acc-1', 3, 'MoneyWithdrawn', 2, '{"amountMinor": 3000}');
```

A command handler that wants to withdraw more loads the three events, replays them to a balance of 70.00, checks the rule, and appends version 4. Another handler that loaded the same three events and tries to append its own version 4 gets a primary-key violation and must reload and retry; that is the whole concurrency story.

The fold in Java, with the three events already upcast to the current schema:

```java
import java.util.List;

public final class AccountReplay {

    sealed interface AccountEvent permits AccountOpened, MoneyDeposited, MoneyWithdrawn {}

    record AccountOpened(String accountId, String owner, String currency) implements AccountEvent {}

    record MoneyDeposited(String accountId, long amountMinor) implements AccountEvent {}

    record MoneyWithdrawn(String accountId, long amountMinor) implements AccountEvent {}

    record AccountBalance(String accountId, String currency, long balanceMinor) {

        AccountBalance apply(AccountEvent event) {
            return switch (event) {
                case AccountOpened opened -> new AccountBalance(opened.accountId(), opened.currency(), 0);
                case MoneyDeposited deposited -> new AccountBalance(accountId, currency, balanceMinor + deposited.amountMinor());
                case MoneyWithdrawn withdrawn -> new AccountBalance(accountId, currency, balanceMinor - withdrawn.amountMinor());
            };
        }
    }

    static AccountBalance replay(List<AccountEvent> events) {
        AccountBalance state = new AccountBalance(null, null, 0);
        for (AccountEvent event : events) {
            state = state.apply(event);
        }
        return state;
    }

    public static void main(String[] arguments) {
        List<AccountEvent> stream = List.of(
                new AccountOpened("acc-1", "Ada", "EUR"),
                new MoneyDeposited("acc-1", 10_000),
                new MoneyWithdrawn("acc-1", 3_000));
        AccountBalance balance = replay(stream);
        System.out.printf("%s %s %d.%02d%n", balance.accountId(), balance.currency(),
                balance.balanceMinor() / 100, balance.balanceMinor() % 100);
    }
}
```

```text
acc-1 EUR 70.00
```

The projection is the same fold run continuously by a projector that reads events in order and writes a read table:

```sql
CREATE TABLE account_balance (
    account_id    text PRIMARY KEY,
    currency      text NOT NULL,
    balance_minor bigint NOT NULL,
    last_version  int NOT NULL
);
```

The projector applies an event only if `event.version = last_version + 1`, which makes redelivery harmless and gaps detectable. A new read model (monthly statements, say) is a new projector started from version 1 of every stream; nothing on the write side changes.

**The schema-evolution problem.** Version 2 of `MoneyDeposited` in the table above has `amount` as a decimal string in major units; the team later switched to integer minor units because string decimals were being parsed inconsistently, and new events carry `amountMinor` with `schema_version` 2. The old event cannot be edited: it is the record of what happened, and rewriting it would invalidate every projection and audit built on it. The solution is an upcaster in the read path that turns a version-1 payload into a version-2 one as it is loaded (`"100.00"` becomes `10000` for a two-decimal currency), so the fold only ever sees the current shape. Upcasters accumulate for the life of the system, which is why event schemas deserve more design care than table columns. And when an event itself was wrong (a deposit recorded against the wrong account), it is not deleted; a compensating event (`DepositReversed`) is appended, exactly as an accountant would.

## Pitfalls

- Adopting event sourcing for the audit log alone. If nothing else needs the history, an append-only history table beside the current-state table gives the audit at a fraction of the cost.
- CQRS as "two databases" by reflex. Views and denormalised tables in the same database are CQRS; separate stores are justified only by a separate need (search, scale, a different shape).
- Forgetting read-your-writes. The user saves, the list is refreshed from a lagging projection, the row is missing; handle it by reading the write side after a command, by returning the new version and waiting for the projection to reach it, or by updating the UI from the command's result.
- Events that mirror CRUD (`AccountUpdated` with the whole row). They carry no meaning, cannot drive rules, and make projections guess what changed; events are named for business facts.
- Snapshots as truth. A snapshot with a bug poisons every load until it is rebuilt; keep them disposable and rebuildable.
- Using a message broker as the event store. Kafka keeps a log but cannot load one aggregate's stream efficiently or enforce an expected version on append; the store needs per-stream reads and a uniqueness constraint.
- Large aggregates. An account with millions of events is a sign the stream boundary is wrong (a stream per account per year, or a different aggregate), not a reason for more snapshots.
- Underestimating deletion. Personal data in immutable events needs crypto-shredding designed in from the start; retrofitting it is a migration of the entire history.

## Check yourself

1. Your product is an internal CRM with forms, lists and "last modified by". Which parts of CQRS and event sourcing, if any, pay for themselves here, and what would you do instead?
2. Two handlers load account `acc-1` at version 3 and both try to withdraw. Explain exactly how the table definition prevents a double withdrawal without any lock.
3. A projection bug has shown wrong balances for a week. What do you do, and why is this easier in an event-sourced system than in a state-based one?
4. You need to rename the `amount` field of an event that has three years of history. Walk through the options and say which one preserves the audit trail.

## Go deeper

- [Fowler: CQRS](https://martinfowler.com/bliki/CQRS.html) · the definition, the simple forms, and the warning about using it beyond a bounded context.
- [Fowler: Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) · the original pattern description with its consequences spelt out.
- [Greg Young: Versioning in an Event Sourced System](https://leanpub.com/esversioning) · upcasting, weak schemas, copy-and-transform migrations and the cases where you do rewrite (free to read online).
- [Microsoft Azure Architecture Center: Event Sourcing pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/event-sourcing) · a sober treatment of the pattern with its issues and considerations listed.
- [Microsoft Azure Architecture Center: CQRS pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/cqrs) · when to use it and when not to, with the event-sourcing combination.

---

Part of [System Design](../README.md) · item 5.4
