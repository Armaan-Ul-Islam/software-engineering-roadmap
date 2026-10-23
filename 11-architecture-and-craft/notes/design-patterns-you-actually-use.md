# Design patterns you actually use in Java and Spring

> **In one sentence:** Most Gang of Four patterns you meet daily are already in the JDK and Spring under other names; knowing where they live tells you when to reach for one, and knowing the modern equivalent (a lambda, a `Map` of handlers, a sealed type with a `switch`) tells you when not to draw the class diagram.

**Why it matters:** Patterns are a review vocabulary ("that is a Decorator, so wrap it instead of editing it") and an over-engineering trap (an `AbstractHandlerFactoryBuilder` for three cases). A Spring developer uses nine of them before lunch without noticing. Naming them lets you see when a growing conditional is a Strategy waiting to happen, and when a lambda is all the pattern you need.

## The idea

A pattern is a named solution to a recurring design problem, so the useful knowledge is the problem, not the class diagram. The 1994 diagrams were drawn for a language without lambdas, sealed types or dependency injection. Three shifts since then change how the patterns look in Java 21:

1. Functional interfaces turned Strategy, Command and Template Method's hook steps into one-line lambdas. The pattern is still there; the ceremony is gone.
2. Sealed interfaces plus pattern-matching `switch` replaced Visitor and most hand-written State machines: the compiler now enforces the exhaustiveness that Visitor's interface used to enforce.
3. Dependency injection replaced Singleton and Service Locator, and Spring's proxies implement Decorator and Proxy for you whenever a concern is declared with an annotation.

| Pattern | Problem it solves | Already in the JDK or Spring | Reach for it when | Modern form |
|---|---|---|---|---|
| Builder | assemble an object step by step, validate once at the end | `StringBuilder`, `HttpRequest.newBuilder()`, `UriComponentsBuilder`, `RestClient.builder()` | many optional parameters, or construction that must read like prose | a record with a static factory when there are few fields |
| Factory (static factory, Factory Method, Abstract Factory) | name a construction, hide the concrete type, reuse instances | `List.of`, `LocalDate.of`, `Executors.newFixedThreadPool`, `DocumentBuilderFactory`; Spring `@Bean` methods and `FactoryBean` | the caller should not know which class it gets, or the construction deserves a name | a static method; a `Supplier<T>` for deferred creation |
| Strategy | swap an algorithm behind one interface | `Comparator`, `RowMapper`, Spring Security's `PasswordEncoder`, everything in `java.util.function` | one operation with interchangeable implementations chosen at runtime | a lambda; a `Map<Key, Handler>`; a `List<Handler>` of Spring beans |
| Template Method | fixed skeleton, variable steps | `AbstractList`, `HttpServlet.doGet` and `doPost`, `InputStream.read(byte[])` calling `read()` | a framework owns the lifecycle and you fill in steps | pass the steps as callbacks: `JdbcTemplate` and `TransactionTemplate` are templates without subclassing |
| Decorator | add behaviour by wrapping, keeping the interface | `BufferedInputStream`, `Collections.unmodifiableList`; the proxies behind `@Transactional` and `@Cacheable` | cross-cutting behaviour (caching, retries, metrics) without touching the core | the same; Spring generates the wrapper when the concern is declarative |
| Adapter | make one interface fit another | `Arrays.asList`, `InputStreamReader`, `Executors.callable(Runnable)`; Spring MVC's `HandlerAdapter`; the adapters of item 7.2 | integrating something whose interface you do not control | a lambda when the target is a functional interface |
| Observer | tell many listeners that something happened | `PropertyChangeListener`, `Flow.Publisher`; Spring `ApplicationEventPublisher` with `@EventListener` and `@TransactionalEventListener` | decoupling the thing that happened from the reactions to it | Spring application events; domain events (item 6.2) |
| Command | make a request an object so it can be queued, logged, retried or undone | `Runnable`, `Callable`, `ExecutorService.submit`; any message on a queue | an action must be deferred, queued, audited or retried | a lambda for behaviour, a record for data (`PlaceOrder` handled by a use case) |
| Chain of Responsibility | pass a request through handlers until one handles it | the Servlet `Filter` chain, the Spring Security filter chain, `HandlerInterceptor`, `ClientHttpRequestInterceptor` | ordered, pluggable processing stages | a `List` of functions applied in order; a stream of validators returning the first failure |

The ones not in the table you will also recognise: Facade (`RestClient` over HTTP, `JdbcTemplate` over JDBC), Proxy (`java.lang.reflect.Proxy`, Spring AOP, Hibernate's lazy-loading proxies, Spring Data repositories), Composite (a validator that is a list of validators), and State (an enum with a body per constant, or a sealed interface with one record per state).

## Example: replacing a conditional with Strategy

The conditional that keeps growing:

```java
public Money shippingCost(Order order) {
    if (order.shippingMethod() == ShippingMethod.STANDARD) {
        return order.weight().isAbove(Weight.kilograms(5)) ? Money.of("79.00", "NOK") : Money.of("49.00", "NOK");
    } else if (order.shippingMethod() == ShippingMethod.EXPRESS) {
        return Money.of("149.00", "NOK");
    } else if (order.shippingMethod() == ShippingMethod.PICKUP) {
        return Money.zero(Currency.getInstance("NOK"));
    }
    throw new IllegalStateException("Unknown shipping method " + order.shippingMethod());
}
```

Strategy with a `Map` and lambdas, no class per rule:

```java
import java.util.Currency;
import java.util.EnumMap;
import java.util.Map;

@FunctionalInterface
public interface ShippingCostRule {
    Money costOf(Order order);
}

public final class ShippingCosts {

    private final Map<ShippingMethod, ShippingCostRule> rules = new EnumMap<>(Map.of(
        ShippingMethod.STANDARD, order -> order.weight().isAbove(Weight.kilograms(5))
            ? Money.of("79.00", "NOK")
            : Money.of("49.00", "NOK"),
        ShippingMethod.EXPRESS, order -> Money.of("149.00", "NOK"),
        ShippingMethod.PICKUP, order -> Money.zero(Currency.getInstance("NOK"))));

    public Money costOf(Order order) {
        ShippingCostRule rule = rules.get(order.shippingMethod());
        if (rule == null) {
            throw new IllegalStateException("No shipping cost rule for " + order.shippingMethod());
        }
        return rule.costOf(order);
    }
}
```

Be honest about when this is better. For a closed enum known at compile time, a `switch` expression is shorter and the compiler checks that every constant is covered, which the `Map` cannot:

```java
public Money costOf(Order order) {
    return switch (order.shippingMethod()) {
        case STANDARD -> order.weight().isAbove(Weight.kilograms(5)) ? Money.of("79.00", "NOK") : Money.of("49.00", "NOK");
        case EXPRESS -> Money.of("149.00", "NOK");
        case PICKUP -> Money.zero(Currency.getInstance("NOK"));
    };
}
```

The `Map` wins when the rules come from outside the class: each rule is a Spring bean in its own module, and Spring injects all of them.

```java
public interface ShippingCostRule {
    ShippingMethod method();
    Money costOf(Order order);
}

@Service
public class ShippingCosts {

    private final Map<ShippingMethod, ShippingCostRule> rules;

    public ShippingCosts(List<ShippingCostRule> discoveredRules) {
        this.rules = discoveredRules.stream()
            .collect(Collectors.toMap(ShippingCostRule::method, Function.identity()));
    }
}
```

Adding a shipping method is now a new `@Component`, and no existing file changes. That is Open/Closed (item 2.1) earning its keep, at the price of losing the compiler's exhaustiveness check, so `toMap` throwing on a duplicate key is the only guard you have left; a startup test that every `ShippingMethod` has a rule restores it.

## Example: sealed types and `switch` instead of Visitor

```java
public sealed interface Shape permits Circle, Rectangle {}
public record Circle(double radius) implements Shape {}
public record Rectangle(double width, double height) implements Shape {}

static double area(Shape shape) {
    return switch (shape) {
        case Circle(double radius) -> Math.PI * radius * radius;
        case Rectangle(double width, double height) -> width * height;
    };
}
```

Visitor needed an `accept(Visitor)` method on every shape, a `Visitor` interface with one method per shape, and a class per operation. Here the operation is a function, the record pattern destructures the data, and adding `Triangle` to `permits` makes every `switch` that lacks a case fail to compile, which is exactly the guarantee Visitor's interface used to give, in a tenth of the code. This is the right shape for a closed set of data types with many operations: parsers, pricing rules, state machines, API response variants.

## Pitfalls

- Pattern names in class names. `OrderStrategyFactoryBuilder` tells the reader about your design process, not about orders. Name things after the domain.
- Builder for a three-field object. A record with a static factory is shorter, immutable and validated in one place.
- The Singleton pattern (static instance, private constructor) in a Spring application. Spring beans are already one-per-context, and they can be replaced in tests; a static singleton cannot.
- Template Method by inheritance when a callback would do. `AbstractBaseService` hierarchies three levels deep are how "which method actually runs?" becomes a research project.
- Observer listeners that throw. A synchronous `@EventListener` runs inside the publisher's call, so its exception propagates and can roll back the publisher's transaction. Use `@TransactionalEventListener` for after-commit reactions, and an outbox when delivery must be reliable.
- Decorator order. Retry wrapped in timeout and timeout wrapped in retry behave very differently; make the wrapping order explicit and test it.
- A chain where no handler handles the request and it silently falls off the end. Decide what the end of the chain does.
- Introducing a pattern for flexibility nobody asked for. A pattern should remove a conditional that exists or decouple a change that happens, not one you imagine.

## Check yourself

1. A `switch` over a three-constant enum appears in exactly one place. Strategy via `Map`, a `switch` expression, or constant-specific enum methods: which do you choose, and what would change your mind?
2. Where does Spring apply Decorator without you writing a class, and what ordering question does that raise when two such decorators apply to the same method?
3. Why does a sealed interface with a pattern-matching `switch` replace Visitor? What does the compiler do when you add a type, and what did Visitor do in the same situation?
4. You need retries, a timeout, logging and a metric around one outbound call. Which pattern, and which two orderings of the wrappers give different behaviour?

## Go deeper

- [refactoring.guru: Design Patterns](https://refactoring.guru/design-patterns) · each pattern with the problem, the structure, and Java code; the best free catalogue.
- [Java Design Patterns](https://java-design-patterns.com/) · implementations with notes on where each pattern appears in the JDK.
- [dev.java: Pattern Matching](https://dev.java/learn/language/fp/pattern-matching/) · the official tutorial for record patterns and `switch`, which is the Visitor replacement above.
- [Brian Goetz: Data Oriented Programming in Java](https://www.infoq.com/articles/data-oriented-programming-java/) · when sealed types and records should replace an object hierarchy, by the person who designed them.
- [Spring Framework: ApplicationContext capabilities, including events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html) · the reference for Spring's Observer: `ApplicationEventPublisher`, `@EventListener`, async and transactional listeners.

---

Part of [Architecture & Craft](../README.md) · items 3.1, 3.2, 3.3
