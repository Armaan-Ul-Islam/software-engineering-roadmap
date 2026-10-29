# TDD as a design practice, and the tests worth keeping

> **In one sentence:** Test-driven development is a design loop (list the behaviours, write one failing test, make it pass with the simplest code, refactor, repeat) whose main output is an interface shaped by its first caller rather than by its implementation; outside-in TDD starts that loop at an acceptance test on the system's edge and works inwards; and the tests it leaves behind are only an asset if they are deterministic, structure-insensitive, built from readable data, and checked by something stronger than line coverage.

**Why it matters:** The teams that get the most from TDD are not using it to find bugs; they use it to find out, before writing a class, what its callers need from it. Code written test-first has fewer parameters, fewer hidden dependencies and fewer reasons to mock, because every awkwardness shows up as an awkward test first. And the suites that teams abandon are not abandoned for being slow; they are abandoned for being flaky, for breaking on every refactoring, and for reporting 90 percent coverage while the bug ships.

## The idea

**Canon TDD.** Kent Beck's own restatement of the loop, because the popular "red, green, refactor" leaves out the step that does the design work:

1. Write a list of the test scenarios you want to cover: the behaviours, edge cases and error cases you can think of now. This is a plan, not a commitment; it grows as you learn.
2. Turn exactly one item on the list into a concrete, runnable test, and watch it fail. The test is where you decide the interface: the name of the method, what it takes, what it returns, what it throws. You are the first caller, so you write the call you would want.
3. Change the code to make that test and all previous tests pass. The simplest change, even one you know is temporary (returning a constant is fine for the first test).
4. Optionally refactor, now that everything is green, to improve the design without changing behaviour. This is when duplication between the constant in step 3 and the next test's expectation gets replaced by the real logic.
5. Back to step 2 until the list is empty.

The step people skip is 4, and skipping it is why "TDD produced ugly code" is a common report: the loop without refactoring produces a pile of special cases. The step people get wrong is 2: writing five tests at once removes the design feedback, because you no longer notice that the second test wanted a different signature than the first.

**What the loop does to the design.** A test is the first client of the code, written before there is any implementation to be loyal to. Dependencies that are hard to construct in a test are hard to construct everywhere, so the test pushes them behind constructor parameters and small interfaces. Methods that need six arguments to test get a parameter object. A class that needs the database to test a pricing rule gets split into the rule and the adapter (item 7.2). None of this needs a principle; the discomfort of the test is the principle.

**Outside-in.** Freeman and Pryce (*Growing Object-Oriented Software*) start one level further out. First a *walking skeleton*: the thinnest possible slice through the whole system (one endpoint, one row, deployed), so the build, deployment and test infrastructure exist before the features. Then, for each feature, an *acceptance test* at the system's edge (an HTTP call, a message) that fails because the feature does not exist. Then the inner TDD loop, class by class, from the edge inwards, until the acceptance test passes. The acceptance test keeps the inner loop honest about what the feature is for; the inner loop keeps the classes small. Outside-in naturally uses test doubles for collaborators that do not exist yet (the mockist style, item 5.3); the trap is keeping those mocks after the collaborators do exist.

**Test quality.** Beck's *Test Desiderata* lists the properties a test can have (isolated, composable, deterministic, specific, behavioural, structure-insensitive, fast, writable, readable, automated, predictive, inspiring), and notes they trade off: an end-to-end test is predictive but slow; a unit test is fast and specific but less predictive. The ones you should not trade away:

- 1.1 **Deterministic.** A flaky test is one that passes and fails on the same code. Fowler's catalogue of causes: shared fixtures and leftover state, asynchrony asserted with a sleep instead of a wait, the system clock, resource leaks, and real remote services. Each has a mechanical fix (fresh state per test, await with a timeout, inject a `Clock`, close in `@AfterEach`, a fake). Quarantine a flaky test the day it flakes; a suite people re-run until it passes has no value as a signal.
- 1.2 **Structure-insensitive.** The test names the behaviour and references only the public API, so refactoring does not break it (item 5.2).
- 1.3 **Readable.** A test should show what matters and hide what does not. *Test data builders* do that: `anOrder().withLine("SKU-1", 2).build()` says that the line matters and the customer, currency and dates are defaults. Without them, each test constructs a full object graph and the one value under test is lost in thirty lines of setup.

Two tools find what example-based tests miss. **Property-based testing** (jqwik on the JVM) generates hundreds of inputs and checks a property that must hold for all of them, then shrinks a failing input to the smallest one. **Mutation testing** (PIT, run as `mvn org.pitest:pitest-maven:mutationCoverage`) changes the production code (flips a `<` to `<=`, deletes a statement, returns null) and runs the tests; every mutant that survives is a line the tests execute but do not check. That is the honest reading of coverage: a line with zero coverage is certainly untested, and a line with coverage is not therefore tested. Coverage is a smell detector for gaps, never a target.

## Example: allocating money without losing a cent

The list: a whole amount splits evenly; a remainder goes to the first shares one cent each; zero shares is rejected; for any amount and share count the parts sum to the amount and differ by at most one cent.

Test 1, the interface decision made as its first caller:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class AllocationTest {

    @Test
    void aWholeAmountSplitsEvenly() {
        assertThat(Allocation.allocate(9000, 3)).containsExactly(3000L, 3000L, 3000L);
    }
}
```

The simplest green: `return List.of(3000L, 3000L, 3000L);`. Test 2 forces the real arithmetic:

```java
@Test
void remainderCentsGoToTheFirstShares() {
    assertThat(Allocation.allocate(10000, 3)).containsExactly(3334L, 3333L, 3333L);
}
```

After the refactoring step, the code that passes both, plus the rejection test:

```java
import java.util.Arrays;
import java.util.List;

public final class Allocation {

    public static List<Long> allocate(long amountInCents, int shares) {
        if (shares < 1) {
            throw new IllegalArgumentException("shares must be at least 1");
        }
        long base = amountInCents / shares;
        long remainder = amountInCents % shares;
        Long[] parts = new Long[shares];
        for (int index = 0; index < shares; index++) {
            parts[index] = index < remainder ? base + 1 : base;
        }
        return Arrays.asList(parts);
    }
}
```

Run on `(10000, 3)`, `(5, 3)` and `(0, 2)` it prints `[3334, 3333, 3333]`, `[2, 2, 1]` and `[0, 0]`. The last list item becomes a property rather than more examples:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Collections;
import java.util.List;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.constraints.IntRange;
import net.jqwik.api.constraints.LongRange;

class AllocationProperties {

    @Property
    void partsSumToTheAmountAndDifferByAtMostOneCent(
            @ForAll @LongRange(min = 0, max = 100_000_000) long amountInCents,
            @ForAll @IntRange(min = 1, max = 500) int shares) {
        List<Long> parts = Allocation.allocate(amountInCents, shares);

        assertThat(parts).hasSize(shares);
        assertThat(parts.stream().mapToLong(Long::longValue).sum()).isEqualTo(amountInCents);
        assertThat(Collections.max(parts) - Collections.min(parts)).isLessThanOrEqualTo(1);
    }
}
```

What mutation testing would add: PIT's conditional-boundary mutator turns `index < remainder` into `index <= remainder`. The two example tests kill that mutant (`10000 / 3` would give `3334, 3334, 3333`, sum 10001), and the property kills it on nearly every generated input. Replace the example tests with one that only asserts `hasSize(3)` and the mutant survives with 100 percent line coverage, which is the whole argument against coverage as a goal.

## Pitfalls

- Writing the implementation in your head first, then a test that matches it. The signature is then designed by the implementation and the loop has lost its value; the test should feel slightly presumptuous.
- Test lists that never shrink. If every test adds two items, the design is telling you the unit is too big.
- Skipping the refactor step because the test is green and the next item beckons. The pile of special cases is the result.
- Outside-in with mocks that outlive the design. Once the real collaborator exists, test through it or through a fake; mocks of your own classes are structure-sensitive (item 5.3).
- `Thread.sleep` in tests. Use Awaitility or a `CountDownLatch`; a sleep is a flaky test with a fixed delay added.
- Builders with every field required. `anOrder()` must produce a valid order with no arguments, or tests go back to thirty lines of setup.
- Property tests with properties that restate the implementation (`allocate(amount, shares).get(0) == amount / shares + (amount % shares > 0 ? 1 : 0)`). Properties should be invariants a domain expert would state.
- A coverage gate at 80 percent. Teams meet it with tests that assert nothing. Gate on mutation score for the modules that matter, or on nothing.

## Check yourself

1. In Canon TDD, what is the design decision made in step 2 that the implementation step cannot make, and what goes wrong when you write three tests before any code?
2. The first green for `aWholeAmountSplitsEvenly` is `return List.of(3000L, 3000L, 3000L)`. Why is that acceptable, and which later step removes it?
3. A test passes locally and fails one run in twenty in CI. List four possible causes and the fix for each.
4. A module reports 95 percent line coverage and a mutation score of 40 percent. What does each number tell you, and which would you act on?

## Go deeper

- [Kent Beck: Canon TDD](https://tidyfirst.substack.com/p/canon-tdd) · the five steps as the author states them, with the common misreadings called out.
- [Growing Object-Oriented Software, Guided by Tests](http://www.growing-object-oriented-software.com/) · outside-in TDD, the walking skeleton, and how mocks drive interface discovery (paid).
- [Kent Beck: Test Desiderata](https://testdesiderata.com/) · the twelve properties and why you cannot have all of them in one test.
- [Fowler: Eradicating Non-Determinism in Tests](https://martinfowler.com/articles/nonDeterminism.html) · the causes of flakiness and the fix for each; quarantine is his recommendation too.
- [Unit Testing Principles, Practices, and Patterns](https://www.manning.com/books/unit-testing) · the four pillars of a good test, and coverage metrics as a negative indicator only (paid).

---

Part of [Architecture & Craft](../README.md) · items 5.5, 5.6
