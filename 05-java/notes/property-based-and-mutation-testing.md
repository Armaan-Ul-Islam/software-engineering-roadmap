# Property-based testing, mutation testing and what coverage does not tell you

> **In one sentence:** Line coverage tells you which code your tests executed, mutation testing (PIT) tells you which code your tests actually check by breaking it and seeing whether a test fails, and property-based testing (jqwik) finds the inputs you did not think of by generating hundreds of them and shrinking any failure to the smallest case.

**Why it matters:** A team can hit 90% coverage with tests that assert nothing meaningful, and the number on the dashboard will say the code is safe. Mutation testing exposes exactly those tests. Property-based testing attacks the other weakness of example tests: the examples were chosen by the same person who wrote the bug, so they share its blind spots. Both techniques are cheap to add to a Maven build and are what separates "we have tests" from "we have tests we trust".

## The idea

**Coverage** (JaCoCo) instruments bytecode and records which lines and branches ran during the test phase. It answers one question: what did the tests not even execute? That is useful for finding untested modules and dead code. It says nothing about assertions. `assertNotNull(result)` after calling every method of a class gives 100% coverage and catches almost nothing; a coverage gate therefore rewards tests that execute code, not tests that check it.

**Mutation testing** (PIT, `pitest`) makes small changes to the bytecode of the class under test, one at a time: negate a conditional, change `<` to `<=`, replace a return value with `null` or `""`, remove a method call, swap `+` for `-`. Each mutant is run against the tests that cover that line (PIT uses coverage data to pick them, so it is much faster than running everything). If a test fails, the mutant is *killed*; if all tests still pass, it *survived*, and PIT shows you the line and the change that no test noticed. The *mutation score* (killed divided by generated) and *test strength* (killed divided by covered) are the numbers to track, and the list of survivors is the actionable output.

**Property-based testing** replaces "for input 100.00 and 10%, expect 90.00" with "for any price and any percent between 0 and 100, the discounted price is between 0 and the price". The framework generates inputs (jqwik defaults to 1,000 tries per property, mixing in edge cases such as 0, -1, `Integer.MAX_VALUE`, empty strings and strings with surrogate pairs), runs the property, and when one fails, *shrinks* the input towards the simplest failing case before reporting it, together with the seed to reproduce the run. The hard part is finding properties. The patterns that work:

1. Invariants: the result is never negative, the list is always sorted, the total equals the sum of the lines.
2. Round trips: `parse(format(x)) == x`, `decode(encode(x)) == x`, `fromJson(toJson(x)) == x`.
3. Idempotence: `normalise(normalise(x)) == normalise(x)`.
4. Comparison with a simpler model: the clever implementation agrees with the obvious slow one.
5. Commutativity or order independence: adding items in any order gives the same cart.

The three fit together: coverage finds what no test touches, mutation testing finds what the tests do not check, and properties give you tests that check a lot of inputs with little code, which is what kills mutants.

## Example

The class under test:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class Discount {

    public static BigDecimal apply(BigDecimal price, int percent) {
        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException("percent must be between 0 and 100");
        }
        BigDecimal factor = BigDecimal.valueOf(100 - percent).movePointLeft(2);
        return price.multiply(factor).setScale(2, RoundingMode.HALF_UP);
    }

    public static String normaliseSku(String raw) {
        String trimmed = raw.strip().toUpperCase();
        if (trimmed.length() > 12) {
            return trimmed.substring(0, 12);
        }
        return trimmed;
    }
}
```

Two example tests and two properties (jqwik 1.9 with `net.jqwik:jqwik` in test scope; it runs on the JUnit platform next to Jupiter tests):

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;
import net.jqwik.api.constraints.IntRange;
import net.jqwik.api.constraints.StringLength;

class DiscountPropertiesTest {

    @Property
    boolean discountNeverExceedsPrice(@ForAll("prices") BigDecimal price, @ForAll @IntRange(min = 0, max = 100) int percent) {
        BigDecimal discounted = Discount.apply(price, percent);
        return discounted.compareTo(price) <= 0 && discounted.signum() >= 0;
    }

    @Property
    void normaliseIsIdempotent(@ForAll @StringLength(max = 40) String raw) {
        String once = Discount.normaliseSku(raw);
        assertThat(Discount.normaliseSku(once)).isEqualTo(once);
    }

    @Provide
    Arbitrary<BigDecimal> prices() {
        return Arbitraries.bigDecimals().between(BigDecimal.ZERO, new BigDecimal("100000")).ofScale(2);
    }
}
```

```text
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0 -- in DiscountExampleTest
tries = 1000                  | # of calls to property
checks = 1000                 | # of not rejected calls
tries = 1000                  | # of calls to property
checks = 1000                 | # of not rejected calls
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0 -- in DiscountPropertiesTest
```

A property that is wrong about rounding, to show shrinking:

```java
@Property
boolean discountIsExactlyPercentOfPrice(@ForAll("prices") BigDecimal price, @ForAll @IntRange(min = 0, max = 100) int percent) {
    BigDecimal discount = price.subtract(Discount.apply(price, percent));
    BigDecimal expected = price.multiply(BigDecimal.valueOf(percent)).movePointLeft(2);
    return discount.compareTo(expected) == 0;
}
```

```text
seed = -5938005128514596584   | random seed to reproduce generated values

Shrunk Sample (2 steps)
-----------------------
  arg0: 0.01
  arg1: 1

Original Sample
---------------
  arg0: 1029.48
  arg1: 72

Property [DiscountRoundTripTest:discountIsExactlyPercentOfPrice] failed with sample {0=0.01, 1=1}
```

The original failure was `1029.48` at 72%, which tells you nothing. The shrunk one, one øre at one percent, makes the cause obvious: the exact discount is `0.0001` and the result is rounded to two decimals. Whether that is a bug in the code or in the property is now a product question, which is the right place for it.

JaCoCo and PIT on the same code, with only the example tests and the first two properties:

```text
Discount: lines covered 7, missed 1; branches covered 4, missed 2

>> Line Coverage (for mutated classes only): 7/10 (70%)
>> Generated 10 mutations Killed 8 (80%)
>> Mutations with no coverage 0. Test strength 80%
normaliseSku : changed conditional boundary → SURVIVED
normaliseSku : replaced return value with "" for Discount::normaliseSku → SURVIVED
```

Coverage says the exception branch never ran (the property's `@IntRange` keeps inputs valid, the example used 10), which is fair. The two survivors say something coverage cannot: the truncation branch *was* executed, by the idempotence property, but no test would notice if `> 12` became `>= 12` or if the truncated result were replaced with an empty string. Idempotence holds for both mutants. The missing test is "a 13-character SKU becomes its first 12 characters", one example, and it kills both.

The Maven side: `jacoco-maven-plugin` with `prepare-agent` and `report` executions, and `pitest-maven` with the `pitest-junit5-plugin` dependency; `mvn test` produces `target/site/jacoco/index.html`, `mvn org.pitest:pitest-maven:mutationCoverage` produces `target/pit-reports/index.html`. PIT's `withHistory` and `targetClasses` options keep it fast enough to run on every pull request for the changed classes.

## Pitfalls

- A coverage gate as the definition of done. It is gamed within a sprint. Use coverage to find untested areas, mutation score to judge test quality, and neither as a target number.
- Properties that restate the implementation. `apply(price, p) == price * (100 - p) / 100` is the code again, and will pass with the same bug. Prefer invariants, round trips and a simpler model.
- Unbounded generators. `@ForAll String` includes empty, blank, 1,000-character and surrogate-pair strings; `@ForAll int` includes `MIN_VALUE`. That is the point, but constrain with `@IntRange`, `@StringLength`, `@AlphaChars` or a `@Provide` method when the domain really excludes them, and let the property document the exclusion.
- Ignoring the seed. A failing property prints its seed; put it in the bug report and use `@Property(seed = "...")` to reproduce while fixing, then remove it so the test keeps exploring.
- Flaky properties from shared state. A property runs a thousand times in one test instance; a static counter, a shared `Random` or a mutable fixture makes the runs depend on each other.
- Running PIT on the whole code base nightly and never reading the report. Scope it to changed classes in CI, and read the survivors like code review comments: each one is either a missing assertion or dead code.
- Equivalent mutants. Some survivors cannot be killed because the mutation does not change behaviour (`i++` versus `++i` as a statement). Mark them, do not chase them.
- Killing mutants with assertions on internals. The goal is a test that would catch a real regression, not one that pins the current implementation; if the only way to kill a mutant is to assert a private detail, the mutant is probably equivalent or the code has a seam problem.

## Check yourself

1. A class has 100% line coverage and a mutation score of 35%. Describe what the tests probably look like, and what one change to each test would raise the score.
2. Write three properties for `List<Integer> sort(List<Integer> input)` that do not re-implement sorting.
3. Why does the idempotence property fail to kill the `> 12` to `>= 12` mutant, and what does that say about choosing properties?
4. jqwik reports a failure with "Shrunk Sample" and "Original Sample". Why is the shrunk sample the one to debug, and when can shrinking make the report misleading?

## Go deeper

- [jqwik](https://jqwik.net/) · the user guide covers generators, constraints, shrinking, stateful testing and the lifecycle; read "How to specify properties" first.
- [PIT](https://pitest.org/) · the mutator list explains every change PIT can make, and the quick start has the Maven configuration.
- [JaCoCo](https://www.jacoco.org/jacoco/) · the Maven plugin documentation, including the `check` goal for thresholds if you decide you want them.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) · for how jqwik, Jupiter and PIT share the JUnit platform.

---

Part of [Java](../README.md) · item 7.5
