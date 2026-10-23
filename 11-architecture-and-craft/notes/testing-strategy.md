# Testing strategy: the pyramid, the trophy, and tests that survive refactoring

> **In one sentence:** Decide what each kind of test is for (unit tests for the rules, integration tests for the adapters, contract tests for the seams between teams, a few end-to-end tests for the wiring), write every test against observable behaviour rather than implementation so that refactoring breaks none of them, and use test doubles only where a real collaborator would make the test slow, non-deterministic or impossible.

**Why it matters:** A suite that fails on every refactoring is worse than no suite, because people stop refactoring or stop trusting red. A suite of two thousand mock-heavy tests that stays green while the application is broken is common in Spring codebases. "How would you test this service?" is also the most frequent design-adjacent question in backend interviews, and the answer reveals how you think about boundaries.

## The idea

**Why we test.** Three reasons, in order of value: fast feedback while you work (seconds, not a deploy), design pressure (code that is hard to test is usually badly coupled, and the test tells you first), and regression safety that makes refactoring possible at all (item 4.2).

**The pyramid and the trophy.** The test pyramid (Mike Cohn, made practical by Ham Vocke) says: many fast unit tests, fewer integration tests, very few end-to-end tests, because cost and feedback time grow as you go up. The testing trophy (Kent C. Dodds, from the frontend world) puts static analysis at the base and makes integration tests the widest layer, arguing they buy the most confidence per hour. For a Spring service the two disagree less than they appear to; the real argument is over the word "unit". Vladimir Khorikov's definition settles it: a unit test verifies a unit of *behaviour*, runs fast, and is isolated from other tests. It does not have to isolate one class. A use case tested with its real domain objects and in-memory fakes for its ports is a unit test, and it is the most valuable test you will write.

| Layer | What it checks | In a Spring Boot service | How many |
|---|---|---|---|
| Unit | business rules, through the public API of a use case or domain object | plain JUnit, no Spring context, fakes for ports; milliseconds | most |
| Integration | one adapter against the real technology | repository against PostgreSQL in Testcontainers; controller serialisation, validation and security with `@WebMvcTest`; a message consumer against a real broker | tens to a few hundred |
| Contract | that a consumer's expectations of a provider hold | consumer-driven contracts with Pact or Spring Cloud Contract, run in both pipelines | one per consumer-provider pair |
| End-to-end | the deployed system's wiring on a few golden paths | smoke tests against a test environment; the checkout path, the login path | a handful |

`@SpringBootTest` belongs mostly in the last two rows: starting the context costs seconds and every distinct set of mocked beans creates another cached context.

**Tests that survive refactoring.** A test couples itself to whatever it references. Reference only the unit's public API and assert only on outcomes: the return value, state observable through the API, and messages that left the system. Never assert on which internal collaborator was called, in which order, with which private intermediate value; those are implementation details and the test will break when they change, which is exactly when you need it to pass. One behaviour per test, named after the behaviour (`placingAnOrderReservesStock`, not `testPlace`), laid out as arrange, act, assert with a blank line between the three, and no `if` or loop in the test body.

**Test doubles.** Gerard Meszaros's vocabulary, which Mockito blurs:

| Double | What it does | Example |
|---|---|---|
| Dummy | fills a parameter and is never used | a `null` or `new Object()` passed as an unused argument |
| Stub | returns canned answers to queries, no assertions on it | `FixedPricing` that returns `10.00 EUR` for everything |
| Fake | a working, simplified implementation | `InMemoryOrders`, a `Map` behind the `Orders` port |
| Mock | records calls and the test asserts on them | `verify(emailSender).send(...)` |
| Spy | a real object that also records calls | Mockito `spy(realObject)` |

`when(...)` makes a Mockito object a stub; `verify(...)` makes it a mock. The classicist school (Fowler's Detroit style) uses real objects and fakes and mocks only awkward collaborations; the mockist school (London style, *Growing Object-Oriented Software*) mocks every collaborator and designs outside-in through the interactions. Khorikov's resolution is the one to adopt: mock only **unmanaged out-of-process dependencies**, the external systems whose interactions other people can observe (a payment provider, an email gateway, a message bus). Do not mock managed ones (your own database: test it for real) and do not mock in-process collaborators (your own classes: use them, or fake the port). Verify an interaction only when the interaction *is* the behaviour, such as "an email was sent".

## Example: the same behaviour tested twice

The code under test:

```java
public class PlaceOrderService {

    private final Orders orders;
    private final Inventory inventory;
    private final Pricing pricing;

    public PlaceOrderService(Orders orders, Inventory inventory, Pricing pricing) {
        this.orders = orders;
        this.inventory = inventory;
        this.pricing = pricing;
    }

    public OrderId place(PlaceOrder command) {
        Money unitPrice = pricing.priceOf(command.productId());
        inventory.reserve(command.productId(), command.quantity());
        Order order = Order.place(command.customerId(), command.productId(), command.quantity(), unitPrice);
        orders.add(order);
        return order.id();
    }
}
```

Over-mocked:

```java
@ExtendWith(MockitoExtension.class)
class PlaceOrderServiceMockTest {

    @Mock Orders orders;
    @Mock Inventory inventory;
    @Mock Pricing pricing;
    @InjectMocks PlaceOrderService service;

    @Test
    void placesOrder() {
        when(pricing.priceOf(PRODUCT)).thenReturn(Money.of("10.00", "EUR"));

        service.place(new PlaceOrder(CUSTOMER, PRODUCT, 2));

        InOrder inOrder = inOrder(pricing, inventory, orders);
        inOrder.verify(pricing).priceOf(PRODUCT);
        inOrder.verify(inventory).reserve(PRODUCT, 2);
        inOrder.verify(orders).add(argThat(order -> order.total().equals(Money.of("20.00", "EUR"))));
    }
}
```

With fakes:

```java
class PlaceOrderServiceTest {

    private final InMemoryOrders orders = new InMemoryOrders();
    private final InMemoryInventory inventory = new InMemoryInventory().withStock(PRODUCT, 5);
    private final PlaceOrderService service =
        new PlaceOrderService(orders, inventory, new FixedPricing(Money.of("10.00", "EUR")));

    @Test
    void placingAnOrderReservesStockAndChargesTheListPrice() {
        OrderId orderId = service.place(new PlaceOrder(CUSTOMER, PRODUCT, 2));

        assertThat(orders.find(orderId)).map(Order::total).contains(Money.of("20.00", "EUR"));
        assertThat(inventory.available(PRODUCT)).isEqualTo(3);
    }

    @Test
    void anOrderThatExceedsStockIsNotPlaced() {
        assertThatThrownBy(() -> service.place(new PlaceOrder(CUSTOMER, PRODUCT, 6)))
            .isInstanceOf(InsufficientStock.class);
        assertThat(orders.all()).isEmpty();
    }
}
```

`InMemoryInventory` is about fifteen lines: a `Map<ProductId, Integer>` and a `reserve` that subtracts or throws `InsufficientStock`. It is written once and shared by every test that needs an inventory.

Now the refactoring. Multi-line orders are coming, so `Inventory.reserve(productId, quantity)` becomes `Inventory.reserve(List<OrderLine> lines)` and, for atomicity, the service reserves before it prices. Behaviour is identical: stock goes from 5 to 3, the total is 20.00 EUR.

- The mock test no longer compiles (`verify(inventory).reserve(PRODUCT, 2)`), and once fixed, the `InOrder` assertion fails because pricing now happens second. The test must be rewritten although nothing it was supposed to protect has changed.
- The fake test is untouched. `InMemoryInventory` gains the new method (one place, five lines) and both tests stay green.

The second suite also already covers the insufficient-stock case naturally, because the fake implements the rule. In the mock suite, `inventory.reserve` is a void method that silently does nothing, so that case needs its own `doThrow` setup that mirrors the implementation once more.

Where the mock is right: `PlaceOrderService` later publishes an `OrderPlaced` event to a message bus. That is an unmanaged out-of-process dependency and the publication *is* the behaviour, so `verify(eventPublisher).publish(any(OrderPlaced.class))` is a correct assertion.

## Pitfalls

- `@SpringBootTest` for logic tests. Minutes of context start to test a pricing rule, and every `@MockitoBean` combination (or `@MockBean` before Spring Boot 3.4) starts yet another context.
- Mocking types you do not own (`RestTemplate`, `EntityManager`, `KafkaTemplate`). Wrap them behind your own port and fake the port; for HTTP, WireMock against a real client is both cheaper and more honest.
- `verify` on queries and `verifyNoMoreInteractions` by reflex. Both assert on implementation.
- H2 as a stand-in for PostgreSQL. Different SQL dialect, different constraint behaviour, different locking. Testcontainers makes the real database cheap.
- One test method per production method, with numbered variants. Tests are per behaviour, and a method with eight behaviours has eight tests with eight names.
- Logic in tests. An `if` in a test means two tests; a loop means a parameterised test.
- Asserting on log lines, `toString`, or private state through reflection.
- Coverage as the goal. Coverage shows what is untested; it never shows what is tested well. Mutation testing does (item 5.6).
- Shared mutable fixtures and tests that depend on execution order; the flakiness shows up only in CI (item 5.6).

## Check yourself

1. A test stubs the repository to return the very order the service just saved, then asserts the service returned it. What does this test prove, and which double would make it prove something?
2. Classify each as mock, stub, fake or "use the real thing in an integration test", using the managed and unmanaged distinction: `Clock`, `OrderRepository`, `EmailSender`, `PaymentGateway`.
3. A team wants to "move from the pyramid to the trophy" for a Spring Boot service. What concretely changes in the suite, and what does not?
4. Describe one behaviour-preserving refactoring of `PlaceOrderService` that breaks the mock test, then say why the fake-based test survives and what the single place you must update is.

## Go deeper

- [Ham Vocke: The Practical Test Pyramid](https://martinfowler.com/articles/practical-test-pyramid.html) · the whole strategy with a Spring Boot example project; read it before anything else on testing.
- [Kent C. Dodds: The Testing Trophy and Testing Classifications](https://kentcdodds.com/blog/the-testing-trophy-and-testing-classifications) · the counter-proposal, and a good explanation of why "unit" is the contested word.
- [Unit Testing Principles, Practices, and Patterns](https://www.manning.com/books/unit-testing) · Khorikov on observable behaviour versus implementation details and the managed/unmanaged rule for mocks (paid).
- [Martin Fowler: Mocks Aren't Stubs](https://martinfowler.com/articles/mocksArentStubs.html) · the classicist versus mockist article; the "state verification versus behaviour verification" distinction is the heart of it.
- [xUnit Patterns: Test Double](http://xunitpatterns.com/Test%20Double.html) · Meszaros's original definitions of dummy, stub, fake, mock and spy.
- [Testcontainers](https://testcontainers.com/) and [Pact](https://docs.pact.io/) · real infrastructure for integration tests, and consumer-driven contracts for the seams between teams.
- [Growing Object-Oriented Software, Guided by Tests](http://www.growing-object-oriented-software.com/) · the mockist school at its best; read it to understand what mocks are for before deciding how little to use them (paid).

---

Part of [Architecture & Craft](../README.md) · items 5.1, 5.2, 5.3
