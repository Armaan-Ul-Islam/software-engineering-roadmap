# Project spec: an observability stack with SLOs, burn-rate alerts and a game day

> **In one sentence:** Instrument one of your Spring Boot services with Micrometer and OpenTelemetry, run Prometheus, Grafana, Tempo and Loki next to it in Docker Compose, link metrics, traces and logs through one trace ID, define two SLOs with multi-window burn-rate alerts that have their own unit tests, then break the system on purpose and watch the alerts do their job.

**Why it matters:** Most teams have dashboards nobody reads and alerts everybody mutes. The difference between that and a system you can operate is knowing what each signal answers, alerting on symptoms with a burn rate instead of on CPU, and having rehearsed an incident before the real one. Interviewers for senior roles ask "how would you know this is broken?" and expect the answer to include an SLO.

## The idea

Reuse the order service (item 2.2) or the URL shortener (item 2.1). Add one Compose file with five infrastructure containers. The service exposes Prometheus metrics directly from Actuator, sends traces and logs over OTLP to an OpenTelemetry Collector, which forwards traces to Tempo and logs to Loki. Grafana reads all three stores and jumps from a trace to its logs and from a metric spike to example traces.

Scope:

- 1.1 Metrics: `spring-boot-starter-actuator` and `micrometer-registry-prometheus`; a RED dashboard built from `http_server_requests_seconds_*`, plus JVM, HikariCP and Kafka consumer metrics.
- 1.2 Traces: `micrometer-tracing-bridge-otel` and `opentelemetry-exporter-otlp`; a trace spans the HTTP request, the database calls and the Kafka consumer in the other service.
- 1.3 Logs: JSON lines with `traceId` and `spanId`, shipped to Loki through the collector.
- 1.4 Two SLOs: availability (99.9 percent of requests not `5xx` over 30 days) and latency (99 percent under 300 ms), each with fast-burn and slow-burn alerts.
- 1.5 One game day with a written timeline and a postmortem.

Concepts exercised: Spring 2.4, 2.5, 8.1, 8.2; DevOps & Delivery 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 8.1, 8.2; System Design 4.5, 4.7; Java 8.6.

## Example: the collector, the alert rule and the milestones

The collector configuration (OpenTelemetry Collector, core or contrib distribution, 0.90 or later; Loki 3 accepts OTLP natively on `/otlp`):

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  otlp/tempo:
    endpoint: tempo:4317
    tls:
      insecure: true
  otlphttp/loki:
    endpoint: http://loki:3100/otlp

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/tempo]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/loki]
```

On the Spring Boot 3.x side, `spring.application.name=orders` names the service in every signal, `management.otlp.tracing.endpoint=http://otel-collector:4318/v1/traces` sends traces, `management.tracing.sampling.probability=1.0` keeps every trace while you develop, and `management.endpoints.web.exposure.include=health,prometheus` opens the scrape endpoint. Prometheus scrapes `app:8080/actuator/prometheus` every 15 seconds.

The fast-burn alert for the availability SLO. With a 30-day window and a 0.1 percent budget, a burn rate of 14.4 over one hour consumes two percent of the month's budget in that hour; the five-minute window makes the alert stop as soon as the problem stops:

```yaml
groups:
  - name: orders-slo
    rules:
      - record: slo:http_error_ratio:rate5m
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[5m]))
          / sum(rate(http_server_requests_seconds_count{job="orders"}[5m]))
      - record: slo:http_error_ratio:rate1h
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[1h]))
          / sum(rate(http_server_requests_seconds_count{job="orders"}[1h]))
      - alert: OrdersErrorBudgetFastBurn
        expr: slo:http_error_ratio:rate1h > (14.4 * 0.001) and slo:http_error_ratio:rate5m > (14.4 * 0.001)
        for: 2m
        labels:
          severity: page
        annotations:
          summary: "orders is burning its 30-day error budget at 14.4x"
```

The rule gets a unit test that `promtool test rules` runs in CI: synthetic series with ten errors and one hundred successes per minute, and an assertion that `OrdersErrorBudgetFastBurn` is firing with `severity: page` at minute 65.

Milestones, each ending in a committed test:

1. **Metrics and the RED dashboard.** Actuator plus Prometheus registry, a Grafana dashboard provisioned from JSON in the repository with request rate, error ratio and p50, p95, p99 latency per `uri`. Test: an integration test calls an endpoint and asserts that `/actuator/prometheus` contains `http_server_requests_seconds_count` with the templated `uri` tag (`/orders/{id}`, not the raw path).
2. **Traces end to end.** Tracing bridge and OTLP exporter, context propagated into Kafka headers and through `@Async` executors (wrap them with Micrometer's context propagation). Test: with `TestObservationRegistry` from `micrometer-observation-test`, assert an observation named `http.server.requests` was recorded for the call; manually, one trace in Tempo shows the controller, the SQL spans and the consumer in the second service.
3. **Logs that join the trace.** Logback JSON encoder with `traceId` and `spanId` fields (Spring Boot's default pattern already prints them once tracing is on the classpath); ship them over OTLP. Spring Boot 3.4 added auto-configuration for the OpenTelemetry Logback appender; on earlier versions add `opentelemetry-logback-appender-1.0` and install it against the auto-configured `OpenTelemetry` bean yourself. Test: `OutputCaptureExtension` captures the log of a traced request and asserts the `traceId` field is present and 32 hex characters.
4. **SLOs and burn-rate alerts.** The recording and alert rules above for availability, the same shape for latency using `http_server_requests_seconds_bucket` with the `le="0.3"` bucket enabled through `management.metrics.distribution.slo.http.server.requests=300ms`, plus slow-burn alerts (6x over 6 hours, 1x over 3 days) that only ticket. Test: `promtool check rules` and `promtool test rules` in CI with one test per alert, for both firing and not firing.
5. **Game day.** Write the plan first: hypothesis, blast radius, abort condition. Then stop PostgreSQL for three minutes, add 500 ms latency to Kafka with Toxiproxy, and fill the connection pool with a slow query. For each, record the time to alert, the time to find the cause from the dashboard and trace, and what was missing. Deliverable: a postmortem with a timeline and three action items, at least one of which you then implement.

Definition of done:

- 2.1 `docker compose up` starts the service and all five infrastructure containers; one `curl` produces a metric sample, a trace in Tempo and a log line in Loki that share one trace ID, and the README shows the screenshot of the jump from trace to logs.
- 2.2 Both SLOs have fast-burn and slow-burn alerts with `promtool` unit tests that run in CI.
- 2.3 The game-day postmortem is in the repository with the measured time to alert for each injected failure.

Stretch goals:

- 3.1 Tail-based sampling in the collector: keep every trace with an error or over 300 ms, sample the rest at one percent, and measure storage per day before and after.
- 3.2 Exemplars: link the latency histogram to example trace IDs so a spike in Grafana opens the slow trace.

## Pitfalls

- High-cardinality tags. One custom tag with a user ID or an order ID on `http.server.requests` multiplies the series count by your user count and takes Prometheus down; tag by template, never by value.
- Alerting on causes. CPU at 80 percent is not an incident; a burn rate is. Keep cause-based rules as dashboard panels, not pages.
- A single short window. Alerting on a 5-minute error ratio alone pages you for a blip and misses a slow leak; the multi-window, multi-burn-rate shape exists for both reasons.
- Losing the trace at a thread boundary. `@Async`, `CompletableFuture.supplyAsync` and Kafka consumers all drop context unless propagation is configured; the sign is a log line with an empty `traceId`.
- 100 percent sampling in production. Fine on a laptop; in production decide a probability or use tail-based sampling, and say which in the README.
- Everything shows as `unknown_service`. Set `spring.application.name`; the resource attribute `service.name` is derived from it.
- The collector's `batch` processor missing. Without it every span is its own request to Tempo, and the collector itself becomes the bottleneck in the load test.

## Check yourself

1. Why does a 14.4x burn rate over one hour correspond to two percent of a 30-day budget, and what burn rate would you page on for a 99.99 percent SLO?
2. Which signal answers "is it broken", which answers "where", and which answers "why" for a request that returned `500` after a slow SQL query?
3. A Grafana panel shows p99 latency doubling but no alert fired. Walk through the latency SLO definition and name two reasons the alert could be correct to stay silent.
4. During the game day the connection-pool exhaustion took eight minutes to alert. What metric would have shown it in one, and should that metric page or ticket?

## Go deeper

- [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) · the multi-window, multi-burn-rate method the rules follow.
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) · how to choose the SLO in the first place.
- [OpenTelemetry documentation](https://opentelemetry.io/docs/) · collector configuration, signals and semantic conventions.
- [Prometheus: Overview](https://prometheus.io/docs/introduction/overview/) · the data model, PromQL and `promtool`.
- [Grafana Loki documentation](https://grafana.com/docs/loki/latest/) · OTLP ingestion and LogQL for milestone 3.
- [Grafana tutorials](https://grafana.com/tutorials/) · provisioning dashboards and data sources from files.
- [Grafana: The RED Method](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/) · the three panels every service dashboard starts with.
- [Principles of Chaos Engineering](https://principlesofchaos.org/) · the hypothesis-first shape of the game day.

---

Part of [Projects](../README.md) · item 4.4
