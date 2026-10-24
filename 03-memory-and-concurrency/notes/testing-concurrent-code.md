# Testing concurrent code: forcing interleavings, stress tests and jcstress

> **In one sentence:** A unit test runs one interleaving out of millions and the scheduler picks a boring one, so concurrent code is tested by making it deterministic where possible (inject executors and clocks), forcing the dangerous interleaving with latches where you can name it, stressing it from a start gate where you cannot, and handing memory-model claims to jcstress; and every blocking call in a test carries a timeout, because a hanging build is the worst result a test can produce.

**Why it matters:** The check-then-act race of item 4.2 passes a hundred thousand ordinary test runs; the visibility bug of item 3.3 passes on x86 and fails on ARM in production. Code review catches some of this; tests catch almost none unless they are written to. The techniques are cheap once learned, and the payoff is large: a seam that lets a test pause a thread between its check and its act turns a once-a-month incident into a test that fails every time until the fix is in.

## The idea

**Why unit tests miss races.** A race needs a specific interleaving: thread B must run inside the window between A's check and A's act, often a few nanoseconds wide. Starting a thread costs tens of microseconds, so two threads started one after the other usually run one after the other. The JIT, the scheduler and the memory system of a laptop differ from production, and a test that "passed a thousand times" sampled a thousand interleavings from a space that grows exponentially with the number of shared accesses. Memory-model bugs are worse still: they need reorderings that the JIT applies only after warm-up and that the hardware applies only on some architectures (item 3.1). Coverage tools count lines, not interleavings.

**Design for determinism first.** Most of the logic in a concurrent component is not concurrent. Separate it from the plumbing:

1. Inject the `Executor`. Production passes a pool; a test passes `Runnable::run`, a same-thread executor, so submitted work completes before `submit` returns, or a controllable executor that runs queued tasks when the test says so.
2. Inject the `Clock`. `Clock.fixed(...)` or a mutable test clock replaces `Instant.now()`, so expiries, timeouts and rate limits are tested by moving time, not by sleeping through it.
3. Make the state machine explicit and test its transitions single-threaded; then test the thin concurrent wrapper separately.
4. Share less. Immutable values and message passing (item 6.1) need no concurrency test at all.

**Force the interleaving with latches.** When you can name the dangerous interleaving, make the code expose a seam at that point: a `Runnable` hook that is a no-op in production. The test's hook counts down one latch to announce "I am past the check" and awaits a second latch before continuing. The test waits for the first latch, runs the second thread to completion, then releases the first. The race reproduces on every run. The same seam, with the fix in place, lets the test observe that the second thread is `BLOCKED` while the first sits inside the critical section. Pausing a thread exactly where you choose is deterministic in a way a `Thread.sleep` never is.

**Stress tests and their limits.** When the interleaving cannot be named, run many threads through the code from a start gate (item 4.4), many times, and check invariants afterwards: the count is exact, nothing was overwritten, no exception escaped. Improve the odds with more threads than cores, `Thread.yield()` at suspicious points, different JVM modes (`-Xint`, `-XX:TieredStopAtLevel=1`) and an ARM machine in CI as well as x86. A failing stress test has found a bug; a passing one has found nothing, so keep them in a separate, slow suite and do not accept green as evidence in a review.

**jcstress for memory-model claims.** Your own stress test cannot tell whether an outcome is *allowed*. jcstress, the OpenJDK harness, can: a test declares a shared `@State`, two or more `@Actor` methods that run concurrently on it, and `@Outcome`s marked acceptable or forbidden; the harness runs the actors millions of times across cores and JIT modes and reports how often each outcome occurred, failing on a forbidden one. It is how the JDK's own concurrency classes are tested, and it is the only tool here that can show that a missing `volatile` matters (item 3.2). The project's Maven archetype produces a runnable `jcstress.jar`; a run takes minutes and belongs in its own module.

**Leaked threads.** A test that starts a pool and never shuts it down leaves threads alive for the rest of the suite, hiding shutdown bugs and slowing everything after it. Snapshot the live threads before and compare after:

```java
Set<Thread> before = Thread.getAllStackTraces().keySet();
// run the code under test
Set<Thread> leaked = new HashSet<>(Thread.getAllStackTraces().keySet());
leaked.removeAll(before);
leaked.removeIf(thread -> !thread.isAlive() || thread.isDaemon());
assertTrue(leaked.isEmpty(), () -> "threads left running: " + leaked);
```

Name every thread you create (`Thread.ofPlatform().name("import-worker-", 0).factory()`) so that a leak is attributable, and close executors with try-with-resources.

**Timeouts on every blocking call.** `latch.await(5, SECONDS)` with the boolean asserted, `future.get(5, SECONDS)`, `queue.poll(timeout, unit)`, `thread.join(5_000)` followed by an `isAlive()` check, and JUnit 5's `@Timeout` on the class as the backstop. A hanging test blocks the pipeline until an outer limit kills it and reports nothing; a test that fails after five seconds names the latch that was never released. Waiting for an eventual condition is Awaitility's job, never a sleep's.

## Example: reproducing a check-then-act race with two latches

`SeatBooking.book()` is the racy check-then-act; `afterCheck` is the seam. The test runs the unsynchronised class and the fixed subclass through the same interleaving.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Function;

public class SeatBookingRace {

    static class SeatBooking {

        private final Runnable afterCheck;
        protected int seatsLeft;

        SeatBooking(int seatsLeft, Runnable afterCheck) {
            this.seatsLeft = seatsLeft;
            this.afterCheck = afterCheck;
        }

        boolean book() {
            if (seatsLeft > 0) {
                afterCheck.run();
                seatsLeft--;
                return true;
            }
            return false;
        }
    }

    static final class SynchronizedSeatBooking extends SeatBooking {

        SynchronizedSeatBooking(int seatsLeft, Runnable afterCheck) {
            super(seatsLeft, afterCheck);
        }

        @Override
        synchronized boolean book() {
            return super.book();
        }
    }

    public static void main(String[] arguments) throws InterruptedException {
        reproduce("unsynchronised", afterCheck -> new SeatBooking(1, afterCheck));
        reproduce("synchronised  ", afterCheck -> new SynchronizedSeatBooking(1, afterCheck));
    }

    static void reproduce(String label, Function<Runnable, SeatBooking> bookingFactory) throws InterruptedException {
        CountDownLatch firstPassedCheck = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean hookArmed = new AtomicBoolean(true);
        SeatBooking booking = bookingFactory.apply(() -> {
            if (hookArmed.getAndSet(false)) {
                firstPassedCheck.countDown();
                awaitOrFail(release);
            }
        });
        boolean[] booked = new boolean[2];
        Thread first = Thread.ofPlatform().name("first").start(() -> booked[0] = booking.book());
        awaitOrFail(firstPassedCheck);
        Thread second = Thread.ofPlatform().name("second").start(() -> booked[1] = booking.book());
        awaitTerminatedOrBlocked(second);
        release.countDown();
        joinOrFail(first);
        joinOrFail(second);
        System.out.println(label + ": first booked " + booked[0] + ", second booked " + booked[1]
                + ", seats left " + booking.seatsLeft);
    }

    static void awaitTerminatedOrBlocked(Thread thread) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != Thread.State.TERMINATED && thread.getState() != Thread.State.BLOCKED) {
            if (System.nanoTime() > deadline) {
                throw new AssertionError("second thread neither finished nor blocked");
            }
            Thread.sleep(1);
        }
    }

    static void awaitOrFail(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("latch not released within 5 seconds");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError("interrupted", exception);
        }
    }

    static void joinOrFail(Thread thread) throws InterruptedException {
        thread.join(5_000);
        if (thread.isAlive()) {
            throw new AssertionError(thread.getName() + " did not finish within 5 seconds");
        }
    }
}
```

Three consecutive runs on OpenJDK 25, identical every time:

```text
unsynchronised: first booked true, second booked true, seats left -1
synchronised  : first booked true, second booked false, seats left 0
```

The hook disarms itself, so only the first caller pauses. For the racy class, the second thread runs the whole method while the first is parked past its check: both book the single seat and the count goes negative, deterministically. For the fixed class, the first thread holds the monitor while parked, so the second thread cannot even reach the check; the test watches it become `BLOCKED`, releases the first, and the second then correctly fails. Every wait has a timeout, so a broken fix (say, a lock that is never released) fails the test in five seconds instead of hanging it. In JUnit 5 this is a `@Test` method with `assertTrue(firstPassedCheck.await(5, SECONDS))` and `@Timeout(10)` on the class.

## Example: a jcstress test skeleton

```java
import org.openjdk.jcstress.annotations.Actor;
import org.openjdk.jcstress.annotations.Expect;
import org.openjdk.jcstress.annotations.JCStressTest;
import org.openjdk.jcstress.annotations.Outcome;
import org.openjdk.jcstress.annotations.State;
import org.openjdk.jcstress.infra.results.II_Result;

@JCStressTest
@Outcome(id = "1, 2", expect = Expect.ACCEPTABLE, desc = "first actor incremented first")
@Outcome(id = "2, 1", expect = Expect.ACCEPTABLE, desc = "second actor incremented first")
@Outcome(id = "1, 1", expect = Expect.ACCEPTABLE_INTERESTING, desc = "both read 0: a lost update")
@State
public class CounterRaceTest {

    private int value;

    @Actor
    public void firstActor(II_Result result) {
        result.r1 = ++value;
    }

    @Actor
    public void secondActor(II_Result result) {
        result.r2 = ++value;
    }
}
```

Each actor runs once per iteration on a fresh `@State` instance, concurrently with the other; `II_Result` collects the two `int`s and the harness tallies the `(r1, r2)` pairs over millions of iterations. `ACCEPTABLE_INTERESTING` flags the lost-update outcome in the report without failing the run; change it to `FORBIDDEN`, make `value` an `AtomicInteger` or the actors `synchronized`, and the run proves the fix by never observing it. Any outcome you did not declare is reported as a failure, which is how a test for a `volatile` flag catches the reordering you forgot was legal. (Compiled against `jcstress-core` 0.16; the harness itself runs from the jar the archetype builds.)

## Pitfalls

- Assertions in worker threads. An `AssertionError` thrown on another thread goes to that thread's uncaught-exception handler and the test passes. Collect failures in an `AtomicReference<Throwable>` or a `Future` and rethrow on the test thread.
- `Thread.sleep(100)` to "let the other thread get there". It is a guess about timing: too short and the test is flaky, long enough and the suite is slow, and it still proves nothing (item 4.4).
- Blocking calls without timeouts. `latch.await()`, `future.get()` and `thread.join()` turn a missing signal into a build that hangs for the CI job's full limit.
- Stress tests in the unit suite. They are slow and occasionally flaky by nature; a separate suite that runs on every architecture you deploy to is where they earn their keep.
- Mocking all the concurrency away. A same-thread executor tests the logic; keep one integration test with the real pool to cover rejection, shutdown and interruption.
- Testing only on x86. Reorderings that the JMM allows but x86 rarely performs show up on ARM (your laptop, Graviton); run the stress and jcstress suites there too.

## Check yourself

1. A test starts two threads that each call `transfer`, joins them and asserts the final balance. It has passed 10,000 times. What does that establish, and what change would make it fail reliably if the bug exists?
2. Why must a failed assertion inside a worker thread be captured and rethrown on the test thread, and what does the test report if it is not?
3. In the example, what does the test observe differently for the synchronised class, and why would `second.join()` without a timeout have been a bug in the test itself for that class?
4. Which kind of bug can jcstress demonstrate that neither a latch-based test nor a stress test of your own can, and what about its method makes that possible?

## Go deeper

- [jcstress](https://github.com/openjdk/jcstress) · the harness; its `jcstress-samples` module is a guided tour from the first test to advanced memory-model cases.
- [Java Concurrency in Practice, chapter 12](https://jcip.net/) · testing concurrent programs: safety and liveness tests, generating interleavings, and the pitfalls of timing-based tests (paid).
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) · `@Timeout`, `assertTimeoutPreemptively` and parallel test execution.
- [Awaitility](https://github.com/awaitility/awaitility) · asserting eventual conditions with a deadline instead of a sleep.
- [Lincheck](https://github.com/JetBrains/lincheck) · model checking of concurrent data structures on the JVM, for when you must write one.

---

Part of [Memory & Concurrency](../README.md) · item 6.2
