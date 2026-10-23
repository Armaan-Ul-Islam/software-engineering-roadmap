# Hexagonal architecture with Spring Boot: ports, adapters and the dependency rule

> **In one sentence:** Put the business rules in the centre with no dependency on Spring, JPA or HTTP, express the ways in (inbound ports, your use cases) and the ways out (outbound ports, what the use cases need) as plain Java interfaces, implement the edges as adapters that depend inward, and accept that the price is mapping code at every edge; onion and clean architecture are the same idea with different ring names.

**Why it matters:** The default Spring Boot layout (controller, service, repository, JPA entities everywhere) works until the domain grows. Then every rule is entangled with persistence annotations, every test needs a database, and swapping a payment provider means editing the core. "Structure a service so the domain depends on neither the framework nor the database, and defend the cost" is an interview question because it is the decision you make on day one of every service.

## The idea

**Ports and adapters.** Alistair Cockburn's picture: the application sits in the middle. Each **port** is a purposeful conversation with the outside ("for placing orders", "for storing orders", "for charging cards"), defined by the application as an interface. Each port is served by one or more **adapters**: a REST controller, a message listener or a test harness on the driving side; a JPA repository, an in-memory fake or a Stripe client on the driven side. The hexagon shape means nothing except "more than two sides".

**The dependency rule.** Source code dependencies point inward only. The domain imports nothing from the application layer; the application layer imports nothing from the adapters; adapters import whatever they like. Robert C. Martin's clean architecture draws this as rings (entities, use cases, interface adapters, frameworks) and Jeffrey Palermo's onion architecture as domain model, domain services, application services, infrastructure. The ring names differ; the rule is identical, and so is its consequence: the interface an inner ring needs is declared *in* the inner ring and implemented outside it (dependency inversion, item 2.1).

**In Java terms.** An inbound port is an interface implemented by an application service: `PlaceOrderUseCase`. An outbound port is an interface the application service needs, implemented by an adapter: `OrderRepository`. The domain and application packages import nothing from `org.springframework` or `jakarta.persistence`. The domain `Order` is plain Java with behaviour; the JPA `OrderJpaEntity` is a separate class in the persistence adapter, and a mapper converts in both directions.

**Keeping annotations out, honestly.** Two compromises are common and you should choose deliberately. First, `@Transactional` on the application service: pragmatic, but it drags Spring into the application layer. The strict alternative is to wire the use case in a `@Configuration` class and wrap it in a transaction there (shown below). Second, `@Service` on the application service for component scanning: same trade. Many teams allow Spring annotations in the application layer and none in the domain; that is a defensible line as long as it is drawn on purpose and enforced with ArchUnit.

**The cost.** Two or three representations of each concept and the mapping between them. No lazy loading: you load whole aggregates, which is right for commands and wrong for reports, so queries get their own port and read model rather than going through the domain. The domain `Order` must carry a `version` it does not care about so that optimistic locking survives the round trip through the mapper. More files, and a learning curve for the team. For a CRUD service none of this pays; for the core domain of a long-lived system it pays every month. A modular monolith (item 7.3) lets the two styles coexist module by module.

## Example: one use case, end to end

```text
com.example.shop.orders
├── domain
│   ├── Order.java                       aggregate root, plain Java
│   ├── OrderLine.java
│   ├── OrderId.java                     record
│   ├── Money.java                       record
│   └── OrderRepository.java             outbound port, owned by the domain
├── application
│   ├── PlaceOrderUseCase.java           inbound port
│   ├── PlaceOrderCommand.java           record
│   └── PlaceOrderService.java           implements the use case
└── adapter
    ├── in
    │   └── web
    │       ├── OrderController.java
    │       └── PlaceOrderRequest.java   request DTO, converts itself to the command
    └── out
        └── persistence
            ├── OrderJpaEntity.java
            ├── OrderLineJpaEntity.java
            ├── OrderMapper.java
            ├── SpringDataOrderRepository.java   extends JpaRepository
            └── OrderPersistenceAdapter.java     implements OrderRepository
```

The ports and the use case, with no framework imports:

```java
public interface PlaceOrderUseCase {
    OrderId placeOrder(PlaceOrderCommand command);
}

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

public class PlaceOrderService implements PlaceOrderUseCase {

    private final OrderRepository orderRepository;

    public PlaceOrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Override
    public OrderId placeOrder(PlaceOrderCommand command) {
        Order order = Order.draft(OrderId.random(), command.customerId());
        command.lines().forEach(line -> order.addLine(line.productId(), line.quantity(), line.unitPrice()));
        order.place();
        orderRepository.save(order);
        return order.id();
    }
}
```

The persistence adapter is where JPA lives:

```java
@Entity
@Table(name = "orders")
class OrderJpaEntity {

    @Id
    private UUID id;
    private UUID customerId;
    @Enumerated(EnumType.STRING)
    private OrderStatus status;
    @OneToMany(cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumn(name = "order_id")
    private List<OrderLineJpaEntity> lines = new ArrayList<>();
    @Version
    private long version;

    protected OrderJpaEntity() {
    }
}

interface SpringDataOrderRepository extends JpaRepository<OrderJpaEntity, UUID> {
}

@Component
class OrderPersistenceAdapter implements OrderRepository {

    private final SpringDataOrderRepository springDataOrderRepository;
    private final OrderMapper orderMapper;

    OrderPersistenceAdapter(SpringDataOrderRepository springDataOrderRepository, OrderMapper orderMapper) {
        this.springDataOrderRepository = springDataOrderRepository;
        this.orderMapper = orderMapper;
    }

    @Override
    public Optional<Order> findById(OrderId id) {
        return springDataOrderRepository.findById(id.value()).map(orderMapper::toDomain);
    }

    @Override
    public void save(Order order) {
        springDataOrderRepository.save(orderMapper.toEntity(order));
    }
}
```

Wiring and the transaction boundary, outside the application layer. Because the inbound port has a single method, a lambda can decorate it:

```java
@Configuration
class OrdersConfiguration {

    @Bean
    PlaceOrderUseCase placeOrderUseCase(OrderRepository orderRepository, TransactionTemplate transactionTemplate) {
        PlaceOrderService service = new PlaceOrderService(orderRepository);
        return command -> transactionTemplate.execute(status -> service.placeOrder(command));
    }
}
```

The web adapter depends on the inbound port only:

```java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final PlaceOrderUseCase placeOrderUseCase;

    OrderController(PlaceOrderUseCase placeOrderUseCase) {
        this.placeOrderUseCase = placeOrderUseCase;
    }

    @PostMapping
    ResponseEntity<Void> place(@RequestBody @Valid PlaceOrderRequest request) {
        OrderId orderId = placeOrderUseCase.placeOrder(request.toCommand());
        return ResponseEntity.created(URI.create("/orders/" + orderId.value())).build();
    }
}
```

What this buys: `PlaceOrderService` is tested with an in-memory `OrderRepository` in milliseconds (item 5.3); the persistence adapter is tested on its own against PostgreSQL in Testcontainers; the controller is tested with `@WebMvcTest` and a stubbed `PlaceOrderUseCase`. Replacing JPA with JDBC, or adding a gRPC adapter, touches one package. An ArchUnit rule keeps it that way:

```java
@ArchTest
static final ArchRule hexagon = onionArchitecture()
    .domainModels("..orders.domain..")
    .applicationServices("..orders.application..")
    .adapter("web", "..orders.adapter.in.web..")
    .adapter("persistence", "..orders.adapter.out.persistence..");
```

## Pitfalls

- Ports named after technology. `JpaOrderPort` is an adapter with the wrong name; a port is named for its purpose, `OrderRepository` or `NotifyCustomer`.
- Reusing the JPA entity as the domain object "to save the mapping". The annotations, the no-argument constructor and the lazy proxies now dictate the model, and the centre is not independent any more. If you make this trade, admit that you have a layered architecture, which is fine.
- Pass-through use cases. A use case that calls `repository.save(mapper.map(dto))` adds nothing; hexagonal architecture is for rules, not for CRUD.
- Adapter types leaking inward: `Page<T>` or `Pageable` in a port, a JPA entity returned from a use case, a `ResponseEntity` built in the application layer.
- Interfaces for everything. Only ports need interfaces; a domain class or a mapper with one implementation does not.
- Forgetting the query side. Reports and list screens through aggregates load the world; give them a query port backed by SQL or a read model.
- Hiding the transaction boundary so well that nobody knows where it is. Wherever you put it (annotation or configuration), document the choice and test it.

## Check yourself

1. Which packages may import `jakarta.persistence`, and which may import `org.springframework`? What breaks in a test the moment the domain imports either?
2. `OrderRepository` lives in the domain package. Why does that location, rather than the persistence package, decide whether this is a hexagonal architecture or a layered one with extra interfaces?
3. A product manager asks for a monthly report over all orders. Through which port does it go, and why not through `OrderRepository`?
4. Name the representations an order passes through between the HTTP request and the database row, and defend them to a colleague who says "it's just a form over a table". Then name a service where the colleague would be right.

## Go deeper

- [Alistair Cockburn: Hexagonal Architecture](https://alistair.cockburn.us/hexagonal-architecture/) · the original article; short, and the "driving and driven" vocabulary comes from here.
- [Robert C. Martin: The Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html) · the rings diagram and the dependency rule, stated in one page.
- [Herberto Graça: DDD, Hexagonal, Onion, Clean, CQRS... how I put it all together](https://herbertograca.com/2017/11/16/explicit-architecture-01-ddd-hexagonal-onion-clean-cqrs-how-i-put-it-all-together/) · the best single article on how the variants relate.
- [Martin Fowler: Presentation Domain Data Layering](https://martinfowler.com/bliki/PresentationDomainDataLayering.html) · the layered baseline this note departs from, and why layering by itself is not enough.
- [ArchUnit User Guide](https://www.archunit.org/userguide/html/000_Index.html) · the `onionArchitecture()` and `layeredArchitecture()` rules used to enforce the dependency rule.
- [jMolecules](https://github.com/xmolecules/jmolecules) · annotations and types for expressing hexagonal and DDD concepts in code, with ArchUnit rules that verify them.

---

Part of [Architecture & Craft](../README.md) · items 7.1, 7.2
