# CPU scheduling and why too many threads hurt

> **In one sentence:** The kernel gives each runnable thread a short time slice on a core, preempts it when the slice ends or something more urgent wakes up, and prefers threads that sleep often; so creating more runnable threads than cores adds no throughput, spreads the same CPU across everyone so nothing finishes early, and pays for the switching with cold caches.

**Why it matters:** The thread-pool size is the one tuning knob every backend service has, and most are set by guesswork. Understanding what the scheduler does with a runnable thread tells you why a pool of 200 threads makes a CPU-bound service slower and a blocking-I/O service faster, why p99 latency explodes before CPU hits 100 percent, and what a load average actually counts.

## The idea

**The scheduler's job.** A core runs one thread at a time. The kernel keeps every thread in one of a few states: *running* on a core, *runnable* (ready, waiting for a core) or *blocked* (waiting for I/O, a lock, a timer, a socket). The scheduler decides which runnable thread gets each core next. Two events trigger a decision: the running thread blocks or exits (it gives the core up voluntarily), or a timer interrupt says its *time slice* is used up and it is preempted. Linux's default scheduler (CFS until kernel 6.6, EEVDF after) does not use fixed slices; it tracks how much CPU each thread has received and runs the one that has had the least, with a target of giving everyone a turn within a few milliseconds. The effect is the same as round-robin with slices in the low-millisecond range. Each switch saves the outgoing thread's registers, restores the incoming thread's, and, as item 2.1 covers, costs more in cache and TLB misses afterwards than in the switch itself.

**CPU-bound versus I/O-bound.** A CPU-bound thread uses its whole slice every time: it is preempted, never blocks. An I/O-bound thread runs for microseconds, issues a read or waits on a socket, and blocks; it gives the core up almost immediately. Schedulers favour threads that block often (they are usually interactive or latency-sensitive), so an I/O-bound thread that wakes up typically runs before a CPU-bound thread that is mid-slice. Priorities (`nice` on Unix, Java's `Thread.setPriority`, which maps to nothing useful on Linux by default) tilt the same mechanism.

**Why more threads than cores does not help CPU-bound work.** With 12 cores and 12 runnable threads, every thread runs continuously. With 96 runnable threads, the same 12 cores are shared: each thread gets one-eighth of a core, and the work still takes exactly as long in total. Nothing was gained, and three things were lost:

1. **Latency.** With a bounded pool, tasks run to completion in batches: the first 12 finish after one task's worth of time, the next 12 after two. With a thread per task, the scheduler interleaves all 96, so almost every task finishes near the very end. The median completion time roughly doubles with no change in throughput.
2. **Cache.** Every switch lands the next thread on a core whose L1 and L2 hold the previous thread's data. For memory-heavy work the lost locality is measurable; for the pure-arithmetic loop below it is not, which is why the wall times match.
3. **Memory and kernel objects.** Each platform thread is a kernel data structure plus a stack. Thousands of them cost memory and make every scheduler decision more expensive.

**Why more threads than cores does help I/O-bound work.** A thread blocked on a database call holds no core. If each request spends 2 ms on CPU and 50 ms waiting for the database, one core can serve about 25 requests concurrently and needs 25 threads to do so. The classic sizing rule is `threads = cores * (1 + waitTime / computeTime)`. The catch is that the pool must then be bounded by the *downstream* capacity too: 200 threads waiting on a 20-connection database pool just queue in a different place. Virtual threads (Java 21) are the way out for I/O-bound services: a blocked virtual thread parks and its carrier thread moves on, so the pool of kernel threads can stay at the core count while the number of in-flight requests is bounded only by memory.

**Reading the machine.** The *load average* in `uptime` and `top` is the average number of threads that are runnable or in uninterruptible disk wait, over 1, 5 and 15 minutes. A load of 24 on 12 cores means on average 12 threads were waiting for a core. `vmstat 1` on Linux prints `r` (runnable threads), `cs` (context switches per second) and the `us`/`sy`/`wa` split of CPU time; a high `cs` with a high `r` is oversubscription, a high `wa` is I/O-bound work.

## Example: thread per task doubles median latency without changing throughput

Ninety-six tasks of about 100 ms pure CPU each, on a 12-core machine, run first on a pool of 12 threads and then on a pool of 96. Each task records when it finished relative to the start of the batch.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class Oversubscription {

    private static final int TASK_COUNT = 96;
    private static final long ITERATIONS_PER_TASK = 150_000_000L;

    public static void main(String[] arguments) throws InterruptedException, ExecutionException {
        int cores = Runtime.getRuntime().availableProcessors();
        System.out.printf("cores: %d, tasks: %d, each task about %d ms of pure CPU%n",
                cores, TASK_COUNT, measureOneTask());
        report(cores, "warm-up");
        report(cores, "bounded pool");
        report(TASK_COUNT, "thread per task");
    }

    private static long measureOneTask() {
        spin(ITERATIONS_PER_TASK);
        long start = System.nanoTime();
        spin(ITERATIONS_PER_TASK);
        return (System.nanoTime() - start) / 1_000_000;
    }

    private static void report(int threadCount, String label) throws InterruptedException, ExecutionException {
        long[] completionMillis = new long[TASK_COUNT];
        long start = System.nanoTime();
        try (ExecutorService executor = Executors.newFixedThreadPool(threadCount)) {
            List<Future<Long>> results = new ArrayList<>();
            for (int taskIndex = 0; taskIndex < TASK_COUNT; taskIndex++) {
                results.add(executor.submit(() -> {
                    spin(ITERATIONS_PER_TASK);
                    return System.nanoTime() - start;
                }));
            }
            for (int taskIndex = 0; taskIndex < TASK_COUNT; taskIndex++) {
                completionMillis[taskIndex] = results.get(taskIndex).get() / 1_000_000;
            }
        }
        long wall = (System.nanoTime() - start) / 1_000_000;
        Arrays.sort(completionMillis);
        System.out.printf("%-14s %3d threads  wall %5d ms  task done: min %4d ms  p50 %5d ms  max %5d ms%n",
                label, threadCount, wall, completionMillis[0], completionMillis[TASK_COUNT / 2],
                completionMillis[TASK_COUNT - 1]);
    }

    private static long spin(long iterations) {
        long accumulator = 0;
        for (long index = 0; index < iterations; index++) {
            accumulator += index ^ (accumulator >>> 3);
        }
        return accumulator;
    }
}
```

```text
$ java Oversubscription.java
cores: 12, tasks: 96, each task about 100 ms of pure CPU
warm-up         12 threads  wall  1146 ms  task done: min  123 ms  p50   648 ms  max  1146 ms
bounded pool    12 threads  wall  1107 ms  task done: min  127 ms  p50   643 ms  max  1107 ms
thread per task  96 threads  wall  1108 ms  task done: min  136 ms  p50  1073 ms  max  1106 ms
```

Same wall time, same CPU work, 12 cores either way. On the bounded pool half of the tasks were done by 643 ms. With a thread per task, the scheduler gave all 96 threads their turns in rotation, so the median task finished at 1073 ms, only 35 ms before the last one. If those tasks were requests, the thread-per-task service would have a p50 close to its p100. (Measured on macOS with an Apple M-series CPU; Linux shows the same shape. The pure-arithmetic loop fits in registers, so cache pollution does not show here; a loop over a large array would also lose throughput.)

Where the ratio of threads to cores comes from in a real service: a Tomcat default of 200 request threads on a 4-core container is 50 threads per core. Fine if requests block on a database most of their time; a slow-motion disaster if a deploy turns a cheap request into a CPU-heavy one, because now 200 threads compete for 4 cores and every request's latency multiplies by 50.

## Pitfalls

- Sizing a pool "generously". For CPU-bound work, more threads than cores only adds latency and switching. Use the core count (`Runtime.getRuntime().availableProcessors()`, which respects container CPU limits on recent JDKs) or one or two more.
- Unbounded pools. `Executors.newCachedThreadPool` and "new thread per request" create as many threads as there is work. Under a burst, the machine spends its time switching, the GC gets no CPU, and the service falls over exactly when it is needed. Bound the pool and queue or reject the rest.
- Mixing CPU-bound and I/O-bound work in one pool. The sizing rules contradict each other. Separate pools, or virtual threads for the blocking part and a core-sized pool for the computing part.
- Blocking in a core-sized pool. A `ForkJoinPool.commonPool()` (used by parallel streams and `CompletableFuture` defaults) has one thread per core; one blocking database call in it idles a whole core, and a few of them stall every parallel stream in the JVM.
- Reading CPU percentage as the only signal. A 12-core box at 60 percent CPU can already have a run queue of 30 if the load is bursty; look at load average, `vmstat`'s `r` column, and the latency distribution.
- `Thread.setPriority` as a fix. On Linux the JVM ignores it unless started with `-XX:ThreadPriorityPolicy=1` as root; design the pools instead.

## Check yourself

1. A service does 3 ms of CPU and 60 ms of database waiting per request on 8 cores. Estimate a thread-pool size, and name the other limit that must be checked before using it.
2. In the example, why is the wall time identical for 12 and 96 threads, and why is the median completion time so different? What single change to the task would make the 96-thread wall time worse too?
3. `uptime` on a 4-core host shows a load average of 16. What does that number count, and what two different causes would you distinguish with `vmstat`?
4. A colleague proposes replacing a bounded pool with virtual threads to "fix" a CPU-bound image-resizing service. What happens, and why would the same change help a service that proxies HTTP calls?

## Go deeper

- [OSTEP: Scheduling](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched.pdf) · turnaround versus response time, round-robin, and why the trade-off exists, in 15 pages.
- [OSTEP: Multi-Level Feedback Queue](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-sched-mlfq.pdf) · how a scheduler learns which threads are interactive without being told.
- [Brendan Gregg: Linux Performance](https://www.brendangregg.com/linuxperf.html) · the tools that show run queues, context switches and off-CPU time on a real host.
- [Linux Performance Analysis in 60 seconds](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55) · the ten commands, with load average and `vmstat` first.

---

Part of [Foundations](../README.md) · item 2.2
