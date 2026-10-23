# SOLID in practice: the problem each principle prevents, and when to leave it alone

> **In one sentence:** SOLID is five heuristics for keeping change cheap, each a response to a specific way Java code rots; apply one when you can name the change it would make cheaper, and skip it when the only benefit is compliance.

**Why it matters:** Interviewers ask for SOLID because it tests whether you can connect a principle to a concrete failure, not whether you can recite five words. In production the damage comes from both directions: the 3,000-line `OrderService` that breaks every principle, and the "interface for everything" codebase that applied them blindly and now needs six files touched to add a field.

## The idea

Robert C. Martin collected the five principles in the early 2000s. They are contested. Dan North's CUPID argues they are too abstract to guide a decision; John Ousterhout's "deep modules" (item 1.2) says the usual reading of the first one produces too many tiny classes; Martin's own "Solid Relevance" defends them as still describing real failure modes. The fair position is in the table: each principle names a genuine way code becomes expensive to change, and each has a cost when applied without that change in view.

| Principle | Plain statement | The Java problem it prevents | Applied blindly, it makes code worse when... |
|---|---|---|---|
| Single Responsibility | Keep together what changes for the same reason; separate what changes for different reasons. | The class every team edits, merge conflicts, tests that need the whole world to start. | You count methods instead of reasons to change and end up with dozens of shallow classes. |
| Open/Closed | Add a behaviour by adding code, not by editing code that already works. | The `switch` on a type code repeated in six places; each new type touches all six and you miss one. | You build extension points for changes that never come. Sealed types make "modification" compiler-checked and cheap. |
| Liskov Substitution | A subtype must work wherever the supertype is promised, with no surprises. | Overrides that throw `UnsupportedOperationException`, tighten preconditions, or return `null` where the parent never does. | Rarely. The caveat is that the JDK itself trades it away (`List`'s optional operations); know when you are making the same trade. |
| Interface Segregation | Clients depend only on the methods they use. | Fat interfaces: every fake implements thirty methods and a change to one ripples to all implementers. | You make one interface per method and nobody can find anything. Split by client role, not by method count. |
| Dependency Inversion | Policy owns the abstraction; details depend on it, not the reverse. | Business logic importing JPA, JDBC or an HTTP client, so it cannot run without infrastructure. | You add `FooService` plus `FooServiceImpl` for everything. One implementation and no boundary means no benefit. |

## Example: one small case per principle

**Single Responsibility.** Three reasons to change in one class: tax rules, PDF layout, mail provider.

```java
public class InvoiceService {
    public Invoice create(Order order) { /* pricing and tax rules */ }
    public byte[] renderPdf(Invoice invoice) { /* layout, PDF library */ }
    public void email(Invoice invoice) { /* SMTP, templates */ }
}
```

Split into `InvoiceCalculator`, `InvoicePdfRenderer` and `InvoiceMailer`, with a thin application service that calls the three. The caveat: do not go on to split `InvoiceCalculator` into `TaxCalculator`, `DiscountCalculator` and `RoundingPolicy` unless those really change independently. The unit is a reason to change, not a method.

**Open/Closed.** The type code `switch` appears in `cost()`, `label()` and `estimatedDelivery()`. Adding `DRONE` means finding all three, and the one you miss falls into a `default` branch at runtime. Two fixes, with different trade-offs:

```java
// Fix 1: open set of types, closed set of operations. Adding Drone is a new class, nothing else changes.
public interface ShippingMethod {
    Money cost(Order order);
    String label();
    Duration estimatedDelivery();
}

// Fix 2: closed set of types, open set of operations. Adding Drone breaks every switch at compile time.
public sealed interface ShippingMethod permits Standard, Express, Pickup {}

static Money cost(ShippingMethod method, Order order) {
    return switch (method) {
        case Standard standard -> order.weight().isAbove(Weight.kilograms(5)) ? Money.of("79.00", "NOK") : Money.of("49.00", "NOK");
        case Express express -> Money.of("149.00", "NOK");
        case Pickup pickup -> Money.zero(Currency.getInstance("NOK"));
    };
}
```

Fix 2 "violates" Open/Closed on purpose: you edit existing switches, but the compiler lists every one of them. Pick Fix 1 when new types are the frequent change, Fix 2 when new operations are. Neither is right in advance, and building either for a single `if` is premature.

**Liskov Substitution.**

```java
public class ReadOnlyAccount extends Account {
    @Override
    public void withdraw(Money amount) {
        throw new UnsupportedOperationException("read-only");
    }
}
```

Every method that accepts an `Account` now carries a hidden landmine, and no test on `Account` finds it. Do not inherit for a type that cannot keep the parent's promises: make `withdraw` available only on a type that supports it (a `Withdrawable` interface or a sealed hierarchy). Note that `Collections.unmodifiableList(list).add(item)` throws in exactly this way; the JDK accepted the violation to keep one `List` interface, and documents it. If you make that trade, document it as loudly.

**Interface Segregation.**

```java
public interface OrderRepository {
    Order save(Order order);
    Optional<Order> findById(OrderId id);
    List<Order> findOverdue(LocalDate today);
    void archiveOlderThan(LocalDate cutoff);
    byte[] exportCsv(YearMonth month);
}
```

The reminder job needs `findOverdue`, but its test fake must implement five methods, and a change to the CSV export breaks the reminder test. Split by client: `OrderRepository` (save, find), `OverdueOrders` (the job's view), `OrderArchive`. The caveat: Spring Data's `JpaRepository` is a fat interface and is fine, because nobody implements it by hand. Interface Segregation bites when humans write the implementations and fakes.

**Dependency Inversion.**

```java
@Service
public class PlaceOrderService {
    private final JpaOrderRepository jpaOrderRepository;   // Spring Data and JPA types inside the use case
    private final RestClient paymentClient;                // HTTP inside the use case
}
```

Declare `OrderRepository` and `PaymentGateway` as interfaces in the use case's own package and let adapters implement them (item 7.2). The use case is now testable with fakes and the payment provider can change without touching it. The caveat: an interface in the same package with one implementation named `...Impl` is not inversion, it is ceremony. Inversion pays at a boundary (persistence, external systems, `Clock`, randomness), not between two classes in the same module.

## Pitfalls

- Citing a principle in review ("violates SRP") without naming the change it would make cheaper. If you cannot name it, the comment is not actionable.
- `Impl` interfaces everywhere. The interface mirrors the class, every refactoring touches two files, and IDE navigation always lands on the wrong one.
- Inheritance for code reuse. Most Liskov violations begin as "it already has most of what I need". Prefer composition (item 2.4).
- Confusing Dependency Inversion with dependency injection. Spring injecting a concrete class is injection without inversion; inversion is about which side owns the interface.
- Splitting classes until none of them does anything. An anemic domain model (item 3.5) is Single Responsibility misapplied: the behaviour ends up in a service that has every responsibility.
- Framework-shaped Open/Closed. A generic `Handler<T, R>` registry inside a five-class application is an extension point for a future that is not coming.

## Check yourself

1. Name one concrete change that becomes cheaper after splitting `InvoiceService`, and one further split that would make the code worse. What distinguishes them?
2. Sealed types with exhaustive `switch` edit existing code when a type is added. When is that the better choice, and what does the compiler give you in exchange for giving up Open/Closed?
3. Is `Collections.unmodifiableList(list).add(item)` throwing an LSP violation? Sketch a strictly substitutable alternative and say what it would cost the JDK's users.
4. `OrderService` depends on `OrderValidator`; both live in the same package and have one implementation each. Does Dependency Inversion call for an `OrderValidator` interface? Why or why not?

## Go deeper

- [Robert C. Martin: Solid Relevance](https://blog.cleancoder.com/uncle-bob/2020/10/18/Solid-Relevance.html) · the author's defence, written in response to the "SOLID is outdated" argument.
- [Dan North: CUPID, for joyful coding](https://dannorth.net/cupid-for-joyful-coding/) · the best-known critique, with an alternative set of properties.
- [Baeldung: SOLID Principles](https://www.baeldung.com/solid-principles) · a plain Java walkthrough of each principle, if you want the textbook version first.
- [Martin Fowler: InterfaceImplementationPair](https://martinfowler.com/bliki/InterfaceImplementationPair.html) · why an interface with exactly one implementation is usually noise.
- [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php) · Ousterhout's "deep modules", the strongest counterweight to a method-counting reading of Single Responsibility (paid).

---

Part of [Architecture & Craft](../README.md) · item 2.1
