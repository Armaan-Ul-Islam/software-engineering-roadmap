# Coordination primitives: `wait`/`notify`, `Condition`, latches, barriers and semaphores

> **In one sentence:** Locks keep threads apart; coordination primitives make them wait for each other: `wait`/`notify` and `Condition` wait for a state change under a lock, `CountDownLatch` waits once for N events, `CyclicBarrier` makes N threads wait for one another round after round, `Semaphore` caps how many threads may be inside at once, and every one of them is waited on in a loop that re-checks the condition, because a wake-up proves nothing.

**Why it matters:** Most "it hangs sometimes" bugs in concurrent code are not deadlocks (item 4.5) but missed signals: a `notify` that fired before anyone was waiting, a latch counted down one time too few because a worker threw, a permit never released on an exception path. The same primitives are what make a concurrency test deterministic (item 6.2) and what stop one slow dependency from taking a whole service down with it. Interviewers ask about `wait`/`notify` because the three rules reveal whether you understand what a condition queue is.

## The idea

**Condition queues: `wait`/`notify`.** Every object has, next to its monitor, a wait set. `lock.wait()` must be called while holding the monitor; it atomically releases the monitor and parks the thread. `lock.notify()` wakes one waiter, `notifyAll()` wakes them all, and each woken thread re-acquires the monitor before its `wait()` returns. Three rules:

1. Hold the lock when waiting or notifying, or you get `IllegalMonitorStateException`.
2. Wait in a loop: `while (!condition) { lock.wait(); }`. The JLS allows *spurious wake-ups* (a `wait` that returns with no `notify` at all), `notifyAll` wakes threads whose condition is still false, and another thread can consume the state between the notify and your re-acquire. An `if` is a bug every time, including on a JVM that never wakes spuriously.
3. Use `notifyAll` unless there is exactly one kind of waiter and each notification satisfies exactly one of them. A single `notify` delivered to the wrong kind of waiter (a producer waking another producer on a full buffer) is a lost signal, and the system hangs with no thread `BLOCKED`.

**Why `Condition` is better.** A `ReentrantLock` can hand out several `Condition` objects (`lock.newCondition()`), so a bounded buffer gets `notFull` and `notEmpty` and signals only the waiters that care, which a monitor's single wait set cannot do. `await(timeout, unit)` returns `false` on timeout, `awaitUninterruptibly()` exists, and the lock brings `tryLock` and fairness with it (item 4.3). The loop rule is unchanged: `while (items.isEmpty()) { notEmpty.await(); }`. The shape of `put` on a buffer with capacity `capacity`:

```java
public void put(T item) throws InterruptedException {
    lock.lock();
    try {
        while (items.size() == capacity) {
            notFull.await();
        }
        items.addLast(item);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}
```

`take` is the mirror image, waiting on `notEmpty` and signalling `notFull`. `signal` instead of `signalAll` is safe here precisely because each condition has one kind of waiter.

**`CountDownLatch`.** A counter initialised to N. `countDown()` decrements; `await()` blocks until it reaches zero and then never blocks again. It is one-shot and cannot be reset. Two shapes: a *starting gate* (count 1, every worker awaits it, the coordinator counts down once) and a *completion gate* (count N, each worker counts down, the coordinator awaits). `await(timeout, unit)` returns `false` when time runs out, which is how a test fails instead of hanging. Each `countDown` happens-before `await` returning (item 3.2), so the coordinator sees everything the workers wrote.

**`CyclicBarrier`.** N parties call `await()`; all block until the Nth arrives, an optional barrier action runs once, all proceed, and the barrier resets for the next round. It fits phased work: simulate a step, exchange results, repeat. If a waiter is interrupted or times out, the barrier breaks and every waiter gets `BrokenBarrierException`; `reset()` repairs it.

**`Semaphore`.** A count of permits: `acquire()` blocks while none are free, `release()` adds one. Permits are not owned by threads: any thread may release, which lets an asynchronous callback return a permit, and there is no ceiling, so a stray extra `release` silently raises the limit. Two uses. As a **bulkhead** it caps concurrent calls into one dependency so that a slow database cannot absorb every request thread; `tryAcquire(timeout, unit)` turns an overload into a fast, explicit failure instead of a queue. As a crude **rate limiter**, a scheduled task tops the permits up every interval, releasing only the difference to the cap; it admits bursts up to the cap, and libraries such as Resilience4j or Bucket4j implement proper token buckets.

**`Phaser`.** A reusable barrier with dynamic membership: parties `register()` and `arriveAndDeregister()` as they come and go, and `arriveAndAwaitAdvance()` waits for the current phase to end. Reach for it when the number of parties changes between phases; otherwise a `CyclicBarrier` or a latch is clearer.

All of these publish memory as well as coordinate: the releasing side (`countDown`, `release`, arriving at a barrier) happens-before the waiting side returning, as listed under "Memory Consistency Properties" in the package Javadoc.

## Example: a latch that starts eight threads together

The three-latch shape every concurrency test should use: workers report ready, the coordinator opens the gate, workers report done.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class StartTogether {

    private int unsafeCounter;

    public static void main(String[] arguments) {
        StartTogether subject = new StartTogether();
        int threadCount = 8;
        int incrementsPerThread = 100_000;
        CountDownLatch ready = new CountDownLatch(threadCount);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threadCount);
        for (int threadNumber = 0; threadNumber < threadCount; threadNumber++) {
            Thread.ofPlatform().start(() -> {
                ready.countDown();
                awaitOrFail(start);
                try {
                    for (int index = 0; index < incrementsPerThread; index++) {
                        subject.unsafeCounter++;
                    }
                } finally {
                    done.countDown();
                }
            });
        }
        awaitOrFail(ready);
        start.countDown();
        awaitOrFail(done);
        System.out.println("expected " + threadCount * incrementsPerThread + ", got " + subject.unsafeCounter);
    }

    static void awaitOrFail(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("latch not released within 5 seconds");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError("interrupted while waiting", exception);
        }
    }
}
```

Three runs on OpenJDK 25: `got 194443`, `got 204905`, `got 271088` out of 800,000. Without the gate each thread begins the moment its `start()` returns, so the first may be finished before the last has begun; on this machine eight threads began their work spread over 300 to 400 microseconds without a gate and within about 80 with one. The gate is what makes a stress test stress; a passing run still proves nothing (item 6.2). The `done.await` edge is what makes reading `unsafeCounter` from `main` legal, `countDown` sits in a `finally` so that a worker that throws cannot leave `main` waiting, and every `await` has a timeout so that a missing count fails the test instead of hanging the build.

## Example: a semaphore as a bulkhead around a payment gateway

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PaymentGatewayBulkhead {

    private final Semaphore permits = new Semaphore(4);
    private final AtomicInteger inFlight = new AtomicInteger();
    private final AtomicInteger highWaterMark = new AtomicInteger();

    String charge(String orderId) throws InterruptedException {
        if (!permits.tryAcquire(150, TimeUnit.MILLISECONDS)) {
            return orderId + ": gateway busy";
        }
        try {
            highWaterMark.accumulateAndGet(inFlight.incrementAndGet(), Math::max);
            Thread.sleep(100);
            return orderId + ": charged";
        } finally {
            inFlight.decrementAndGet();
            permits.release();
        }
    }

    public static void main(String[] arguments) throws Exception {
        PaymentGatewayBulkhead gateway = new PaymentGatewayBulkhead();
        List<Future<String>> outcomes = new ArrayList<>();
        try (ExecutorService requests = Executors.newVirtualThreadPerTaskExecutor()) {
            for (int orderNumber = 1; orderNumber <= 20; orderNumber++) {
                String orderId = "order-" + orderNumber;
                outcomes.add(requests.submit(() -> gateway.charge(orderId)));
            }
        }
        long charged = 0;
        long rejected = 0;
        for (Future<String> outcome : outcomes) {
            if (outcome.get().endsWith("charged")) {
                charged++;
            } else {
                rejected++;
            }
        }
        System.out.println("charged " + charged + ", rejected " + rejected
                + ", most calls in flight at once: " + gateway.highWaterMark.get());
    }
}
```

```text
charged 8, rejected 12, most calls in flight at once: 4
```

Twenty requests arrive at once (the `Thread.sleep` stands in for a 100 ms remote call). The gateway never sees more than four; four more get in when the first batch releases its permits inside the 150 ms wait; the remaining twelve fail fast with a message the caller can act on, instead of queueing until the gateway is even slower. The `release()` is in `finally`, after the `tryAcquire` succeeded, so an exception in the call cannot leak a permit and a failed acquire cannot return one it never held. This is also the standard way to bound concurrency on virtual threads, where there is no pool size to lean on (item 5.5).

## Pitfalls

- `if` instead of `while` around `wait()` or `await()`. Works for months, then a spurious wake-up or a second consumer makes the code act on a state that is no longer true.
- `notify()` with two kinds of waiters on one monitor. The signal goes to a thread that cannot use it and the one that could stays parked forever. Use `notifyAll()` or one `Condition` per kind.
- Counting down outside `finally`. A worker that throws before `countDown()` leaves `await()` waiting for a count that will never come; with no timeout, the thread dump shows a lonely `WAITING` thread and nothing else.
- Treating a latch as reusable. Once at zero it stays open; the second round sails straight through. Reusable waiting is `CyclicBarrier` or `Phaser`.
- Leaking permits. `acquire()` inside the `try`, or `release()` on the path where `tryAcquire` returned `false`, and the limit silently drifts in one direction or the other.
- `Thread.sleep` as coordination. It encodes a guess about timing; the primitives above encode the condition itself (item 6.2).

## Check yourself

1. Why is `if (queue.isEmpty()) { lock.wait(); }` wrong even on a JVM that never produces spurious wake-ups? Describe two interleavings that break it.
2. Ten workers each `countDown()` a latch of ten; one throws `NullPointerException` before reaching the call. What does the awaiting thread do, and which two changes make the failure visible within seconds?
3. A `Semaphore(20)` guards a dependency that can handle 20 concurrent requests. Under overload, requests wait on `acquire()` for several seconds. What should change in the code, and what should the caller receive?
4. A permit is acquired on a request thread and released in an HTTP client's completion callback on another thread. Why does `Semaphore` allow this where `ReentrantLock` would throw, and what bug becomes possible when the callback runs twice?

## Go deeper

- [Oracle: Guarded Blocks](https://docs.oracle.com/javase/tutorial/essential/concurrency/guardmeth.html) · the `wait`/`notify` protocol, with the loop rule, from the official tutorial.
- [Baeldung: CountDownLatch](https://www.baeldung.com/java-countdown-latch) · the starting-gate and completion-gate shapes with code.
- [Condition Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html) · the class comment contains the canonical two-condition bounded buffer and spells out the spurious wake-up rule.
- [Semaphore Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html) · permits, fairness, and the statement that a releasing thread need not have acquired.
- [Java Concurrency in Practice, chapter 14](https://jcip.net/) · building custom synchronisers on condition queues and `AbstractQueuedSynchronizer` (paid).

---

Part of [Memory & Concurrency](../README.md) · item 4.4
