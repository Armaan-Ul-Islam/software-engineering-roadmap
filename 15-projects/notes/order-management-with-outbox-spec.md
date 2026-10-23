# Project spec: order management with real transactions and an outbox

> **In one sentence:** Build a small order service whose correctness you can prove under concurrency and failure: optimistic locking, idempotency keys, a transactional outbox to Kafka, and a consumer with retries and a dead-letter topic.

**Why it matters:** This project exercises the ideas that separate working services from correct ones: isolation anomalies, idempotency, the dual-write problem and at-least-once delivery. Every one of them shows up in senior interviews, and every one of them is best learned by reproducing the failure first and fixing it second.

## The idea

You will build one Spring Boot service, `orders`, with a PostgreSQL database and a Kafka topic, plus one consumer, `inventory`, that reserves stock when an order is placed. The point is not the features. The point is the five proofs listed under "Definition of done", each of which is a test you can run.

Scope, deliberately small:

- 1.1 `POST /orders` creates an order with lines; `POST /orders/{id}/cancel` cancels it; `GET /orders/{id}` reads it.
- 1.2 Each order has a `version` for optimistic locking and a `status` that moves `PLACED` to `RESERVED` to `CANCELLED` or `FAILED`.
- 1.3 Placing an order writes an `OrderPlaced` event to an `outbox` table in the same transaction. A relay publishes outbox rows to Kafka and marks them sent.
- 1.4 `inventory` consumes `OrderPlaced`, reserves stock in its own PostgreSQL schema, and publishes `StockReserved` or `StockRejected`. It must be idempotent: the same event delivered twice reserves stock once.
- 1.5 `orders` consumes the inventory events and moves the order to `RESERVED` or `FAILED`.

Concepts exercised: Databases 5.2, 5.3, 6.1, 6.4; Spring 4.3, 5.8, 9.1, 9.3; System Design 3.7, 3.8, 4.1, 4.4; DevOps & Delivery 3.5.

## Example: the data model and the proofs

```sql
CREATE TABLE orders (
    id              uuid PRIMARY KEY,
    customer_id     uuid        NOT NULL,
    status          text        NOT NULL CHECK (status IN ('PLACED', 'RESERVED', 'CANCELLED', 'FAILED')),
    total_minor     bigint      NOT NULL CHECK (total_minor >= 0),
    version         bigint      NOT NULL DEFAULT 0,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE idempotency_keys (
    key             text        PRIMARY KEY,
    request_hash    text        NOT NULL,
    response_status int,
    response_body   jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE outbox (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_id    uuid        NOT NULL,
    event_type      text        NOT NULL,
    payload         jsonb       NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    sent_at         timestamptz
);
CREATE INDEX outbox_unsent_idx ON outbox (id) WHERE sent_at IS NULL;
```

Milestones, each ending in a committed test:

1. **Lost update, reproduced and fixed.** Write a test that loads the same order in two threads, changes it, and saves both. Without `@Version` the second save silently wins. Add `@Version`; the test now expects `ObjectOptimisticLockingFailureException` on one side. Then add a retry outside the transaction and assert both changes apply.
2. **Idempotent create.** `POST /orders` requires an `Idempotency-Key` header. Store the key, the request hash and the response in `idempotency_keys` inside the same transaction as the order. A replay returns the stored response; a replay with a different body returns `422`. Prove it with two concurrent identical requests (`CountDownLatch`), which must produce exactly one order. The unique constraint on `key` is what makes the race safe; handle the constraint violation by returning the stored response.
3. **Outbox instead of dual write.** First write the naive version: save the order, then publish to Kafka in the same method. Kill Kafka (stop the container) and show that orders exist with no event. Then move publication into the `outbox` table and a relay that polls `SELECT ... WHERE sent_at IS NULL ORDER BY id LIMIT 100 FOR UPDATE SKIP LOCKED`. Stop Kafka again: orders still succeed, and events flow when Kafka returns.
4. **Idempotent consumer.** Deliver the same `OrderPlaced` twice to `inventory` (Kafka does this under rebalances; you can also just re-send). Stock must be reserved once. Store processed event IDs in a `processed_events` table in the same transaction as the reservation.
5. **Retries and dead letters.** Make `inventory` fail for one poison message (for example a product that does not exist). Configure a retry with backoff and a dead-letter topic. Prove that the poison message ends in the dead-letter topic and that the messages behind it are still processed.

Definition of done:

- 2.1 All five milestone tests pass with Testcontainers for PostgreSQL and Kafka.
- 2.2 `docker compose up` starts both services, PostgreSQL and Kafka, and a `curl` script walks through place, reserve and cancel.
- 2.3 The README documents each proof with the failure you saw first and the fix.
- 2.4 Micrometer exposes a counter for outbox lag (unsent rows) and the consumer records processing time; both appear on a Grafana dashboard or at least on `/actuator/prometheus`.

Stretch goals:

- 3.1 Replace the polling relay with Debezium change data capture and compare latency and complexity.
- 3.2 Add a saga: if stock is rejected, refund a (fake) payment through a compensating action, and make the whole flow survive a crash between steps.
- 3.3 Run the create endpoint under load with k6 and find the connection-pool size at which throughput stops improving.

## Pitfalls

- Testing idempotency with sequential requests only. The bug is in the concurrent case; always include the latch-based test.
- Retrying inside the transaction. An `OptimisticLockException` marks the transaction rollback-only; the retry must wrap the transactional method from outside (a separate bean or a `TransactionTemplate` loop).
- Relying on `@Transactional` on the test to clean up. It hides flush problems and `LazyInitializationException`; use Testcontainers with a fresh schema per test class and explicit cleanup instead.
- Publishing from the outbox without ordering. Order rows by `id` and use a single relay per partition key range, or accept that cross-order ordering is not guaranteed and design consumers accordingly.
- Marking the outbox row sent before Kafka acknowledges. Wait for the producer's acknowledgement (`acks=all`) before updating `sent_at`; a crash in between produces a duplicate, which the idempotent consumer absorbs, never a loss.
- Letting the consumer's processed-event table grow forever. Add a retention job or a time-based partition.

## Check yourself

1. Why must the idempotency key, the order and the outbox row be written in the same database transaction, and what breaks if any one of them is written separately?
2. Under what delivery guarantee does Kafka hand `OrderPlaced` to `inventory`, and which table makes "exactly-once effects" true anyway?
3. Your relay crashed after sending to Kafka but before updating `sent_at`. What happens next, and why is that acceptable?
4. A reviewer suggests dropping `@Version` because "the UI never edits the same order twice". Which test do you show them?

## Go deeper

- [microservices.io: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) · the pattern and its variants.
- [Debezium: Reliable data exchange with the outbox pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/) · the CDC version for the stretch goal.
- [Brandur: Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys) · the design behind milestone 2.
- [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/) · retry topics, dead-letter publishing and acknowledgement modes.
- [Baeldung: Optimistic Locking in JPA](https://www.baeldung.com/jpa-optimistic-locking) · `@Version` mechanics for milestone 1.

---

Part of [Projects](../README.md) · item 2.2
