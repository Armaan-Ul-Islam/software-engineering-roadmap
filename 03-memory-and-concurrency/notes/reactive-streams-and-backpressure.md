# Reactive streams and backpressure: `Flow`, Project Reactor, and when virtual threads are simpler

> **In one sentence:** Backpressure is the consumer telling the producer how many items it can take, so that a fast producer cannot bury a slow consumer under an unbounded buffer; the Reactive Streams interfaces (`Publisher`, `Subscriber`, `Subscription.request(n)`, in the JDK as `java.util.concurrent.Flow`) express that contract for asynchronous pipelines, Project Reactor builds `Mono` and `Flux` and their operators on top of it, and the price is an inverted, operator-based programming model that pays off when you genuinely stream data and not for request-response work that virtual threads handle in plain code.

**Why it matters:** Whenever one side of a system is faster than the other, something has to give: data is dropped, a queue grows until the heap is gone, or the producer is slowed down. Blocking I/O slows the producer for free (a slow reader makes `write` block). The moment the code is asynchronous, nothing pushes back unless you build it, and that is what reactive libraries do and what Spring WebFlux, R2DBC and the reactive Kafka clients are built on. Knowing what `request(n)` means tells you whether a reactive stack solves a problem you actually have.

## The idea

**The problem.** A producer emits 10,000 items a second; the consumer handles 1,000. The options are to buffer (unbounded means `OutOfMemoryError`; bounded means deciding what happens when it fills), to drop, to block the producer (free in a blocking design, forbidden on an event loop, item 5.4), or to let the consumer signal demand. The last is backpressure in the Reactive Streams sense: pull-based demand on a push-based stream. The consumer says "I can take 32", the producer sends at most 32 and waits for the next request. When the source cannot be slowed (a sensor, a socket you do not control), the missing demand must be turned into a policy: buffer up to a bound, drop, keep only the latest, or fail.

**The interfaces.** Reactive Streams is a small specification, adopted into the JDK in Java 9 as `java.util.concurrent.Flow`:

```text
Publisher<T>      subscribe(Subscriber<? super T>)
Subscriber<T>     onSubscribe(Subscription), onNext(T), onError(Throwable), onComplete()
Subscription      request(long n), cancel()
Processor<T, R>   a Subscriber that is also a Publisher
```

The protocol: `subscribe` leads to exactly one `onSubscribe`; then zero or more `onNext` calls, never more in total than the subscriber has requested; then at most one terminal signal, `onError` or `onComplete`; and all signals to one subscriber are delivered serially, never concurrently. `request(Long.MAX_VALUE)` means unbounded demand and switches backpressure off. The specification has 43 numbered rules and a compatibility kit, which is why you should implement these interfaces almost never: their value is interoperability. Reactor, RxJava, Akka Streams, Mutiny, R2DBC drivers and reactive HTTP clients all speak this protocol and plug into each other. The JDK ships one implementation, `SubmissionPublisher`, with a bounded buffer per subscriber (default `Flow.defaultBufferSize()`, 256) whose `submit` blocks the producer when a buffer is full and whose `offer` variants drop or time out instead.

**Project Reactor at a glance.** `Mono<T>` publishes zero or one item, `Flux<T>` zero to many. Both are lazy: nothing runs until something subscribes (in WebFlux, the framework subscribes for you). You assemble a pipeline of operators: `map` and `filter`; `flatMap` (asynchronous, concurrent, unordered) and `concatMap` (sequential); `zip`; `timeout`, `retryWhen`, `onErrorResume`; `limitRate(n)` to request in batches; `onBackpressureBuffer`, `onBackpressureDrop`, `onBackpressureLatest` and `onBackpressureError` as the policy for sources that cannot slow down; `publishOn(scheduler)` to move downstream work to another thread pool and `subscribeOn(scheduler)` to choose where the source runs. `Schedulers.parallel()` is for CPU work, `Schedulers.boundedElastic()` for blocking calls you cannot avoid. `block()` turns a pipeline back into a blocking call and must never run on an event-loop thread; BlockHound detects such calls in tests.

**Operators versus blocking.** Operators compose asynchronous steps without any thread waiting. A blocking call inside an operator (JDBC in `map`, `Thread.sleep`, `CompletableFuture.join`, a `synchronized` wait) holds the event-loop thread and stalls every other stream scheduled on it (item 5.4). So either the stack is non-blocking end to end (R2DBC rather than JDBC, `WebClient` rather than `RestTemplate`, reactive drivers for the broker and the cache), or blocking calls are fenced off on `boundedElastic()`, at which point you have rebuilt a thread pool with more steps. Stack traces suffer too: an exception in the seventh operator shows Reactor's internals rather than your call chain, and the debugging aids (`checkpoint()`, `Hooks.onOperatorDebug()`) cost performance.

**When reactive is worth its complexity.** You are genuinely streaming: server-sent events or WebSockets fanning out to thousands of clients that consume at different speeds; a message broker or change stream where demand must flow back to the source; large result sets or network streams processed item by item without ever being held in memory; or extreme connection counts per core where an event loop beats a thread per connection. It also makes sense when the whole stack is already reactive and the team already knows how to debug it.

**When virtual threads are the simpler answer.** The typical service loads a few rows, calls one or two services and renders JSON. The reason such services went reactive was to avoid blocking a scarce platform thread; virtual threads make the blocking cheap (item 5.5), so the same service is plain code with JDBC, exceptions, stack traces and a debugger that work. Backpressure in a request-response service is a bounded queue or a `Semaphore` (items 4.4 and 5.1), and thread-per-request has it built in: a request blocks on its slow dependency, and the server's connection limit does the rest. If the word "stream" does not describe your data, you do not need reactive streams.

## Example: a `Flow` subscriber that asks for two items at a time

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class RequestNDemo {

    static final class SlowSubscriber implements Flow.Subscriber<Integer> {

        private final CountDownLatch completed = new CountDownLatch(1);
        private Flow.Subscription subscription;
        private int receivedInBatch;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            log("subscribed, requesting 2");
            subscription.request(2);
        }

        @Override
        public void onNext(Integer item) {
            log("received " + item);
            sleep(100);
            if (++receivedInBatch == 2) {
                receivedInBatch = 0;
                log("requesting 2 more");
                subscription.request(2);
            }
        }

        @Override
        public void onError(Throwable throwable) {
            log("error " + throwable);
            completed.countDown();
        }

        @Override
        public void onComplete() {
            log("complete");
            completed.countDown();
        }
    }

    public static void main(String[] arguments) throws InterruptedException {
        ExecutorService deliveryThread = Executors.newSingleThreadExecutor(Thread.ofPlatform().name("subscriber").factory());
        SlowSubscriber subscriber = new SlowSubscriber();
        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>(deliveryThread, 2)) {
            publisher.subscribe(subscriber);
            for (int item = 1; item <= 6; item++) {
                long started = System.nanoTime();
                publisher.submit(item);
                log("submitted " + item + " after waiting " + (System.nanoTime() - started) / 1_000_000 + " ms");
            }
        }
        subscriber.completed.await(5, TimeUnit.SECONDS);
        deliveryThread.shutdown();
    }

    static void log(String message) {
        System.out.printf("[%-10s] %s%n", Thread.currentThread().getName(), message);
    }

    static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }
}
```

On OpenJDK 25:

```text
[subscriber] subscribed, requesting 2
[subscriber] received 1
[main      ] submitted 1 after waiting 0 ms
[main      ] submitted 2 after waiting 0 ms
[main      ] submitted 3 after waiting 0 ms
[subscriber] received 2
[main      ] submitted 4 after waiting 99 ms
[subscriber] requesting 2 more
[subscriber] received 3
[main      ] submitted 5 after waiting 103 ms
[subscriber] received 4
[main      ] submitted 6 after waiting 101 ms
[subscriber] requesting 2 more
[subscriber] received 5
[subscriber] received 6
[subscriber] requesting 2 more
[subscriber] complete
```

Two mechanisms are visible. Demand: the subscriber asked for two, received items 1 and 2, and item 3, although already submitted, was not delivered until `requesting 2 more`; the publisher never exceeds the requested count. Propagation to the producer: the first three `submit` calls returned at once (one item in delivery, two in the buffer of capacity 2), and from the fourth onwards each `submit` blocked for about one item's processing time. The consumer's pace reached the producer's thread with no queue growing anywhere. Closing the publisher delivers the buffered items and then `onComplete`. In Reactor the same shape is `Flux.range(1, 6).limitRate(2)` subscribed with a `BaseSubscriber` that requests in `hookOnSubscribe` and `hookOnNext`.

## Pitfalls

- Unbounded demand by default. Reactor's `subscribe(consumer)` requests `Long.MAX_VALUE`, so a pipeline with no `limitRate`, no `onBackpressure*` and no bounded operator in it has no backpressure at all; the source pushes as fast as it can.
- Blocking inside an operator. One JDBC call in `map` on an event-loop thread stalls every stream on that thread, and the symptom is latency on endpoints that never touch the database (item 5.4).
- `flatMap` without a concurrency argument. On a `Flux` of ten thousand ids, `flatMap(this::callService)` starts up to 256 concurrent calls (Reactor's default); pass the concurrency explicitly and size it against the dependency.
- Never subscribing, or subscribing twice. A pipeline that is built and returned but not subscribed does nothing; a cold publisher subscribed twice runs its side effects twice.
- Lost context. `ThreadLocal`-based MDC and security context do not follow a pipeline across threads (item 4.8); Reactor's `Context` and the context-propagation library exist for this, and must be wired in.
- Retrying non-idempotent work. `retryWhen` on a `Mono` that posts a payment duplicates the payment; retries belong on idempotent operations only.
- Writing your own `Publisher`. The 43 rules are easy to violate (concurrent `onNext`, signals after `cancel`). Use `SubmissionPublisher`, `Flux.create` or `Sinks`, all of which honour the specification for you.

## Check yourself

1. In the example, why did the fourth `submit` take about 100 ms when the first three returned immediately? Which two numbers determine where the producer first blocks?
2. A `Flux` of Kafka records is processed with `flatMap(record -> webClient.post(...))`. What bounds the number of HTTP calls in flight, what happens to the Kafka consumer when the HTTP service slows down, and where would you make the bound explicit?
3. A team proposes rewriting a CRUD service (JDBC, 300 requests a second, two downstream HTTP calls per request) in WebFlux "for scalability", on Java 21. Argue both sides in four sentences.
4. A publisher cannot be slowed down. Name three legitimate policies when its subscriber has requested nothing, and the one behaviour the specification forbids.

## Go deeper

- [Reactive Streams](https://www.reactive-streams.org/) · the specification; the Publisher and Subscriber rules are short enough to read in one sitting.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/) · "Reactor Core Features" for the model and the appendix "Which operator do I need?" for the operators.
- [Flow Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html) · the four interfaces with a worked example of a backpressured subscriber.
- [SubmissionPublisher Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html) · how the JDK's own publisher buffers, blocks and drops.
- [Spring Framework: Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) · the "Applicability" section is the WebFlux authors' own account of when to choose it and when not to.

---

Part of [Memory & Concurrency](../README.md) · item 5.7
