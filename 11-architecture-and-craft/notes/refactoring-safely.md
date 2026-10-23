# Refactoring safely: characterisation tests, small steps, and letting the IDE do the typing

> **In one sentence:** Refactoring is changing structure without changing behaviour, which is only safe when something proves the behaviour did not change; so pin it with tests first (characterisation tests when there are none), move in steps small enough that each is obviously correct, let the IDE perform the mechanical transformations, and commit after every step.

**Why it matters:** The 400-line class nobody dares touch got that way because every earlier attempt mixed a refactoring with a bug fix, broke something unrelated, and was reverted whole. Interviewers ask "how would you refactor this?" to see whether you reach for a test and a small step or for a rewrite. Rewrites of working code fail far more often than sequences of behaviour-preserving steps, and they fail late.

## The idea

**The definition is strict.** Fowler: a change to the internal structure of software that makes it easier to understand and cheaper to modify without changing its observable behaviour. Kent Beck's two hats: at any moment you are either changing behaviour or refactoring, never both. The practical rule is one hat per commit, so that a reviewer can read a refactoring diff knowing that any behaviour change in it is a mistake.

**The catalogue you actually use.** Most daily refactoring is a handful of named moves, and all of them are automated in IntelliJ IDEA and Eclipse:

| Refactoring | Use it when | Mechanics the IDE does for you |
|---|---|---|
| Extract Method | a block of code has a name a caller could trust without reading it (item 1.2) | finds parameters and return value, replaces duplicates of the same block |
| Inline Method | the body is as clear as the name, or the method is a shallow pass-through | replaces every call with the body |
| Rename | the name lies or is unclear | updates every reference, including overrides and Javadoc |
| Move Method or Field | the method uses another class's data more than its own | updates callers, adjusts visibility |
| Extract Class | a class has two clusters of fields used by two clusters of methods | creates the class, delegates, offers to move members |
| Introduce Parameter Object | three or more parameters travel together | creates the record or class, rewrites every signature and call |
| Replace Magic Literal | `3`, `"NO"`, `0.80` carry meaning | extracts a constant or enum and replaces occurrences |
| Replace Conditional with Polymorphism | the same `switch` on a type appears in several places | manual, but built from the moves above, one branch at a time |

Letting the IDE perform them is not laziness. The IDE updates references you did not know existed, handles overloads and overrides, and (for the moves in the table) preserves semantics. Michael Feathers calls this "leaning on the compiler": a renamed method either compiles everywhere or shows you every place it does not.

**Legacy code and characterisation tests.** Feathers defines legacy code as code without tests. Before changing it, write **characterisation tests**: call the code, assert on whatever it returns today, and let the first failure tell you the actual value. The test records the current behaviour, including behaviour you suspect is wrong; fixing the wrong behaviour is a separate commit with a changed expectation. For complex output (a generated PDF, a report), serialise it once and compare against the stored copy (a golden master). Write these tests at the coarsest boundary that is stable: a service method, an HTTP endpoint, the output of a batch job. Tests on private helpers you are about to delete are wasted.

To test legacy code you often need a **seam**: a place where behaviour can be altered without editing the code at that place. The common seams in Java are constructor injection (pass a `Clock` or a fake repository), and "extract and override" (extract the awkward call into a protected method and override it in a test subclass). Introduce a seam with the safest IDE moves, then test, then refactor properly.

**Small steps, one commit each.** Each step compiles, passes the tests, and is committed. When a step breaks a test and the cause is not obvious within a minute, revert the step and take a smaller one; debugging a broken refactoring is how a two-hour job becomes a two-day job. Signature changes across many callers use parallel change (expand, migrate, contract; item 4.3): add the new form, move callers over, remove the old form, as three commits.

## Example: a growing `switch`, three commits

The starting point. A sibling method `maxProjects(subscription)` has the same `switch`, and a fourth plan is coming.

```java
public class SubscriptionPricing {

    public BigDecimal price(Subscription subscription) {
        switch (subscription.planCode()) {
            case "FREE":
                return BigDecimal.ZERO;
            case "PRO":
                BigDecimal proPrice = new BigDecimal("99.00");
                if (subscription.isAnnual()) {
                    proPrice = proPrice.multiply(new BigDecimal("12")).multiply(new BigDecimal("0.80"));
                }
                return proPrice;
            case "TEAM":
                BigDecimal teamPrice = new BigDecimal("49.00").multiply(BigDecimal.valueOf(subscription.seats()));
                if (subscription.isAnnual()) {
                    teamPrice = teamPrice.multiply(new BigDecimal("12")).multiply(new BigDecimal("0.80"));
                }
                return teamPrice;
            default:
                throw new IllegalArgumentException("Unknown plan: " + subscription.planCode());
        }
    }
}
```

**Commit 1: "Add characterisation tests for SubscriptionPricing".** No production code changes.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class SubscriptionPricingTest {

    private final SubscriptionPricing pricing = new SubscriptionPricing();

    @ParameterizedTest
    @CsvSource({
        "FREE, false, 1, 0.00",
        "PRO,  false, 1, 99.00",
        "PRO,  true,  1, 950.40",
        "TEAM, false, 4, 196.00",
        "TEAM, true,  4, 1881.60",
    })
    void priceMatchesCurrentBehaviour(String planCode, boolean annual, int seats, BigDecimal expected) {
        assertThat(pricing.price(new Subscription(planCode, annual, seats))).isEqualByComparingTo(expected);
    }

    @Test
    void unknownPlanIsRejected() {
        assertThatThrownBy(() -> pricing.price(new Subscription("ENTERPRISE", false, 1)))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
```

The first run printed `950.4000`: the multiplications produce a scale of four. `isEqualByComparingTo` ignores scale so the test records the value, and the scale goes on the list as a bug to fix later, in its own commit, with a changed assertion.

**Commit 2: "Extract the billing-period rule and name the constants".** Three IDE actions (convert to `switch` expression, Extract Method on the duplicated discount block, Replace Magic Literal), tests run after each, one commit because each action is one click and provably behaviour-preserving.

```java
private static final BigDecimal MONTHS_PER_YEAR = new BigDecimal("12");
private static final BigDecimal ANNUAL_DISCOUNT_FACTOR = new BigDecimal("0.80");

public BigDecimal price(Subscription subscription) {
    return switch (subscription.planCode()) {
        case "FREE" -> BigDecimal.ZERO;
        case "PRO" -> forBillingPeriod(new BigDecimal("99.00"), subscription);
        case "TEAM" -> forBillingPeriod(new BigDecimal("49.00").multiply(BigDecimal.valueOf(subscription.seats())), subscription);
        default -> throw new IllegalArgumentException("Unknown plan: " + subscription.planCode());
    };
}

private static BigDecimal forBillingPeriod(BigDecimal monthlyPrice, Subscription subscription) {
    if (!subscription.isAnnual()) {
        return monthlyPrice;
    }
    return monthlyPrice.multiply(MONTHS_PER_YEAR).multiply(ANNUAL_DISCOUNT_FACTOR);
}
```

**Commit 3: "Replace the plan switch with a sealed Plan type".** Replace Conditional with Polymorphism, done as: create the type, move one branch at a time while the `switch` delegates, remove the `switch` when it is empty.

```java
public sealed interface Plan {

    BigDecimal monthlyPrice();

    static Plan fromCode(String planCode, int seats) {
        return switch (planCode) {
            case "FREE" -> new Free();
            case "PRO" -> new Pro();
            case "TEAM" -> new Team(seats);
            default -> throw new IllegalArgumentException("Unknown plan: " + planCode);
        };
    }

    record Free() implements Plan {
        public BigDecimal monthlyPrice() { return BigDecimal.ZERO; }
    }

    record Pro() implements Plan {
        public BigDecimal monthlyPrice() { return new BigDecimal("99.00"); }
    }

    record Team(int seats) implements Plan {
        public BigDecimal monthlyPrice() { return new BigDecimal("49.00").multiply(BigDecimal.valueOf(seats)); }
    }
}

public BigDecimal price(Subscription subscription) {
    return forBillingPeriod(subscription.plan().monthlyPrice(), subscription);
}
```

`Subscription` keeps its `planCode` constructor and gains `plan()`, which calls `Plan.fromCode`, so the tests from commit 1 compile unchanged and stay green; retiring the string constructor is a later parallel change. One `switch` on the code survives, in `fromCode`, at the boundary where a string from the database becomes a type (item 1.4). That is the right place for it: the sibling `maxProjects` becomes a second method on `Plan`, a fourth plan is a new record plus one line in `fromCode`, and the compiler lists every method the new plan must implement.

## Pitfalls

- Mixing hats. A diff that renames twenty things and fixes one bug cannot be reviewed; the reviewer either reads every line as suspicious or misses the fix.
- "Pure" renames that change behaviour. Jackson derives JSON property names from getters, JPA derives column names from fields, JPQL in `@Query` strings references field names, and `@ConfigurationProperties` keys come from setters. Search for string usages before renaming anything a framework reflects on.
- Characterisation tests too fine-grained: pinning private helpers you intend to delete, instead of the public boundary you intend to keep.
- The clean rewrite. It discards the bug fixes nobody documented, ships nothing for months, and ends up with its own 400-line class.
- Debugging a failed step. Revert and take a smaller step; the discipline only works if reverting is cheap, which is why each step is a commit.
- Leaving a parallel change half done, so both the old and the new path live forever and every new caller picks one at random.
- Refactoring hot code without measuring. Extracted methods are almost always inlined by the JIT, but a changed data structure or an extra allocation in a tight loop is not free. Profile before and after when it matters.
- Treating green characterisation tests as proof of correctness. They prove sameness, not rightness.

## Check yourself

1. Why may a characterisation test assert a value you believe is wrong, and what exactly do you do with that belief, in which commit?
2. Name three mechanisms by which an IDE rename can change the observable behaviour of a Spring Boot service, and the check you run before renaming.
3. In the example, one `switch` on the plan code survives. Where, and why is that one acceptable when the others were not?
4. A refactoring step breaks a test you did not expect. What are your two options, and which does the small-steps discipline prefer, and why?

## Go deeper

- [Refactoring (Fowler)](https://refactoring.com/) · the book; the free [catalogue](https://refactoring.com/catalog/) lists the mechanics of every refactoring step by step.
- [refactoring.guru: Refactoring](https://refactoring.guru/refactoring) · the same catalogue with diagrams and Java examples, plus the smells that motivate each move.
- [Working Effectively with Legacy Code](https://www.oreilly.com/library/view/working-effectively-with/0131177052/) · Feathers on seams, characterisation tests and sprouting; still the only book on this (paid).
- [Martin Fowler: Legacy Seam](https://martinfowler.com/bliki/LegacySeam.html) · a two-minute definition of the seam concept with Feathers's own example.
- [Martin Fowler: Workflows of Refactoring](https://martinfowler.com/articles/workflowsOfRefactoring/) · when refactoring happens: preparatory, comprehension, litter-pickup, planned.
- [IntelliJ IDEA: Refactoring source code](https://www.jetbrains.com/help/idea/refactoring-source-code.html) · the full list of automated refactorings; learn the shortcuts for Extract Method, Inline, Rename and Change Signature.
- [Kent Beck: Tidy First?](https://www.oreilly.com/library/view/tidy-first/9781098151232/) · the smallest refactorings and when to make them relative to a behaviour change (paid).

---

Part of [Architecture & Craft](../README.md) · items 4.1, 4.2
