# Observability: logs, metrics and traces

> **In one sentence:** Metrics tell you *that* something is wrong and how much, traces tell you *where* in the request path it went wrong, and logs tell you *why*, and the three only work together when a trace ID stitches them and labels are kept to a bounded set of values.

**Why it matters:** Without correlation, an incident is `grep` across ten services' logs with a stopwatch; without cardinality discipline, Prometheus falls over the week you need it most. "The p99 doubled, how do you find out why?" is a standard interview question, and the answer is a sequence through the three signals, not a hunch.

## The idea

**Three signals, three questions.**

| Signal | Answers | Shape and cost | In Spring Boot |
|---|---|---|---|
| Metrics | is it wrong, how much, since when? | numbers aggregated over time; cheap, alertable, no per-request detail | Micrometer, `/actuator/prometheus` |
| Traces | where in the request path did the time or the error go? | a tree of spans per request across services; sampled | Micrometer Tracing with the OpenTelemetry bridge |
| Logs | why did this particular thing happen? | discrete events with context; expensive per event | Logback or Log4j2 with structured output |

**Structured logs.** One JSON object per line, fields rather than sentences: timestamp, level, logger, message, service, plus the request context. Spring Boot 3.4 produces them with `logging.structured.format.console=ecs` (or `logstash` or `gelf`). Micrometer Tracing puts `traceId` and `spanId` into the MDC, so every line written during a request carries them; a `correlationId` from the inbound request header is the pre-tracing version of the same idea. Levels mean something: `ERROR` needs a human, `WARN` is degraded, `INFO` is a business event, `DEBUG` is off in production. Never log secrets or personal data.

**Metric types and methods.** A *counter* only increases (`_total`) and is read with `rate()`; a *gauge* is a current value; a *histogram* counts observations into buckets (`_bucket{le="0.3"}`, plus `_sum` and `_count`) and lets the server compute quantiles that can be aggregated across instances; a *summary* computes quantiles in the client and cannot be aggregated. RED (Rate, Errors, Duration, per endpoint) describes a service; USE (Utilisation, Saturation, Errors) describes a resource such as a connection pool, a thread pool or a disk. Spring Boot's `http.server.requests` timer becomes `http_server_requests_seconds_count`, `_sum`, `_max` and, with `management.metrics.distribution.percentiles-histogram.http.server.requests=true`, `_bucket`, tagged with `method`, `status`, `outcome` and `uri`, where `uri` is the route template `/orders/{id}`, not the actual path.

**Cardinality.** A time series exists per unique combination of label values; the cost of a metric is that count. A `customer_id` label with a million customers is a million series per metric name, and raw URLs, session IDs or exception messages do the same. Keep labels to sets of at most a few hundred values; put the rest in logs and traces, which are built for per-event detail.

**PromQL in four ideas.** `rate(counter[5m])` is the per-second average increase over the window (use a window of at least four scrape intervals); `sum by (uri) (...)` aggregates; `histogram_quantile(0.99, sum by (le) (rate(bucket[5m])))` computes a quantile from buckets, always aggregating buckets with `sum by (le)` first; `topk(5, ...)` finds the worst offenders.

**Tracing.** A trace is a tree of spans; a span has a name, start and end, attributes, a status and a parent. Context travels between services in the W3C `traceparent` header, `00-<trace-id>-<parent-span-id>-<flags>`, and in message headers for Kafka. Sampling decides which traces are kept: head-based sampling decides at the root (`management.tracing.sampling.probability`, default 0.1) and is parent-based so a trace is kept or dropped whole; tail-based sampling in the OpenTelemetry Collector keeps slow and failed traces after seeing them. The SDK exports over OTLP (gRPC on 4317, HTTP on 4318) to the Collector, whose pipelines of receivers, processors (batching, memory limits, tail sampling, attribute scrubbing) and exporters feed Tempo, Jaeger or a vendor. In Spring Boot: `micrometer-tracing-bridge-otel` plus `opentelemetry-exporter-otlp`, and `management.otlp.tracing.endpoint=http://otel-collector:4318/v1/traces`.

## Example: the queries and the log line for a Spring Boot service

```promql
# Rate: requests per second, per endpoint (RED)
sum by (uri) (rate(http_server_requests_seconds_count{job="orders"}[5m]))

# Errors: share of requests answered with 5xx
sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[5m]))
  / sum(rate(http_server_requests_seconds_count{job="orders"}[5m]))

# Duration: p99 across all Pods, per endpoint; buckets first, quantile second
histogram_quantile(0.99, sum by (le, uri) (rate(http_server_requests_seconds_bucket{job="orders"}[5m])))

# The five slowest endpoints
topk(5, histogram_quantile(0.95, sum by (le, uri) (rate(http_server_requests_seconds_bucket{job="orders"}[5m]))))

# Saturation of the connection pool (USE)
hikaricp_connections_active{job="orders"} / hikaricp_connections_max{job="orders"}
```

A structured log line written during a traced request, with the ECS-style field names Spring Boot's `ecs` format uses:

```json
{"@timestamp":"2026-10-24T09:15:02.113Z","log.level":"WARN","service.name":"orders","process.thread.name":"http-nio-8080-exec-7","log.logger":"com.example.orders.PaymentClient","message":"payment provider timeout after 2000 ms","traceId":"4bf92f3577b34da6a3ce929d0e0e4736","spanId":"00f067aa0ba902b7","orderId":"o-18422","ecs.version":"8.11"}
```

The investigation this enables: the error-ratio query fires an alert; the p99 panel shows `/orders/{id}` is the slow endpoint; a trace search for that route with status 500 opens a trace in which the span `PaymentClient.charge` took 2.0 s of a 2.1 s request; the log view filtered by `traceId=4bf92f3577b34da6a3ce929d0e0e4736` shows the line above. Four steps, no guessing, and each step used the signal built for that question.

## Pitfalls

- High-cardinality labels: user IDs, order IDs, raw paths, full exception messages. Prometheus memory grows until it is OOM-killed, and queries time out.
- Averaging percentiles. `avg(histogram_quantile(...))` across Pods is meaningless; aggregate the buckets with `sum by (le)` first, then take the quantile.
- Averages in general. A mean latency of 80 ms hides a p99 of 4 s. Use histograms and look at tails.
- `rate()` on a gauge, or `rate()` with a window shorter than two scrape intervals, which returns nothing.
- Breaking context propagation. Work handed to a custom thread pool, `@Async` or a `CompletableFuture` loses the trace unless the executor propagates context; the trace ends abruptly and the logs lose their `traceId`.
- Sampling that cannot see errors. One percent head-based sampling keeps one in a hundred failures; use tail sampling or always keep error traces.
- Logging per request at `INFO` in hot paths, and multi-line stack traces in non-JSON output that break parsers. Structured logs plus log levels solve both.
- Clock skew between hosts. Spans appear to end before they start; run NTP everywhere and log in UTC.

## Check yourself

1. p99 latency doubled at 09:15. Give the sequence of steps through the three signals, naming the query or search at each step.
2. Why is `avg(histogram_quantile(0.99, rate(http_server_requests_seconds_bucket[5m])))` wrong, and what is the correct expression for a fleet-wide p99?
3. A colleague adds `customer_id` as a label on the request counter to debug one customer. What happens to Prometheus, and where should that detail live instead?
4. What does the `traceparent` header contain, and what happens to a trace when a service forwards a request without it?

## Go deeper

- [OpenTelemetry: Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/) · the three signals, context propagation and the Collector in one page.
- [Prometheus: Overview](https://prometheus.io/docs/introduction/overview/) and [Querying basics](https://prometheus.io/docs/prometheus/latest/querying/basics/) · the data model and PromQL from instant vectors to `rate`.
- [Prometheus: histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile) · why buckets must be aggregated before the quantile is computed.
- [Grafana: The RED Method](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/) and [Brendan Gregg: The USE Method](https://www.brendangregg.com/usemethod.html) · what to measure for services and for resources.
- [OpenTelemetry: Traces](https://opentelemetry.io/docs/concepts/signals/traces/) · spans, context and sampling, from the specification's authors.
- [Spring Boot: Structured Logging](https://docs.spring.io/spring-boot/reference/features/logging.html#features.logging.structured) · the `ecs`, `logstash` and `gelf` formats and how to add your own fields.

---

Part of [DevOps & Delivery](../README.md) · items 5.1, 5.2, 5.3
