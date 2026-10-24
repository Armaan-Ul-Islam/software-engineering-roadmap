# Event-driven architecture: choreography vs orchestration

> **In one sentence:** Asynchronous messaging trades the simple failure model of a request (it either answered or it did not) for decoupling in time and in knowledge, and the main decision inside it is whether a business process is driven by each service reacting to the previous one's events (choreography) or by one component that knows the whole process and tells the others what to do (orchestration).

**Why it matters:** Teams adopt events to decouple services and then cannot answer "where is order 42 and why has it stopped?", or they build an orchestrator that every other team must change for every feature. Both are the right pattern applied to the wrong kind of flow. The underlying skills (telling events from commands, versioning a schema that is already in production, tracing a request across a broker) are what make an event-driven system operable rather than merely eventual.

## The idea

**Synchronous versus asynchronous.** A synchronous call (HTTP, gRPC) blocks until the other service answers. Its virtues are its failure model and its simplicity: the caller gets a result or an error now, and the data it sees is current. Its costs are temporal coupling (both sides must be up at the same moment, so availabilities multiply, see item 1.1), latency that adds up along a chain, and cascading failure when a slow dependency ties up every caller's threads (see item 4.2). An asynchronous message goes through a broker (see item 2.7): the producer continues immediately, the consumer processes when it can, and a consumer that is down simply builds up a backlog. The costs move rather than vanish: delivery is at least once, so consumers must be idempotent (see item 3.8); ordering holds only per key; the producer gets no answer, so errors surface somewhere else; data read by consumers is as stale as the lag; and the producer must publish atomically with its own state change (the outbox, see item 3.7).

**Events versus commands.** An event is a fact about something that has already happened, named in the past tense (`OrderPlaced`), owned by the service where it happened, published without knowing who listens, and consumed by zero or many services. A command is a request for something to happen (`ReserveStock`), addressed to exactly one handler, which may reject it, and the sender cares about the outcome. Mixing them produces events that are really commands in disguise (`SendWelcomeEmail` published as an "event" with one intended consumer) and the coupling returns with worse tooling. Fowler's distinction between event notification (a small event, the consumer calls back for details, which couples it to the producer's API and adds load) and event-carried state transfer (the event carries the data the consumer needs, which gives autonomy at the cost of duplicated, possibly stale copies) is the other axis to decide.

**Choreography.** Each service subscribes to the events it cares about and publishes its own. There is no process definition anywhere; the process emerges from the subscriptions. Adding a consumer (search indexing, analytics, loyalty points) needs no change to anyone. The weaknesses appear when the flow has more than a few steps or needs compensation: nobody can say what state a given order is in without querying every service, reordering steps means editing subscriptions in several services, cycles creep in, and a step that silently stops (a consumer bug, a dead-letter queue filling) is noticed by customers before engineers.

**Orchestration.** One component owns the process: a persisted state machine per instance (per order) that sends commands, waits for the replies or events, applies timeouts, and decides the next step or the compensation. The flow is explicit and readable in one place, testable in isolation, observable (the orchestrator's table *is* the status page), and changing the order of steps is a change to one component. The weaknesses are the mirror image: the orchestrator knows about every participant and every participant's quirks, so it can grow into the service every team must edit; participants become passive command handlers; and the orchestrator must be durable and itself highly available, which is why teams use a workflow engine (see item 2.8) or a carefully persisted state machine rather than in-memory code.

**Choosing.** Orchestrate a process: a sequence with a defined end state, compensations, deadlines and someone who will ask about its status. Choreograph reactions: things that should happen because a fact occurred, where the producer must not know or wait for the consumers. Most systems do both: an orchestrator drives the order process by sending commands, and publishes `OrderConfirmed` as an event for whoever cares. The compensation mechanics (sagas) are in item 3.7; this note is about the shape of the architecture.

**Schemas and versioning.** An event, once published, is a contract with consumers you may not know. Give every event an envelope (event id, type, schema version, occurrence time, producer, correlation id, causation id, the aggregate key) and a schema in a registry (Avro, Protobuf or JSON Schema) with a compatibility rule enforced at publish time. The rules that keep you out of trouble: add optional fields with defaults; never remove, rename or retype a field; never change what an existing field means; and when you must break the contract, publish a new type or version alongside the old one and run both until the last consumer has moved. Consumers follow the tolerant reader principle: ignore fields they do not know, fail only on fields they need. Compatibility direction matters for rollout order: backward compatible (consumers on the new schema can read old events) means consumers upgrade first; forward compatible (old consumers can read new events) means producers may go first.

**Observability of a flow.** A request that passes through a broker leaves no single trace unless you carry one: propagate the trace context (W3C `traceparent`) in message headers, so producer and consumer spans join one trace, and put the business correlation id (the order id) in every event and every log line so support can search by it. Watch consumer lag per group (the backlog is the health signal of an asynchronous system), dead-letter depth, and the age of the oldest unprocessed message. Document the events in a catalogue (AsyncAPI is the OpenAPI of messaging) so that "who consumes `OrderPlaced`?" has an answer.

## Example: an order flow drawn both ways

Choreographed:

```text
Order ──OrderPlaced──▶ Inventory ──StockReserved──▶ Payment ──PaymentCaptured──▶ Shipping ──Shipped──▶ Notification
                            │                            │
                            └─StockRejected─▶ Order      └─PaymentFailed─▶ Inventory (release), Order (cancel)
```

Five services, five subscriptions, no process anywhere. The question it answers badly: "Order 42 was placed forty minutes ago and has not shipped. Where is it and why?" Each service knows only its own step; answering means querying all of them and reconstructing the sequence by timestamps. The second bad question: "Add a fraud check between reservation and payment." Payment must switch from subscribing to `StockReserved` to `FraudCleared`, Fraud must subscribe to `StockReserved`, and the release path on fraud rejection must be added to Inventory; a one-step change edits three services, and nothing in the system tells you which ones.

Orchestrated:

```text
                 ┌──────────── Order process (one row per order) ────────────┐
                 │ PLACED → RESERVING → CHARGING → SHIPPING → CONFIRMED       │
                 │                 ↘ CANCELLED (after compensation)           │
                 └───────┬──────────────────┬──────────────────┬──────────────┘
          ReserveStock ↓ ↑ StockReserved    │                  │
                   Inventory       ChargePayment ↓ ↑ PaymentCaptured
                                           Payment      CreateShipment ↓ ↑ Shipped
                                                                  Shipping
```

The process row answers "where is order 42" in one query, and the fraud check is one new state and one new command. The question it answers badly: "Loyalty wants to award points, search wants to index the order, finance wants a ledger entry. Do all of them go through the orchestrator?" If they do, the order process becomes the integration point for the whole company and every team queues to change it. The answer is to have the orchestrator publish facts (`OrderConfirmed`) that those services consume by choreography, and to keep the orchestrator to the steps it must sequence. The second bad question: "What happens when the orchestrator is down?" Nothing progresses, which is acceptable only because its state is persisted and it resumes where it stopped.

The envelope that both designs need:

```json
{
  "id": "0192f7a1-3c2e-7b4d-9d2a-5f3f2e6b8c11",
  "type": "OrderPlaced",
  "schemaVersion": 2,
  "occurredAt": "2026-10-24T09:12:03.412Z",
  "producer": "order-service",
  "correlationId": "a4f1c2d0-9b7e-4e3a-8f21-6d5c4b3a2e10",
  "causationId": "7b2e9c44-1d3f-4a8b-9e6c-2f1a0d8b7c65",
  "key": "order-42",
  "data": {
    "orderId": 42,
    "customerId": 7,
    "currency": "EUR",
    "totalMinor": 12990,
    "lines": [
      { "sku": "LAMP-01", "quantity": 1, "priceMinor": 12990 }
    ]
  }
}
```

`id` is what consumers deduplicate on, `key` is what the broker partitions on so that all events for one order stay in order, `correlationId` ties every message of this order's journey together, and `causationId` points at the message that caused this one, which is how you rebuild the chain after the fact.

## Pitfalls

- Commands dressed as events. An "event" with one intended consumer and an imperative name has the coupling of a command and none of the clarity; make it a command, or make it a real fact.
- Event notification with a callback for every consumer. Ten consumers each call the producer's API on every event; the producer is now coupled to and loaded by its consumers.
- No schema registry, or one without compatibility checks. The first producer that removes a field breaks consumers in production, hours later, in a different team.
- Publishing outside the transaction. The service commits, crashes before publishing, and the rest of the process never hears about it; see item 3.7 for the outbox.
- Choreographing a long process. Beyond three or four steps with compensation, nobody can state the flow, and the status question has no answer.
- An orchestrator that integrates everything. Reactions (indexing, analytics, notifications) belong on events the orchestrator publishes, not in its state machine.
- No correlation id in messages and logs. The first production incident becomes archaeology across five services' logs by timestamp.
- Ignoring lag. An asynchronous system fails by falling behind, not by returning errors; alert on consumer lag and oldest-message age, not only on exceptions.

## Check yourself

1. A service calls three others synchronously, each at 99.9 percent availability. What changes about the service's own availability and latency when the three calls become messages, and what new failure modes appear?
2. Classify `InvoiceGenerated`, `GenerateInvoice` and `InvoiceRequested`, and say how many consumers each should have and who owns the schema.
3. Redraw the choreographed flow with a fraud check between reservation and payment. Which services change, and how would the orchestrated version differ?
4. You must add a required field to `OrderPlaced` and the current version has 200 million events in the log. What do you do, and in which order do producers and consumers deploy?

## Go deeper

- [Fowler: What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html) · event notification, event-carried state transfer, event sourcing and CQRS told apart.
- [Fowler: Focusing on Events](https://martinfowler.com/eaaDev/EventNarrative.html) · events as facts, and the shift from request-driven to event-driven thinking.
- [microservices.io: Saga](https://microservices.io/patterns/data/saga.html) · choreography and orchestration compared on the same order example, with the compensation mechanics.
- [OpenTelemetry: Semantic conventions for messaging](https://opentelemetry.io/docs/specs/semconv/messaging/) · how producer and consumer spans are linked across a broker.
- [AsyncAPI](https://www.asyncapi.com/) · the specification for documenting event-driven APIs: channels, messages and schemas.
- [Building Microservices, 2nd edition](https://samnewman.io/books/building_microservices_2nd_edition/) · the communication-styles and workflow chapters cover this decision at length (paid).

---

Part of [System Design](../README.md) · item 5.3
