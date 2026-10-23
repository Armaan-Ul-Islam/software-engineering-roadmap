# Race conditions and locks: compound actions, `synchronized` and `ReentrantLock`

> **In one sentence:** A race condition is a bug whose outcome depends on which thread gets there first, it almost always hides in a *compound action* (check-then-act or read-modify-write) that looks like one line but is several steps, and the fix is to make the whole action atomic with one lock that every access to that state shares.

**Why it matters:** Races pass unit tests, pass code review, and fail under load as lost updates, duplicate records, or a cache that hands two users each other's session. "Thread-safe" classes do not help by themselves: a `ConcurrentHashMap` makes each `get` and `put` atomic, not the `if` between them. Interviewers ask you to fix a racy counter because the answer reveals whether you think in operations or in lines.

## The idea

**Atomic is per operation, not per line.** `count++` is a read, an add and a write. Two threads can both read 5 and both write 6, and one increment is lost. That is a **read-modify-write** race. `if (!map.containsKey(key)) map.put(key, value)` is a **check-then-act** race: between the check and the act another thread can make the check stale. Both are *compound actions*: sequences of steps that must appear to other threads as one indivisible step. Making them atomic means ensuring that no other thread can touch the same state between the first step and the last.

**Intrinsic locks.** Every Java object has a monitor. `synchronized (lock) { ... }` acquires it on entry and releases it on exit, including exit by exception. A `synchronized` instance method locks `this`; a `synchronized` static method locks the `Class` object. Intrinsic locks are **reentrant**: a thread holding the lock can enter another block guarded by the same lock, so a synchronised method may call another synchronised method on the same object. Besides mutual exclusion, a lock gives visibility: everything a thread did before releasing the lock is visible to the next thread that acquires it (item 3.2). What `synchronized` cannot do is give up: a thread waiting for the monitor cannot be interrupted or time out.

**`ReentrantLock`** is the same idea as an object with methods: `lock()`, `unlock()` (always in a `finally`), `tryLock()` which returns immediately, `tryLock(timeout, unit)`, `lockInterruptibly()`, an optional fairness mode, and several `Condition` queues per lock (item 4.4). Use it when you need one of those features; otherwise `synchronized` is shorter, cannot be left locked by a forgotten `unlock`, and on current JVMs is just as fast.

**`ReadWriteLock`** (`ReentrantReadWriteLock`) lets any number of readers hold the read lock together while a writer needs the write lock alone. It pays off only when reads are long and far outnumber writes; for short reads the extra bookkeeping costs more than a plain lock, and `StampedLock`'s optimistic read is usually better (item 4.3).

**Granularity.** One lock for the whole service serialises everything; one lock per account lets unrelated transfers proceed in parallel but complicates operations that touch two accounts (item 4.5). `ConcurrentHashMap` locks per bin, which is why it scales where `Collections.synchronizedMap` does not. Whatever the granularity: all accesses to a piece of state, reads included, must use the *same* lock, and the lock should be held for as short a time as possible and never across I/O or calls into unknown code.

## Example: a racy counter, fixed two ways

```java
public class RacyCounter {

    private int count;

    void increment() {
        count++;
    }

    public static void main(String[] arguments) throws InterruptedException {
        RacyCounter counter = new RacyCounter();
        Thread firstThread = new Thread(() -> { for (int index = 0; index < 1_000_000; index++) counter.increment(); });
        Thread secondThread = new Thread(() -> { for (int index = 0; index < 1_000_000; index++) counter.increment(); });
        firstThread.start();
        secondThread.start();
        firstThread.join();
        secondThread.join();
        System.out.println("count = " + counter.count);
    }
}
```

Three runs on OpenJDK 25: `count = 1642086`, `count = 1351626`, `count = 1615384`. Up to a third of the increments vanished, and the result differs every run.

Fix one, a lock: `synchronized void increment() { count++; }`, and read `count` under the same lock. Fix two, an atomic: `private final AtomicInteger count = new AtomicInteger();` with `count.incrementAndGet()`, which uses a hardware instruction instead of a lock (item 4.6). Both print `2000000` every time. Making the field `volatile` does *not* fix it (item 3.3).

## Example: a racy "put if absent", fixed two ways

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class SessionRegistry {

    record Session(String userId) {
    }

    private final Map<String, Session> sessions = new ConcurrentHashMap<>();

    Session sessionFor(String userId) {
        Session existing = sessions.get(userId);
        if (existing == null) {
            existing = new Session(userId);
            sessions.put(userId, existing);
        }
        return existing;
    }
}
```

Each map operation is atomic, the method is not. With eight threads asking for 200,000 users each, counting how often `put` replaced a value another thread had just stored: `25539`, `26458`, `40301` sessions silently overwritten in three runs. Two users end up holding different `Session` objects for the same id, and whichever was created second wins the map.

Fix one, a lock around the compound action, using a lock that every access to the map shares:

```java
private final Object sessionsLock = new Object();

Session sessionFor(String userId) {
    synchronized (sessionsLock) {
        Session existing = sessions.get(userId);
        if (existing == null) {
            existing = new Session(userId);
            sessions.put(userId, existing);
        }
        return existing;
    }
}
```

Fix two, let the map do the compound action atomically, which is what these methods exist for:

```java
Session sessionFor(String userId) {
    return sessions.computeIfAbsent(userId, Session::new);
}
```

`putIfAbsent` works too when the value is cheap to build: `Session created = new Session(userId); Session previous = sessions.putIfAbsent(userId, created); return previous != null ? previous : created;`. Both fixes report `0` overwrites. The second scales better because `ConcurrentHashMap` locks only the bin for that key, but its mapping function must be short and must not touch the same map (item 4.7).

## Pitfalls

- Guarding writes but not reads. A `synchronized` setter with a plain getter is still a race: the getter may see a stale or half-written value. Every access to guarded state goes through the lock.
- Locking the wrong object. Two methods that synchronise on different locks do not exclude each other. Document which lock guards which fields, and keep the lock private: `synchronized (this)` and `synchronized` methods let any caller lock your object and deadlock you.
- Locking on strings, boxed numbers or `Boolean`. String literals are interned and `Boolean.TRUE` is a single instance, so unrelated code ends up sharing your lock. Use `private final Object lock = new Object()`.
- Calling out while holding a lock. A listener, a remote call or a database query under a lock turns every slow dependency into a global stall, and calls into code that takes other locks are how deadlocks start (item 4.5).
- Forgetting `finally` with `ReentrantLock`. An exception between `lock()` and `unlock()` leaves the lock held forever; the next caller blocks until the process restarts.
- Reaching for `ReadWriteLock` for short reads. Measure first; a plain `synchronized` or `StampedLock` is usually faster.
- `Collections.synchronizedMap` with external iteration. Each call is atomic, iteration is not; iterate under `synchronized (map)`, or use a concurrent collection whose iterators are weakly consistent.

## Check yourself

1. `if (balance >= amount) balance -= amount;` runs on a `volatile int balance`. Name the two races in this line and fix both with one change.
2. Two methods on the same object: `synchronized void deposit()` and `static synchronized void audit()`, both touching the same instance field. Do they exclude each other? Why?
3. A `ReentrantLock` guards a cache. A request takes the lock, then calls a remote service to populate the cache, then unlocks. What happens to throughput when the remote service slows to two seconds, and how would you restructure it?
4. Why does `computeIfAbsent` make the session example safe when a plain `get` followed by `put` on the same `ConcurrentHashMap` does not? What property of the map does each rely on?

## Go deeper

- [Java Concurrency in Practice, chapter 2](https://jcip.net/) · the definitive treatment of compound actions, intrinsic locks and guarding state (paid).
- [Jenkov: Java synchronized](https://jenkov.com/tutorials/java-concurrency/synchronized.html) · what `synchronized` locks in each position, with the reentrancy and visibility rules.
- [Baeldung: Guide to java.util.concurrent.Locks](https://www.baeldung.com/java-concurrent-locks) · `ReentrantLock`, `ReadWriteLock` and `StampedLock` side by side.
- [java.util.concurrent package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html) · the atomicity guarantees each concurrent collection actually makes.

---

Part of [Memory & Concurrency](../README.md) · items 4.2, 4.3
