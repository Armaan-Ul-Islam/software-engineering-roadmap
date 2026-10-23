# CPU caches, cache lines and false sharing

> **In one sentence:** The CPU moves memory in cache lines of 64 or 128 bytes, not in variables, so two threads writing to two different fields that share a line fight over it as if it were one variable, and the fix is to lay data out so that hot, independently written fields sit on different lines.

**Why it matters:** A main-memory access costs on the order of a hundred nanoseconds; an L1 hit costs about one. Code that walks memory sequentially runs tens of times faster than code that chases pointers, and a pair of "independent" counters updated by two threads can run three to ten times slower than expected for no reason visible in the source. This is the layer below the memory model (item 3.1): correct code that is slow because of where its bytes are.

## The idea

Between the core and main memory sit two or three levels of cache (L1 per core, L2 per core or cluster, L3 shared). They hold **cache lines**: aligned blocks of 64 bytes on x86 and most ARM servers, 128 bytes on Apple M-series chips (`sysctl hw.cachelinesize` on macOS, `getconf LEVEL1_DCACHE_LINESIZE` on Linux). Reading one `int` pulls in the whole line, which gives you two kinds of **locality** for free: *spatial* (the next `int` in the array is already in cache) and *temporal* (recently used data is still there). The hardware **prefetcher** notices sequential or strided access and fetches lines before you ask. Pointer chasing (linked lists, trees, `Object[]` full of references to scattered objects) defeats both: each hop is a cache miss the prefetcher cannot predict.

Caches on different cores stay coherent through a protocol (MESI and its variants): before a core may write to a line it must own it exclusively, which invalidates every other core's copy; the next reader or writer on another core must fetch it back. That transfer costs tens of nanoseconds, and it happens per line, not per variable.

**False sharing** is that transfer when the threads are not actually sharing data. Thread A writes `requestsServed`, thread B writes `bytesSent`, the two `long`s are adjacent in the same object and therefore in the same line, and the line bounces between the two cores on every write. Neither thread reads the other's field; the hardware cannot tell. The same happens with adjacent array slots (one slot per thread is a classic trap) and with a hot field next to a frequently written one in the same object.

The fix is padding: keep each hot, independently written field on its own line. HotSpot has an annotation for exactly this, `jdk.internal.vm.annotation.Contended`, which pads a field (or a whole class) with `ContendedPaddingWidth` bytes (default 128) on both sides. The JDK uses it inside `ConcurrentHashMap`, `LongAdder`'s cells and `ForkJoinPool`. Application code may use it too, with two flags: the package must be exported to your code, and the JVM only honours the annotation outside `java.base` when started with `-XX:-RestrictContended`.

## Example: two counters, adjacent and padded

```java
import jdk.internal.vm.annotation.Contended;

public class FalseSharingDemo {

    static final long ITERATIONS = 100_000_000L;

    static final class AdjacentCounters {
        volatile long requestsServed;
        volatile long bytesSent;
    }

    static final class ContendedCounters {
        @Contended volatile long requestsServed;
        @Contended volatile long bytesSent;
    }

    public static void main(String[] arguments) throws InterruptedException {
        for (int round = 0; round < 3; round++) {
            AdjacentCounters adjacent = new AdjacentCounters();
            long adjacentMillis = time(
                    () -> { for (long index = 0; index < ITERATIONS; index++) adjacent.requestsServed++; },
                    () -> { for (long index = 0; index < ITERATIONS; index++) adjacent.bytesSent++; });
            ContendedCounters contended = new ContendedCounters();
            long contendedMillis = time(
                    () -> { for (long index = 0; index < ITERATIONS; index++) contended.requestsServed++; },
                    () -> { for (long index = 0; index < ITERATIONS; index++) contended.bytesSent++; });
            System.out.printf("adjacent fields: %d ms, @Contended fields: %d ms%n", adjacentMillis, contendedMillis);
        }
    }

    static long time(Runnable firstTask, Runnable secondTask) throws InterruptedException {
        Thread firstThread = new Thread(firstTask);
        Thread secondThread = new Thread(secondTask);
        long start = System.nanoTime();
        firstThread.start();
        secondThread.start();
        firstThread.join();
        secondThread.join();
        return (System.nanoTime() - start) / 1_000_000;
    }
}
```

Compile and run:

```text
javac --add-exports java.base/jdk.internal.vm.annotation=ALL-UNNAMED FalseSharingDemo.java
java -XX:-RestrictContended FalseSharingDemo
```

On an Apple M4 Pro with OpenJDK 25, each thread performing 100 million `volatile` increments:

```text
adjacent fields: 838 ms, @Contended fields: 274 ms
adjacent fields: 832 ms, @Contended fields: 271 ms
adjacent fields: 841 ms, @Contended fields: 272 ms
```

Run it again without `-XX:-RestrictContended` and both lines show about 830 ms: the annotation is silently ignored, and the padded class is as slow as the plain one. The fields are `volatile` so that every increment is a real memory write (a plain field would be kept in a register); the same effect appears with `AtomicLong`s stored side by side in an array.

JOL (item 1.2) shows what the annotation did to the layout:

```text
java -XX:-RestrictContended --add-exports java.base/jdk.internal.vm.annotation=ALL-UNNAMED \
     -cp jol-cli-0.17-full.jar:. org.openjdk.jol.Main internals 'FalseSharingDemo$ContendedCounters'

OFF  SZ   TYPE DESCRIPTION                        VALUE
  0   8        (object header: mark)              ...
  8   4        (object header: class)             ...
 12 132        (alignment/padding gap)
144   8   long ContendedCounters.requestsServed   0
152 128        (alignment/padding gap)
280   8   long ContendedCounters.bytesSent        0
Instance size: 288 bytes
```

Thirty-two bytes became 288. That is the price, and it is why padding belongs on the handful of objects that are genuinely hot (per-thread statistics, ring-buffer cursors, striped counters), never on domain objects.

To measure this on your own machine, run the program twice, with and without `-XX:-RestrictContended`, and compare the ratio; absolute numbers depend on the chip. For production code, `LongAdder` (item 4.6) already pads its cells, and a per-thread object that is only ever written by one thread needs no padding at all.

## Pitfalls

- Padding by declaring extra `long` fields next to the hot one. HotSpot reorders fields by size and fills gaps, so your padding may land anywhere. Use `@Contended`, or the inheritance trick (hot field in a superclass, padding fields in a subclass, next hot field in a sub-subclass), which the JVM does respect because superclass fields are laid out first.
- Per-thread slots in a shared array. `long[] countsPerThread` puts eight threads' counters in one or two lines. Give each thread its own object, or stripe with padding.
- Measuring with a cold JVM and one run. Warm up, repeat, and look at the ratio, not the absolute number; or write a proper JMH benchmark.
- Assuming 64 bytes. Apple M-series chips use 128-byte lines, and the JDK's `ContendedPaddingWidth` default of 128 exists for machines like that.
- Optimising layout before measuring a miss. Most code is not bound by false sharing; a profiler that shows cache-miss counters (Linux `perf stat -e cache-misses`, or async-profiler in `cache-misses` event mode, item 6.3) tells you whether it is. Data-oriented layouts (arrays of primitives instead of arrays of objects) usually help more than padding.
- Forgetting the flag in production. `@Contended` outside `java.base` does nothing without `-XX:-RestrictContended`; put the flag next to the annotation in the deployment configuration, or you ship the 288-byte layout's cost without its benefit.

## Check yourself

1. Two threads each increment their own `AtomicLong`, stored in `AtomicLong[] counters = new AtomicLong[2]`. Where is the false sharing: in the array, in the `AtomicLong` objects, or both? What decides it?
2. Why did the padded class not speed up without `-XX:-RestrictContended`, and how would you detect that misconfiguration in a running service?
3. Iterating a `LinkedList<Integer>` and an `int[]` of the same length touches the same number of elements. Explain, in terms of lines and the prefetcher, why the array can be an order of magnitude faster.
4. A reader thread polls a `volatile boolean stop` flag that sits in the same object as a counter written millions of times per second by another thread. What happens to the reader, and what is the cheapest fix?

## Go deeper

- [Mechanical Sympathy](https://mechanical-sympathy.blogspot.com/) · Martin Thompson's blog; the posts on false sharing and the Disruptor measured all of this on real hardware.
- [What Every Programmer Should Know About Memory](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) · Ulrich Drepper's paper; sections 3 and 6 cover caches, coherence and what the programmer can do.
- [Shipilёv: JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/) · the quark on `@Contended` and field layout explains the padding rules precisely.
- [JOL: Java Object Layout](https://github.com/openjdk/jol) · to see where your fields actually land.

---

Part of [Memory & Concurrency](../README.md) · item 1.5
