# Virtual threads in practice

> **In one sentence:** Virtual threads (Java 21) are cheap JDK-scheduled threads that unmount from their carrier while blocked, so a thread-per-request server can run tens of thousands of concurrent requests with ordinary blocking code; adopting them means switching the executor, hunting the places that still pin a carrier (in Java 21, `synchronized` around blocking calls, fixed by JEP 491 in Java 24), rethinking `ThreadLocal`, and learning the new thread dump.

**Why it matters:** The promise is simple: keep writing blocking JDBC and HTTP code and stop running out of threads. The catch is that a few habits that were harmless with 200 platform threads behave differently with 50,000 virtual ones: a pinned carrier turns into a stalled service, a `ThreadLocal` cache of heavy objects multiplies by the request count, and `jcmd Thread.print` no longer shows the threads you care about. The concepts behind scheduling and continuations are covered in the Memory & Concurrency domain; this note is about using them.

## The idea

**The API.** `Thread.ofVirtual().start(runnable)` and `Thread.startVirtualThread(runnable)` start one thread; `Thread.ofVirtual().name("payment-", 0).factory()` gives a `ThreadFactory` with numbered names (virtual threads have no name by default, which makes dumps unreadable). `Executors.newVirtualThreadPerTaskExecutor()` creates a new virtual thread per submitted task; it is `AutoCloseable`, and `close()` waits for the tasks, so the natural shape is a try-with-resources block around a fan-out. Virtual threads are always daemon threads, have a fixed priority, and report `Thread.currentThread().isVirtual()`. They run on a `ForkJoinPool` of carrier threads sized to the number of cores (`-Djdk.virtualThreadScheduler.parallelism` to change it). Blocking in `java.*` APIs (sockets, `Thread.sleep`, `java.util.concurrent` locks and queues) unmounts the virtual thread and frees the carrier; file I/O cannot unmount and is compensated by temporarily adding carriers.

**What changes for a Spring Boot or Tomcat service.** Spring Boot 3.2 and later: `spring.threads.virtual.enabled=true` makes Tomcat handle each request on a virtual thread and switches `@Async` and `@Scheduled` executors as well. Plain Tomcat 10.1 and later: `useVirtualThreads="true"` on the connector. Then the request thread pool stops being the concurrency limit, and the next limit shows up immediately: the JDBC pool (ten connections by default in HikariCP), downstream rate limits, and memory per in-flight request. Do not raise the pool to thousands; the database cannot serve that. Limit concurrency where it matters with a `Semaphore` or a bulkhead, set timeouts on every blocking call, and expect throughput to rise while a single request's latency stays the same. CPU-bound work gains nothing: the same cores do the same work. Reactive frameworks are no longer required to scale I/O-bound services.

**Pinning.** A virtual thread that blocks while it cannot unmount pins its carrier, and with enough pinned carriers the scheduler stalls. In Java 21 to 23 that happens when a virtual thread blocks inside a `synchronized` block or method, or in `Object.wait()`. JEP 491 (Java 24) reimplemented monitors so these no longer pin. Native frames on the stack (JNI) pin in every version. To find pinning in Java 21, run with `-Djdk.tracePinnedThreads=full` (or `short`), which prints a stack trace with `<== monitors` markers when a pinned thread blocks; the property was removed in Java 24 along with the problem it diagnosed. In every version the JFR event `jdk.VirtualThreadPinned` records pinning longer than 20 ms by default:

```text
jcmd <pid> JFR.start duration=60s filename=/tmp/pinned.jfr
jfr print --events jdk.VirtualThreadPinned /tmp/pinned.jfr
```

The Java 21 workaround is `ReentrantLock` instead of `synchronized` around blocking calls in your own code, and upgrading libraries: JDBC drivers, connection pools and HTTP clients shipped virtual-thread-friendly releases during 2023 and 2024.

**`ThreadLocal`.** It works, but every one of your 50,000 threads has its own copy. A `ThreadLocal<SimpleDateFormat>` that amortised one expensive object over a pooled thread's lifetime now creates one per request and throws it away; a `ThreadLocal` holding a large buffer multiplies memory by the request count. Pass context explicitly, keep expensive objects in a small pool, or use `ScopedValue` (JEP 506, final in Java 25, preview in 21 to 24), which is immutable, bounded to a scope and cheap to inherit. Logging MDC is `ThreadLocal`-based and must be set on the virtual thread handling the request, not on whatever submitted it.

**Observability.** `jcmd <pid> Thread.print` lists platform threads only; the carriers appear as `ForkJoinPool-1-worker-N` and look idle while thousands of virtual threads are parked. Use `jcmd <pid> Thread.dump_to_file -format=json /tmp/threads.json` (or without `-format` for plain text), which groups threads by the executor that owns them and marks virtual ones. JFR adds `jdk.VirtualThreadStart`, `jdk.VirtualThreadEnd` (both off by default, they are high volume), `jdk.VirtualThreadPinned` and `jdk.VirtualThreadSubmitFailed`. A virtual thread's `toString()` names its carrier, which is useful in logs: `VirtualThread[#26]/runnable@ForkJoinPool-1-worker-5`.

## Example: ten thousand blocking tasks

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

public class FanOut {
    public static void main(String[] arguments) throws Exception {
        long started = System.nanoTime();
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> futures = IntStream.range(0, 10_000)
                .mapToObj(index -> executor.submit(() -> {
                    Thread.sleep(Duration.ofMillis(200));
                    return Thread.currentThread().toString();
                }))
                .toList();
            System.out.println(futures.get(0).get());
        }
        System.out.println("elapsed ms: " + Duration.ofNanos(System.nanoTime() - started).toMillis());
    }
}
```

```text
VirtualThread[#26]/runnable@ForkJoinPool-1-worker-5
elapsed ms: 248
```

Ten thousand tasks that each block for 200 ms finish in a quarter of a second on a handful of carriers. The same code with `Executors.newFixedThreadPool(200)` takes about ten seconds, and with a platform thread per task would need ten thousand stacks.

The JSON dump taken while such tasks are parked shows the structure you will navigate in an incident:

```text
container: <root>                                               threadCount: 8
container: ForkJoinPool-1/jdk.internal.vm.SharedThreadContainer threadCount: 6
  thread: tid 27, name ForkJoinPool-1-worker-1, state WAITING
container: java.util.concurrent.ThreadPerTaskExecutor@41acd2f    threadCount: 3
  thread: tid 26, virtual true, state TIMED_WAITING
    java.base/java.lang.VirtualThread.parkNanos(VirtualThread.java:780)
    java.base/java.lang.VirtualThread.sleepNanos(VirtualThread.java:971)
```

## Pitfalls

- Pooling virtual threads. A fixed pool of virtual threads reintroduces the limit you removed. Use the per-task executor and put explicit limits (`Semaphore`, bulkheads) only where a downstream needs protection.
- Expecting lower latency. Virtual threads raise the number of concurrent blocked requests you can hold; they do not make any single request faster.
- `synchronized` around I/O in Java 21. Your own code is easy to fix; the library in the middle of the stack is the one that pins. Check `jdk.VirtualThreadPinned` before and after an upgrade.
- Flooding downstreams. Twenty thousand requests all waiting for one of ten connections produce timeouts and a queue, not throughput. Size pools for the database, not for the thread count.
- Long CPU-bound loops. Virtual threads are not time-sliced; a thread that computes for a second occupies its carrier for a second. Keep CPU-heavy work on a dedicated platform-thread pool.
- `ThreadLocal` as a per-thread cache or object pool, and `InheritableThreadLocal` for request context. Both scale with the number of threads, which is now the number of requests.
- Diagnosing from `Thread.print` alone and concluding the service is idle.

## Check yourself

1. Why does `Executors.newVirtualThreadPerTaskExecutor()` take no size, and how do you then stop a fan-out from overwhelming a downstream service?
2. A Java 21 service collapses under load and `jdk.VirtualThreadPinned` events point at a `synchronized` block inside a JDBC driver. List your options in order of preference.
3. Why was `ThreadLocal<SimpleDateFormat>` a reasonable optimisation with pooled platform threads and a bad idea with virtual threads?
4. `Thread.print` shows sixteen idle `ForkJoinPool-1-worker-N` threads and no request threads while 5,000 requests are in flight. Explain, and give the command that shows the requests.

## Go deeper

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · the design, the scheduling model, pinning, and the observability section with the JFR events and the new dump format.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) · what changed in Java 24 and what still pins.
- [JEP 506: Scoped Values](https://openjdk.org/jeps/506) · the replacement for `ThreadLocal` context passing, final in Java 25.
- [Oracle Java 21 Core Libraries: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) · the practical guide from the JDK team: when to use them, pinning, `ThreadLocal`, and debugging.

---

Part of [Java](../README.md) · item 5.4
