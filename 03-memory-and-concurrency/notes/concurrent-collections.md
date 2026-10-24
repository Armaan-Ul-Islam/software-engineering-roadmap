# Concurrent collections: `ConcurrentHashMap`, copy-on-write lists and blocking queues

> **In one sentence:** A concurrent collection makes each of its *operations* atomic without one global lock, so the win comes from using the atomic compound operations it offers (`computeIfAbsent`, `merge`, `putIfAbsent`, `take`) instead of your own get-then-put, and the traps come from forgetting that iteration is weakly consistent or a snapshot, that `size()` is an estimate under writes, and that a remapping function runs while the map holds a lock.

**Why it matters:** `ConcurrentHashMap` is in every service (caches, registries, per-key counters), a `BlockingQueue` sits inside every thread pool, and `CopyOnWriteArrayList` holds most listener lists. Choosing the wrong one is a performance bug (copy-on-write under writes, `synchronizedMap` under contention); misusing the right one is a correctness bug (a lost update behind get-then-put, a deadlock inside `compute`). Both are standard interview ground, and both pass unit tests.

## The idea

**`ConcurrentHashMap`.** Reads take no lock. Writes lock only the bin (hash bucket) they touch: a CAS for an empty bin, a short `synchronized` on the bin's first node otherwise. So it scales with the number of distinct keys being written, where `Collections.synchronizedMap` serialises everything behind one monitor. Its semantics in five points:

1. `get`, `put`, `remove`, `putIfAbsent`, `replace(key, expected, value)` and `remove(key, expected)` are each atomic. A `get` followed by a `put` is not: that is a check-then-act race (item 4.2).
2. `compute`, `computeIfAbsent`, `computeIfPresent` and `merge` run your function *while holding the bin's lock*, which is what makes them atomic per key. The Javadoc's conditions follow from that: the function must be short and simple, must not block, and must not update the same map. A recursive call that lands in the same bin is detected on Java 9 and later and throws `IllegalStateException: Recursive update` (on Java 8 it could spin forever); a call into a different bin, with another thread doing the reverse, is a deadlock on two bin monitors. The function is invoked exactly once per call.
3. Iterators and the `keySet()`, `values()` and `entrySet()` views are **weakly consistent**: they never throw `ConcurrentModificationException`, they reflect the map at some point at or since the iterator was created, and they may or may not include updates made during the traversal. `size()`, `isEmpty()` and `mappingCount()` are estimates while writes are in flight.
4. No `null` keys or values, so that `get` returning `null` means "absent" without a second call.
5. `ConcurrentHashMap.newKeySet()` is the concurrent `Set`; the bulk operations (`forEach`, `reduce`, `search`) take a parallelism threshold and run on the common pool (item 5.3).

**`CopyOnWriteArrayList`** (and `CopyOnWriteArraySet`). Every write copies the whole backing array under a lock; reads and iteration use an immutable snapshot, so iteration never fails, never blocks and never sees a later change (the iterator's `remove` throws `UnsupportedOperationException`). Right for data that is read constantly and written rarely, such as listener lists and configuration; wrong for anything written per request, where each write is O(n) and allocates.

**`BlockingQueue`.** The producer-consumer interface, with four behaviours for each operation:

| | Throws | Special value | Blocks | Times out |
|---|---|---|---|---|
| Insert | `add(item)` | `offer(item)` | `put(item)` | `offer(item, timeout, unit)` |
| Remove | `remove()` | `poll()` | `take()` | `poll(timeout, unit)` |
| Examine | `element()` | `peek()` | | |

Implementations: `ArrayBlockingQueue` (bounded, one lock, optional fairness), `LinkedBlockingQueue` (optionally bounded, separate put and take locks so producers and consumers do not contend), `SynchronousQueue` (no capacity, a hand-off where `put` waits for a `take`), `PriorityBlockingQueue` (unbounded, ordered), `DelayQueue` (elements become available when their delay expires; the basis of schedulers) and `LinkedTransferQueue`. A *bounded* queue with `put` is backpressure: a producer that outruns its consumers waits instead of filling the heap, and `offer(item, timeout, unit)` turns the wait into a rejection you can report. A thread pool's work queue is exactly this (item 5.1).

**`ConcurrentLinkedQueue`** is unbounded, lock-free and non-blocking: `offer` and `poll` never wait, `size()` walks the whole list, and there is no way to wait for an element. It suits hand-offs where the consumer is already awake for other reasons (an event loop draining its task queue). A consumer that should sleep until work arrives needs a `BlockingQueue`.

**`ConcurrentSkipListMap`** (and `ConcurrentSkipListSet`) is the concurrent sorted map: `firstKey`, `headMap`, `ceilingEntry` and range iteration under concurrent updates in O(log n), without the single lock a `TreeMap` would need. Time-ordered indexes and expiry queues live here.

**What `Collections.synchronizedMap` does not give you.** It wraps every method, `computeIfAbsent` and `merge` included, in `synchronized (mutex)`, so each call is atomic. But there is one lock for the whole map, so writers to unrelated keys queue behind each other; its iterators are fail-fast, so every loop must hold `synchronized (map)` while other threads block; and compound actions of your own must hold that same mutex. It makes a `HashMap` safe to call from several threads; it does not make the program concurrent.

## Example: a racy get-then-put, fixed with `computeIfAbsent`

Eight threads count 400,000 words each into a shared map, three ways.

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.LongAdder;
import java.util.function.Consumer;

public class WordCounts {

    private static final List<String> WORDS = List.of("alpha", "beta", "gamma", "delta");
    private static final int THREADS = 8;
    private static final int WORDS_PER_THREAD = 400_000;

    public static void main(String[] arguments) throws InterruptedException {
        Map<String, Integer> racy = new ConcurrentHashMap<>();
        count(word -> {
            Integer current = racy.get(word);
            racy.put(word, current == null ? 1 : current + 1);
        });
        Map<String, LongAdder> adders = new ConcurrentHashMap<>();
        count(word -> adders.computeIfAbsent(word, key -> new LongAdder()).increment());
        Map<String, Integer> merged = new ConcurrentHashMap<>();
        count(word -> merged.merge(word, 1, Integer::sum));

        int expected = THREADS * WORDS_PER_THREAD;
        System.out.println("expected total         " + expected);
        System.out.println("get then put           " + racy.values().stream().mapToLong(Integer::longValue).sum());
        System.out.println("computeIfAbsent+adder  " + adders.values().stream().mapToLong(LongAdder::sum).sum());
        System.out.println("merge                  " + merged.values().stream().mapToLong(Integer::longValue).sum());
    }

    static void count(Consumer<String> counter) throws InterruptedException {
        try (ExecutorService executor = Executors.newFixedThreadPool(THREADS)) {
            for (int threadNumber = 0; threadNumber < THREADS; threadNumber++) {
                executor.submit(() -> {
                    for (int index = 0; index < WORDS_PER_THREAD; index++) {
                        counter.accept(WORDS.get(index % WORDS.size()));
                    }
                });
            }
        }
    }
}
```

Two runs on OpenJDK 25:

```text
expected total         3200000
get then put           2185886
computeIfAbsent+adder  3200000
merge                  3200000
```

```text
get then put           2069224
```

Every `get` and every `put` was atomic and a third of the counts still vanished, because two threads read the same `current` and both wrote `current + 1`. `computeIfAbsent` creates the `LongAdder` for a word exactly once under the bin's lock, after which `increment()` is a lock-free hot-path operation that never touches the map again (item 4.6); `merge` does the read-add-write itself under the lock. Both are exact; the first is the one to use for counters that are hit millions of times.

## Example: a `compute` that recurses into the same map

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class RecursiveCompute {

    private static final Map<Integer, Long> FIBONACCI_CACHE = new ConcurrentHashMap<>();

    static long fibonacci(int number) {
        if (number < 2) {
            return number;
        }
        return FIBONACCI_CACHE.computeIfAbsent(number, key -> fibonacci(key - 1) + fibonacci(key - 2));
    }

    public static void main(String[] arguments) throws InterruptedException {
        try {
            System.out.println("fibonacci(30) = " + fibonacci(30));
        } catch (IllegalStateException exception) {
            System.out.println("fibonacci(30) threw " + exception);
        }

        Map<String, Integer> balances = new ConcurrentHashMap<>(Map.of("alice", 100, "bob", 50));
        Thread aliceToBob = Thread.ofPlatform().name("alice-to-bob").start(() ->
                balances.compute("alice", (key, balance) -> {
                    pause();
                    balances.compute("bob", (otherKey, otherBalance) -> otherBalance + 10);
                    return balance - 10;
                }));
        Thread bobToAlice = Thread.ofPlatform().name("bob-to-alice").start(() ->
                balances.compute("bob", (key, balance) -> {
                    pause();
                    balances.compute("alice", (otherKey, otherBalance) -> otherBalance + 5);
                    return balance - 5;
                }));
        Thread.sleep(500);
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        long[] deadlocked = threads.findDeadlockedThreads();
        if (deadlocked == null) {
            System.out.println("no deadlock this time");
        } else {
            for (ThreadInfo info : threads.getThreadInfo(deadlocked, 3)) {
                System.out.println(info.getThreadName() + " is " + info.getThreadState()
                        + " on " + info.getLockName() + " held by " + info.getLockOwnerName());
                for (StackTraceElement frame : info.getStackTrace()) {
                    System.out.println("    at " + frame);
                }
            }
        }
        System.exit(0);
    }

    static void pause() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }
}
```

```text
fibonacci(30) threw java.lang.IllegalStateException: Recursive update
alice-to-bob is BLOCKED on java.util.concurrent.ConcurrentHashMap$Node@2c7b84de held by bob-to-alice
    at java.base@25.0.1/java.util.concurrent.ConcurrentHashMap.compute(ConcurrentHashMap.java:1948)
    at app//RecursiveCompute.lambda$main$1(RecursiveCompute.java:29)
    ...
bob-to-alice is BLOCKED on java.util.concurrent.ConcurrentHashMap$Node@4617c264 held by alice-to-bob
    at java.base@25.0.1/java.util.concurrent.ConcurrentHashMap.compute(ConcurrentHashMap.java:1948)
    at app//RecursiveCompute.lambda$main$4(RecursiveCompute.java:35)
    ...
```

The memoised Fibonacci looks like textbook code, and its mapping function calls `computeIfAbsent` on the same map while the outer call holds a reservation on its bin; the JDK notices and throws. The transfer is the two-thread version: each thread locks the bin of its first key, then asks for the other's, and both block on a `ConcurrentHashMap$Node` monitor. The JVM's deadlock detector finds it like any other lock-ordering deadlock (item 4.5), but you will not find it by reading the code for `synchronized`. The fix in both cases is the same: a remapping function computes a value from its arguments and nothing else. Compute the second value first, outside the function, or guard the pair of updates with one explicit lock if they must be atomic together.

## Pitfalls

- Get-then-put, or `containsKey`-then-`put`, on a concurrent map. Each call is atomic, the pair is not; use `computeIfAbsent`, `putIfAbsent` or `merge` (item 4.2).
- Slow or blocking work inside a remapping function. A 2-second loader in `computeIfAbsent` blocks every writer to that bin for 2 seconds. Cache a `CompletableFuture` instead (the `compute` stores the future at once and the loading happens outside the lock), or load first and `putIfAbsent` after.
- Expecting a snapshot from iteration. Summing `values()` while writers run may miss or double-count entries; weakly consistent is a guarantee about not failing, not about a consistent view.
- Deciding on `size()` under writes. It is an estimate; keep an explicit counter if the number matters.
- `CopyOnWriteArrayList` as a queue or a per-request accumulator. Every `add` copies the array; a thousand adds is a million element copies.
- An unbounded `LinkedBlockingQueue` "so nothing is rejected". Nothing is rejected until the heap is gone; bound it and handle `offer` returning `false` (item 5.1).
- Iterating a `synchronizedMap` without holding its lock. `ConcurrentModificationException` under load, and only under load.

## Check yourself

1. `if (!cache.containsKey(key)) { cache.put(key, load(key)); }` runs on a `ConcurrentHashMap`. What can happen with two threads, how does `computeIfAbsent` fix it, and when is `putIfAbsent` the better fix?
2. `load(key)` takes two seconds and is called inside `computeIfAbsent`. What happens to threads writing unrelated keys in the same bin, and how does caching a `CompletableFuture` change that?
3. Why is `queue.offer(task, 100, TimeUnit.MILLISECONDS)` returning `false` a feature in an overloaded service, and what should the caller do with it?
4. Ten listeners registered at start-up and invoked 50,000 times a second: which collection, and why? The same list, but listeners are added and removed on every request: what changes?

## Go deeper

- [Baeldung: Guide to ConcurrentMap](https://www.baeldung.com/java-concurrent-map) · the `ConcurrentMap` methods and `ConcurrentHashMap` specifics, with code.
- [ConcurrentHashMap Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html) · the class comment defines weakly consistent iteration and the conditions on remapping functions; read it once.
- [BlockingQueue Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html) · the four-behaviour table and a producer-consumer example.
- [java.util.concurrent package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html) · the overview of every concurrent collection and the memory-consistency guarantees they make.
- [Java Concurrency in Practice, chapter 5](https://jcip.net/) · building blocks: synchronised versus concurrent collections, blocking queues and the producer-consumer pattern (paid).

---

Part of [Memory & Concurrency](../README.md) · item 4.7
