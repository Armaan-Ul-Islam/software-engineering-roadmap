# The Java Memory Model: happens-before, visibility and volatile

> **In one sentence:** Unless a *happens-before* relationship connects a write in one thread to a read in another, Java promises nothing about whether, or when, the read will see the write; `volatile`, locks, thread start and join, and the `java.util.concurrent` classes are how you create that relationship.

**Why it matters:** Visibility bugs do not show up in unit tests. They appear after the JIT compiler has optimised a hot loop on a production server, or when the same code runs on an ARM machine (Apple Silicon laptops, Graviton and Ampere servers) whose CPU reorders memory operations more aggressively than x86. The symptom is an "impossible" state: a flag that is `true` in the debugger while the loop reading it never ends.

## The idea

Within one thread, Java behaves as if statements run in program order; the compiler and CPU may reorder and cache as long as that thread cannot tell the difference. Across threads, the difference is visible. The Java Memory Model (JLS chapter 17) defines exactly when a read is guaranteed to observe a write, using one relation:

**Happens-before (hb).** If action A happens-before action B, then B sees the effects of A. The rules that matter in daily work:

| Rule | A happens-before B when... |
|---|---|
| Program order | A comes before B in the same thread. |
| Monitor lock | A is the release of a lock (`synchronized` exit, `Lock.unlock`) and B is a later acquire of the same lock. |
| Volatile | A is a write to a `volatile` field and B is a later read of that field. |
| Thread start | A is `thread.start()` and B is any action in that thread. |
| Thread join | A is any action in a thread and B is the return of `thread.join()` on it. |
| Transitivity | A hb X and X hb B. |

The `java.util.concurrent` classes document their own edges on top of these: putting an element into a concurrent collection hb removing it; `executor.submit` hb the task; the task's actions hb `future.get()` returning; `countDown()` hb `await()` returning; and so on. Read the "Memory Consistency Properties" section of the package documentation once; it is short.

If two threads access the same variable, at least one access is a write, and no hb edge orders them, the program has a **data race**, and the reading thread may see a stale value indefinitely.

Transitivity is what makes the model usable. A `volatile` write publishes *everything* the writing thread did before it, not only the volatile field. That is called piggybacking, and it is why a single `volatile boolean ready` can safely publish a whole object graph.

## Example 1: the stop flag that never stops

```java
public final class Worker implements Runnable {

    private boolean running = true;   // plain field

    @Override
    public void run() {
        while (running) {
            // spin
        }
        System.out.println("stopped");
    }

    public void stop() {
        running = false;
    }

    public static void main(String[] arguments) throws InterruptedException {
        Worker worker = new Worker();
        Thread thread = new Thread(worker);
        thread.start();
        Thread.sleep(100);
        worker.stop();
        thread.join();                // on HotSpot this usually never returns
    }
}
```

There is no hb edge between `stop()`'s write and `run()`'s reads, so the JIT compiler is allowed to read `running` once and hoist it out of the loop. On a typical HotSpot JVM this program hangs; run it with `-Xint` (interpreter only) and it terminates, which proves the point: the code was always wrong, the interpreter was just forgiving.

Fix: declare `private volatile boolean running`, or use an `AtomicBoolean`. Both create the hb edge.

## Example 2: safe publication by piggybacking

```java
private int[] data;              // plain
private volatile boolean ready;  // volatile

// Thread 1                           // Thread 2
data = computeData();                 if (ready) {
ready = true;                             use(data);   // guaranteed to see the full array
                                      }
```

The write to `data` happens-before the volatile write (program order), which happens-before the volatile read (volatile rule), which happens-before `use(data)` (program order). Transitivity does the rest.

## Example 3: double-checked locking

```java
public final class Settings {

    private static volatile Settings instance;   // volatile is essential

    public static Settings get() {
        Settings result = instance;
        if (result == null) {
            synchronized (Settings.class) {
                result = instance;
                if (result == null) {
                    instance = result = new Settings();
                }
            }
        }
        return result;
    }
}
```

Without `volatile`, another thread may see a non-null `instance` whose fields have not been written yet: the JIT may publish the reference before the constructor's stores. The `synchronized` block protects the writers from each other but says nothing to the reader that skipped the lock. Since Java 5 the `volatile` write/read pair closes the gap. In practice, prefer a holder class or a single `enum` constant and avoid the pattern altogether.

## Example 4: volatile is not atomic

```java
private volatile int counter;

public void increment() {
    counter++;            // read, add, write: three actions, still a race
}
```

`volatile` guarantees that each read sees the latest write; it does not make read-modify-write sequences atomic. Two threads can both read 5 and both write 6. Use `AtomicInteger.incrementAndGet()`, `LongAdder` for hot counters, or a lock.

## Pitfalls

- "It works on my machine." x86 has a strong memory model, so many races never manifest there. The same code on ARM (your M-series laptop, Graviton in AWS) can fail. Test on both, and use [jcstress](https://github.com/openjdk/jcstress) for anything that claims to be lock-free.
- Treating `synchronized` as only mutual exclusion. It is also the visibility mechanism: exiting a `synchronized` block publishes everything done inside it to the next thread that enters.
- `volatile` arrays and collections. Only the reference is volatile; writes to the elements are plain and need their own synchronisation.
- Leaking `this` from a constructor. `final` fields are guaranteed visible after construction only if the reference does not escape before the constructor finishes (registering `this` as a listener in the constructor is the classic mistake).
- `Thread.sleep`, `yield` and timing. They create no hb edges. A race that "went away after adding a sleep" is still there.
- Sharing a `HashMap` between threads without synchronisation. Readers can see a half-rebuilt table; in old JDKs this produced infinite loops during resize. Use `ConcurrentHashMap` or confine the map to one thread.

## Check yourself

1. Thread A executes `x = 1; y = 1;` with plain fields. Thread B reads `y` and sees `1`, then reads `x`. Can B see `x == 0`? What single change makes that impossible?
2. In the double-checked locking example, the `synchronized` block is still there. Why does it not make the reader safe on its own?
3. Does `volatile` make `balance += amount` thread-safe? What does?
4. Name three `java.util.concurrent` operations whose happens-before guarantees you rely on without thinking about it.

## Go deeper

- [JSR-133 FAQ](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html) · the model explained by its authors; short and definitive.
- [Aleksey Shipilёv: Java Memory Model Pragmatics](https://shipilev.net/blog/2014/jmm-pragmatics/) · what the rules mean in practice, with the test harness that proves it.
- [Aleksey Shipilёv: Safe Publication and Safe Initialization](https://shipilev.net/blog/2014/safe-public-construction/) · `final` fields, constructors and the publication idioms, measured.
- [JLS 17.4: Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4) · the specification itself, for when you need the exact wording.
- [java.util.concurrent: Memory Consistency Properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility) · the hb edges the library gives you.
- [Preshing: Memory Ordering at Compile Time](https://preshing.com/20120625/memory-ordering-at-compile-time/) · the compiler's side of the story, language-neutral.

---

Part of [Memory & Concurrency](../README.md) · items 3.2, 3.3, 3.4
