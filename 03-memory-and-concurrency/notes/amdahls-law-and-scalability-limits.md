# Amdahl's law and the limits of scaling: why adding threads stops helping

> **In one sentence:** If a fraction `s` of a job cannot run in parallel, no number of cores can make the job more than `1/s` times faster (Amdahl's law); the universal scalability law adds that coordination costs grow with the square of the thread count, so throughput eventually falls; and in a Java service the serial fraction hides in locks, in the database and in single-threaded consumers, where a lock-contention profile will find it.

**Why it matters:** "We doubled the instance size and gained 15 percent" is Amdahl's law experienced as a cloud bill. The same arithmetic explains why a service with one hot lock flat-lines at a load that no thread-pool setting changes (item 5.1), why a 64-core box sometimes serves fewer requests than a 16-core one, and which 10 ms of a 100 ms request is the one worth optimising. Interviewers ask for the formula; incidents ask for the diagnosis.

## The idea

**Amdahl's law.** A job takes time `T` on one core. A fraction `p` of that time parallelises perfectly over `N` cores; the remaining fraction `s = 1 - p` is serial. Then:

```text
T(N) = s * T + (1 - s) * T / N
speedup(N) = T / T(N) = 1 / (s + (1 - s) / N)
limit as N grows: 1 / s
```

| serial fraction `s` | 2 cores | 8 cores | 32 cores | 128 cores | ceiling `1/s` |
|---|---|---|---|---|---|
| 1% | 1.98 | 7.48 | 24.43 | 56.39 | 100 |
| 5% | 1.90 | 5.93 | 12.55 | 17.41 | 20 |
| 10% | 1.82 | 4.71 | 7.80 | 9.34 | 10 |
| 25% | 1.60 | 2.91 | 3.66 | 3.91 | 4 |
| 50% | 1.33 | 1.78 | 1.94 | 1.98 | 2 |

Two readings. Across a row, the gains shrink fast: with 10 percent serial, cores 9 to 128 together add less than the first 8 did. Down a column, the serial fraction decides more than the core count does: 8 cores with 1 percent serial beat 128 cores with 25 percent. The law describes a fixed amount of work; when the work grows with the machine (more requests, bigger datasets), Gustafson's law gives a kinder curve, which is why a service's throughput can scale even when a single request cannot get faster.

**The universal scalability law.** Amdahl assumes the parallel part costs nothing extra. In practice `N` threads also pay a *coherency* cost: they must see each other's updates (cache-line transfers between cores, item 1.5), hand locks over, and keep shared queues and counters consistent. Neil Gunther's USL models capacity as:

```text
C(N) = N / (1 + a * (N - 1) + b * N * (N - 1))
```

`a` is contention, the serialised fraction (with `b = 0` the formula is Amdahl's law); `b` is the coherency cost per pair of threads. Because the `b` term grows as `N` squared, throughput does not flatten, it peaks at `N* = sqrt((1 - a) / b)` and then falls. With `a = 0.10` and `b = 0.001` the peak is at 30 threads (6.3 times the single-thread throughput), and 128 threads deliver 4.3 times, less than 16 threads do. That retrograde curve is what a service that gets slower on a bigger machine is showing you. Measure throughput at several thread counts, fit `a` and `b`, and you can predict the knee before buying the hardware.

**Where serial fractions hide in a Java service.**

1. Locks: a `synchronized` method on a shared singleton (a cache, a registry, a legacy `Hashtable`, a synchronous logging appender, a shared `SecureRandom`); the lock inside a connection pool under churn.
2. The database: a hot row (a counter, a "last updated" record), a sequence, foreign-key locks, the single commit path of one primary. Every request passes through it, so it is a serial section the JVM never sees.
3. Single-threaded consumers: one queue consumer, an actor, an event loop that does CPU work, a `newSingleThreadExecutor` that someone added for ordering.
4. The JVM itself: stop-the-world pauses are serial time for every thread (item 2.3); `System.out` is synchronised; class loading and JIT compilation early in the process's life.
5. Coherency rather than contention: an `AtomicLong` incremented by every thread, false sharing (item 1.5), one hot key in a `ConcurrentHashMap`. No thread ever blocks, and the `b` term grows all the same.
6. Outside the process: a rate-limited downstream, a leader-only code path, a single-threaded proxy.

**How to find them.** First, measure throughput at 1, 2, 4, 8 and 16 threads; a curve that bends early gives `s`, one that turns down gives `b`. Then look for the lock. JFR records `jdk.JavaMonitorEnter` (waiting for a `synchronized` monitor), `jdk.ThreadPark` (waiting on `java.util.concurrent` locks, queues and semaphores) and `jdk.JavaMonitorWait`, each with a stack trace, but only when the wait exceeds the threshold: 20 ms in the `default` settings, 10 ms in `profile`, so lower it in a custom `.jfc` to catch contention that is short but constant; JDK Mission Control then ranks monitors by the total time threads spent waiting for them. async-profiler's lock profiling mode (`-e lock`) draws the same information as a flame graph and includes `ReentrantLock`. Two thread dumps a few seconds apart with many threads `BLOCKED` on the same monitor say the same thing with no tooling at all (item 6.3). For the database, `pg_stat_activity.wait_event` and `pg_locks` show which sessions wait for what. Then shrink the section: hold the lock for less (compute outside, publish inside), split it (striping, per-key locks, `LongAdder`, item 4.6), remove it (immutable snapshots, `ConcurrentHashMap`, item 4.7), or move it off the hot path (asynchronous logging, batched writes).

## Example: a request with a 10 percent serial section

A request takes 100 ms on one core: 90 ms of work that can be spread over cores and 10 ms that runs under one lock.

| cores | speedup | latency |
|---|---|---|
| 1 | 1.00 | 100.0 ms |
| 2 | 1.82 | 55.0 ms |
| 8 | 4.71 | 21.3 ms |
| 16 | 6.40 | 15.6 ms |
| 32 | 7.80 | 12.8 ms |
| 128 | 9.34 | 10.7 ms |

The floor is 10 ms, and cores 9 to 128 buy 10.6 ms between them. Shrink the serial section instead, from 10 ms to 1 ms, and 8 cores give `1 / (0.01 + 0.99 / 8) = 7.5` times, more than 16 cores gave with the 10 ms section. In throughput terms: if those 10 ms are spent under a lock that every request takes, the lock admits at most `1 s / 10 ms = 100` requests per second from that JVM, whatever the thread count, and at 100 ms per request that is about 10 requests in flight (Little's law, item 6.5), so the eleventh thread only queues. Cut the lock time to 1 ms and the ceiling is 1,000 per second. The ceiling is the same `1/s`; the throughput view tells you how many threads it takes to hit it.

## Example: measuring a shared lock

Six thousand simulated requests, each a fixed amount of CPU work with 10 or 25 percent of it inside one `synchronized` block, run on pools of 1 to 12 threads. The no-lock column runs the same work without the lock.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class SerialSectionScaling {

    private static final int REQUESTS = 6_000;
    private static final Object SHARED_LOCK = new Object();
    private static volatile long sink;

    public static void main(String[] arguments) throws InterruptedException {
        runWith(4, 10, true);
        System.out.println("threads | no lock | 10% under the lock | 25% under the lock");
        for (int threads : new int[] {1, 2, 4, 8, 12}) {
            System.out.printf("%7d | %4d ms | %7d ms | %7d ms%n", threads,
                    runWith(threads, 10, false), runWith(threads, 10, true), runWith(threads, 25, true));
        }
    }

    static long runWith(int threads, int serialPercent, boolean useLock) throws InterruptedException {
        long started = System.nanoTime();
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        for (int request = 0; request < REQUESTS; request++) {
            pool.submit(() -> {
                work(100 - serialPercent);
                if (useLock) {
                    synchronized (SHARED_LOCK) {
                        work(serialPercent);
                    }
                } else {
                    work(serialPercent);
                }
            });
        }
        pool.shutdown();
        pool.awaitTermination(5, TimeUnit.MINUTES);
        return (System.nanoTime() - started) / 1_000_000;
    }

    static void work(int units) {
        long hash = 7;
        for (int index = 0; index < units * 2_000; index++) {
            hash = hash * 31 + index;
        }
        sink = hash;
    }
}
```

On an Apple M4 Pro (8 performance and 4 efficiency cores) with OpenJDK 25, a rough timing rather than a benchmark:

```text
threads | no lock | 10% under the lock | 25% under the lock
      1 | 1463 ms |    1461 ms |    1475 ms
      2 |  722 ms |     721 ms |     721 ms
      4 |  358 ms |     360 ms |     420 ms
      8 |  179 ms |     195 ms |     419 ms
     12 |  135 ms |     210 ms |     422 ms
```

Read the 25 percent column first: it stops improving at 4 threads and stays at about 420 ms however many threads are added, a ceiling of 3.5 times against the law's 4. The ceiling is the lock's capacity: each request spends about 61 µs inside it (a quarter of 244 µs), and 6,000 requests need 366 ms of lock time that nothing can overlap; the remaining 15 percent is the cost of handing the lock between threads, the coherency term in miniature. The 10 percent column shows how the ceiling is approached in a service: at 4 threads the lock is busy 40 percent of the time and costs nothing; at 8 it is busy 80 percent of the time and queueing appears; at 12 it is saturated, 146 ms of mandatory lock time has become the bottleneck, and the run is 55 percent slower than the same work without the lock. Independent requests overlap one request's locked section with other requests' parallel work, so the lock bites later and harder than Amdahl's smooth curve for a single job, but the ceiling `1/s` is the same, and so is the cure.

## Pitfalls

- Growing the thread pool when the bottleneck is serial. More threads queue at the lock: latency rises, throughput stays flat, and CPU use drops because threads are parked (item 5.1).
- Looking only for `BLOCKED` threads. Coherency costs (atomics, false sharing, cache misses, GC) scale just as badly and never show a thread waiting on a lock.
- Treating "lock-free" as "scalable". A CAS loop on one hot `AtomicLong` is a coherency storm (item 4.6); `LongAdder` exists because of this law.
- Load-testing against a mocked database. The service scales perfectly in the test and dies at a row lock in production; the serial fraction was never in the JVM.
- Trusting the default JFR threshold. Twenty milliseconds hides a lock held for one millisecond ten thousand times a second, which is the common shape of contention.
- Optimising the parallel part. Halving the 90 ms in the example moves the 8-core latency from 21.3 ms to 15.6 ms; halving the 10 ms serial part moves the ceiling from 10 ms to 5 ms for every core count.

## Check yourself

1. A batch job spends 5 percent of its single-core time merging results on one thread. It moves from 16 to 64 cores. What speedup over one core did it have, what does it have now, and what should the team work on instead?
2. Throughput on a 32-core machine is lower than on a 16-core one. Which law describes this, which term is responsible, and what are three Java mechanisms that produce that term without any thread ever blocking?
3. Every request holds one `synchronized` lock for 2 ms. What is the hard ceiling on requests per second for that JVM instance, and how does it change if the lock is striped eight ways by customer id?
4. Which JFR events reveal lock contention, why can a default recording show none while a service is contention-bound, and what do you change?

## Go deeper

- [Amdahl's law](https://en.wikipedia.org/wiki/Amdahl%27s_law) · the formula, its derivation and its history, including Gustafson's reply.
- [Neil Gunther: The Universal Scalability Law](http://www.perfdynamics.com/Manifesto/USLscalability.html) · the model's author on contention, coherency and fitting the curve to measurements.
- [Little's law](https://en.wikipedia.org/wiki/Little%27s_law) · the formula that turns a serial section's duration into a throughput ceiling and a thread count.
- [async-profiler](https://github.com/async-profiler/async-profiler) · the lock profiling mode that shows where threads waited, as a flame graph.
- [Java Concurrency in Practice, chapter 11](https://jcip.net/) · Amdahl's law for Java programmers, then lock splitting, striping and reducing lock scope (paid).

---

Part of [Memory & Concurrency](../README.md) · item 6.4
