# Resilience with Resilience4j and Spring

> **In one sentence:** Resilience is layered in a fixed order: a timeout on every remote call so that failure becomes detectable, a bounded retry with backoff for failures that are transient, a circuit breaker so that a dependency that is down is not called at all, and a bulkhead or rate limiter so that one dependency cannot consume every thread, with Resilience4j supplying each as an annotation and Micrometer showing the breaker's state.

**Why it matters:** Cascading failure is how one slow partner takes down an otherwise healthy service, and the usual quick fix, a retry loop, makes it worse. Interviewers ask about circuit breakers because the pattern is famous; what marks a strong answer is knowing why the timeout comes first, why fallbacks are dangerous, and how to see the breaker's state in production rather than in a diagram.

## The idea

**Timeouts first.** A call without a timeout can block forever, and a blocked call is invisible to every other mechanism: a retry cannot start and a breaker cannot count a failure that has not happened yet. Set connect and read timeouts on the HTTP client (item 3.5), `query-timeout` on JDBC and `timeout` on long transactions, and only then layer the rest. Resilience4j's `@TimeLimiter` works on methods returning `CompletableFuture` only; for blocking code the client's own timeout is the tool.

**Retry.** `@Retry(name)` re-invokes the method on failure: `max-attempts` (3 by default, counting the first call), `wait-duration`, exponential backoff with `enable-exponential-backoff` and `exponential-backoff-multiplier`, jitter with `enable-randomized-wait`, and `retry-exceptions` and `ignore-exceptions` to say which failures qualify. Retry only what can succeed on a second try (timeouts, 5xx, connection resets) and only operations that are safe to repeat, and do the arithmetic: attempts times timeout plus waits is the latency the caller must tolerate.

**Circuit breaker.** `@CircuitBreaker(name)` records the outcome of recent calls in a sliding window (`sliding-window-size` calls, or seconds with `TIME_BASED`) and, once `minimum-number-of-calls` have been recorded, opens when the failure rate exceeds `failure-rate-threshold` or the slow-call rate exceeds `slow-call-rate-threshold`, a slow call being one longer than `slow-call-duration-threshold`. While OPEN, calls fail at once with `CallNotPermittedException` for `wait-duration-in-open-state`; then HALF_OPEN lets `permitted-number-of-calls-in-half-open-state` through and closes or reopens on their outcome. `ignore-exceptions` lists failures that are the caller's fault (a 4xx) and must not count. Every retry attempt is a separate call from the breaker's point of view.

**Bulkhead and rate limiter.** `@Bulkhead(name)` caps concurrent calls to a dependency (`max-concurrent-calls`, `max-wait-duration`), so a slow dependency can hold at most that many threads; the thread-pool variant (`type = THREADPOOL`) isolates `CompletableFuture` methods in their own pool. `@RateLimiter(name)` caps calls per period (`limit-for-period`, `limit-refresh-period`, `timeout-duration`), which is for respecting a partner's quota rather than protecting yourself.

**Decorator order.** With several annotations on one method, the Resilience4j aspects apply in a fixed order: Retry outermost, then CircuitBreaker, RateLimiter, TimeLimiter, and Bulkhead innermost. So the retry sees the breaker: when the breaker is open, every attempt gets `CallNotPermittedException`, which is why retries should be limited to specific exceptions or that one excluded. The order is configurable through the `*-aspect-order` properties, rarely for a good reason.

**Fallbacks.** `fallbackMethod` names a method in the same class with the same parameters plus a trailing exception parameter; Resilience4j picks the fallback whose exception type matches, so you can fall back for an open breaker and let other failures propagate. A fallback is right when a degraded answer exists: a cached value, a default, an empty recommendation list marked as such. It is dangerous when it hides failure: an empty list from "the customer's orders" turns an outage into "you have no orders", a fallback on a write pretends the write happened, and a fallback that reaches the same dependency another way doubles the load. Count fallbacks in a metric and alert on the breaker state independently of the error rate, which the fallback has just made look fine.

**Metrics and endpoints.** With Actuator present, Resilience4j registers `resilience4j.circuitbreaker.state` (a gauge per state, 1 for the current one), `resilience4j.circuitbreaker.calls` (a timer tagged `kind` = `successful`, `failed` or `ignored`), `resilience4j.circuitbreaker.not.permitted.calls`, `resilience4j.circuitbreaker.failure.rate` and `slow.call.rate`, and `resilience4j.retry.calls` tagged `kind` (`successful_without_retry`, `successful_with_retry`, `failed_with_retry`, `failed_without_retry`), all tagged `name`. `/actuator/circuitbreakers` and `/actuator/circuitbreakerevents` show the states and recent transitions. `register-health-indicator: true` adds the breaker to `/actuator/health`, where an open breaker reports the dependency as down; that is useful in the readiness discussion and must never reach a liveness probe (item 8.3).

**Spring Framework 7.** Core Spring now ships `@Retryable` (attempts, delay, multiplier, maximum delay, jitter, included and excluded exceptions) and `@ConcurrencyLimit`, enabled with `@EnableResilientMethods`, plus a programmatic `RetryTemplate`. They cover retry and a semaphore bulkhead without a library; there is no circuit breaker in core, so Resilience4j stays the tool when you need one.

## Example: a partner call with timeout, retry and circuit breaker

Dependencies: `io.github.resilience4j:resilience4j-spring-boot3`, `spring-boot-starter-aop` and `spring-boot-starter-actuator`. `ShippingPartnerApi` is the interface client from item 3.5, whose `RestClient` has a two-second connect timeout and a five-second read timeout.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      shippingPartner:
        sliding-window-type: COUNT_BASED
        sliding-window-size: 50
        minimum-number-of-calls: 20
        failure-rate-threshold: 50
        slow-call-duration-threshold: 2s
        slow-call-rate-threshold: 80
        wait-duration-in-open-state: 30s
        permitted-number-of-calls-in-half-open-state: 5
        automatic-transition-from-open-to-half-open-enabled: true
        register-health-indicator: true
        ignore-exceptions:
          - org.springframework.web.client.HttpClientErrorException
  retry:
    instances:
      shippingPartner:
        max-attempts: 3
        wait-duration: 200ms
        enable-exponential-backoff: true
        exponential-backoff-multiplier: 2
        enable-randomized-wait: true
        randomized-wait-factor: 0.5
        retry-exceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
  bulkhead:
    instances:
      shippingPartner:
        max-concurrent-calls: 20
        max-wait-duration: 0
```

```java
@Service
public class ShipmentStatusService {

    private static final Logger log = LoggerFactory.getLogger(ShipmentStatusService.class);

    private final ShippingPartnerApi shippingPartnerApi;

    public ShipmentStatusService(ShippingPartnerApi shippingPartnerApi) {
        this.shippingPartnerApi = shippingPartnerApi;
    }

    @Retry(name = "shippingPartner")
    @CircuitBreaker(name = "shippingPartner", fallbackMethod = "statusUnavailable")
    @Bulkhead(name = "shippingPartner")
    public ShipmentStatus status(String shipmentId) {
        return shippingPartnerApi.shipment(shipmentId).status();
    }

    private ShipmentStatus statusUnavailable(String shipmentId, CallNotPermittedException exception) {
        log.warn("shipping partner circuit is open, reporting UNKNOWN for shipment {}", shipmentId);
        return ShipmentStatus.UNKNOWN;
    }
}
```

Reading it from the inside out: the bulkhead admits at most twenty concurrent calls and rejects the twenty-first immediately (`max-wait-duration: 0`) with `BulkheadFullException`. The breaker records each call; a 404 is ignored, a timeout (`ResourceAccessException`) or a 5xx counts as a failure, and a 3-second answer counts as slow. Once twenty calls are in the window and half have failed or eighty percent were slow, it opens for thirty seconds, then trials five calls. The retry wraps all of that and repeats only on timeouts and 5xx, waiting about 200 ms and then about 400 ms, each randomised by half. `CallNotPermittedException` is not in `retry-exceptions`, so an open breaker costs one attempt, and the fallback handles exactly that exception: the business decided that `UNKNOWN` is an acceptable degraded status when the partner is known to be down, while a timeout after three attempts propagates and becomes a 503 through the advice of item 3.3, so the failure stays visible.

The worst case for one call is three attempts of up to seven seconds (connect plus read) plus the waits, roughly twenty-two seconds. If the caller's budget is eight seconds, cut the read timeout or the attempts; do not add a fallback to hide the wait.

Prometheus during an outage (abridged):

```text
resilience4j_circuitbreaker_state{name="shippingPartner",state="closed"} 0.0
resilience4j_circuitbreaker_state{name="shippingPartner",state="open"} 1.0
resilience4j_circuitbreaker_failure_rate{name="shippingPartner"} 62.0
resilience4j_circuitbreaker_not_permitted_calls_total{kind="not_permitted",name="shippingPartner"} 318.0
resilience4j_retry_calls_total{kind="failed_with_retry",name="shippingPartner"} 31.0
```

Alert on `state{state="open"} == 1` lasting more than a few minutes, and dashboard the `not_permitted` count: it is the number of users who received `UNKNOWN`.

## Pitfalls

- A breaker on a call with no timeout. Nothing fails, so nothing is counted, and the threads pile up; only the slow-call threshold could eventually open it, after each call has finally returned.
- Retrying everything, including `CallNotPermittedException`, 4xx responses and non-idempotent writes. The first wastes attempts, the second cannot succeed, the third duplicates side effects.
- Retries without jitter. Every instance retries at the same instant and the partner sees synchronised waves.
- A fallback that hides failure. Empty lists, zero balances and "success" for writes turn an outage into silent wrong data; prefer an explicit degraded value or a propagated error.
- `minimum-number-of-calls` mismatched to traffic. Too high on a quiet dependency and the breaker never opens; too low and a single blip opens it.
- One breaker name for everything a partner offers. A slow reporting endpoint opens the breaker for the fast lookup too; name breakers per failure domain.
- A method that catches its own exceptions. The breaker sees success; make failures visible to it by throwing or by configuring `record-exceptions`.
- A fallback method with the wrong signature. It is resolved at runtime, so the mistake surfaces during the first outage.

## Check yourself

1. Why is a circuit breaker on a call without a read timeout almost useless, and which threshold could still open it eventually?
2. With retry outermost, what happens on each attempt while the breaker is open, and which two configuration lines make that cheap?
3. A fallback returns an empty list for "orders of this customer" while the order service is down. What does the user see, what does the error rate show, and what would you return instead?
4. Work out the worst-case latency of the example and name the knob you would turn first if the caller's budget were eight seconds.

## Go deeper

- [Resilience4j](https://resilience4j.readme.io/) · the documentation; the CircuitBreaker and Retry pages explain every property and state transition.
- [Resilience4j: CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker) · the state machine, sliding windows and thresholds, with diagrams.
- [Resilience4j: Getting started with Spring Boot](https://resilience4j.readme.io/docs/getting-started-3) · the Boot starter, the annotations, the aspect order and the Actuator endpoints.
- [Spring: Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html) · Spring Framework 7's `@Retryable`, `@ConcurrencyLimit` and `RetryTemplate`.
- [Release It!, second edition](https://pragprog.com/titles/mnee2/release-it-second-edition/) · Michael Nygard's book, where circuit breakers and bulkheads were named (paid).
- [AWS Builders' Library: Timeouts, retries and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) · why jitter and budgets matter, from a team that runs at scale.

---

Part of [Spring](../README.md) · item 8.4
