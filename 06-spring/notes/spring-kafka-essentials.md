# Spring for Apache Kafka essentials

> **In one sentence:** A Kafka producer decides durability with `acks` and idempotence and ordering with the record key, a `@KafkaListener` in a consumer group reads each partition on exactly one thread and commits offsets after processing, so delivery is at-least-once and every consumer must tolerate duplicates, while `DefaultErrorHandler` decides how often a failing record is retried before it goes to a dead-letter topic.

**Why it matters:** A Kafka consumer fails differently from an HTTP endpoint: one bad record can block a partition for good, a slow retry loop gets the consumer thrown out of its group, and a crash after the database commit but before the offset commit delivers the same event twice. All three are handled by configuration you have to choose, because the defaults (ten blocking attempts, then log and skip) suit a demo and not an invoicing system.

## The idea

**Producer.** `acks=all` waits until the partition's in-sync replicas have the record; with `min.insync.replicas=2` on the topic, an acknowledged record survives a broker failure. `enable.idempotence=true` makes the broker drop duplicates caused by producer retries, so retrying is safe. Both have been Kafka's defaults since 3.0, and Boot passes `spring.kafka.producer.*` straight through. The **key** chooses the partition, and Kafka orders records only within a partition, so all events about one order must share a key, usually the order id; a `null` key spreads records across partitions and gives up ordering. `KafkaTemplate.send(topic, key, value)` returns a `CompletableFuture<SendResult<K, V>>`: the send is asynchronous and batched according to `linger.ms` and `batch.size`, and the future is the only place a failure is reported.

**Consumer groups and concurrency.** Every partition is assigned to exactly one consumer in a group, and a `@KafkaListener` with `concurrency = "3"` is three consumers with a thread each. More consumers than partitions means idle consumers, so the partition count caps parallelism per group. Two groups reading the same topic each receive every record, which is how billing and shipping both react to `orders`. A rebalance redistributes partitions when a consumer joins, leaves, or stops polling for longer than `max.poll.interval.ms` (five minutes by default), which is why long processing inside the listener is dangerous.

**Acknowledgement and at-least-once.** Spring Kafka sets `enable.auto.commit=false` and commits offsets itself according to `spring.kafka.listener.ack-mode`: `BATCH` (the default) after all records of a poll are processed, `RECORD` after each record, `MANUAL` and `MANUAL_IMMEDIATE` when your method calls `Acknowledgment.acknowledge()`. In every mode the commit comes after processing, so a crash in between replays the records: at-least-once. Exactly-once exists only for read-process-write chains inside Kafka using Kafka transactions; a database write plus an offset commit is never atomic, so the consumer must be **idempotent**. The standard technique is to insert each event id into a table with a unique constraint, in the same database transaction as the business write, and skip the record when the insert conflicts. Where possible, make the operation itself idempotent instead: an upsert, or a state transition that ignores repeats.

**Errors, retries and the dead-letter topic.** The container's `CommonErrorHandler` is a `DefaultErrorHandler`, which by default retries a failed record nine times without delay and then logs and skips it. You give it a `BackOff` and a recoverer: `DeadLetterPublishingRecoverer` publishes the exhausted record, with headers describing the exception, to `<topic>-dlt` (Spring Kafka 3.x; 2.x used `.DLT`), by default to the same partition number, so the dead-letter topic needs at least as many partitions as the source unless you supply a destination resolver. Retries block the consumer thread, so the total back-off must stay well under `max.poll.interval.ms`; for longer delays use `@RetryableTopic`, which retries through extra topics without blocking the partition. `addNotRetryableExceptions` sends validation failures straight to the dead-letter topic, and deserialization failures are not retryable by default. After the recoverer succeeds, the offset is committed and the partition moves on.

**Poison pills.** A record that `JsonDeserializer` cannot parse fails inside `poll()`, before any listener runs, and is retried on every poll forever. Wrap the deserializer in `ErrorHandlingDeserializer`, which turns the failure into a `DeserializationException` that reaches the error handler, and so the dead-letter topic, raw bytes included.

**JSON.** `JsonSerializer` writes JSON and adds a `__TypeId__` header; `JsonDeserializer` reads that header, so the consumer must trust the package (`spring.json.trusted.packages`) and have the class. Between services in different languages, or when the producer's class name should not leak, turn type headers off and tell the consumer the type with `spring.json.value.default.type`.

## Example: a listener with retry, dead-letter topic and idempotency check

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        enable.idempotence: true
        spring.json.add.type.headers: false
    consumer:
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        spring.deserializer.value.delegate.class: org.springframework.kafka.support.serializer.JsonDeserializer
        spring.json.trusted.packages: com.example.orders.events
        spring.json.value.default.type: com.example.orders.events.OrderPlaced
        spring.json.use.type.headers: false
    listener:
      ack-mode: record
```

```java
public record OrderPlaced(UUID eventId, long orderId, String customerEmail, BigDecimal total) {
}
```

```java
@Configuration(proxyBeanMethods = false)
public class KafkaErrorHandlingConfiguration {

    @Bean
    CommonErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> kafkaTemplate) {
        DeadLetterPublishingRecoverer recoverer = new DeadLetterPublishingRecoverer(kafkaTemplate);
        ExponentialBackOffWithMaxRetries backOff = new ExponentialBackOffWithMaxRetries(4);
        backOff.setInitialInterval(500L);
        backOff.setMultiplier(2.0);
        backOff.setMaxInterval(5_000L);
        DefaultErrorHandler errorHandler = new DefaultErrorHandler(recoverer, backOff);
        errorHandler.addNotRetryableExceptions(InvalidOrderEventException.class);
        return errorHandler;
    }
}
```

Boot's auto-configured listener container factory picks up the `CommonErrorHandler` bean. The retries wait 0.5, 1, 2 and 4 seconds, 7.5 seconds in total, far below the five-minute poll interval. If the dead-letter topic must also receive the raw bytes of records that failed deserialization, give the recoverer a second template with a `ByteArraySerializer`, keyed by `byte[].class`.

```java
@Component
public class BillingListener {

    private static final Logger log = LoggerFactory.getLogger(BillingListener.class);

    private final ProcessedEventRepository processedEventRepository;
    private final InvoiceService invoiceService;

    public BillingListener(ProcessedEventRepository processedEventRepository, InvoiceService invoiceService) {
        this.processedEventRepository = processedEventRepository;
        this.invoiceService = invoiceService;
    }

    @KafkaListener(topics = "orders", groupId = "billing", concurrency = "3")
    @Transactional
    public void onOrderPlaced(OrderPlaced event,
                              @Header(KafkaHeaders.RECEIVED_PARTITION) int partition,
                              @Header(KafkaHeaders.OFFSET) long offset) {
        if (!processedEventRepository.markProcessed(event.eventId(), "billing")) {
            log.info("skipping duplicate event {} at partition {} offset {}", event.eventId(), partition, offset);
            return;
        }
        invoiceService.createInvoice(event.orderId(), event.total());
    }
}
```

```java
@Repository
public class ProcessedEventRepository {

    private final JdbcClient jdbcClient;

    public ProcessedEventRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public boolean markProcessed(UUID eventId, String consumer) {
        return jdbcClient.sql("""
                insert into processed_event (event_id, consumer, processed_at)
                values (:eventId, :consumer, now())
                on conflict do nothing
                """)
                .param("eventId", eventId)
                .param("consumer", consumer)
                .update() == 1;
    }
}
```

The sequence per record: the method runs in a database transaction (the `@Transactional` here is the JDBC one, not a Kafka transaction); the idempotency row and the invoice are committed together; then the container commits the offset. A crash between the two commits redelivers the record, the insert hits the primary key on `(event_id, consumer)`, and the duplicate is skipped. If `createInvoice` throws, the database transaction rolls back including the idempotency row, the error handler retries with the back-off above, and after the fourth retry the record goes to `orders-dlt` with the exception in its headers.

The test runs against real brokers:

```java
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }

    @Bean
    @ServiceConnection
    KafkaContainer kafkaContainer() {
        return new KafkaContainer(DockerImageName.parse("apache/kafka:3.9.0"));
    }
}
```

```java
@SpringBootTest
@Import(TestcontainersConfiguration.class)
class BillingListenerTest {

    @Autowired
    private KafkaTemplate<String, OrderPlaced> kafkaTemplate;

    @Autowired
    private InvoiceRepository invoiceRepository;

    @Test
    void createsOneInvoiceWhenTheSameEventArrivesTwice() {
        OrderPlaced event = new OrderPlaced(UUID.randomUUID(), 42L, "ada@example.com", new BigDecimal("99.00"));

        kafkaTemplate.send("orders", "42", event).join();
        kafkaTemplate.send("orders", "42", event).join();

        await().during(3, TimeUnit.SECONDS).atMost(20, TimeUnit.SECONDS)
                .untilAsserted(() -> assertThat(invoiceRepository.findByOrderId(42L)).hasSize(1));
    }
}
```

`@ServiceConnection` derives `spring.kafka.bootstrap-servers` and the datasource properties from the containers (item 7.4); recent Boot versions accept this `org.testcontainers.kafka.KafkaContainer` as well as the older Confluent-image one. `auto-offset-reset: earliest` matters here: the listener may be assigned its partitions after the two sends, and with the default `latest` it would never see them. Awaitility's `during` insists that the assertion holds for three seconds, which is what proves the second delivery did not create a second invoice.

## Pitfalls

- A listener that is not idempotent. At-least-once is the contract; a duplicate will arrive after the first rebalance or crash, and "we have never seen one" means it has not happened yet.
- Retry back-off or processing time that approaches `max.poll.interval.ms`. The broker evicts the consumer, the partition is reassigned, the record is reprocessed from the beginning, and the group rebalances in a loop.
- `JsonDeserializer` without `ErrorHandlingDeserializer`. One malformed record stops the partition until someone changes the offset by hand.
- A dead-letter topic with fewer partitions than the source. The default recoverer targets the same partition number and the publish fails.
- Sending to Kafka inside a database transaction and treating it as atomic. The send can succeed while the transaction rolls back, or the reverse; use the outbox pattern (item 9.3).
- `spring.json.trusted.packages=*`. Deserialising arbitrary types from a header the producer controls is the classic deserialisation hole; list the packages.
- `concurrency` higher than the partition count, or one partition and a wish for parallelism. Threads idle; partition count is the knob, and it is set when the topic is created.
- Tests with the default `auto-offset-reset=latest`. Records sent before the listener's partitions are assigned are never read, and the test is flaky in exactly the way that gets it deleted.

## Check yourself

1. The process crashes after the invoice transaction committed but before the offset was committed. What happens on restart, and which line in the listener prevents a second invoice?
2. The topic has 6 partitions and the listener declares `concurrency = "8"`. How many threads do work? What changes with `"3"`?
3. Why can a retry back-off totalling six minutes make the consumer reprocess the same record indefinitely, and which two configurations avoid it?
4. A producer publishes `orders` events with a `null` key. What can a consumer that keeps per-order state observe, and why does the fix belong on the producer?

## Go deeper

- [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/) · the reference; the "Receiving Messages" and "Serialization" chapters cover everything above in depth.
- [Spring for Apache Kafka: Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html) · `DefaultErrorHandler`, back-off, `DeadLetterPublishingRecoverer` and the dead-letter headers.
- [Spring for Apache Kafka: Non-Blocking Retries](https://docs.spring.io/spring-kafka/reference/retrytopic.html) · `@RetryableTopic` for retries that must not block the partition.
- [Spring Boot: Kafka](https://docs.spring.io/spring-boot/reference/messaging/kafka.html) · the `spring.kafka.*` properties and what Boot auto-configures.
- [Apache Kafka: Producer Configs](https://kafka.apache.org/documentation/#producerconfigs) · `acks`, `enable.idempotence`, `linger.ms` and friends, from the source.
- [Testcontainers: Kafka module](https://java.testcontainers.org/modules/kafka/) · the container classes and the images they support.

---

Part of [Spring](../README.md) · item 9.1
