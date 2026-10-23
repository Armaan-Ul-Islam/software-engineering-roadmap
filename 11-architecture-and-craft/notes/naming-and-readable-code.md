# Naming, functions and comments: code that reads like what it does

> **In one sentence:** A name is the cheapest documentation you will ever write and the first design decision you make, so spell out intent in full words, build functions that do one thing at one level of abstraction behind a small interface, and keep comments for what code cannot say: why, gotchas, and the decisions behind it.

**Why it matters:** Code is read many times more often than it is written, and most of a maintainer's day is spent working out what existing code does. A method called `process` with a `boolean flag` costs every reader a trip into its body, and the cost repeats on every change. In code review and in interviews, naming is the fastest signal of whether someone thinks about the next reader.

## The idea

**Naming.** Three rules cover most of it.

1. Intention-revealing: the name states what the thing is or does from the caller's point of view, not how it is implemented. `daysSinceLastPayment`, not `d`; `customers`, not `customerList`.
2. Full words: an abbreviation saves a few keystrokes once and costs a decode on every read. It also forks the vocabulary (`cust`, `cstmr`, `customer`), which breaks search. The only exceptions are abbreviations that are the domain's own words (`id`, `url`, `vat`).
3. One vocabulary per concept: if `fetch`, `get`, `load` and `retrieve` all mean the same thing, nobody can tell when they do not. Pick one word per meaning and distinct words for distinct meanings (`find` may return nothing, `get` must succeed). This is the ubiquitous language of item 6.1 applied to code.

Two consequences follow. A name's precision should grow with its scope: a two-line lambda parameter can be short, a public method cannot. And when you cannot name something, you have not understood it yet; renaming until the name is honest is the cheapest design tool you own.

**Functions.** A function should do one thing, where "one thing" means its body reads as steps at the same level of abstraction. A body that mixes `for` loops over bytes with words like `invoice` makes the reader switch altitude on every line. A `boolean` parameter that selects between two behaviours is two functions sharing a name.

How small? This is where the literature disagrees. *Clean Code* argues for very short functions (a handful of lines each). John Ousterhout's *A Philosophy of Software Design* argues this produces **shallow modules**: pieces whose interface is nearly as complex as their implementation, so the reader gains nothing by not reading the body and must now jump between five fragments to understand one idea. His measure is depth: the functionality a module hides divided by the interface it exposes. `Files.readString(path)` is deep; a `UserServiceHelper.doValidateInternal` that is only called once is shallow. The two authors debated this at length in 2025 (link below) and did not converge. The fair reading: split a function when the piece has a name a caller can trust without opening it, not because a line count says so.

**Comments.** Also contested. *Clean Code* calls a comment "a failure to express yourself in code"; Ousterhout calls comments an essential part of design, because code cannot state a rationale, a unit, or an invariant. Both agree that a comment restating the code is noise. In practice a comment earns its place when it says:

- why: a business-rule exception, a workaround, a performance trick that looks wrong;
- a gotcha: "do not reorder these two calls, the driver caches the first";
- the contract of a public API: units, what `null` or an empty result means, thread-safety, which exceptions are thrown and when.

A comment is a smell when it narrates the obvious, when it compensates for a bad name (`int d; // days overdue`), when it is a section banner, when it is commented-out code, or when nobody updated it and it now lies.

## Example: one method, before and after

Before (names changed from a real code base, structure intact):

```java
public List<String> getList(List<Order> list, int n) {
    List<String> res = new ArrayList<>();
    LocalDate now = LocalDate.now();
    for (Order o : list) {
        // skip if not invoiced
        if (o.getStatus() != 3) {
            continue;
        }
        LocalDate dt = o.getDate().plusDays(n);
        if (dt.isBefore(now)) {
            Customer c = o.getCust();
            String em = c.getEmail();
            if (em != null && !em.isBlank()) {
                if (!c.isFlag()) {
                    // de-dup
                    if (!res.contains(em.toLowerCase())) {
                        res.add(em.toLowerCase());
                    }
                }
            }
        }
    }
    return res;
}
```

After:

```java
public Set<EmailAddress> customersToRemindAboutOverduePayment(List<Order> orders, Period gracePeriod) {
    LocalDate today = LocalDate.now(clock);
    Set<EmailAddress> recipients = new LinkedHashSet<>();
    for (Order order : orders) {
        if (order.isOverdue(today, gracePeriod) && order.customer().acceptsPaymentReminders()) {
            order.customer().email().ifPresent(recipients::add);
        }
    }
    return recipients;
}
```

with the date rule moved next to the data it uses:

```java
public boolean isOverdue(LocalDate today, Period gracePeriod) {
    return status == OrderStatus.INVOICED && invoicedOn.plus(gracePeriod).isBefore(today);
}
```

Every change, and why:

1. `getList` became `customersToRemindAboutOverduePayment`. The old name said what type came back; the new one says what the result is for. `get` was also wrong: nothing is fetched, something is computed.
2. `list` became `orders` and `int n` became `Period gracePeriod`. The unit (days) now lives in the type instead of in the reader's memory, and `plusDays(n)` cannot be called with hours by mistake.
3. `List<String> res` became `Set<EmailAddress> recipients`. The type now carries two facts: no duplicates (so the `contains` check and the `// de-dup` comment disappear) and a valid, normalised address (so the null check, the blank check and the `toLowerCase` move into the value object once, see item 1.5).
4. `o.getStatus() != 3` became `order.isOverdue(today, gracePeriod)`. The magic number is now `OrderStatus.INVOICED` inside `Order`, the comment `// skip if not invoiced` is deleted because the code says it, and the date arithmetic sits beside the field it reads (Tell, Don't Ask, item 2.4).
5. `c.isFlag()` became `customer.acceptsPaymentReminders()`. A boolean is named for the question it answers, phrased positively so the negation vanishes.
6. `now` became `today`, computed from an injected `Clock`. `now` is an instant; this value is a date. The rename exposed the hidden dependency on the system clock, which is why the method was untestable.
7. `em` disappeared. `email()` returns `Optional<EmailAddress>`, and `ifPresent` replaces the null handling.

The body now reads at one altitude: for each order, if it is overdue and the customer wants reminders, collect the address. A caller can trust the name and never open it, which is exactly what a deep method is.

## Pitfalls

- Encoding the type or implementation in the name (`customerList`, `customerMap`, `cachedTotal`). The first refactoring turns the name into a lie.
- Agreeing on good names but not on one vocabulary. `Client`, `Customer` and `Account` for the same concept costs more than any single bad local variable.
- Extracting methods by line count. `validate`, `doValidate` and `validateInternal`, each called once, are shallow; the reader has to hold all three to understand one.
- Boolean flag parameters. `send(message, true)` tells the reader nothing at the call site; make two methods or pass an enum.
- Comments as deodorant. If you feel the need to explain what a variable holds, rename the variable.
- IDE-generated Javadoc (`/** Gets the customer. */`). It adds lines and no information, and it trains readers to skip all Javadoc, including the one paragraph that matters.
- Negated booleans (`isNotActive`, `disableCaching = false`). Every reader does a double negation in their head.

## Check yourself

1. You find `process(data, true)`. What two changes would you make, and why does the boolean argument alone tell you the method does two things?
2. Why is `Set<EmailAddress>` a better return type than `List<String>` even when every caller only iterates over the result? Name the code that disappears because of the type.
3. Ousterhout argues a method can be too short. State the test you would apply before extracting a method, and describe a case where extraction makes the code harder to read.
4. Which of these comments should stay, and why: `// increment counter`; `// The vendor's API returns 500 for roughly 1 in 200 calls under load; one retry is agreed in VEND-123`; `// TODO fix`; a Javadoc on a public `parse(String)` stating that blank input throws `IllegalArgumentException`?

## Go deeper

- [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php) · Ousterhout on deep modules, comments as design, and why "shorter is better" is not a design principle (paid).
- [John Ousterhout: A Philosophy of Software Design (talk)](https://www.youtube.com/watch?v=bmSAYlu0NcY) · the one-hour version, with the depth argument in the first twenty minutes.
- [Ousterhout and Martin: A Philosophy of Software Design vs Clean Code](https://github.com/johnousterhout/aposd-vs-clean-code) · the two authors argue method length and comments over the same code; read both sides before picking one.
- [Kevlin Henney: Seven Ineffective Coding Habits of Many Programmers](https://www.youtube.com/watch?v=ZsHMHukIlJY) · naming, noise and layout habits, with examples you will recognise.
- [Google Java Style Guide: Javadoc](https://google.github.io/styleguide/javaguide.html#s7-javadoc) · where documentation is required and, as importantly, where it is not.
- [Martin Fowler: Function Length](https://martinfowler.com/bliki/FunctionLength.html) · the "intention versus implementation" rule for when to extract.

---

Part of [Architecture & Craft](../README.md) · items 1.1, 1.2, 1.3
