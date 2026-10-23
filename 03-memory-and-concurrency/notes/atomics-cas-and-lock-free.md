# Atomics, compare-and-set and lock-free counters

> **In one sentence:** Compare-and-set is a single hardware instruction that writes a new value only if the current value is still the one you read, every `java.util.concurrent.atomic` class is a loop around it, and that loop beats a lock for single-variable updates under moderate contention while losing to striped counters under heavy contention and to locks for anything that spans two variables.

**Why it matters:** `AtomicInteger`, `AtomicReference` and `LongAdder` are how the JDK's own concurrent collections, pools and counters avoid locks, and they are the right tool for the hot counters and flags in your own services. Used blindly they still race (`get` then `set` is two operations), and under real contention an `AtomicLong` can be dozens of times slower than a `LongAdder`. Interviewers like the ABA problem because it tests whether you understand what CAS actually compares.

## The idea

**Compare-and-set (CAS).** `compareAndSet(expected, newValue)` atomically does: if the variable currently holds `expected`, store `newValue` and return `true`; otherwise change nothing and return `false`. The CPU provides it as one instruction (`lock cmpxchg` on x86; on ARM a load-linked/store-conditional pair or the LSE `cas` instruction), so no lock is involved and a thread that is descheduled in the middle cannot block anyone.

**The retry loop.** Every non-trivial atomic update is: read the current value, compute the new one, try to CAS it in, and if another thread changed the value in between, start over. `incrementAndGet`, `updateAndGet(IntUnaryOperator)` and `accumulateAndGet` run this loop for you; `compareAndSet` lets you write your own when the new value depends on a condition. On x86, plain increments compile to a `lock xadd` that never retries.

**Lock-free** means that some thread always completes its operation in a bounded number of steps even if others stall; the retry loop qualifies because a failed CAS means another thread succeeded. A lock gives no such guarantee: a thread that holds a lock and is descheduled blocks everyone.

**`AtomicReference` and immutable snapshots.** State that spans several fields can still be updated lock-free if it is held as one immutable object: read the reference, build a modified copy, CAS the reference. If the CAS fails, rebuild from the new current value. This is the copy-on-write idea behind `CopyOnWriteArrayList` (which serialises its writers with a lock) with the lock replaced by a CAS on the reference; it suits small, rarely updated state such as a registry or a configuration snapshot.

**The ABA problem.** CAS compares values, not history. If a thread reads A, another thread changes A to B and back to A, the first thread's CAS succeeds although the world changed underneath it. For counters this is harmless; for pointer-based structures that reuse nodes (a lock-free stack where a popped node is pushed again) it corrupts the structure. The JVM's garbage collector removes most of the danger because a node cannot be reused while any thread still references it; where it remains, `AtomicStampedReference` pairs the reference with a version stamp that changes on every update, so A-then-A is no longer "the same".

**`LongAdder` versus `AtomicLong`.** An `AtomicLong` is one memory location; under contention every core fights for the same cache line (item 1.5) and most CAS attempts fail and retry. `LongAdder` keeps a set of padded cells, hashes each thread to a cell, and sums the cells when you call `sum()`. Writes scale, but `sum()` is not an atomic snapshot and the result can be slightly stale while updates continue; there is no `compareAndSet` on the total. Use `LongAdder` for statistics and metrics, `AtomicLong` when you need the exact value after each update, for sequence numbers, or for CAS-based logic.

**When atomics beat locks.** The state is one variable (or one immutable object), the operation is short, and contention is moderate: the fast path is one instruction instead of a lock acquire and release, and no thread ever parks. **When they do not.** The invariant spans two variables you cannot fold into one object; the operation is long (a CAS loop spinning for milliseconds burns CPU where a lock would park the thread); you need to wait for a condition (item 4.4); or contention is extreme and a striped structure or a lock with queueing is cheaper than a CAS storm.

## Example: a bounded counter with a CAS retry loop

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ConnectionLimiter {

    private final AtomicInteger activeConnections = new AtomicInteger();

    boolean tryAcquire(int limit) {
        while (true) {
            int current = activeConnections.get();
            if (current >= limit) {
                return false;
            }
            if (activeConnections.compareAndSet(current, current + 1)) {
                return true;
            }
        }
    }

    void release() {
        activeConnections.decrementAndGet();
    }
}
```

`incrementAndGet()` followed by a check would overshoot the limit and need a compensating decrement; the loop never admits more than `limit`. Sixteen threads each calling `tryAcquire(100)` a thousand times on OpenJDK 25: `acquired 100 of limit 100, counter = 100`, every run. The same loop is what `updateAndGet(current -> current >= limit ? current : current + 1)` does internally; the explicit version lets you return the boolean.

## Example: `AtomicLong` versus `LongAdder` under contention

Twelve threads each incrementing a shared counter five million times, on a 12-core Apple M4 Pro with OpenJDK 25, three rounds (a rough timing with `System.nanoTime`, not a benchmark):

```text
12 threads x 5M increments: AtomicLong 2585 ms (60000000), LongAdder 73 ms (60000000)
12 threads x 5M increments: AtomicLong 2068 ms (60000000), LongAdder 50 ms (60000000)
12 threads x 5M increments: AtomicLong 2722 ms (60000000), LongAdder 40 ms (60000000)
1 thread x 60M increments:  AtomicLong 183 ms, LongAdder 426 ms
```

Both are correct (60,000,000 every time). Under contention the striped counter is about forty times faster on this machine; the same 60 million increments from a single thread run twice as fast on the `AtomicLong`, because `LongAdder` pays for its cell lookup and gains nothing when nobody is fighting. The ratio depends heavily on the CPU; the shape of the result does not.

## Pitfalls

- `get()` then `set()`. Reading an atomic, deciding, and writing it back is a check-then-act race (item 4.2). Use `compareAndSet`, `updateAndGet` or `accumulateAndGet` so that the decision and the write are one operation.
- One atomic per field. Two `AtomicInteger`s updated one after another are not atomic together; a reader can see the first updated and the second not. Fold the pair into one immutable object behind an `AtomicReference`, or use a lock.
- `compareAndSet` on `AtomicReference<Integer>` or `<String>`. It compares references with `==`, not `equals`, so two equal `Integer`s above 127 are different objects and the CAS fails or, worse, succeeds by accident at the boundary.
- Spinning without `Thread.onSpinWait()`. A retry loop that hammers a contended variable should hint the CPU; and if the loop runs for more than a few iterations regularly, contention is too high for an atomic.
- `LongAdder.sum()` as an exact value. It is a snapshot summed cell by cell while writers continue; use it for metrics, not for decisions that must be exact.
- Lock-free data structures of your own. A correct lock-free queue or map is research-grade work; use `ConcurrentLinkedQueue`, `ConcurrentHashMap` and friends (item 4.7), and reserve `jcstress` (item 6.2) for the rare case where you must write one.

## Check yourself

1. Why does `if (counter.get() < limit) counter.incrementAndGet();` overshoot the limit, and what does the CAS loop guarantee that it does not?
2. A lock-free stack pops node A, another thread pops A and B and pushes A back, and the first thread's CAS succeeds. What went wrong, and why does this rarely bite in Java?
3. You need a request counter for a metrics endpoint scraped every 15 seconds, and a separate counter that assigns unique order numbers. Which class for each, and why?
4. When does a `synchronized` block outperform a CAS loop protecting the same single variable?

## Go deeper

- [Jenkov: Compare and Swap](https://jenkov.com/tutorials/java-concurrency/compare-and-swap.html) · CAS explained from the instruction up, with the retry loop.
- [Baeldung: Atomic Variables](https://www.baeldung.com/java-atomic-variables) · the `java.util.concurrent.atomic` classes and their methods.
- [java.util.concurrent.atomic package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html) · the memory-ordering guarantees of each access mode, straight from the source.
- [Preshing: An Introduction to Lock-Free Programming](https://preshing.com/20120612/an-introduction-to-lock-free-programming/) · what lock-free actually promises, language-neutral and precise.

---

Part of [Memory & Concurrency](../README.md) · item 4.6
