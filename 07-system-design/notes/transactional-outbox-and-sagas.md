# Transactional outbox and sagas

> **In one sentence:** You cannot atomically write to your database and publish to a message broker, so you write the message into your own database in the same transaction (the outbox) and let a relay publish it; and when a business operation spans several services, you replace the impossible distributed transaction with a saga, a sequence of local transactions each of which has a compensating action.

**Why it matters:** Every service that both saves state and tells others about it has the dual-write problem, and most teams discover it as "the order exists but inventory never heard about it" at 3 a.m. Two-phase commit looks like the answer and is not; the outbox plus sagas is how production systems keep services consistent without sharing a database or a transaction.

## The idea

**The dual-write problem.** A service saves an order and publishes `OrderPlaced`. Save first, then publish: a crash in between produces an order nobody knows about. Publish first, then save: the save fails and consumers act on an order that does not exist. Wrapping both in a database transaction does not help, because the broker is not part of it; a Kafka send inside `@Transactional` is not rolled back with the database.

**The transactional outbox.** Write the event into an `outbox` table in the same local transaction as the business change. Either both commit or neither does. A separate component then moves outbox rows to the broker:

1. A polling relay: a loop that selects unpublished rows, publishes them, and marks them published (or deletes them). Simple, works with any database and broker. Select with `FOR UPDATE SKIP LOCKED` if several relay instances run, and track state per row (`published_at IS NULL`) rather than a "last published id" cursor, because a row with a lower id can commit after a row with a higher id has already been published and a cursor would skip it.
2. Change data capture: Debezium reads the database's write-ahead log and streams each committed outbox insert to Kafka, in commit order, with no polling and no extra load on the table. Its outbox event router routes rows to topics by aggregate type and uses the aggregate id as the Kafka key.

Either way delivery is at-least-once: a relay that publishes and crashes before marking the row will publish again. Consumers must therefore deduplicate on the event id (see item 3.8), and ordering is per aggregate (all events for order 42 on one partition, in commit order), never global.

**Two-phase commit, and why it is avoided.** 2PC gives atomic commit across participants: a coordinator asks everyone to prepare (write their changes durably and hold their locks), and if all vote yes, tells everyone to commit. The flaw is in the middle: a participant that has voted yes must wait for the coordinator's decision, holding its locks, for as long as it takes. If the coordinator crashes, every participant is stuck "in doubt" until it returns; application threads block, lock queues grow, and operators end up resolving transactions by hand. It also needs every participant to speak the protocol (XA), which Kafka and HTTP services do not. Inside a single database product, 2PC is fine; across services, it couples availability of everyone to everyone and is avoided.

**Sagas.** A saga splits the operation into local transactions, one per service, each committing on its own. If step N fails, the saga runs compensating transactions for steps N − 1 down to 1: not a rollback (those commits are visible and done) but a semantic undo, "release the reservation", "refund the charge". Two coordination styles:

- Choreography: each service reacts to the previous service's event and publishes its own. No central component; fine for two or three steps; beyond that, nobody can say where an order is or why it stopped, and cyclic dependencies appear.
- Orchestration: a saga orchestrator (a state machine persisted in the ordering service, or a workflow engine such as Temporal or Camunda) sends commands to each participant, records each reply, and decides what comes next, including compensation. Explicit, testable and observable; the orchestrator's state is just another table, so it is not a single point of failure.

Sagas have no isolation: other transactions see the intermediate states (an order that is placed but not yet paid). The countermeasures are design, not technology: mark records with a pending status (a semantic lock) so other code treats them accordingly, order the steps so the ones most likely to fail come first and the ones that cannot be compensated (sending the goods, emailing the customer) come last, and make every step and every compensation idempotent, because commands and events will be redelivered.

## Example: the outbox table and an order saga

```sql
CREATE TABLE outbox (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id       uuid        NOT NULL UNIQUE,
    aggregate_type text        NOT NULL,
    aggregate_id   text        NOT NULL,
    event_type     text        NOT NULL,
    payload        jsonb       NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    published_at   timestamptz
);

CREATE INDEX outbox_unpublished_idx ON outbox (id) WHERE published_at IS NULL;
```

Debezium's outbox router expects, by default, columns named `id`, `aggregatetype`, `aggregateid`, `type` and `payload`; either name them that way or map them in the connector configuration. With CDC the `published_at` column and the index are unnecessary, and the Debezium blog describes deleting each row right after inserting it in the same transaction, since only the insert needs to reach the log.

Placing an order with stock reservation and payment, orchestrated by the order service:

1. Order service, one transaction: insert `order` with status `PENDING`; insert outbox row `OrderPlaced` with `aggregate_id = 42`. Commit.
2. Relay publishes `OrderPlaced` to `order-events`, keyed by `42`.
3. The orchestrator (in the order service) consumes `OrderPlaced`, records saga step `RESERVING_STOCK`, and in the same transaction writes a `ReserveStock` command to its outbox.
4. Inventory service consumes `ReserveStock`. In one transaction: insert the command's event id into `processed_message` (a duplicate aborts here and the message is acknowledged without effect); decrement available stock; insert outbox row `StockReserved`, or `StockRejected` if there is not enough. Commit.
5. Orchestrator consumes `StockReserved`, moves to `CHARGING`, emits `ChargePayment` carrying the order id as the payment idempotency key.
6. Payment service charges the card through its provider using that key, records the payment, and emits `PaymentCharged` or `PaymentFailed`.
7. Happy path: the orchestrator consumes `PaymentCharged`, sets the order to `CONFIRMED`, emits `OrderConfirmed`; shipping and email react to that last event, because neither can be compensated.
8. Compensation path: on `PaymentFailed` the orchestrator emits `ReleaseStock`; inventory adds the quantity back (idempotently, keyed by the saga id) and emits `StockReleased`; the orchestrator sets the order to `CANCELLED` and emits `OrderCancelled`. If `StockRejected` arrived at step 4 there is nothing to compensate; the order is cancelled directly.

At every step the service's own state and the message it sends commit together, every message can arrive twice, and the only places money or goods move are after everything that could fail has succeeded.

## Pitfalls

- Publishing in the same `@Transactional` method as the write and calling it transactional. The send is not part of the transaction; this is the dual write with extra confidence.
- A relay with a "last id" cursor. Sequence gaps from concurrent transactions make it skip rows; track state per row or use CDC.
- Trusting outbox delivery to be exactly once. The relay will republish after a crash; consumers that do not deduplicate will double-process.
- Compensations that can fail and are not retried. A failed refund after a failed shipment is money kept by mistake; compensations need the same retry and alerting as the forward steps.
- Non-compensatable steps in the middle. Once the email is sent or the goods have left, there is no undo. Put those steps last.
- Letting the outbox table grow forever. Delete or archive published rows; the index on unpublished rows keeps polling cheap only if the table is pruned.

## Check yourself

1. Why does a database transaction around "insert order, send to Kafka" not solve the dual-write problem, and what exactly does the outbox change?
2. A polling relay tracks the highest id it has published. Describe the sequence of two transactions that makes it skip an event.
3. In the order saga, what happens if the inventory service receives `ReserveStock` twice, and which design choice makes that harmless?
4. Why is 2PC a poor fit between an order service and a payment service, even if both used databases that support XA?

## Go deeper

- [microservices.io: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) · the pattern with its polling and log-tailing variants.
- [Debezium: Reliable data exchange with the outbox pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/) · the CDC implementation end to end, including the event router.
- [Debezium: Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html) · the expected columns and configuration options.
- [microservices.io: Saga](https://microservices.io/patterns/data/saga.html) · choreography versus orchestration with the order example, and the countermeasures for missing isolation.
- [Pat Helland: Life Beyond Distributed Transactions](https://queue.acm.org/detail.cfm?id=3025012) · why large systems give up distributed transactions and what replaces them.
- [Garcia-Molina and Salem: Sagas (1987)](https://www.cs.cornell.edu/andru/cs711/2002fa/reading/sagas.pdf) · the original paper; short and still exactly right.

---

Part of [System Design](../README.md) · item 3.7
