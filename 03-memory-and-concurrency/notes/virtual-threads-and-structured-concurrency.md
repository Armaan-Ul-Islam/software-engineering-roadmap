# Virtual threads and structured concurrency

> **In one sentence:** A virtual thread is a `Thread` whose stack lives on the heap and which the JDK mounts on a small pool of carrier threads only while it is running, so a blocking call parks the virtual thread instead of an OS thread and you can have a million of them; structured concurrency adds the rule that subtasks forked inside a scope all finish, fail or are cancelled before the scope ends.

**Why it matters:** Virtual threads (final in Java 21, JEP 444) let a thread-per-request service handle as many concurrent requests as its downstream dependencies allow, without callbacks and without a thread pool to size. They also change old habits: pooling them is wrong, `ThreadLocal` caches become a memory problem, and on JDK 21 to 23 a `synchronized` block around I/O quietly pins a carrier. Structured concurrency is the companion API that stops forked work from leaking when the request that started it fails.

## The idea

**Scheduling.** The JDK schedules virtual threads on a `ForkJoinPool` of **carrier** platform threads, by default as many as there are cores (`jdk.virtualThreadScheduler.parallelism`, at most `jdk.virtualThreadScheduler.maxPoolSize`, default 256). When a virtual thread runs, it is *mounted* on a carrier. When it blocks in a JDK blocking operation (socket read, `Thread.sleep`, `BlockingQueue.take`, `Future.get`, `ReentrantLock.lock`), the JDK *unmounts* it: its frames are copied to the heap, the carrier picks up another virtual thread, and when the operation completes (the JDK's I/O poller sees the socket ready) the virtual thread is queued to be mounted again. Creation costs an object, not a system call; memory is proportional to the actual stack depth, not a fixed 1 to 2 MB reservation.

**Good for** I/O-bound concurrency: many requests each waiting on databases, HTTP calls or queues, written in plain blocking style. **Not for** CPU-bound work: there are still only as many cores, and a virtual thread doing arithmetic holds its carrier like any thread. A single request does not get faster; a service gets more concurrent.

**Pinning.** A virtual thread that blocks while it cannot be unmounted *pins* its carrier, and with carriers equal to cores a handful of pinned threads can stall the whole scheduler. In JDK 21 to 23, blocking inside a `synchronized` block or method (and `Object.wait()`) pinned; the standard advice was to use `ReentrantLock` around I/O. JDK 24 removed that limitation (JEP 491, "Synchronize Virtual Threads without Pinning"): `synchronized` now unmounts like `java.util.concurrent` locks do. What still pins is blocking inside a native frame (JNI or the foreign function API) and a few narrow cases; the JFR event `jdk.VirtualThreadPinned` records every occurrence with a stack trace, and on JDK 21 to 23 `-Djdk.tracePinnedThreads=full` printed them. Ordinary file I/O cannot be made non-blocking by the OS either, so the JDK compensates by temporarily adding carriers while a virtual thread is inside a file operation.

**`ThreadLocal`.** It works, but each virtual thread has its own copy, and a million threads with a cached 16 KB buffer each is 16 GB. Worse, since virtual threads are never pooled, a `ThreadLocal` cache is populated once and thrown away with the thread. Pass context explicitly, or use `ScopedValue` (item 4.8, final in Java 25) for per-request context that child threads inherit cheaply.

**Structured concurrency.** A method that forks subtasks should not return until they are done, and if it fails or is cancelled, so should they. `StructuredTaskScope` encodes that: subtasks are forked inside a `try`-with-resources scope, `join()` waits for the policy's outcome (by default: all succeed, or the first failure cancels the rest and is rethrown), the scope cannot be exited with subtasks still running, and a thread dump (`jcmd <pid> Thread.dump_to_file -format=json <file>`) shows the subtasks nested under their parent. It has been a **preview API in Java 21 through 25** (JEP 453, 462, 480, 499 and 505), needing `--enable-preview`, and the API changed between previews: Java 21 to 24 used `new StructuredTaskScope.ShutdownOnFailure()` with `scope.join().throwIfFailed()`; Java 25 redesigned it around `StructuredTaskScope.open()` and `Joiner` policies. Learn the shape, and check the JEP for your JDK before writing it.

## Example: many blocking calls on a virtual-thread executor

```java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.stream.IntStream;

public class ManyBlockingCalls {

    public static void main(String[] arguments) {
        run("virtual threads", Executors.newVirtualThreadPerTaskExecutor(), 10_000);
        run("200 platform threads", Executors.newFixedThreadPool(200), 2_000);
    }

    static void run(String label, ExecutorService executor, int taskCount) {
        Instant start = Instant.now();
        try (executor) {
            IntStream.range(0, taskCount).forEach(taskNumber -> executor.submit(() -> {
                Thread.sleep(Duration.ofSeconds(1));   // stands in for a blocking remote call
                return taskNumber;
            }));
        }
        System.out.printf("%s: %d one-second tasks in %d ms%n", label, taskCount, Duration.between(start, Instant.now()).toMillis());
    }
}
```

On OpenJDK 25, 12 cores:

```text
virtual threads: 10000 one-second tasks in 1048 ms
200 platform threads: 2000 one-second tasks in 10098 ms
```

Ten thousand "remote calls" completed in about one second on twelve carriers, because a sleeping virtual thread occupies no carrier. The fixed pool did a fifth of the work in ten times the time: 2,000 tasks in batches of 200. Printing `Thread.currentThread()` inside a task shows what is running: `VirtualThread[#10248]/runnable@ForkJoinPool-1-worker-12`, the virtual thread and the carrier it happens to be mounted on at that moment.

## Example: the shape of a structured scope (Java 25 preview)

```java
import java.util.concurrent.StructuredTaskScope;
import java.util.concurrent.StructuredTaskScope.Subtask;

record Order(String user, String basket) {
}

Order loadOrder() throws InterruptedException {
    try (var scope = StructuredTaskScope.open()) {
        Subtask<String> user = scope.fork(() -> fetchUser());
        Subtask<String> basket = scope.fork(() -> fetchBasket());
        scope.join();
        return new Order(user.get(), basket.get());
    }
}
```

Compiled and run with `--enable-preview` on OpenJDK 25: when `fetchBasket` throws, `join()` cancels `fetchUser`, and the caller sees `StructuredTaskScope.FailedException` with the basket failure as its cause. If the thread calling `loadOrder` is interrupted, both subtasks are interrupted too. The same method with two bare `executor.submit` calls would leave `fetchUser` running after the failure, and nothing would connect the three threads in a dump.

## Pitfalls

- Pooling virtual threads. A pool caps the concurrency you adopted virtual threads to get, and shared threads bring back `ThreadLocal` leakage. Create one per task with `Executors.newVirtualThreadPerTaskExecutor()` or `Thread.ofVirtual().start(task)`, and limit concurrency with a `Semaphore` around the scarce resource instead.
- `synchronized` around I/O on JDK 21 to 23. The carrier is pinned for the duration; the connection-pool client that synchronises around `getConnection` is the classic case. Use `ReentrantLock`, or upgrade to JDK 24 or later where JEP 491 removes the problem.
- CPU-bound work on virtual threads. No gain, and long computations starve other virtual threads of their carrier (the scheduler does not preempt). Use a sized platform pool or the fork/join framework (item 5.3).
- `ThreadLocal` caches of heavy objects. Multiply the cached size by the number of concurrent requests; pass the object as a parameter instead.
- Unbounded fan-out. Spawning a virtual thread per item in a list of a million is cheap for the JVM and fatal for the database behind it. Bound with a `Semaphore` or a structured scope that limits its forks.
- Forgetting that virtual threads are daemon threads. The JVM exits when the last platform thread finishes, however many virtual threads are mid-request; use the executor's `close()` or `join()` before `main` returns.
- Writing `StructuredTaskScope` code against the wrong preview. The 21 to 24 and 25 APIs are not source compatible; keep the usage small and isolated until it is final.

## Check yourself

1. A virtual thread calls `Thread.sleep(1000)`. What happens to its carrier, to its stack frames, and to the thread's `Thread.currentThread()` identity when it resumes?
2. Why does moving a CPU-heavy image-resizing endpoint to virtual threads not speed it up, and what can it make worse?
3. Your service on JDK 21 shows carrier threads all `BLOCKED` while virtual threads pile up. Name the likely cause, the JFR event that confirms it, and two fixes.
4. In the structured example, what does the scope guarantee when `fetchBasket` fails that two independent `Future`s do not, and why does that matter for a request that was cancelled by the client?

## Go deeper

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · the design, the scheduler, pinning, and the "do not pool" guidance, in the JDK team's own words.
- [Oracle: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) · the developer guide, including how to observe virtual threads with JFR and thread dumps.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) · what pinned before JDK 24, what the fix changed, and what still pins.
- [JEP 505: Structured Concurrency](https://openjdk.org/jeps/505) · the Java 25 shape of the API, with the history of the previews.

---

Part of [Memory & Concurrency](../README.md) · items 5.5, 5.6
