# Deadlock, livelock and starvation

> **In one sentence:** A deadlock needs four conditions at once (mutual exclusion, hold-and-wait, no preemption, circular wait), so you prevent it by breaking one, usually by acquiring locks in a global order or by using `tryLock` with a timeout, and you diagnose it from a thread dump, where the JVM names the cycle for you.

**Why it matters:** A deadlocked service does not crash; it stops answering while its health check keeps passing, its CPU idle, its threads all `BLOCKED`. The same reasoning covers deadlocks that are not about locks at all: two threads each holding a database connection and waiting for a second one from an exhausted pool, or tasks waiting on tasks in the same bounded thread pool. Reading a thread dump is the skill that turns an "it just hangs" incident into a ten-minute fix.

## The idea

**The four conditions (Coffman).** A deadlock can exist only if all of these hold:

1. **Mutual exclusion**: a resource can be held by one thread at a time.
2. **Hold and wait**: a thread holds one resource while waiting for another.
3. **No preemption**: a resource is released only by the thread holding it.
4. **Circular wait**: thread A waits for B, B waits for A (or a longer cycle).

Each condition suggests a way out. Remove mutual exclusion with immutable data or lock-free structures (item 4.6). Remove hold-and-wait by acquiring everything you need in one step, or by giving up what you hold when you cannot get the rest. Add preemption with timeouts: `tryLock(timeout, unit)` instead of `lock()`. Break circular wait with **lock ordering**: define a global order on locks (by account id, by object address, by a fixed hierarchy) and always acquire in that order, so no cycle can form. Ordering is the standard fix for two-resource cases like transfers between accounts; when the order depends on runtime arguments (`transfer(from, to)` and `transfer(to, from)`), sort the two locks by a stable key before taking them, and use a third "tie-breaking" lock when the keys can be equal.

**Resource deadlocks.** The conditions apply to any exclusive resource. A connection pool of 10 and 10 request threads that each take one connection and then need a second one deadlocks with the pool empty. A fixed thread pool whose tasks submit subtasks to the same pool and `get()` them deadlocks when all threads are waiting for subtasks that cannot start (item 5.3, the common pool trap). Timeouts on pool acquisition turn these from hangs into errors you can see.

**Livelock** is a deadlock with motion: threads are not blocked, but they keep responding to each other without progressing. The classic case is two threads that `tryLock`, fail, release everything, retry at the same moment, and fail again forever. The fix is randomised back-off so that one of them wins.

**Starvation** is a thread that never gets what it needs because others keep taking it: a low-priority thread on a busy CPU, a writer behind an endless stream of readers on a read-write lock, or a thread waiting on a `synchronized` monitor that newcomers keep "barging" into. Java locks are unfair by default because fairness costs throughput; `new ReentrantLock(true)` hands the lock to the longest waiter, at a measurable price, and is rarely needed.

**Reading a thread dump.** `jcmd <pid> Thread.print` (or `jstack <pid>`, or `kill -3 <pid>` to print to stdout) dumps every thread's stack with its state and the monitors it holds or waits for. The JVM also runs a cycle detector over `synchronized` monitors *and* `java.util.concurrent` locks and appends a `Found one Java-level deadlock` section naming the threads and the locks. `ThreadMXBean.findDeadlockedThreads()` exposes the same detector to monitoring code.

## Example: a two-lock deadlock and its thread dump

```java
public class TwoLockDeadlock {

    private static final Object ACCOUNT_LOCK = new Object();
    private static final Object LEDGER_LOCK = new Object();

    public static void main(String[] arguments) {
        Thread transferThread = new Thread(() -> {
            synchronized (ACCOUNT_LOCK) {
                pause();
                synchronized (LEDGER_LOCK) {
                    System.out.println("transfer recorded");
                }
            }
        }, "transfer");
        Thread reportThread = new Thread(() -> {
            synchronized (LEDGER_LOCK) {
                pause();
                synchronized (ACCOUNT_LOCK) {
                    System.out.println("report produced");
                }
            }
        }, "report");
        transferThread.start();
        reportThread.start();
    }

    private static void pause() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }
}
```

Each thread takes its first lock, sleeps long enough for the other to take the second, then waits forever. Nothing is printed and the process never exits. `jcmd $(pgrep -f TwoLockDeadlock) Thread.print` shows the two threads (OpenJDK 25, trimmed):

```text
"transfer" #25 [25859] prio=5 os_prio=31 cpu=0.21ms elapsed=3.24s tid=0x0000007adf16e800 nid=25859 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
	at TwoLockDeadlock.lambda$main$0(TwoLockDeadlock.java:11)
	- waiting to lock <0x0000007018418160> (a java.lang.Object)
	- locked <0x0000007018418150> (a java.lang.Object)

"report" #26 [32771] prio=5 os_prio=31 cpu=0.09ms elapsed=3.24s tid=0x0000007adf16f000 nid=32771 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
	at TwoLockDeadlock.lambda$main$1(TwoLockDeadlock.java:19)
	- waiting to lock <0x0000007018418150> (a java.lang.Object)
	- locked <0x0000007018418160> (a java.lang.Object)
```

and, at the end of the dump, the detector's verdict:

```text
Found one Java-level deadlock:
=============================
"transfer":
  waiting to lock monitor 0x0000007adec9e760 (object 0x0000007018418160, a java.lang.Object),
  which is held by "report"

"report":
  waiting to lock monitor 0x0000007adec9e840 (object 0x0000007018418150, a java.lang.Object),
  which is held by "transfer"

Java stack information for the threads listed above:
===================================================
"transfer":
	at TwoLockDeadlock.lambda$main$0(TwoLockDeadlock.java:11)
	- waiting to lock <0x0000007018418160> (a java.lang.Object)
	- locked <0x0000007018418150> (a java.lang.Object)
...
Found 1 deadlock.
```

Read it as a graph: each thread's `locked` address is the other's `waiting to lock` address, and the line numbers point at the two inner `synchronized` blocks. With `ReentrantLock` the section looks the same except that the threads are `WAITING (parking)` and the lines read `parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)`.

Fix one, ordering: both threads take `ACCOUNT_LOCK` first and `LEDGER_LOCK` second. The report thread then simply waits for the transfer to finish. Fix two, timeouts, when a fixed order is impossible:

```java
static boolean transferWithTimeout() throws InterruptedException {
    if (!ACCOUNT_LOCK.tryLock(200, TimeUnit.MILLISECONDS)) {
        return false;
    }
    try {
        if (!LEDGER_LOCK.tryLock(200, TimeUnit.MILLISECONDS)) {
            return false;
        }
        try {
            return true;
        } finally {
            LEDGER_LOCK.unlock();
        }
    } finally {
        ACCOUNT_LOCK.unlock();
    }
}
```

(with the locks as `ReentrantLock`s). A `false` means "back off and retry after a random delay", and the retry limit becomes an error the caller can report instead of a hang.

## Pitfalls

- Open calls under a lock. Calling a listener, a remote service or any method you do not own while holding a lock hands your lock order to code you cannot see. Copy what you need, release, then call.
- Deadlocks that the detector cannot see. A thread blocked in `Object.wait()` for a `notify` that never comes, a `Future.get()` on a task that cannot be scheduled, a database lock cycle, or a pool exhaustion all hang the same way but show no `Found one Java-level deadlock`. Look for many threads parked at the same line.
- One dump. Two dumps a few seconds apart show which threads have not moved; monitoring that counts `BLOCKED` threads or calls `findDeadlockedThreads()` finds the hang before the pager does.
- Timeouts without back-off. Two threads that time out, release and retry in lockstep have turned a deadlock into a livelock; add jitter.
- Nested `REQUIRES_NEW` transactions on a small connection pool. The outer transaction holds a connection while the inner one waits for a second; under load every thread waits for a connection held by a thread that is waiting for a connection.
- Turning on fair locks to "fix" starvation everywhere. Fairness can cut lock throughput by an order of magnitude; use it only on the one lock where starvation is observed.

## Check yourself

1. Which of the four conditions does lock ordering remove, and why does `tryLock` with a timeout attack a different one?
2. A thread dump has 200 Tomcat threads, all `WAITING` in `HikariPool.getConnection`, and no deadlock section. Is this a deadlock? What would you look for next?
3. `transfer(from, to)` locks `from` then `to`. Two concurrent calls, `transfer(a, b)` and `transfer(b, a)`, deadlock. Write the locking order that fixes it, and say what happens when `from == to`.
4. Two threads keep failing `tryLock`, releasing and retrying in perfect alternation. What is this called, and what one-line change ends it?

## Go deeper

- [Baeldung: Deadlock and Livelock](https://www.baeldung.com/java-deadlock-livelock) · both failure modes reproduced in small programs.
- [Java Concurrency in Practice, chapter 10](https://jcip.net/) · lock-ordering deadlocks, open calls, resource deadlocks and the tie-breaking lock for dynamic order (paid).
- [jcmd reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) · every diagnostic command, including `Thread.print` and its options.
- [Oracle Java Tutorials: Concurrency](https://docs.oracle.com/javase/tutorial/essential/concurrency/) · the "Liveness" lesson defines deadlock, starvation and livelock in a page each.

---

Part of [Memory & Concurrency](../README.md) · item 4.5
