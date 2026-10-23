# Coupling, cohesion, connascence, and the wrong abstraction

> **In one sentence:** Coupling is how much one piece must know about another, cohesion is how much a piece's parts belong together, connascence gives you precise words for the kinds of coupling and which are worse, dependency direction decides who pays when something changes, and when a shared helper starts growing flags to serve its callers, duplication was the cheaper option all along.

**Why it matters:** Nearly every "this one-day change took a week" story is a coupling story: a renamed field that touched forty files, a helper nobody dares change because of its five boolean parameters. A review comment that says "too coupled" is not actionable; one that says "connascence of position across two modules, convert to a parameter object" is. And the most expensive coupling in most codebases was introduced in the name of avoiding duplication.

## The idea

**Coupling and cohesion.** Two modules are coupled to the degree that changing one forces a change in the other. A module is cohesive to the degree that its parts work on the same thing: methods that read and write the same fields belong together; eighty unrelated statics in `StringUtils` do not (that is coincidental cohesion, the weakest kind). A class named `Manager`, `Helper` or `Utils` has announced that it has no cohesion. The goal is low coupling between modules and high cohesion within them, and the two usually move together: putting behaviour next to the data it uses removes the need to reach across.

**Connascence.** Meilir Page-Jones's vocabulary for coupling: two elements are connascent if changing one requires changing the other to keep the program correct. The forms, weakest to strongest:

| Form | The two sides must agree on... | Java example | Caught by the compiler? |
|---|---|---|---|
| Name | a name | `orderRepository.save(order)` | yes |
| Type | a type | a parameter declared `Money` | yes |
| Meaning | what a value means | `status == 3`, `return -1` for "not found", `null` meaning "all customers" | no |
| Position | the order of values | `new Address("Oslo", "Norway", "0150")` | no, when types coincide |
| Algorithm | a shared algorithm | producer and consumer both compute the same checksum or date format | no |
| Execution order | the order of calls | `connection.open()` must precede `send()` | no |
| Timing | timing | a test that sleeps 100 ms before asserting | no |
| Value | several values changing together | `MINIMUM_AGE` defined in the domain and again in the SQL check constraint | no |
| Identity | the same object instance | two components that must share one `EntityManager` | no |

Three properties decide how bad an instance is: **strength** (lower in the table is worse), **degree** (how many places share it), and **locality** (strong connascence inside one class is fine; across modules or services it is a liability). The rules follow: convert stronger forms into weaker ones (position into name with a parameter object or builder; meaning into name with an enum or a constant; a repeated algorithm into one function both sides call), reduce the degree, and keep whatever strong connascence remains local.

**Dependency direction.** Arrows should point from the volatile to the stable: from adapters to use cases, from use cases to domain rules. Domain rules change only for business reasons; frameworks, databases and wire formats change for everyone else's reasons. When a stable module needs a volatile one (the order rules need persistence), do not import it. Declare an interface in the stable module and let the volatile one implement it. That is dependency inversion (item 2.1), and the test is simple: which package owns the interface? If `OrderRepository` lives next to `Order`, the domain owns it; if it lives next to the JPA entity, it is just a wrapper.

**DRY, and the wrong abstraction.** DRY is about knowledge, not text: one business rule should have one home. Two methods that look alike but encode different rules (the invoice total and the shipping-weight total both sum lines) are not duplicates; they rhyme, and merging them couples two things that will diverge. Sandi Metz describes how the wrong abstraction grows:

1. Programmer A sees two similar snippets and extracts a shared method.
2. Programmer B needs almost the same thing, adds a parameter and a branch.
3. Programmers C and D repeat step 2.
4. The method now has flags and branches nobody fully understands, and everyone is afraid of it. Because effort was spent building it, nobody considers removing it (sunk cost).

The repair is counter-intuitive: put the duplication back. Inline the abstraction into every caller, delete at each site the branches that site never used, and only then look for the shared concept that remains, if any. YAGNI is the preventive version: do not write the abstraction for the second caller before the second caller exists.

## Example: the helper that grew flags

```java
public static String formatAddress(Address address, boolean includeCountry, boolean upperCase,
                                   boolean singleLine, boolean forLabel) {
    String separator = singleLine ? ", " : "\n";
    StringBuilder text = new StringBuilder();
    if (forLabel && address.recipient() != null) {
        text.append(address.recipient()).append(separator);
    }
    text.append(address.street()).append(separator);
    text.append(address.postalCode()).append(' ').append(address.city());
    if (includeCountry && (!forLabel || !address.country().equals("NO"))) {
        text.append(separator).append(address.country());
    }
    String result = text.toString();
    return upperCase ? result.toUpperCase(Locale.ROOT) : result;
}
```

The call sites read `formatAddress(address, true, false, true, false)` and `formatAddress(address, true, true, false, true)`. That is connascence of position and of meaning, with a degree equal to the number of callers, and the `forLabel && !country.equals("NO")` branch shows two concepts fighting inside one method. There are exactly two callers in the codebase: the invoice header and the shipping label. Inlined and cleaned, they become:

```java
public final class InvoiceAddressLine {
    public static String of(Address address) {
        return String.join(", ", address.street(), address.postalLine(), address.country());
    }
}

public final class ShippingLabel {
    public static String of(Recipient recipient, Address address) {
        List<String> lines = new ArrayList<>();
        lines.add(recipient.name());
        lines.add(address.street());
        lines.add(address.postalLine());
        if (!address.isDomestic()) {
            lines.add(address.country());
        }
        return String.join("\n", lines).toUpperCase(Locale.ROOT);
    }
}
```

Each is readable without a legend. The nullable `recipient` disappeared, because a label always has one and an invoice line never does; that fact was hidden inside a flag before. One piece of genuine shared knowledge survived, how a postal line is written, and it moved onto `Address` as `postalLine()`, next to the data it uses. `isDomestic()` replaced the magic `"NO"`, converting connascence of meaning into connascence of name. The lines of code went up slightly; the number of things a reader must hold in their head went down a lot.

## Pitfalls

- Measuring coupling by counting imports. The question is what breaks when something changes, not how many `import` lines there are.
- DRY applied to text. Merging similar code from two bounded contexts (item 6.1) ties together concepts that need to evolve apart.
- Boolean parameters as extension points. Each one doubles the paths through the method and is a new connascence of meaning at every call site.
- Shared "common" libraries holding domain classes across services. That is connascence of type and algorithm at the widest possible locality; a change needs a coordinated deployment.
- Execution-order APIs: `initialise()` then `start()` then `process()`. Make the constructor do the work, or have `start()` return a type on which `process()` exists, so the wrong order does not compile.
- `null` carrying meaning: "not set" in one method, "all" in another, "unknown" in a third. Use an `Optional` return, an enum, or a sealed type.
- Keeping the flagged helper because "it is already there". Sunk cost is not a design argument.

## Check yourself

1. Name the connascence in `createUser("Smith", "John", "jsmith@example.com")` and two ways to weaken it.
2. Why is strong connascence acceptable inside one class but a liability across modules? Which property of connascence is that, and how does it change what you refactor first?
3. Two services both compute "order total = sum of line totals plus VAT". Is that duplicated knowledge or coincidence? What question decides, and what goes wrong if you answer it incorrectly in each direction?
4. `formatAddress` has five callers across three modules. Describe the steps to get rid of it safely without a big-bang rewrite, and what you commit after each step.

## Go deeper

- [Sandi Metz: The Wrong Abstraction](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction) · the essay this note's example is built on; short, and the sunk-cost argument is the part to remember.
- [Connascence](https://connascence.io/) · each form defined with examples, plus the strength, degree and locality rules.
- [Martin Fowler: Yagni](https://martinfowler.com/bliki/Yagni.html) · the cost of presumptive features, which is also the cost of presumptive abstractions.
- [Parnas: On the Criteria To Be Used in Decomposing Systems into Modules](https://www.win.tue.nl/~wstomv/edu/2ip30/references/criteria_for_modularization.pdf) · the 1972 paper that defined information hiding; the modularisation it argues against is still the one most teams start with.
- [Sandi Metz: All the Little Things](https://www.youtube.com/watch?v=8bZh5LMaSmE) · a live refactoring of a conditional-heavy method, including the moment duplication is deliberately reintroduced.

---

Part of [Architecture & Craft](../README.md) · items 2.2, 2.3
