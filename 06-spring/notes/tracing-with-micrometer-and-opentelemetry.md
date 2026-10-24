# Tracing with Micrometer and OpenTelemetry

> **In one sentence:** A trace is a tree of timed spans that follows one request across threads, HTTP calls and Kafka topics by carrying a trace id in headers; Micrometer Tracing creates the spans from the same `Observation`s that produce Boot's metrics, the OpenTelemetry bridge exports them over OTLP to a collector, and putting the trace id into every log line is what turns a slow request into a diagnosis.

**Why it matters:** Metrics tell you that p99 latency doubled, logs tell you what each service said, and only a trace tells you that the 1.8 seconds of this request went into the second of three calls to the shipping partner, inside a retry, after a cache miss. Every service in the chain has to participate for that picture to exist, so the setup is a team skill, and the cost (sampling, span count, exporter load) decides whether it stays on in production.

## The idea

**Spans and traces.** A span is a named operation with a start time, a duration, attributes (key-value pairs) and a parent. A trace is the set of spans sharing one 128-bit trace id, rooted at the span with no parent; each span has its own 64-bit span id. The server span for `POST /api/orders` is the parent of the client span for the partner call, which is the parent of the partner's own server span, and so on down the chain.

**Propagation.** Inside a process the current span lives in a `ThreadLocal`; across processes it travels in headers. The W3C Trace Context format, Boot's default, is `traceparent: 00-<trace id>-<parent span id>-<flags>`; B3 is the older Zipkin format, selectable with `management.tracing.propagation.type`. Boot's instrumented clients add the header: `RestClient` and `WebClient` built from the auto-configured builders, and `KafkaTemplate` with `spring.kafka.template.observation-enabled=true`. The server side reads it and continues the trace: Spring MVC through its observation filter, `@KafkaListener` containers with `spring.kafka.listener.observation-enabled=true`. Across threads nothing happens by itself: an `@Async` method or a `CompletableFuture` continuation starts with an empty context unless the task is wrapped. Spring Framework 6.1's `ContextPropagatingTaskDecorator`, declared as a `TaskDecorator` bean that Boot's executor builder picks up, does it for `@Async`; for a hand-built executor, wrap tasks with Micrometer's `ContextSnapshot`.

**Micrometer Tracing and the bridge.** Boot does not talk to OpenTelemetry directly. Spring's instrumentation creates `Observation`s through the `ObservationRegistry`; Micrometer turns each observation into a `Timer` (the metrics of item 8.1) and, when Micrometer Tracing is on the classpath, into a span as well. Micrometer Tracing is a facade with two bridges: `micrometer-tracing-bridge-otel` to the OpenTelemetry SDK and `micrometer-tracing-bridge-brave` to Zipkin's Brave. The exporter is a separate dependency; `opentelemetry-exporter-otlp` sends spans over OTLP to an OpenTelemetry Collector (HTTP on port 4318 by default), which forwards them to Jaeger, Tempo, Zipkin or a vendor. Boot configures the SDK: `spring.application.name` becomes the `service.name` resource attribute, and `management.otlp.tracing.endpoint` the destination.

**Sampling.** Every span costs CPU to create and bytes to export and store. `management.tracing.sampling.probability` is head-based sampling: the first service decides at the start of a trace, with probability 0.1 by default, and the decision travels in the `traceparent` flags so that every downstream service agrees. One in ten is enough for latency analysis and useless for debugging one failed request; tail-based sampling in the collector (keep every trace with an error or above a latency threshold) gives both, and it is a collector feature, not a Boot property.

**Logs.** Micrometer Tracing puts `traceId` and `spanId` into the MDC, and when it is on the classpath Boot's default console pattern prints them as `[traceId-spanId]` next to the thread name (Boot 3.1 and later; `logging.pattern.correlation` changes the format, and `[${spring.application.name:},%X{traceId:-},%X{spanId:-}]` reproduces the older Sleuth style). That is the join between logs and traces: copy the trace id from the slow span into the log search, or from the log line into the tracing UI. Structured JSON logging emits the same MDC fields as properties.

**Custom spans.** Boot's built-in observations cover HTTP in and out, Kafka when enabled, and `@Scheduled` runs (Spring Framework 6.1). It does not instrument JDBC out of the box (the `datasource-micrometer-spring-boot` library adds query spans), and it knows nothing about your business operations. `@Observed(name = "order.place")` on a bean method creates an observation around it, provided an `ObservedAspect` bean exists and AOP is on the classpath. The programmatic form, `Observation.createNotStarted(name, registry)...observe(...)`, is more flexible: `lowCardinalityKeyValue` becomes a metric tag and a span attribute, so it must have a bounded set of values, while `highCardinalityKeyValue` becomes a span attribute only, where an order id is fine. One observation yields a timer, a span and, through `contextualName`, a readable span name.

**The cost.** Creating a span takes microseconds and the SDK exports in batches on a background thread; the real costs are the collector and storage bill, which scale with the sampling rate and the number of spans per request, and the attention cost of a trace with hundreds of tiny spans (one per JDBC statement in a loop) that nobody can read. Instrument the boundaries (requests, remote calls, messages, the business operation), sample at the head, and let the collector keep the interesting traces.

## Example: OTLP export, a custom observation and the log line

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
```

```properties
spring.application.name=orders
management.tracing.sampling.probability=1.0
management.otlp.tracing.endpoint=http://localhost:4318/v1/traces
spring.kafka.template.observation-enabled=true
spring.kafka.listener.observation-enabled=true
```

Probability 1.0 is for development; production starts at the 0.1 default and moves the decision to the collector. Locally, Jaeger's all-in-one image accepts OTLP on 4318 directly and shows the traces at once. These are the Boot 3.x coordinates; Boot 4 bundles the bridge and exporter into `spring-boot-starter-opentelemetry` and moves the export settings to `management.opentelemetry.tracing.export.otlp.*`.

```java
@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ObservedAspect observedAspect(ObservationRegistry observationRegistry) {
        return new ObservedAspect(observationRegistry);
    }

    @Bean
    TaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
```

```java
@Service
public class OrderService {

    private final ObservationRegistry observationRegistry;
    private final OrderRepository orderRepository;
    private final ShippingPartnerApi shippingPartnerApi;

    public OrderService(ObservationRegistry observationRegistry, OrderRepository orderRepository,
                        ShippingPartnerApi shippingPartnerApi) {
        this.observationRegistry = observationRegistry;
        this.orderRepository = orderRepository;
        this.shippingPartnerApi = shippingPartnerApi;
    }

    public Long place(PlaceOrderCommand command) {
        return Observation.createNotStarted("order.place", observationRegistry)
                .contextualName("place-order")
                .lowCardinalityKeyValue("channel", command.channel().name())
                .highCardinalityKeyValue("customer.id", command.customerId().toString())
                .observe(() -> placeAndShip(command));
    }

    private Long placeAndShip(PlaceOrderCommand command) {
        Order order = orderRepository.save(Order.from(command));
        shippingPartnerApi.create(new CreateShipmentRequest(order.getId()), order.getId().toString());
        return order.getId();
    }
}
```

What arrives at the collector for one request, as a tracing UI draws it (names and timings illustrative):

```text
trace 4bf92f3577b34da6a3ce929d0e0e4736                                        212 ms
└─ orders     http post /api/orders                                            212 ms
   └─ orders     place-order            channel=web  customer.id=42            180 ms
      ├─ orders     http post /v1/shipments                                    150 ms
      │  └─ shipping   http post /v1/shipments                                 140 ms
      └─ orders     orders send                                                  3 ms
         └─ billing    orders receive                                            (continues in the consumer)
```

The outbound request that created the second-level span carried the context:

```http
POST /v1/shipments HTTP/1.1
Host: shipping.example.com
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
```

And every log line written while the request ran carries the same ids, in Boot's default pattern:

```text
2026-10-24T10:15:02.113+02:00  INFO 41213 --- [orders] [nio-8080-exec-7] [4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7] c.e.orders.OrderService : placing order for customer 42
```

The `channel` tag also appears on the `order.place` timer in `/actuator/prometheus`, so the same observation answers "how long does placing an order take per channel" and "where did this particular order spend its time".

## Pitfalls

- Spans without a bridge, or a bridge without an exporter. Both produce "tracing does not work" with no error; check that all three dependencies are present and watch the SDK's log for `Failed to export spans` when the collector is unreachable.
- Sampling at 1.0 in production for a busy service, or at 0.1 and expecting to find the one failed request. Head sampling cannot know the outcome; move that decision to the collector.
- `@Async` without context propagation. Child spans become orphan roots and their log lines have empty ids; one `TaskDecorator` bean fixes it for Boot's executor.
- High-cardinality values in `lowCardinalityKeyValue`. The same observation feeds a timer, so a customer id there is a metrics explosion (item 8.1); use `highCardinalityKeyValue`.
- A span per statement in a loop. Thousands of 1 ms spans hide the one that mattered and multiply the export bill; instrument boundaries, not iterations.
- Mixed propagation formats. One service on B3 and the next on W3C breaks the chain; set `management.tracing.propagation.type` the same everywhere, or accept both on consumption.
- No `spring.application.name`. Every service reports under the same default `service.name`, and the trace is a tree of identical labels.
- Treating the trace id as a request id for users. It is sampled away nine times out of ten; keep a correlation id in the response header (item 3.4) for support tickets.

## Check yourself

1. A trace shows the `POST /api/orders` server span and nothing below it, although the service calls the partner with a `RestClient` and publishes to Kafka. Name two likely causes.
2. Why must the sampling decision be made by the first service and propagated, and what does that imply for debugging a failure that occurs in one request in a thousand?
3. An `@Async` listener logs lines with empty trace ids. What is missing, and what is the one-bean fix?
4. You add `highCardinalityKeyValue("order.id", ...)` and `lowCardinalityKeyValue("customer.email", ...)` to an observation. Which one is the mistake, and what breaks?

## Go deeper

- [Spring Boot: Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) · the supported tracers and exporters, the properties, and the log correlation pattern.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/) · the facade, the bridges, context propagation and baggage.
- [Micrometer: Observation](https://docs.micrometer.io/micrometer/reference/observation.html) · the Observation API, conventions and the low versus high cardinality rule.
- [Spring Framework: Observability](https://docs.spring.io/spring-framework/reference/integration/observability.html) · every built-in observation with its name, contextual name and key values.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) · the `traceparent` and `tracestate` headers, including the sampling flag.
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) · receivers, processors (including tail sampling) and exporters.

---

Part of [Spring](../README.md) · item 8.2
