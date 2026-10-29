# Low-level design interviews

> **In one sentence:** A low-level design interview asks you to turn a small, familiar system (a parking lot, an elevator, a cache, a rate limiter) into classes, interfaces and responsibilities in 45 minutes, and it is scored on whether the design absorbs the follow-up change the interviewer has prepared without a rewrite.

**Why it matters:** This is the interview closest to the day job: the same judgement that keeps a service maintainable after two years of feature requests. Candidates who can solve graph problems often fail here by producing one god class, by modelling every noun as a class without behaviour, or by applying patterns before there is a problem for them to solve.

## The idea

**What is being tested.** Not UML fluency. The interviewer wants to see: clarified requirements, a small set of types with clear responsibilities, the right abstraction at the points that are likely to change, and code that would actually run. The hidden test is the follow-up ("now add a reserved spot type", "now the elevator must prefer the direction it is going", "now the limit is per endpoint as well as per client"), which reveals whether your boundaries were in the right place.

**A protocol for 45 minutes.**

1. **Requirements (5 minutes).** Ask what is in and out of scope, the scale (one process or many?), concurrency (one thread or many?), and what "correct" means. Write the three or four functional requirements down. For a rate limiter: per-client limits, what happens on rejection, whether bursts are allowed, single node.
2. **Core entities and operations (10 minutes).** List the nouns that have behaviour and the verbs the caller invokes. Pick the one interface the caller sees (`RateLimiter.tryAcquire(clientId)`, `ParkingLot.park(vehicle)`, `Cache.get(key)`). Decide which decisions are *policies* (the limiting algorithm, the spot assignment strategy, the eviction policy) and which are *mechanics* (storage, time, locking). Policies become interfaces; mechanics are injected.
3. **Code the core path (20 minutes).** Write the real code for the main operation, not pseudocode. Keep state private, make invariants obvious, and inject the clock and any store so that the design is testable without sleeping.
4. **Extend and harden (10 minutes).** Take the follow-up. Show which class changes and which do not. Then discuss concurrency (which methods are entry points, what is locked, what is lock-free) and failure (what happens when the store is unavailable).

**SOLID as concrete choices, not slogans.**

| Principle | What it looks like in the interview |
|---|---|
| Single responsibility | `TokenBucket` knows about tokens and refill; the limiter knows about clients; neither knows about HTTP. |
| Open/closed | A new algorithm (sliding window) is a new `RateLimiter` implementation, not an `if` in the old one. |
| Liskov substitution | Every `ParkingSpot` subtype honours `canFit(vehicle)`; no subtype throws "unsupported". |
| Interface segregation | The caller sees `tryAcquire`; the admin API that resets buckets is a separate interface. |
| Dependency inversion | The limiter takes a `LongSupplier` clock and a store interface; tests pass a fake clock. |

**The four classic problems and their one key decision.**

| Problem | Key abstraction | The prepared follow-up |
|---|---|---|
| Parking lot | `Spot` types with `canFit(Vehicle)`, a `SpotAssignmentStrategy`, a `Ticket` that records entry time and spot | pricing by vehicle type, reserved or electric spots, multiple entrances |
| Elevator | `Elevator` state machine (idle, moving up, moving down), a `Dispatcher` strategy choosing which car takes a request, request queues per direction | several cars, express floors, a maintenance mode |
| Cache | `Cache<K, V>` interface, an `EvictionPolicy` (LRU is a hash map plus a doubly linked list; `LinkedHashMap` with access order in Java), capacity and TTL | TTL, size in bytes instead of entries, thread safety, write-through |
| Rate limiter | `RateLimiter.tryAcquire(key)`, an algorithm (token bucket, fixed window, sliding log), a clock, a per-key store | per-endpoint keys, distributed store, returning retry-after |

## Example: a token-bucket rate limiter

Requirements agreed with the interviewer: each client may make `tokensPerSecond` requests on average with bursts up to `capacity`; one process, many threads; rejected calls return `false` immediately.

```java
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.function.LongSupplier;

public final class RateLimiterDemo {

    public interface RateLimiter {
        boolean tryAcquire(String clientId);
    }

    public static final class TokenBucket {
        private final int capacity;
        private final double tokensPerNanosecond;
        private double tokens;
        private long lastRefillNanos;

        TokenBucket(int capacity, double tokensPerNanosecond, long nowNanos) {
            this.capacity = capacity;
            this.tokensPerNanosecond = tokensPerNanosecond;
            this.tokens = capacity;
            this.lastRefillNanos = nowNanos;
        }

        synchronized boolean tryConsume(long nowNanos) {
            refill(nowNanos);
            if (tokens < 1) {
                return false;
            }
            tokens -= 1;
            return true;
        }

        private void refill(long nowNanos) {
            long elapsed = nowNanos - lastRefillNanos;
            tokens = Math.min(capacity, tokens + elapsed * tokensPerNanosecond);
            lastRefillNanos = nowNanos;
        }
    }

    public static final class TokenBucketRateLimiter implements RateLimiter {
        private final int capacity;
        private final double tokensPerNanosecond;
        private final LongSupplier clock;
        private final Map<String, TokenBucket> bucketsByClient = new HashMap<>();

        public TokenBucketRateLimiter(int capacity, int tokensPerSecond, LongSupplier clock) {
            this.capacity = capacity;
            this.tokensPerNanosecond = tokensPerSecond / (double) Duration.ofSeconds(1).toNanos();
            this.clock = clock;
        }

        @Override
        public boolean tryAcquire(String clientId) {
            long now = clock.getAsLong();
            TokenBucket bucket;
            synchronized (bucketsByClient) {
                bucket = bucketsByClient.computeIfAbsent(clientId,
                        ignored -> new TokenBucket(capacity, tokensPerNanosecond, now));
            }
            return bucket.tryConsume(now);
        }
    }

    public static void main(String[] arguments) {
        long[] fakeNowNanos = {0L};
        RateLimiter limiter = new TokenBucketRateLimiter(3, 2, () -> fakeNowNanos[0]);
        StringBuilder trace = new StringBuilder();
        for (int attempt = 0; attempt < 5; attempt++) {
            trace.append(limiter.tryAcquire("alice") ? 'A' : '.');
        }
        System.out.println("t=0ms   alice: " + trace);
        System.out.println("t=0ms   bob:   " + limiter.tryAcquire("bob"));
        fakeNowNanos[0] = Duration.ofMillis(500).toNanos();
        System.out.println("t=500ms alice: " + limiter.tryAcquire("alice") + " " + limiter.tryAcquire("alice"));
        fakeNowNanos[0] = Duration.ofSeconds(10).toNanos();
        trace.setLength(0);
        for (int attempt = 0; attempt < 5; attempt++) {
            trace.append(limiter.tryAcquire("alice") ? 'A' : '.');
        }
        System.out.println("t=10s   alice: " + trace);
    }
}
```

```text
$ java RateLimiterDemo.java
t=0ms   alice: AAA..
t=0ms   bob:   true
t=500ms alice: true false
t=10s   alice: AAA..
```

What to point out while writing it:

- The clock is a `LongSupplier`, so the demo advances time by assignment and the test runs in milliseconds; in production pass `System::nanoTime`.
- Bob has his own bucket; the map is the per-key store. Locking the map only around `computeIfAbsent` and locking each bucket separately keeps clients from contending with each other. A `ConcurrentHashMap` would remove the outer lock.
- After 500 ms at 2 tokens per second, one token has refilled: one success, then a rejection. After 10 seconds the bucket is capped at `capacity`, not at 20, which is the burst limit doing its job.
- The follow-ups fall out of the boundaries: per-endpoint limits change only the key the caller passes; a sliding-window algorithm is a second `RateLimiter` implementation; a distributed limiter replaces the map with a store interface, and the token arithmetic moves server-side (a Redis Lua script) so that read-modify-write stays atomic.

## Pitfalls

- A god class. `ParkingLot` with `park`, `unpark`, `calculateFee`, `findSpot` and `printReceipt` fails the follow-up because every change lands in the same file. Split by reason to change.
- Classes without behaviour. `Vehicle`, `Car`, `Truck` as empty subclasses add nothing; a `VehicleType` enum plus `Spot.canFit(VehicleType)` is smaller and clearer. Subclass only when behaviour differs.
- Patterns first. Announcing "I will use Factory, Strategy, Observer and Singleton" before the requirements are clear is a red flag. Introduce a strategy when there are two concrete strategies to choose between.
- Calling `System.currentTimeMillis()` or `Instant.now()` inside the logic. The design is then untestable without sleeping. Inject the clock.
- Ignoring concurrency until asked, or sprinkling `synchronized` on every method. Name the entry points, say what is shared, and lock the smallest thing that keeps the invariant.
- Pseudocode. Interviewers at most companies expect compilable code for the core path; a sketch that would not compile costs more than a missing feature.
- Inheritance for reuse. A `Cache` that extends `HashMap` exposes `put` without eviction; compose instead.
- No invariants stated. "The bucket never exceeds capacity", "a spot holds at most one vehicle", "the elevator never reverses while carrying passengers in the current direction" are the sentences that show you understand the domain.

## Check yourself

1. The interviewer adds: "limits are per client *and* per endpoint, and the per-endpoint limit is global across clients". Which classes in the example change, and what does the key become?
2. Why is injecting a `LongSupplier` clock preferable to a `Clock` field set via a setter, and what test does it make possible that would otherwise require `Thread.sleep`?
3. Design the interfaces for an LRU cache with a TTL. Which class owns the eviction order, which owns the expiry, and why should neither know about the other?
4. For the elevator, what state does a single `Elevator` need, and which decision belongs to a `Dispatcher` rather than to the elevator itself? Give one input where a naive "nearest car" dispatcher behaves badly.

## Go deeper

- [awesome-low-level-design](https://github.com/ashishps1/awesome-low-level-design) · worked designs for the classic problems, including the parking lot, elevator, cache and rate limiter, with Java code.
- [Refactoring Guru: Design Patterns](https://refactoring.guru/design-patterns) · each pattern with the problem it solves and the symptoms that mean you do not need it.

---

Part of [DSA & Interviews](../README.md) · item 8.4
