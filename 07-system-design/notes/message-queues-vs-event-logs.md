# Message queues vs event logs

> **In one sentence:** A queue hands each message to one consumer and forgets it once acknowledged, while a log appends messages in order and lets any number of consumers read them at their own pace, so "Kafka or RabbitMQ" is really "do I want the broker to track work, or do I want a replayable history?".

**Why it matters:** Teams pick Kafka for a job queue and then build retries, per-message acknowledgements and dead-letter handling themselves, or pick RabbitMQ for event streaming and discover a second consumer cannot read what the first already consumed. The semantics decide what your consumers must handle (duplicates, reordering, head-of-line blocking) far more than throughput numbers do.

## The idea

**Queue semantics (RabbitMQ, Amazon SQS, ActiveMQ).** A producer puts a message on a queue; the broker delivers it to one of the consumers attached to that queue (competing consumers). The consumer acknowledges when it has finished processing, and the broker then deletes the message. If the consumer crashes or rejects, the broker redelivers to another consumer: in RabbitMQ when the channel closes or on `basic.nack`/`basic.reject` with requeue, in SQS when the visibility timeout expires (default 30 s) without a delete. Consumers pull in bounded batches (RabbitMQ prefetch, SQS `MaxNumberOfMessages`), which gives natural backpressure: a slow consumer simply takes fewer messages. Routing is rich: RabbitMQ exchanges route by key or pattern to many queues, SQS pairs with SNS for fan-out. Once a message is acknowledged it is gone; there is no "read it again tomorrow" unless you kept a copy.

**Log semantics (Apache Kafka, and the same model in Pulsar, Kinesis and Redpanda).** A topic is split into partitions; each partition is an append-only, ordered file. Messages get an offset in their partition and stay for the retention period (time or size based, or compacted by key) whether or not anyone read them. Consumers do not acknowledge messages; they commit the offset up to which they have processed, and the broker stores that offset per consumer group. Within a group each partition is assigned to exactly one consumer, so parallelism is bounded by the partition count. Two groups reading the same topic each get every message. Replay is resetting an offset. Nothing is deleted when consumed, which is what makes a log a history and not a task list.

**Ordering, and its limits.** A queue with a single consumer is FIFO; add a second consumer or a redelivery and order is gone (SQS FIFO queues restore it per message group, with deduplication by message ID inside a five-minute window). A log is ordered within a partition, never across partitions; producers choose the partition by key, so "all events for order 42 in order" is one line of configuration, and "all events in order" means one partition and no parallelism. Three things break per-key order in Kafka silently: producer retries without idempotence (enabled by default since Kafka 3.0), changing the number of partitions (the key to partition mapping changes), and a consumer that processes a batch concurrently.

**Delivery guarantees.** Both models are at-least-once by default when you acknowledge or commit after processing, and at-most-once if you acknowledge first. Kafka's transactions give exactly-once for consume-transform-produce chains that stay inside Kafka; the moment you write to a database or call an API, you are back to idempotent consumers (see item 3.8).

**Dead-letter queues.** A message that fails every time (a poison message) must not block the others. Queues have this built in: RabbitMQ dead-letter exchanges, quorum queues with a delivery limit, SQS redrive policies with a maximum receive count. Kafka has no broker-side equivalent because the log does not track per-message state; the pattern is a retry topic and a dead-letter topic written by the consumer framework (Spring Kafka's `DeadLetterPublishingRecoverer`, Kafka Connect's `errors.deadletterqueue.topic.name`). Either way, keep the payload, the error and the attempt count, and alert on the dead-letter depth.

**Head-of-line blocking.** In a log, one slow or failing message holds up its whole partition; the consumer cannot skip ahead without losing it, which is why the retry-topic pattern exists. In a queue, a slow message holds up only the consumer working on it.

**Side by side.**

| | Queue (RabbitMQ, SQS) | Log (Kafka) |
|---|---|---|
| Unit the broker tracks | Each message, until acknowledged | Each consumer group's offset per partition |
| After consumption | Message deleted | Message stays until retention expires |
| Several independent consumers of the same data | Needs a queue per consumer (fan-out via exchange or SNS) | Natural: one consumer group each |
| Parallelism | Add consumers to the queue, unbounded | Bounded by partition count |
| Ordering | Single consumer only, or SQS FIFO per message group | Per partition, chosen by key |
| Replay | No | Yes, reset offsets |
| Backpressure | Prefetch and visibility timeout | Consumer pulls at its own pace; lag is visible |
| Poison messages | Dead-letter queue built in | Retry and dead-letter topics built by you |
| Routing and priorities | Exchanges, routing keys, priority queues, per-message TTL and delay | Topics and keys only |
| Typical throughput shape | Thousands to tens of thousands of messages per second per queue | Very high, scales with partitions and brokers |
| Fits | Task distribution, commands, RPC-style requests, work with per-message retries | Event streams, audit history, CDC, feeding several systems from one source |

## Example: the same order flow on both

An order service emits `OrderPlaced`; a billing worker charges the card and an analytics job counts orders per hour.

- On RabbitMQ: `OrderPlaced` goes to a fanout exchange bound to `billing` and `analytics` queues. Billing runs four workers competing on its queue; a failed charge is nacked, retried through a delayed queue, and after five attempts dead-lettered. Analytics reads its own queue and acknowledges. If analytics was deployed a week late, it missed a week of orders.
- On Kafka: `OrderPlaced` is produced to the `orders` topic with key `customerId` across 12 partitions. Billing is a consumer group with up to 12 instances; a failed charge is republished to `orders-retry`, and after five attempts to `orders-dlq`, so the partition keeps moving. Analytics is a second group that reads the same records, and the team that joins a week late sets its offset to the beginning and processes the whole week.

The queue made per-message failure handling trivial and replay impossible; the log did the reverse.

## Pitfalls

- Using Kafka as a work queue with per-message acknowledgement in mind. You will reimplement visibility timeouts, retries and dead-lettering, badly, on top of offsets.
- Choosing partition counts late. Partitions can be added but never removed, and adding them breaks key ordering. Overprovision at creation.
- Committing offsets before processing (or auto-commit with slow handlers). A crash loses the batch; the log looks healthy because lag is zero.
- Assuming queue order. Two RabbitMQ consumers or one redelivery is enough to reorder; design consumers to tolerate it.
- Infinite redelivery. Without a delivery limit, a poison message is redelivered forever, consuming a worker and filling logs.
- Processing taking longer than the visibility timeout or `max.poll.interval.ms`. The broker assumes the consumer died and gives the work to another, so it runs twice.
- Treating RabbitMQ Streams or Kafka compacted topics as "the other model for free". They borrow features across the line, but the consumer model you build against is still one of the two above.

## Check yourself

1. A new team wants to consume the last 30 days of `PaymentSettled` events to backfill a report. Which model makes that possible, and what configuration had to be in place beforehand?
2. Why does adding a thirteenth consumer to a Kafka consumer group on a 12-partition topic achieve nothing, and what does adding a fifth worker to a RabbitMQ queue do?
3. A consumer takes 10 minutes to process one message and the queue's visibility timeout is 30 s. Describe what happens and two ways to fix it.
4. You need "exactly one email per order". Which broker feature gets you there, and which part of the problem does no broker solve?

## Go deeper

- [Apache Kafka: Introduction](https://kafka.apache.org/intro) · topics, partitions, offsets and consumer groups from the source.
- [RabbitMQ: Reliability Guide](https://www.rabbitmq.com/docs/reliability) · acknowledgements, confirms, and what each failure does to a message in flight.
- [Jay Kreps: The Log](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying) · the essay that explains why a replayable log is a different kind of thing from a queue.
- [Designing Data-Intensive Applications, chapter 11](https://dataintensive.net/) · message brokers versus log-based brokers, with the delivery-guarantee consequences.

---

Part of [System Design](../README.md) · item 2.7
