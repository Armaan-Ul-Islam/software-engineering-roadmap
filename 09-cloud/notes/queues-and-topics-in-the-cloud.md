# Queues and topics in the cloud: SQS, SNS, EventBridge, Service Bus, Event Grid and Event Hubs

> **In one sentence:** Managed queues deliver each message at least once to a consumer that must acknowledge it within a visibility window, topics fan a message out to many subscribers, event buses route events by content, and because every one of them can redeliver, your consumer must be idempotent and your queue must have a dead-letter destination.

**Why it matters:** The queue is how a cloud system survives a burst and how services talk without waiting for each other. The same queue is also how a system double-charges a customer: a consumer took 45 seconds, the visibility timeout was 30, and a second consumer processed the message again. Knowing the delivery semantics of each service, and designing for duplicates, is the difference between a pattern and an incident.

## The idea

### The service map

| Need | AWS | Azure | Notes |
|---|---|---|---|
| Point-to-point queue | SQS (Standard, FIFO) | Service Bus queues; Storage Queues for simple, cheap cases | Service Bus has sessions, transactions, scheduled messages and duplicate detection; SQS is simpler and scales further |
| Publish/subscribe fan-out | SNS topics (push to SQS, Lambda, HTTP, email) | Service Bus topics and subscriptions (pull); Event Grid (push) | SNS plus SQS per subscriber is the standard AWS fan-out; Service Bus subscriptions are durable queues with filters |
| Event routing by content | EventBridge (rules, schema registry, SaaS and AWS service events, archive and replay) | Event Grid (system topics for Azure resources, custom topics, filters) | Both deliver at least once and do not order; both are the hook for "a blob was created" |
| Ordered, replayable stream | Kinesis Data Streams, MSK | Event Hubs (with a Kafka-compatible endpoint) | Partitions, consumer offsets and retention; see item 7.2 |

### Visibility timeouts and locks

A consumer receives a message, and the queue hides it from other consumers for the **visibility timeout** (SQS; 30 seconds by default, up to 12 hours, extendable per message) or the **lock duration** in peek-lock mode (Service Bus; renewable, at most five minutes per renewal). If the consumer deletes (SQS) or completes (Service Bus) the message in time, it is gone. If it crashes, or simply takes too long, the message reappears and someone else processes it. Set the window above your p99 processing time and extend it from the consumer for long jobs; never rely on it being exact.

### Dead-letter queues

After `maxReceiveCount` deliveries (SQS redrive policy) or `MaxDeliveryCount` (Service Bus, default 10) the message is moved to a **dead-letter queue** instead of looping forever. Service Bus moves them into a `$DeadLetterQueue` sub-queue, and can optionally dead-letter expired messages and messages that fail subscription filters as well. A dead-letter queue is only useful if someone looks at it: alarm on its depth, keep a redrive path (SQS has a built-in redrive to the source queue), and record why each message landed there.

### FIFO and ordering

Standard SQS and Event Grid deliver **at least once** with **best-effort ordering**, which means duplicates and reordering are rare but normal. SQS **FIFO** queues order messages within a **message group ID** and deduplicate by a deduplication ID within a five-minute window; the price is throughput (300 operations per second without batching, more with batching and high-throughput mode) and parallelism limited to the number of groups. Service Bus achieves the same with **sessions**: messages with one session ID are delivered in order to one receiver at a time, and **duplicate detection** drops repeated message IDs within a window. Ordering is a per-key property on both clouds; there is no cheap global order.

### At-least-once means idempotent consumers

Because redelivery is guaranteed to happen eventually, a consumer must produce the same result whether it sees a message once or three times. Two strategies: make the operation naturally idempotent (an upsert, a `SET status = 'paid'`), or record the message ID in the same transaction as the side effect and skip on conflict. Side effects that live outside your database (an email, a payment API call) need the outbox pattern on the producing side and an idempotency key on the receiving API.

### The patterns

**Queue-based load levelling**: a producer writes to the queue at burst speed; consumers drain it at the rate the database can sustain. The queue's depth becomes the buffer and the metric. You size consumers for the average, not the peak, which is the cheapest capacity decision in this domain. **Competing consumers**: several instances read from one queue; the queue hands each message to exactly one of them at a time, so scaling is adding instances (see item 5.5 for scaling on backlog per worker). With FIFO or sessions, effective parallelism is the number of distinct groups, not the number of consumers.

## Example: a duplicate, then an idempotent consumer

The incident in numbers: processing an `OrderPaid` message takes 12 seconds at the median and 45 seconds at p99 (it calls a slow invoicing system). The SQS visibility timeout is the default 30 seconds. One message in a hundred takes longer than 30 seconds, reappears, is picked up by a second instance, and both instances issue an invoice. At 10,000 orders a day that is 100 double invoices a day. The timeout should have been at least 60 seconds with the consumer extending it; but even then a crash after the invoice and before the delete produces a duplicate, so the consumer must also be idempotent.

```sql
CREATE TABLE processed_message (
    message_id   text PRIMARY KEY,
    processed_at timestamptz NOT NULL DEFAULT now()
);
```

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaidConsumer {

    private final JdbcTemplate jdbcTemplate;
    private final InvoiceService invoiceService;

    public OrderPaidConsumer(JdbcTemplate jdbcTemplate, InvoiceService invoiceService) {
        this.jdbcTemplate = jdbcTemplate;
        this.invoiceService = invoiceService;
    }

    @Transactional
    public void handle(String messageId, OrderPaidEvent event) {
        int insertedRows = jdbcTemplate.update(
                "INSERT INTO processed_message (message_id) VALUES (?) ON CONFLICT (message_id) DO NOTHING",
                messageId);
        if (insertedRows == 0) {
            return;
        }
        invoiceService.createInvoice(event.orderId(), event.amount());
    }
}
```

The dedup row and the invoice are written in one transaction. If the consumer dies after the commit but before deleting the message, the redelivery hits the conflict, `insertedRows` is 0, and the handler returns without a second invoice; the listener then deletes the message. If the consumer dies before the commit, nothing was written and the redelivery does the work. The message ID is the broker's (SQS `MessageId`, Service Bus `MessageId`); for FIFO or sessions you could use the deduplication ID or a business key such as the order number. Expire old rows with a scheduled delete, keeping them longer than the queue's retention period so a very late redelivery is still caught.

What this does *not* cover: if `createInvoice` calls an external API, the API call is not rolled back with the transaction. Give that call an idempotency key derived from the order number, or move it behind an outbox.

## Pitfalls

- Visibility timeout below p99 processing time. The symptom is duplicates under load, never in tests.
- No dead-letter queue. A poison message is redelivered forever, consumes a consumer each time, and hides behind the healthy traffic.
- A dead-letter queue nobody monitors. It is a slower way of losing messages.
- Expecting ordering from a standard queue or an event bus. Only message groups and sessions order, and only per key.
- One FIFO group for everything "to be safe". Throughput drops to one message at a time.
- Deleting the message before the work commits. A crash in between loses the message; delete after the transaction.
- Treating a topic subscription as a queue you can skip. Service Bus subscriptions and SQS subscriber queues accumulate until read; a forgotten subscriber fills up and costs money.
- Large payloads in messages. Put the object in storage and send the key (the claim-check pattern); SQS and Service Bus Standard both cap message size.

## Check yourself

1. A consumer takes 20 seconds at p50 and 90 seconds at p99 with a 60-second visibility timeout. What is the failure, what are two fixes in the consumer, and why is neither sufficient on its own?
2. You need all events for one customer processed in order, but want parallelism across customers. Design it on SQS and on Service Bus, and state what limits the parallelism.
3. Explain, step by step, why the `processed_message` table prevents a double invoice when the consumer crashes after committing but before deleting the message, and why it does not help if `createInvoice` posts to an external payment API.
4. Why is queue depth a better scaling signal for a consumer fleet than CPU, and what target would you set?

## Go deeper

- [Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) · visibility timeouts, redrive policies and the FIFO limits, from the primary source.
- [Azure Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-messaging-overview) · peek-lock, sessions, duplicate detection and dead-lettering.
- [Azure Architecture Center: Cloud Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/patterns/) · queue-based load levelling, competing consumers, claim check and the idempotent-receiver discussion; readable even if you deploy to AWS.

---

Part of [Cloud](../README.md) · items 7.1, 7.3
