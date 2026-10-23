# The modular monolith: package by feature, enforced boundaries, and extracting later

> **In one sentence:** A modular monolith is one deployable whose code is divided into modules by business capability, each with a small public API and private internals, talking through that API or through events, with the boundaries enforced by a failing test (ArchUnit or Spring Modulith) rather than by good intentions; it gives you most of the organisational benefit of services with none of the network, and leaves the door open to extract a service when a module earns it.

**Why it matters:** Most painful microservice migrations started from a monolith with no boundaries, so the teams guessed where to cut and built a distributed monolith: the same coupling, now over HTTP. A monolith with enforced module boundaries is faster to build, easier to test, and the only sane starting point for extracting services later. "How would you structure a new Spring Boot application?" has this as its best answer for almost every team of fewer than a few dozen developers.

## The idea

**Package by feature, not by layer.** The default layout (`controller`, `service`, `repository`, `model`) spreads every feature across every package and forces everything to be `public`, because the controller in one package must see the service in another. A change to orders touches five packages. Package by feature (`orders`, `billing`, `inventory`) puts a feature's controller, service, repository and entities together, so most of them can be package-private and a change is local. Cohesion goes up and coupling becomes visible: a cross-package import is now a cross-feature dependency you can see and question.

**A module is a feature package with a contract.** Three parts:

1. A public API: a handful of types other modules may use. A service interface or facade, the commands it accepts, the events it publishes, its identifiers. Everything else is internal.
2. Internals: in an `internal` sub-package or package-private, invisible to other modules and free to change.
3. Its own data: the module owns its tables. No other module reads or joins them; it asks the module. Whether to allow foreign keys between modules' tables is a real trade-off: they protect integrity now and make extraction harder later. Decide per module and write the decision down (item 9.2).

**Communication.** Two ways, and the direction matters. A synchronous call through the other module's API when you need an answer now (`inventory.availableStock(productId)` while adding a line). An application event when you are announcing a fact and the reaction is someone else's business (`OrderPlaced`, to which inventory reserves stock and billing creates an invoice). Dependencies between modules should form a directed acyclic graph; if orders calls billing and billing calls orders, one of them needs an event instead, and the event type belongs to the publisher's API. A shared kernel (`Money`, common ids) is allowed and must stay tiny.

**Enforcement.** Boundaries that are not tested erode within weeks. Two tools:

- **ArchUnit**: rules written as JUnit tests over the imported classes. No access to another module's `internal`, no cycles between module slices, layered or onion rules inside a module (item 7.2).
- **Spring Modulith**: a convention plus a verifier. Every direct sub-package of the application's main package is a module; types in the module's base package are its API; types in sub-packages are internal unless exposed with `@NamedInterface`. `ApplicationModules.of(Application.class).verify()` fails the build on internal access and cycles, `@ApplicationModuleListener` gives you asynchronous, after-commit, persisted event handling between modules, `@ApplicationModuleTest` bootstraps a single module for integration tests, and a `Documenter` generates C4-style module diagrams from the code.

JPMS (`module-info.java`) enforces encapsulation at the JVM level but fights Spring's reflection-based wiring; it is rarely used for application modules.

**Extracting a service later.** Because the module already has an API, events and its own tables, extraction is mechanical: the API becomes a remote API (HTTP or gRPC) behind the same interface, the events become messages on a broker, the tables move with the module. A strangler fig routes callers to the new service one at a time while the module in the monolith becomes a thin client, then disappears. Extract when a module needs independent scaling, a different release cadence or runtime, separate ownership, or regulatory isolation. Do not extract because services are fashionable: every extraction buys you network failures, eventual consistency where you used to have a transaction, distributed tracing and API versioning.

## Example: the structure and the test that guards it

```text
com.example.shop
├── ShopApplication.java
├── orders                          module "orders"
│   ├── Orders.java                 public API: the module's service interface
│   ├── OrderId.java                public API
│   ├── OrderPlaced.java            public API: event record published by this module
│   └── internal
│       ├── Order.java
│       ├── OrderController.java
│       ├── OrderService.java       implements Orders
│       └── OrderRepository.java
├── inventory                       module "inventory"
│   ├── Inventory.java
│   └── internal
│       ├── Stock.java
│       └── OrderPlacedListener.java
└── billing                         module "billing"
```

Spring Modulith's verification is three lines, and the documentation is one more:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModularityTest {

    private final ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

    @Test
    void modulesRespectTheirBoundaries() {
        modules.verify();
    }

    @Test
    void writeModuleDocumentation() {
        new Documenter(modules).writeDocumentation();
    }
}
```

`verify()` fails if `billing.internal` imports `orders.internal.Order`, or if orders and billing depend on each other. The same rules without the convention, in ArchUnit:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;
import static com.tngtech.archunit.library.dependencies.SlicesRuleDefinition.slices;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

@AnalyzeClasses(packages = "com.example.shop", importOptions = ImportOption.DoNotIncludeTests.class)
class ModuleBoundariesTest {

    @ArchTest
    static final ArchRule modulesDoNotFormCycles = slices()
        .matching("com.example.shop.(*)..")
        .should().beFreeOfCycles();

    @ArchTest
    static final ArchRule ordersInternalsArePrivate = internalsArePrivate("orders");

    @ArchTest
    static final ArchRule inventoryInternalsArePrivate = internalsArePrivate("inventory");

    @ArchTest
    static final ArchRule billingInternalsArePrivate = internalsArePrivate("billing");

    private static ArchRule internalsArePrivate(String module) {
        String modulePackage = "com.example.shop." + module;
        return noClasses()
            .that().resideOutsideOfPackage(modulePackage + "..")
            .should().dependOnClassesThat().resideInAPackage(modulePackage + ".internal..")
            .as("Only the " + module + " module may use " + module + ".internal");
    }
}
```

A violation fails with the offending import, file and line, which is the whole point: the boundary is now as real as a compile error. The event between the modules:

```java
// orders: part of the public API
public record OrderPlaced(OrderId orderId, List<OrderedItem> items) {}

// orders.internal.OrderService, inside the transaction that saves the order
applicationEventPublisher.publishEvent(new OrderPlaced(order.id(), order.items()));

// inventory.internal.OrderPlacedListener
@ApplicationModuleListener
void on(OrderPlaced event) {
    stock.reserve(event.items());
}
```

Inventory depends on the orders API (the event record) and never on its internals; orders knows nothing about inventory. With `spring-modulith-starter-jpa` or `-jdbc` on the classpath, the publication is recorded in a table before the listener runs and marked complete afterwards, so a crash between the two does not lose the event. When inventory becomes a service, this listener becomes a Kafka consumer and nothing in orders changes.

## Pitfalls

- Package-by-layer habits inside a module, with everything `public`. The compiler's visibility rules are the cheapest boundary you have; use package-private by default.
- Cross-module reads in SQL or JPQL. An ArchUnit rule on Java imports does not see `JOIN billing_invoice`, and the schema is the coupling that hurts most at extraction time. Separate schemas per module, or at least a naming convention and a review rule.
- The fat `common` module. It starts with `Money` and ends with half the domain; every module depends on it and nothing can move.
- Cycles hidden by events. If orders publishes an event type that lives in billing, the dependency still points the wrong way. Event types belong to the publisher.
- Events for questions. "What is the price of this product?" is a query with an answer; use the API, not an event and a cache.
- Boundaries documented in a wiki and enforced by nobody. If the test cannot fail, the boundary does not exist.
- Extracting early. A module that has been stable for a year and never needed independent deployment is telling you something.
- `@SpringBootTest` for every module test. Use `@ApplicationModuleTest` so a module's tests start only that module.

## Check yourself

1. What concretely can be package-private in package-by-feature that could not be in package-by-layer, and why does that matter more than taste?
2. Inventory needs the items when an order is placed; orders needs to know available stock when a line is added. Design both interactions (event or API call) and justify the direction of each dependency.
3. Your ArchUnit rules pass, but a module reads another module's table in a native query. Which coupling did the rule miss, and how would you detect it?
4. Give two signals that a module should become a service, and two that look like signals but are not.

## Go deeper

- [Spring Modulith](https://docs.spring.io/spring-modulith/reference/) · the reference: module conventions, verification, event publication registry, module tests and documentation.
- [Oliver Drotbohm: Introducing Spring Modulith](https://spring.io/blog/2022/10/21/introducing-spring-modulith) · the motivation and the model in one post, by its author.
- [ArchUnit](https://www.archunit.org/) · the library and its user guide; the slices and `onionArchitecture()` sections cover everything in this note.
- [Philipp Hauer: Package by Feature](https://phauer.com/2020/package-by-feature/) · the case against package-by-layer with concrete Kotlin and Java examples.
- [Martin Fowler: Monolith First](https://martinfowler.com/bliki/MonolithFirst.html) and [Microservice Premium](https://martinfowler.com/bliki/MicroservicePremium.html) · why starting with a monolith is the default, and what services cost.
- [Martin Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) · the extraction pattern referred to above.

---

Part of [Architecture & Craft](../README.md) · item 7.3
