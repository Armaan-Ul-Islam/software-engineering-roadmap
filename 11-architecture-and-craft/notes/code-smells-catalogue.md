# Code smells and anti-patterns: a shared vocabulary for code review

> **In one sentence:** A code smell is a named surface symptom (a long parameter list, a class that envies another's data, a type code with a `switch` on it) that usually points at a deeper design problem and at a specific refactoring that fixes it; an anti-pattern is the same idea one level up, a recurring structure (god class, anemic domain model, service locator) that looked like a solution and became the problem.

**Why it matters:** "This feels wrong" is not a review comment anyone can act on. "Feature envy: `OrderService.total` reads six fields of `Order`, move it onto `Order`" is, and it takes the same ten seconds to write. Smells are also how you triage a 400-line class before you refactor it (item 4.2): you list the smells, each one names its refactoring, and the order of work falls out. Interviewers who hand you a snippet and ask "what would you change?" are asking you to recite this vocabulary.

## The idea

Kent Beck coined the term and Martin Fowler's *Refactoring* catalogued the smells; refactoring.guru groups them into five families. The families are more useful than the full list because they tell you what kind of problem you are looking at.

| Family | The symptom | Members you will meet weekly | The usual fix |
|---|---|---|---|
| Bloaters | something has grown too big to hold in your head | Long Method, Large Class, Long Parameter List, Primitive Obsession, Data Clumps | Extract Method or Class, Introduce Parameter Object, Replace Primitive with Object |
| Object-orientation abusers | the language's tools are misused | Switch Statements on a type code, Refused Bequest (a subclass that throws on inherited methods), Parallel Inheritance Hierarchies, Temporary Field | Replace Conditional with Polymorphism, Replace Inheritance with Delegation |
| Change preventers | one change touches many places | Divergent Change (one class changed for many reasons), Shotgun Surgery (one reason changes many classes) | Extract Class (divergent), Move Method and Inline Class (shotgun) |
| Dispensables | something adds nothing | Comments that narrate, Duplicate Code, Lazy Class, Dead Code, Speculative Generality, Data Class | Delete, Inline, Collapse Hierarchy |
| Couplers | classes know too much about each other | Feature Envy, Inappropriate Intimacy, Message Chains (`a.getB().getC().getD()`), Middle Man | Move Method, Hide Delegate, Remove Middle Man |

Three things to keep straight. A smell is a *heuristic*, not a rule: a `switch` over a sealed type at the boundary where a string becomes a type is correct (see item 4.1's example), and a long method that is a straight-line recipe with no branches can be the most readable version. A smell names a refactoring, so a review comment that names the smell should also name the move. And smells compound: Primitive Obsession produces Data Clumps (the same three parameters travelling together), which produce Long Parameter Lists, which produce Feature Envy in whatever method finally uses them.

**Anti-patterns.** The structural ones in item 3.5 are smells you can see on an architecture diagram:

- 1.1 **God class.** One class that knows everything and does everything, typically named `...Manager`, `...Service` or `...Util` and several thousand lines long. Every change touches it, every merge conflicts in it, and no test can start without it. Divergent Change at its limit.
- 1.2 **Anemic domain model.** Entities are bags of getters and setters and all behaviour lives in services that pull data out, compute, and push it back. It has the cost of objects (mapping, identity) without the benefit (behaviour next to the data it protects). The smells on the ground are Data Class plus Feature Envy in every service.
- 1.3 **Service locator.** Classes fetch their dependencies from a global registry (`ServiceLocator.get(OrderRepository.class)`, or `applicationContext.getBean(...)`) instead of receiving them. Dependencies become invisible in the constructor signature, so a test discovers them one `NullPointerException` at a time.
- 1.4 **Singletons as globals.** A `static getInstance()` is a global variable with a design pattern's name. It hides the dependency, prevents substitution in tests, and keeps state between tests. Spring-managed singletons are fine precisely because they are injected, not fetched.
- 1.5 **Primitive obsession.** `String customerEmail`, `int status`, `BigDecimal amount` with the currency in a separate field. Every rule about the value (format, range, which currency can be added to which) is re-checked, or forgotten, at each use. The fix is the value object (item 1.5).

## Example: five smells in twenty lines, and the version after the moves

The before. It computes the correct total, and every reviewer senses something is off:

```java
public class OrderService {

    public BigDecimal total(Order order) {
        BigDecimal total = BigDecimal.ZERO;
        for (int index = 0; index < order.getLinePrices().size(); index++) {
            total = total.add(order.getLinePrices().get(index)
                .multiply(BigDecimal.valueOf(order.getLineQuantities().get(index))));
        }
        if (order.getDiscountCode() != null && order.getDiscountCode().startsWith("WELCOME")) {
            total = total.multiply(new BigDecimal("0.90"));
        }
        if (order.getStatus() == 2 && order.getCustomerEmail().endsWith("@example.com")) {
            total = total.setScale(0, RoundingMode.DOWN);
        }
        return total.setScale(2, RoundingMode.HALF_UP);
    }
}
```

Name them, in review-comment form:

1. **Feature Envy.** `total` reads six getters of `Order` and none of its own fields. Move it to `Order`.
2. **Primitive Obsession.** Prices are `BigDecimal` with the currency somewhere else; the status is `2`; the discount code is a nullable `String`. Introduce `Money`, an `OrderStatus` enum, and a `DiscountCode` record.
3. **Data Clumps.** `linePrices` and `lineQuantities` are two parallel lists that only make sense together. Introduce `OrderLine`.
4. **Data Class.** `Order` is all getters and no behaviour; the anemic domain model in miniature.
5. **Magic values and a hidden rule.** `0.90`, `2` and `"@example.com"` carry meaning only the author knows. The email check is the worst of the five: it encodes "internal test customers get whole-unit invoices" as a string comparison, and nobody will find it when the domain changes.

The after. The same calculation, with each smell replaced by the type that names the concept:

```java
public record Money(BigDecimal amount, String currency) {
    public Money {
        amount = amount.setScale(2, RoundingMode.HALF_UP);
    }
    public Money plus(Money other) { return new Money(amount.add(other.amount), currency); }
    public Money times(int factor) { return new Money(amount.multiply(BigDecimal.valueOf(factor)), currency); }
    public Money times(BigDecimal factor) { return new Money(amount.multiply(factor), currency); }
    public Money roundedDownToWholeUnits() { return new Money(amount.setScale(0, RoundingMode.DOWN), currency); }
}

public record OrderLine(Money unitPrice, int quantity) {
    public Money total() { return unitPrice.times(quantity); }
}

public enum OrderStatus { DRAFT, PLACED, INVOICED }

public record DiscountCode(String value) {
    public boolean isWelcomeOffer() { return value.startsWith("WELCOME"); }
}

public record Order(List<OrderLine> lines, OrderStatus status, Optional<DiscountCode> discountCode, boolean roundsToWholeUnits) {

    private static final BigDecimal WELCOME_OFFER_FACTOR = new BigDecimal("0.90");

    public Money total() {
        Money subtotal = lines.stream().map(OrderLine::total).reduce(Money::plus).orElseThrow();
        Money discounted = discountCode.filter(DiscountCode::isWelcomeOffer)
            .map(code -> subtotal.times(WELCOME_OFFER_FACTOR))
            .orElse(subtotal);
        return status == OrderStatus.INVOICED && roundsToWholeUnits
            ? discounted.roundedDownToWholeUnits()
            : discounted;
    }
}
```

Both versions, run on two lines of 199.50 and 49.00 NOK, status invoiced, code `WELCOME10`, print `403.00` (the after prints `403.00 NOK`). The behaviour is identical; what changed is where a reader has to look. The email rule became an explicit `roundsToWholeUnits` fact on the order that whoever creates the order must decide, which is the point: a smell is often a business rule hiding in a string.

The `Money` record does nothing for a currency mismatch yet (`plus` keeps the left operand's currency). That is deliberate for the size of this note; a real `Money` checks in the compact constructor and in `plus` (item 1.5).

## Pitfalls

- Treating the catalogue as a lint rule set. "Method longer than 20 lines" catches straight-line recipes that are fine and misses the 15-line method with four responsibilities. Smells need a human to confirm the deeper problem exists.
- Fixing the smell without the refactoring. Splitting a god class into `OrderServiceA` and `OrderServiceB` along line count is Shotgun Surgery with extra steps; split by reason to change.
- Fighting Primitive Obsession at the edges only. A `Money` type that is unwrapped to `BigDecimal` at the first service method is a mapping cost with no benefit; the value object has to travel through the domain.
- Mistaking a data transfer object for a Data Class smell. A record at an HTTP or persistence boundary is supposed to be behaviour-free (item 3.4). The smell is a *domain* type with no behaviour.
- "Speculative Generality" used as an excuse to never introduce an interface. The smell is an abstraction with one implementation and no boundary; an interface at a real boundary (persistence, external system) with one implementation is dependency inversion (item 2.1).
- Smell comments without a move. "Feature Envy" alone is a verdict; "Feature Envy, move `total()` onto `Order`" is a review.
- Hunting Message Chains in fluent builders and streams. `stream().filter().map().toList()` is a chain by shape and not a smell; the smell is reaching through three objects' internals.

## Check yourself

1. A reviewer writes "this class is too big" on a 600-line `CustomerService`. Rewrite the comment using two named smells, and say what question decides whether to split it and along which line.
2. Why is Primitive Obsession the root of several other smells in the example? Trace the chain from `String customerEmail` to the hidden business rule.
3. `Collections.unmodifiableList(list).add(item)` throws `UnsupportedOperationException`. Which smell is that, and why did the JDK accept it?
4. Give one case where each of the following is not a smell: a `switch` on a type, a 40-line method, a class with only getters.

## Go deeper

- [refactoring.guru: Code Smells](https://refactoring.guru/refactoring/smells) · the catalogue by family, each smell with its signs, reasons and the refactorings that cure it.
- [Fowler: Anemic Domain Model](https://martinfowler.com/bliki/AnemicDomainModel.html) · why a domain model without behaviour is an anti-pattern and not "just a style".
- [Refactoring (Fowler)](https://refactoring.com/) · chapter 3 is the original smell list, written with Kent Beck; the rest of the book is the refactorings it names (paid).
- [Fowler: Value Object](https://martinfowler.com/bliki/ValueObject.html) · the cure for Primitive Obsession in two pages.
- [Robert C. Martin: Solid Relevance](https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html) · the principles that most smells violate, and the author's view of when they do not apply.

---

Part of [Architecture & Craft](../README.md) · items 1.6, 3.5
