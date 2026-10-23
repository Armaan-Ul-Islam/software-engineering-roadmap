# Records, sealed types and pattern matching

> **In one sentence:** Records are transparent, immutable carriers of data; sealed interfaces declare a closed set of alternatives; and pattern matching in `switch` lets the compiler prove that you handled every alternative, which together give Java algebraic data types.

**Why it matters:** The old way to model "an event is one of these four things" was an enum field plus nullable fields that only apply to some kinds, or a class hierarchy with `instanceof` chains and a `default` branch. Both let a new kind slip through silently. With a sealed interface and an exhaustive `switch`, adding a fifth kind is a compile error in every consumer that forgot it. Since Java 21 this is standard Java, and it has become the marker of "modern Java" in code reviews and interviews.

## The idea

**Records** (Java 16, JEP 395). `record Money(BigDecimal amount, String currency)` declares two components. The compiler generates private final fields, a canonical constructor, accessors named after the components (`amount()`, not `getAmount()`), and `equals`, `hashCode` and `toString` over all components. A record is implicitly `final`, cannot extend a class (it extends `java.lang.Record`), may implement interfaces, and may not declare instance fields other than its components. A **compact constructor**, written `Money { ... }` without a parameter list, runs before the fields are assigned: it is the place for validation and normalisation, and it may reassign the parameters but not the fields. Immutability is shallow; a `List` or array component still needs a defensive copy (see item 1.5).

**Sealed types** (Java 17, JEP 409). `sealed interface PaymentEvent permits PaymentAuthorised, PaymentCaptured, ...` restricts which types may implement it. Each permitted subtype must be `final` (records are), `sealed` itself, or `non-sealed` to reopen that branch. The `permits` clause may be omitted when all subtypes are in the same source file. Because the compiler knows the complete set of subtypes, it can check a `switch` over the interface for exhaustiveness.

**Pattern matching for `instanceof`** (Java 16). `if (event instanceof PaymentRefunded refunded)` tests and binds in one step, and the binding is in scope wherever the compiler can prove the test passed, including after an early return from `if (!(event instanceof PaymentRefunded refunded)) return;`.

**Pattern matching for `switch`** (Java 21, JEP 441). Cases can be type patterns with optional guards (`case PaymentRefunded refunded when refunded.amount().signum() == 0 ->`), and `case null` is allowed. A `switch` over a sealed type with no `default` must cover every permitted subtype or it does not compile. More specific cases must come before more general ones; a case that can never match because an earlier one covers it is an error ("dominated").

**Record patterns** (Java 21, JEP 440). A case can destructure a record, nested as deep as you like: `case PaymentCaptured(String paymentId, Money(BigDecimal amount, String currency))`. `var` is allowed for component types. Java 22 added the unnamed pattern `_` for components you do not use (`case PaymentCaptured(_, Money(var amount, _))`); in Java 21 you still have to name them. Primitive types in patterns are still a preview feature in Java 25 (JEP 507), so match on reference types.

**Algebraic data types.** A sealed interface is a *sum* type (one of these), a record is a *product* type (all of these). Modelling the domain this way makes illegal states unrepresentable: `PaymentRefunded` has a `reason`, `PaymentFailed` has an `errorCode`, and neither has a nullable field that only means something for the other kind.

## Example: a `PaymentEvent` hierarchy and an exhaustive switch

```java
import java.math.BigDecimal;
import java.util.Objects;

record Money(BigDecimal amount, String currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }
}

sealed interface PaymentEvent permits PaymentAuthorised, PaymentCaptured, PaymentRefunded, PaymentFailed {
    String paymentId();
}

record PaymentAuthorised(String paymentId, Money amount) implements PaymentEvent {}

record PaymentCaptured(String paymentId, Money amount) implements PaymentEvent {}

record PaymentRefunded(String paymentId, Money amount, String reason) implements PaymentEvent {
    PaymentRefunded {
        if (reason.isBlank()) {
            throw new IllegalArgumentException("a refund needs a reason");
        }
    }
}

record PaymentFailed(String paymentId, String errorCode) implements PaymentEvent {}

public class Ledger {

    static BigDecimal ledgerDelta(PaymentEvent event) {
        return switch (event) {
            case PaymentAuthorised authorised -> BigDecimal.ZERO;
            case PaymentCaptured(String paymentId, Money(BigDecimal amount, String currency)) -> amount;
            case PaymentRefunded(var paymentId, var money, var reason) -> money.amount().negate();
            case PaymentFailed failed -> BigDecimal.ZERO;
        };
    }

    static String describe(PaymentEvent event) {
        if (event instanceof PaymentRefunded(var paymentId, Money(var amount, var currency), var reason)
                && amount.signum() > 0) {
            return paymentId + " refunded " + amount + " " + currency + " because " + reason;
        }
        return event.paymentId() + " " + event.getClass().getSimpleName();
    }
}
```

Feeding one event of each kind through `describe(event) + " -> " + ledgerDelta(event)` prints:

```text
p-1 PaymentAuthorised -> 0
p-1 PaymentCaptured -> 10.00
p-1 refunded 4.00 EUR because damaged -> -4.00
p-2 PaymentFailed -> 0
```

The record `toString` is readable for free: `PaymentCaptured[paymentId=p-1, amount=Money[amount=10.00, currency=EUR]]`.

## Example: the compiler catches the missing case

Delete the `PaymentFailed` case from `ledgerDelta` and compile:

```text
Ledger.java:31: error: the switch expression does not cover all possible input values
        return switch (event) {
               ^
```

Add a new permitted type `PaymentDisputed` to the interface and you get the same error in every `switch` that does not handle it, which is exactly the point. Put the guarded case after the unguarded one for the same type and you get the dominance error instead:

```text
error: this case label is dominated by a preceding case label
            case PaymentCaptured captured when captured.amount().signum() == 0 -> "zero capture";
                 ^
```

## Pitfalls

- A `default` branch on a sealed switch. It compiles today and silently handles the type you add next year. Leave it out; the exhaustiveness check is the feature.
- Mutable components. `record Invoice(List<Line> lines)` is only as immutable as the list passed in; copy with `List.copyOf` in the compact constructor. Arrays in records compare by reference, so `equals` is almost never what you want.
- Records as JPA entities. Entities need a no-argument constructor, mutable state and proxying; records cannot provide any of it. Records are excellent for DTOs, projections and value objects embedded in entities.
- Sealed hierarchies across modules. All permitted subtypes must live in the same module, or in the same package if you are not using modules. A sealed type is for a set you control, not for plugin points.
- `switch (null)`. A pattern switch without `case null` still throws `NullPointerException` on a null selector, as every switch always has.
- Compact constructors that assign fields. `this.amount = amount.setScale(2)` does not compile; reassign the parameter (`amount = amount.setScale(2)`) and the generated assignment picks it up.
- Over-destructuring. A nested record pattern three levels deep with six bindings is harder to read than a type pattern plus two accessor calls. Destructure when you use most of the components.

## Check yourself

1. You add `PaymentDisputed` to `PaymentEvent`. Which switches fail to compile, and which keep compiling and misbehave?
2. Why can a compact constructor reassign the parameter `amount` but not the field `this.amount`?
3. When is `non-sealed` the right choice for a permitted subtype, and what do you give up for that branch?
4. Rewrite `if (event instanceof PaymentCaptured captured && captured.amount().amount().signum() == 0)` as a `switch` case with a guard. Why must it come before `case PaymentCaptured captured`?

## Go deeper

- [dev.java: Pattern Matching](https://dev.java/learn/language/fp/pattern-matching/) · the official tutorial covering `instanceof`, `switch` and record patterns together.
- [dev.java: Using Record to Model Immutable Data](https://dev.java/learn/records/) · compact constructors, what the compiler generates, and the restrictions.
- [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441) · exhaustiveness and dominance rules with examples; the "Motivation" section alone is worth reading.
- [JEP 409: Sealed Classes](https://openjdk.org/jeps/409) and [JEP 440: Record Patterns](https://openjdk.org/jeps/440) · the specifications for the other two pieces, both short.
- [nipafx](https://nipafx.dev/) · Nicolai Parlog's articles on data-oriented programming in Java, which is the name for this style.

---

Part of [Java](../README.md) · item 1.6
