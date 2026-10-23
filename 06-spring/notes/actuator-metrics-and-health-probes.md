# Actuator, metrics and health probes

> **In one sentence:** Actuator exposes the application's health and metrics over HTTP so that Kubernetes can decide when to restart or route to a pod and Prometheus can scrape what the application measured, and getting it right means separate liveness and readiness groups, a Micrometer `Timer` or `Counter` per business operation with low-cardinality tags, and nothing sensitive exposed without authentication.

**Why it matters:** A liveness probe that checks the database turns a database outage into a restart storm of perfectly healthy pods. A metric tagged with the customer id produces a million time series and takes Prometheus down. An unprotected `/actuator/env` or `/actuator/heapdump` is a data breach waiting for a port scan. All three are one property away from correct, and all three are routinely wrong.

## The idea

`spring-boot-starter-actuator` registers endpoints under `/actuator`. Over HTTP only `health` is exposed by default; everything else must be opted in:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
```

Expose `env`, `beans`, `conditions`, `loggers`, `threaddump` and `heapdump` only where authentication protects them, or on a separate management port (`management.server.port=9090`) that the ingress does not route. With Spring Security, `EndpointRequest.toAnyEndpoint()` matches all of them in one rule, and `EndpointRequest.to(HealthEndpoint.class)` lets you leave health open for the orchestrator.

**Health** aggregates `HealthIndicator` beans: `db` (runs a validation query), `diskSpace`, `ping`, plus one per configured technology (Redis, Kafka, mail). The status is `UP`, `DOWN`, `OUT_OF_SERVICE` or `UNKNOWN`; details are shown according to `management.endpoint.health.show-details` (`never` by default; `when-authorized` is the sane production value). **Health groups** let you build several views: `management.endpoint.health.group.<name>.include=...` creates `/actuator/health/<name>` from a subset of indicators.

**Kubernetes probes** are two such groups with special indicators. `livenessState` reflects `LivenessState.CORRECT` or `BROKEN`: is the process in a state it can recover from only by restarting? `readinessState` reflects `ReadinessState.ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`: should the Service route requests here right now? Boot flips readiness to accepting after `ApplicationReadyEvent` and back to refusing when graceful shutdown begins, so with `server.shutdown=graceful` a terminating pod is removed from the load balancer before in-flight requests finish. Boot enables the groups automatically when it detects Kubernetes (`KUBERNETES_SERVICE_HOST` in the environment); `management.endpoint.health.probes.enabled=true` enables them everywhere.

The rule for what goes where: liveness contains **only** `livenessState`. A failing database is not fixed by restarting the application, so it must not be in the liveness group. Readiness may include external dependencies that the pod cannot serve without, but think about shared failures: if every pod depends on the same database and it goes down, every pod turns unready at once and the Service has no endpoints, which is sometimes the right outcome and sometimes worse than serving degraded responses.

**Micrometer** is the metrics facade Boot uses. Four meter types cover almost everything:

- `Counter`: a monotonically increasing count (`orders.placed`). Rates and totals are computed from it at query time.
- `Timer`: count, total time and max of an operation, optionally with a histogram so the backend can compute percentiles (`publishPercentileHistogram()`).
- `Gauge`: a value sampled when the registry is read (queue depth, pool size). It holds a weak reference to the object it observes; a gauge registered on an object nobody else references is garbage collected and reports `NaN`.
- `DistributionSummary`: like a timer, for sizes rather than durations (payload bytes).

**Tags** split a meter into one time series per distinct combination of values. `http.server.requests` is tagged with `method`, `uri`, `status`, `outcome` and `exception`; `uri` holds the template (`/api/orders/{id}`), never the actual path, and that is the whole cardinality discipline in one example. A tag is safe when you can list its possible values: status codes, methods, a provider name, an order type. User ids, order ids, email addresses, free text and raw URLs are never tags; they go in logs or traces.

**Prometheus** scrapes `/actuator/prometheus` (add `micrometer-registry-prometheus`). Micrometer renames meters to the Prometheus convention: `http.server.requests` becomes `http_server_requests_seconds_count`, `_sum` and `_max`, and histograms add `_bucket` series. The same meters can be shipped to any other supported backend by swapping the registry dependency.

**What you get for free:** `http.server.requests` for every MVC request; `http.client.requests` for `RestClient` and `RestTemplate` instances built from the auto-configured builders; `jvm.memory.used`, `jvm.gc.pause`, `jvm.threads.live`; `process.cpu.usage` and `system.cpu.usage`; `hikaricp.connections.active`, `idle`, `pending`, `timeout` and `acquire` for the connection pool; `jdbc.connections.*`; `logback.events` by level; `spring.data.repository.invocations`; `application.started.time` and `application.ready.time`; and, when tracing is configured, exemplars linking histogram buckets to traces.

## Example: probe properties and a custom timer

Application properties:

```properties
management.endpoints.web.exposure.include=health,info,metrics,prometheus
management.endpoint.health.probes.enabled=true
management.endpoint.health.show-details=when-authorized
management.endpoint.health.group.liveness.include=livenessState
management.endpoint.health.group.readiness.include=readinessState,db
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

The matching probes in the pod spec:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 2
  failureThreshold: 60
```

The startup probe gives the JVM up to two minutes to come up before liveness checks begin, which avoids the classic restart loop of a slow-starting service on a busy node.

A service measuring its own business operation:

```java
@Service
public class PaymentGateway {

    private final PaymentProviderClient paymentProviderClient;
    private final Timer captureTimer;
    private final Counter declinedCounter;

    public PaymentGateway(PaymentProviderClient paymentProviderClient, MeterRegistry meterRegistry) {
        this.paymentProviderClient = paymentProviderClient;
        this.captureTimer = Timer.builder("payments.capture")
                .description("Time to capture a payment at the provider")
                .tag("provider", "stripe")
                .publishPercentileHistogram()
                .register(meterRegistry);
        this.declinedCounter = Counter.builder("payments.declined")
                .tag("provider", "stripe")
                .register(meterRegistry);
    }

    public CaptureResult capture(Payment payment) {
        return captureTimer.record(() -> {
            CaptureResult result = paymentProviderClient.capture(payment);
            if (result.declined()) {
                declinedCounter.increment();
            }
            return result;
        });
    }
}
```

Meters are created once in the constructor and reused; `Timer.record` handles the timing and the exception path. After a few requests `/actuator/prometheus` contains (abridged):

```text
# HELP payments_capture_seconds Time to capture a payment at the provider
# TYPE payments_capture_seconds histogram
payments_capture_seconds_bucket{provider="stripe",le="0.1"} 38.0
payments_capture_seconds_bucket{provider="stripe",le="0.5"} 41.0
payments_capture_seconds_bucket{provider="stripe",le="+Inf"} 42.0
payments_capture_seconds_count{provider="stripe"} 42.0
payments_capture_seconds_sum{provider="stripe"} 9.87
payments_capture_seconds_max{provider="stripe"} 1.2
payments_declined_total{provider="stripe"} 3.0
```

`@Timed("payments.capture")` on the method does the same declaratively, provided the Micrometer aspect and AOP support are on the classpath; the programmatic form works everywhere and makes the tags explicit. In Boot 3 the `ObservationRegistry` is the higher-level option: one `Observation` produces both the timer and a trace span (item 8.2).

## Pitfalls

- `db` in the liveness group. The database hiccups, every pod restarts, the connection storm on recovery makes it worse.
- `management.endpoints.web.exposure.include=*` on the application port with no security. `env` shows configuration, `heapdump` contains everything in memory including credentials and session data.
- High-cardinality tags. Each distinct value is a new series; a user id tag on a request counter is a slow-motion outage of your monitoring. Micrometer can cap it with a `MeterFilter.maximumAllowableTags`, but the fix is to not do it.
- Creating meters inside the request path with `meterRegistry.counter("...", "tag", value)`. The lookup is cached, but building tag values from request data is how cardinality explodes; build meters once.
- Gauges on temporary objects, or gauges that compute something expensive. The first reports `NaN` after garbage collection; the second runs on every scrape.
- Readiness that stays green while a dependency the service cannot function without is gone, or liveness that goes red because of it. Decide per dependency and write the decision in the group configuration.
- Treating `show-details=always` as harmless. Health details include connection errors with hostnames and sometimes usernames; keep them behind authentication.

## Check yourself

1. The database goes down for two minutes. Describe what Kubernetes does to the pods with `db` in the liveness group, and with `db` only in readiness.
2. Which of these are acceptable tags on `orders.placed`: `channel` (web, app, api), `country`, `customer_id`, `coupon_code`? Explain each.
3. What does `server.shutdown=graceful` change about the readiness probe during a rolling deployment, and why does that matter for in-flight requests?
4. A `Gauge` registered on a locally created `Queue` reports `NaN` after a few minutes. Why, and what is the fix?

## Go deeper

- [Spring Boot: Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html) · endpoints, exposure, health groups and securing them.
- [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) · the liveness and readiness states, when they change, and how to contribute to them.
- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) · the full list of auto-configured meters and the registry properties.
- [Micrometer](https://micrometer.io/) · meter types, naming conventions and the Prometheus registry.
- [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) · the probe semantics from the other side.

---

Part of [Spring](../README.md) · items 2.5, 8.1, 8.3
