# Thread pools: `ThreadPoolExecutor` parameters and sizing with Little's law

> **In one sentence:** A `ThreadPoolExecutor` creates threads up to the core size, then queues, and only grows towards the maximum when the queue is full, so with an unbounded queue the maximum is never used; and the right number of threads is the number of requests in flight at your target throughput, which Little's law gives you as arrival rate times time per request.

**Why it matters:** Most production pools are `Executors.newFixedThreadPool(10)` chosen by habit, or a Spring `ThreadPoolTaskExecutor` whose `maxPoolSize` is never reached because its queue is unbounded. The symptoms are latency that climbs under load while CPU sits at 20 percent, or an `OutOfMemoryError` from a queue holding a million tasks. Sizing a pool from measured numbers is a five-minute calculation that interviewers and incidents both ask for.

## The idea

**The parameters.** `new ThreadPoolExecutor(corePoolSize, maximumPoolSize, keepAliveTime, unit, workQueue, threadFactory, handler)`. When a task is submitted:

1. If fewer than `corePoolSize` threads exist, a new thread is created for the task, even if others are idle.
2. Otherwise the task is offered to the `workQueue`. If the queue accepts it, no thread is created.
3. Only if the queue *refuses* the task is a new thread created, up to `maximumPoolSize`.
4. If the queue is full and the pool is at maximum, the `RejectedExecutionHandler` runs: `AbortPolicy` (default) throws `RejectedExecutionException`, `CallerRunsPolicy` runs the task on the submitting thread (natural backpressure), `DiscardPolicy` and `DiscardOldestPolicy` drop work silently.

Threads above the core size that stay idle for `keepAliveTime` exit; `allowCoreThreadTimeOut(true)` applies that to core threads too.

**The counter-intuitive part.** Step 3 means the queue type decides what `maximumPoolSize` means. A `LinkedBlockingQueue` with no capacity never refuses, so the pool never grows past `corePoolSize` and the queue grows without limit; `maximumPoolSize` is decoration. A `SynchronousQueue` has no capacity at all, so it refuses whenever no thread is waiting to take the task; the pool grows to `maximumPoolSize` immediately under load and then rejects. A bounded `ArrayBlockingQueue(200)` fills up first, adding queueing latency, and only then do extra threads appear. `Executors.newFixedThreadPool(n)` is core = max = n with an unbounded queue; `newCachedThreadPool()` is core 0, max unbounded, `SynchronousQueue`, 60-second keep-alive, which under a burst creates thousands of threads.

**Sizing.** Little's law: the average number of items in a system `L` equals the arrival rate `λ` times the average time each spends there `W`. For a pool, `L` is the number of busy threads you need at throughput `λ` when each task takes `W` (item 6.5). For **CPU-bound** work, `W` is pure compute, so more threads than cores only add context switches: use the core count, perhaps plus one. For **I/O-bound** work most of `W` is waiting, so the pool needs `λ × W` threads regardless of cores; Java Concurrency in Practice writes the same thing as `threads = cores × targetUtilisation × (1 + waitTime / computeTime)`. Then check the result against every downstream limit: a 10-connection database pool caps useful concurrency at 10 for tasks that each hold a connection, whatever the thread count says.

**Shutdown.** `shutdown()` stops accepting tasks and lets queued ones finish; `awaitTermination(timeout, unit)` waits; `shutdownNow()` interrupts running tasks and returns the queue's contents, which you must handle (persist, log, or drop knowingly). Since Java 19 `ExecutorService` is `AutoCloseable`: `close()` does `shutdown()` and waits indefinitely, interrupting the workers only if the closing thread is interrupted. Tasks must respond to interruption for any of this to work.

## Example: what the queue does to the maximum

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueueVersusMaxSize {

    public static void main(String[] arguments) throws InterruptedException {
        demonstrate("unbounded LinkedBlockingQueue", new LinkedBlockingQueue<>());
        demonstrate("ArrayBlockingQueue(4)", new ArrayBlockingQueue<>(4));
    }

    static void demonstrate(String queueDescription, BlockingQueue<Runnable> queue) throws InterruptedException {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(2, 10, 60, TimeUnit.SECONDS, queue);
        int rejected = 0;
        for (int taskNumber = 0; taskNumber < 20; taskNumber++) {
            try {
                executor.execute(() -> sleepQuietly(500));
            } catch (RejectedExecutionException exception) {
                rejected++;
            }
        }
        System.out.printf("%s: pool size %d, queued %d, rejected %d%n",
                queueDescription, executor.getPoolSize(), executor.getQueue().size(), rejected);
        executor.shutdown();
        executor.awaitTermination(10, TimeUnit.SECONDS);
    }

    static void sleepQuietly(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Twenty tasks into a pool with core 2 and max 10:

```text
unbounded LinkedBlockingQueue: pool size 2, queued 18, rejected 0
ArrayBlockingQueue(4): pool size 10, queued 4, rejected 6
```

Same core, same maximum, same tasks; the queue alone decided between two threads with eighteen waiting and ten threads with six rejections.

## Example: sizing an order-processing pool

Assumptions, each one measured or chosen, never guessed:

- 8 cores. Target peak: 400 orders per second.
- Each order spends about 5 ms on CPU (parsing, validation, serialisation) and about 45 ms waiting (one database round trip of 20 ms, one HTTP call of 25 ms), so `W` is roughly 50 ms under light load.
- Latency budget: an order may wait at most 500 ms in the queue before we would rather reject it.
- The database pool has 10 connections; each order holds one for its 20 ms round trip.

Threads: `L = λ × W = 400/s × 0.050 s = 20` busy threads on average. Arrivals are bursty and `W` grows under load, so allow 50 percent headroom: 32 threads. CPU: `400 × 0.005 s = 2` core-seconds per second, a quarter of the machine, so 32 threads will not saturate it. Database: `400 × 0.020 s = 8` connections busy on average; a pool of 10 is tight at peak, so raise it to 16 or accept that the database is the real limit. Queue: `400/s × 0.5 s = 200` tasks is the most that can wait within budget. Beyond that, reject, and let the caller see a 503 rather than a 30-second response.

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ThreadPoolExecutor orderExecutor = new ThreadPoolExecutor(
        32, 32,
        0L, TimeUnit.MILLISECONDS,
        new ArrayBlockingQueue<>(200),
        Thread.ofPlatform().name("order-worker-", 0).factory(),
        new ThreadPoolExecutor.AbortPolicy());
```

Core equals maximum on purpose: with a bounded queue the pool would only grow once 200 tasks were already waiting, which is far too late to help. Shutdown, in the component's stop hook:

```java
orderExecutor.shutdown();
if (!orderExecutor.awaitTermination(30, TimeUnit.SECONDS)) {
    List<Runnable> neverStarted = orderExecutor.shutdownNow();
    log.warn("{} orders were queued and not processed", neverStarted.size());
}
```

Then watch `getActiveCount()`, `getQueue().size()` and the rejection count in your metrics, and re-run the arithmetic when the measured `W` changes.

## Pitfalls

- An unbounded queue "so nothing is rejected". Nothing is rejected until the heap is full; a bounded queue plus a rejection policy turns overload into a signal.
- Spring's `ThreadPoolTaskExecutor` defaults: `corePoolSize` 1, `maxPoolSize` and `queueCapacity` both `Integer.MAX_VALUE`. That is a single-threaded pool with an infinite queue. Set all three.
- `newCachedThreadPool` for request handling. A burst creates a thread per task; thousands of threads later the machine is swapping.
- Blocking inside the pool on work submitted to the same pool. When every thread waits for a subtask that cannot start, the pool deadlocks (items 4.5 and 5.3). Use a separate pool for the subtasks or restructure.
- Sizing I/O-bound pools by core count. `2 × cores` is a CPU-bound heuristic; an I/O-bound pool needs `λ × W` threads, which on an 8-core box serving slow dependencies may be 200.
- Losing exceptions. `submit` stores a task's exception in the `Future`; if nobody calls `get()`, it is never seen. `execute` propagates to the thread's uncaught-exception handler instead. Pick one and log accordingly.
- No timeouts on the I/O. If `W` can grow without bound, so can the number of threads you need; every blocking call inside a pooled task needs a timeout.

## Check yourself

1. A pool has core 4, max 16 and a `LinkedBlockingQueue` with no capacity bound. Under a sustained flood of tasks, how many threads run, and where does the extra work go?
2. Your service receives 50 requests per second and each spends 200 ms waiting on a downstream API. How many threads does it need on average, and what happens if you give it 4?
3. Why does `CallerRunsPolicy` slow down the producer, and when is that the behaviour you want?
4. After `shutdownNow()`, a task that loops on `while (true)` with no interrupt check keeps running. What is wrong with the task, and what should the loop condition be?

## Go deeper

- [ThreadPoolExecutor Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) · the class comment spells out the queueing and growth rules this note is built on; read it once in full.
- [Jenkov: ExecutorService](https://jenkov.com/tutorials/java-util-concurrent/executorservice.html) · submit, invokeAll, shutdown and the differences between the factory methods.
- [Baeldung: Thread Pools in Java](https://www.baeldung.com/thread-pool-java-and-guava) · the `Executors` factories and what each one configures.
- [Little's law](https://en.wikipedia.org/wiki/Little%27s_law) · the one formula; the article also explains why it holds for any stable system regardless of distribution.

---

Part of [Memory & Concurrency](../README.md) · item 5.1
