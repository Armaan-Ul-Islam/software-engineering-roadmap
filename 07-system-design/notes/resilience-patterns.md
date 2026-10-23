# Resilience patterns: timeouts, circuit breakers, bulkheads and load shedding

> **In one sentence:** A service survives a failing dependency by refusing to wait for it indefinitely (timeouts), refusing to keep calling it when it is clearly down (circuit breakers), refusing to let it consume every thread and connection (bulkheads), refusing work it cannot finish (load shedding and bounded queues), and degrading on purpose instead of by accident.

**Why it matters:** Most large outages are not caused by the component that failed; they are caused by healthy components waiting on it until they fail too. A slow recommendations service that nobody needs for checkout takes down checkout because every request thread is blocked on it. These patterns exist to turn "one dependency is slow" back into a local problem.

## The idea

**Timeouts everywhere.** Every network call needs a timeout, because the default is usually infinite: Java's `HttpClient` waits forever unless you set one, and so does a JDBC query without a socket or statement timeout. Set both a connect timeout (short: a healthy host inside a region answers in milliseconds) and a response timeout. Choose the response timeout from the dependency's measured tail (its p99 or p99.9 plus margin, see item 1.4), then cap it by your own deadline: if your caller gives up after 2 s, a 5 s timeout on a dependency is a lie. Deadlines should flow down the call chain (gRPC propagates them; over HTTP you pass the remaining budget in a header), so that each hop knows how long it may take.

**Retries** belong only after timeouts and only for idempotent calls, with backoff, jitter and a budget; see [idempotency, retries and exactly once](idempotency-retries-and-exactly-once.md) for the rules. The one point to repeat here: a retry is extra load on a struggling dependency, so the circuit breaker must be allowed to stop it.

**Circuit breakers.** A breaker wraps calls to one dependency and has three states. *Closed*: calls pass, outcomes are recorded in a sliding window. *Open*: after the failure rate (or the slow-call rate) in the window crosses a threshold, calls fail immediately with an exception, without touching the dependency, for a wait duration. *Half-open*: a few trial calls are let through; success closes the breaker, failure reopens it. The point is not to protect the dependency, though it helps; it is to make your own failures fast and cheap instead of a timeout each. Thresholds: require a minimum number of calls before judging (so a single failure at startup does not trip it), count slow calls as failures, and keep one breaker per dependency (ideally per host), not one for the whole service. Export the state; a breaker that opens silently is an outage you learn about from users.

**Bulkheads.** Give each dependency its own bounded pool of resources (threads, connections, or simply a semaphore of N concurrent calls) so that one slow dependency can block at most N of your workers. With virtual threads the bulkhead is a semaphore in front of the call. Size it from Little's law (concurrency = request rate × latency, plus headroom): twenty calls per second at 100 ms needs about two permits in steady state, perhaps ten under stress.

**Load shedding and admission control.** When more work arrives than you can finish, serving everything slowly serves nobody: every request times out at the client, which retries, and goodput falls to zero. Shed early instead: reject with 503 (or 429 for a specific client) when the queue is deeper or older than your latency target allows, when CPU is saturated, or when in-flight requests exceed a limit. Drop low-priority work first, keep health checks and already-admitted requests flowing, and make the rejection cheaper than the work, so the server keeps its full useful throughput however much is thrown at it.

**Backpressure and bounded queues.** An unbounded queue hides overload: latency grows for minutes, then the process dies of memory exhaustion. Bound every queue and decide the rejection policy explicitly. Little's law again: with 1,000 requests per second arriving and a queue bounded at 500, the longest any request waits in the queue is about 0.5 s, which you can promise. `Executors.newFixedThreadPool` uses an unbounded queue, so it is the wrong default for request handling; `ThreadPoolExecutor` with an `ArrayBlockingQueue` and a rejection handler is the right one. Pull-based systems (Kafka consumers, Reactive Streams `request(n)`, TCP flow control) propagate pressure upstream naturally; push-based ones need a bound and a response code.

**Graceful degradation.** Decide in advance what the product looks like without each dependency: a product page without recommendations, search without personalisation, a stale price with a warning. Build those paths, flag them so they can be switched manually, and test them, because a degraded mode nobody has run is a second outage waiting behind the first.

**Why fallbacks can make things worse.** A fallback is code that runs only when something is already wrong, under the worst conditions, and is almost never tested. It fails in new ways; it adds load (falling back to the database when the cache is down is how the database dies); it can silently return wrong data (an empty list as the fallback for "items in cart" ships nothing); and it hides the failure from the people who should fix it. Amazon's guidance is to prefer failing fast, keeping the normal path simple, or exercising the "fallback" path all the time so it is not special. Use a fallback when the degraded answer is clearly labelled, cheaper than the normal path, and exercised continuously.

## Example: a dependency call wrapped with Resilience4j

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.core.IntervalFunction;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.timelimiter.TimeLimiter;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import java.io.IOException;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeoutException;

public final class ResilientPricingClient {

    private final PricingApi pricingApi;
    private final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();

    private final TimeLimiter timeLimiter = TimeLimiter.of(TimeLimiterConfig.custom()
            .timeoutDuration(Duration.ofMillis(800))
            .cancelRunningFuture(true)
            .build());

    private final CircuitBreaker circuitBreaker = CircuitBreaker.of("pricing", CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(100)
            .minimumNumberOfCalls(20)
            .failureRateThreshold(50)
            .slowCallDurationThreshold(Duration.ofMillis(500))
            .slowCallRateThreshold(80)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .permittedNumberOfCallsInHalfOpenState(5)
            .build());

    private final Retry retry = Retry.of("pricing", RetryConfig.custom()
            .maxAttempts(3)
            .intervalFunction(IntervalFunction.ofExponentialRandomBackoff(Duration.ofMillis(100), 2.0, 0.5))
            .retryExceptions(TimeoutException.class, IOException.class)
            .build());

    public ResilientPricingClient(PricingApi pricingApi) {
        this.pricingApi = pricingApi;
    }

    public Optional<Price> priceFor(String productId) {
        Callable<Price> timed = TimeLimiter.decorateFutureSupplier(timeLimiter, () -> executor.submit(() -> pricingApi.fetch(productId)));
        Callable<Price> guarded = CircuitBreaker.decorateCallable(circuitBreaker, timed);
        Callable<Price> retried = Retry.decorateCallable(retry, guarded);
        try {
            return Optional.of(retried.call());
        } catch (CallNotPermittedException exception) {
            return Optional.empty();          // breaker open: degrade without waiting
        } catch (Exception exception) {
            return Optional.empty();          // all attempts failed: the page renders without a price
        }
    }
}
```

The order matters and reads inside out: the time limiter wraps the raw call, so a hung request becomes a `TimeoutException` after 800 ms; the circuit breaker wraps that, so timeouts and slow calls are recorded against the dependency and, once it opens, calls fail in microseconds with `CallNotPermittedException`; the retry wraps everything, so each attempt is a fresh, time-limited, breaker-checked call. Because `retryExceptions` lists only timeouts and I/O errors, an open breaker is not retried, which is the whole point of having it. Worst case for one page: three attempts of 800 ms plus two backoffs of roughly 100 and 200 ms, about 2.7 s, which must fit inside the caller's deadline or the limits are wrong. Resilience4j's Spring Boot annotations apply the same nesting by default: Retry outside, then CircuitBreaker, RateLimiter, TimeLimiter, and Bulkhead closest to the call. The `Optional.empty()` is a deliberate, labelled degradation ("price unavailable"), not a guessed value.

## Pitfalls

- Default timeouts. Infinite is the default in more clients than you think; audit every HTTP client, JDBC pool and message client for connect, read and pool-acquire timeouts.
- Timeouts longer than the caller's deadline. The work completes after the caller has gone; you have paid for it and nobody benefits.
- One circuit breaker for everything, or thresholds without a minimum call count. The first opens for the wrong reason; the second opens on the first failure after a deploy.
- Fallback to the thing you were caching. The cache failing sends full load to the database, which was sized for the miss rate.
- Unbounded queues and `newFixedThreadPool` for request work. Latency climbs for minutes with no error, then the heap fills.
- Shedding load after doing the work. Admission control must happen before deserialisation, authentication and database calls, or it saves nothing.

## Check yourself

1. A dependency's p99 is 300 ms and your endpoint promises 1 s. What timeout, how many retries, and why does the arithmetic matter?
2. Explain what each of the three breaker states does to a call, and why a breaker needs a minimum number of calls before it may open.
3. Requests arrive at 2,000 per second and your queue is bounded at 1,000. What is the worst-case queueing delay, and what happens to the 2,001st request?
4. Give one example of a fallback that makes an outage worse, and one of a degradation that is safe. What distinguishes them?

## Go deeper

- [Release It!, 2nd edition](https://pragprog.com/titles/mnee2/release-it-second-edition/) · the stability patterns (timeouts, circuit breaker, bulkhead, steady state) told through real outages (paid).
- [AWS Builders' Library: Avoiding fallback in distributed systems](https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/) · the case against fallback logic, with what Amazon does instead.
- [AWS Builders' Library: Using load shedding to avoid overload](https://aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/) · goodput, admission control and why the server must stay fast under any load.
- [Google SRE Book: Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) · how one slow component takes the rest down, and the ordered list of defences.
- [Resilience4j: Circuit breaker](https://resilience4j.readme.io/docs/circuitbreaker) · the state machine and every threshold in the example, documented.

---

Part of [System Design](../README.md) · items 4.2, 4.3
