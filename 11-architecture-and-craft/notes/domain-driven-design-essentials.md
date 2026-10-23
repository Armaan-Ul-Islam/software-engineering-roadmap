# Domain-driven design essentials: language, boundaries, aggregates and events

> **In one sentence:** DDD is two practices: a strategic one, drawing boundaries around the places where a word means exactly one thing (bounded contexts, each with its own ubiquitous language), and a tactical one (entities, value objects, aggregates, repositories, domain services, domain events) for putting business rules in the model rather than in services; it pays off where the rules are rich and changing, and costs more than it returns where they are not.

**Why it matters:** Most "the business says X but the system does Y" bugs come from one class trying to be the Order for sales, warehouse and accounting at once. Senior interviews ask you to model something and then poke at the boundaries: where is the transaction, which object owns the rule, what happens when two users change it concurrently. DDD gives you the vocabulary and the defaults for those answers.

## The idea

**Strategic design: where the boundaries go.**

- *Ubiquitous language*: one vocabulary shared by developers and domain experts, used in conversation, code and tests. If the warehouse says "consignment" and the code says `ShipmentDto`, every translation is a bug opportunity. The language is per context, not per company.
- *Bounded context*: the boundary within which a model and its language are consistent. In Sales an order has lines, discounts and a payment; in Shipping it has parcels, a weight and an address; in Accounting it is an invoice and ledger entries. One `Order` class for all three is how god classes are born. A context usually maps to a module (item 7.3) or a service, and ideally to one team.
- *Context map*: the relationships between contexts, named so their cost is visible: partnership, shared kernel, customer-supplier, conformist, anti-corruption layer (item 6.4), open host service with a published language, or separate ways.
- *Subdomains*: core (where the business competes; invest the modelling effort here), supporting (necessary, not differentiating; keep it simple), generic (authentication, payments; buy it).

**Tactical design: the building blocks.**

| Block | Definition | Rule of thumb |
|---|---|---|
| Entity | has identity that persists across changes; equality by id | `Order`, `Customer` |
| Value object | no identity, immutable, equality by value (item 1.5) | `Money`, `Address`, `Quantity`; a record |
| Aggregate | a cluster of entities and values changed as one unit through a root; the root enforces invariants that must hold at the end of every transaction | `Order` with its `OrderLine`s; other aggregates referenced by id only |
| Repository | collection-like access to whole aggregates, one per root | `OrderRepository.findById`, `save`; the interface is owned by the domain (item 7.2) |
| Domain service | an operation in the language that belongs to no single entity | transferring between two accounts |
| Domain event | a fact that happened, past tense, carrying what others need | `OrderPlaced(orderId, customerId, total)` |

**Aggregates and transactions.** Vaughn Vernon's four rules: model true invariants inside consistency boundaries; keep aggregates small; reference other aggregates by identity; use eventual consistency between aggregates. The practical form is **one aggregate per transaction**: a use case loads one aggregate, calls one method on it, saves it. Anything else that must change as a consequence changes in reaction to a domain event, in its own transaction. The reasons are concrete: a large aggregate means every change locks or version-conflicts with every other, and two aggregates in one transaction couple their lifecycles so tightly that they can never live in different modules or services.

**Where DDD pays and where it is overkill.** It pays in the core domain, where rules are many, interrelated and change with the business: pricing, insurance, logistics, finance. It is overkill for forms over tables, supporting subdomains, prototypes and small CRUD services; there, Spring Data entities with validation are the right model and the tactical patterns are ceremony. The strategic half (agree the language, draw the contexts) is almost always worth doing even when the tactical half is not.

## Example: an `Order` aggregate and the boundary with Shipping

The invariants: lines can only change while the order is a draft, an order has at most fifty lines, and an order can only be placed if it has lines and fits the customer's credit limit. Every one of them is enforced in a method of the root; there is no setter anywhere.

```java
public class Order {

    private static final int MAXIMUM_LINES = 50;

    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private final List<DomainEvent> pendingEvents = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    private Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    public static Order draft(OrderId id, CustomerId customerId) {
        return new Order(id, customerId);
    }

    public void addLine(ProductId productId, Quantity quantity, Money unitPrice) {
        requireStatus(OrderStatus.DRAFT, "add a line to");
        if (lines.size() >= MAXIMUM_LINES) {
            throw new OrderRuleViolated("An order has at most " + MAXIMUM_LINES + " lines");
        }
        lines.add(new OrderLine(productId, quantity, unitPrice));
    }

    public void place(CreditLimit creditLimit) {
        requireStatus(OrderStatus.DRAFT, "place");
        if (lines.isEmpty()) {
            throw new OrderRuleViolated("An order needs at least one line before it can be placed");
        }
        Money total = total();
        if (!creditLimit.covers(total)) {
            throw new OrderRuleViolated("Total " + total + " exceeds the credit limit " + creditLimit);
        }
        status = OrderStatus.PLACED;
        pendingEvents.add(new OrderPlaced(id, customerId, total));
    }

    public Money total() {
        return lines.stream().map(OrderLine::subtotal).reduce(Money.zero(Currency.getInstance("EUR")), Money::plus);
    }

    public List<DomainEvent> pullPendingEvents() {
        List<DomainEvent> events = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return events;
    }

    private void requireStatus(OrderStatus required, String action) {
        if (status != required) {
            throw new OrderRuleViolated("Cannot " + action + " an order that is " + status);
        }
    }
}
```

`ProductId` and `CustomerId` are references by identity: `Order` never holds a `Product` or a `Customer`. The credit limit belongs to the `Customer` aggregate, so the application service reads it and passes it in as a value; the use case still modifies exactly one aggregate:

```java
@Transactional
public void placeOrder(OrderId orderId) {
    Order order = orderRepository.getById(orderId);
    CreditLimit creditLimit = customerRepository.creditLimitOf(order.customerId());
    order.place(creditLimit);
    orderRepository.save(order);
    order.pullPendingEvents().forEach(applicationEventPublisher::publishEvent);
}
```

Shipping is another bounded context. It has no `Order` class. It has a `Shipment` aggregate with a `DeliveryAddress` and `Parcel`s, and it keeps the sales order id only as a reference. It learns that something happened through the event, and the listener is a small anti-corruption layer translating Sales vocabulary into Shipping vocabulary:

```java
@Component
class OrderPlacedHandler {

    private final RequestShipmentUseCase requestShipment;

    OrderPlacedHandler(RequestShipmentUseCase requestShipment) {
        this.requestShipment = requestShipment;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        requestShipment.request(new SalesOrderReference(event.orderId().value()), event.customerId());
    }
}
```

`@ApplicationModuleListener` (Spring Modulith) runs after the publishing transaction commits, asynchronously, in its own transaction, and records the publication so it can be retried if the handler fails. With plain Spring, `@TransactionalEventListener` gives you the after-commit part but not the persistence. Prices never cross this boundary, because Shipping does not need them; if it did, the event would carry them, or Shipping would query Sales through its published API. If stock reservation in Inventory fails in reaction to the same event, Inventory publishes `StockReservationFailed` and Sales reacts by cancelling the order: consistency between aggregates is eventual and compensating, not transactional.

## Pitfalls

- The anemic model (item 3.5): entities as bags of getters and setters, rules in services. `order.setStatus(PLACED)` callable from anywhere means the invariant lives nowhere.
- Giant aggregates. A `Customer` that contains all its orders loads thousands of rows for a name change and conflicts with every concurrent order.
- Two aggregates in one transaction "because it is simpler". It is, until the second one needs to live in another module or service.
- Letting JPA decide the model. `@OneToMany` across aggregate roots and lazy loading quietly dissolve the boundary; keep the domain model separate from the persistence model or map carefully (item 6.6).
- Events that are commands in disguise (`SendShippingEmail`) or that carry the whole entity. An event is a past-tense fact with the data consumers need.
- A shared "common model" library across contexts: a shared kernel without the agreement that makes a shared kernel work.
- Repositories with forty query methods for reports. Reporting is a read model over the tables, not a trip through the aggregate.
- DDD vocabulary on a CRUD application. `CustomerAggregateRootFactoryImpl` for a table of customers helps nobody.

## Check yourself

1. Name two attributes of an order that Sales needs and Shipping must not have, and two the other way round. What happens to the code if you ignore that and share one class?
2. Why is `CreditLimit` passed into `Order.place` rather than `Order` holding a reference to `Customer`? Which of Vernon's rules does each alternative break?
3. Stock reservation fails after `OrderPlaced` has been published. Walk through the flow with one aggregate per transaction, including the compensation, and say what the customer sees in between.
4. Describe a system where tactical DDD is overkill, and say which parts of DDD you would still apply there and why.

## Go deeper

- [Eric Evans: Domain-Driven Design Reference](https://www.domainlanguage.com/ddd/reference/) · the free pattern summary by the author; the definitions in this note follow it.
- [Vaughn Vernon: Effective Aggregate Design](https://www.dddcommunity.org/library/vernon_2011/) · the three-part essay behind the four rules and "one aggregate per transaction".
- [Martin Fowler: Bounded Context](https://martinfowler.com/bliki/BoundedContext.html) · the strategic idea in one page, with the sales-and-support diagram everyone redraws.
- [DDD Crew: Context Mapping](https://github.com/ddd-crew/context-mapping) · every context-map relationship with a cheat sheet you can use in a workshop.
- [Jens Schauder: Spring Data JDBC, References, and Aggregates](https://spring.io/blog/2018/09/24/spring-data-jdbc-references-and-aggregates) · how a persistence library built around aggregates treats references, and why it refuses to load across roots.
- [Spring Modulith](https://docs.spring.io/spring-modulith/reference/) · application modules as bounded contexts, and the event publication registry used by the handler above.
- [Learning Domain-Driven Design](https://www.oreilly.com/library/view/learning-domain-driven-design/9781098100124/) · Khononov's book, the most approachable full treatment, including when to use which pattern (paid).

---

Part of [Architecture & Craft](../README.md) · items 6.1, 6.2, 6.3
