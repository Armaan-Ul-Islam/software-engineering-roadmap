# Testing with JUnit 5, Mockito and Testcontainers

> **In one sentence:** JUnit 5 runs every test method on a fresh instance with `@BeforeEach` and `@AfterEach` around it, parameterised tests replace copy-pasted cases, AssertJ gives readable assertions and failure messages, Mockito replaces the collaborators you cannot or should not run (stubs supply inputs, mocks verify outputs, spies are a warning sign), and Testcontainers gives you the real database in a throwaway container so the integration test proves the SQL instead of mocking it away.

**Why it matters:** A suite is only useful if it is fast enough to run on every change and trustworthy enough to act on. Teams drift into slow suites nobody runs locally, mocks that mirror the implementation and break on every refactor, and H2-backed tests that pass while the PostgreSQL query fails. A handful of container-backed integration tests plus many millisecond unit tests is the shape of a healthy backend suite, and "stub versus mock, and when is mocking a smell" is a standard interview question because it reveals whether you test behaviour or implementation.

## The idea

**JUnit 5 lifecycle.** By default JUnit creates a new test class instance per test method, so fields are fresh and tests cannot share state by accident. `@BeforeEach` and `@AfterEach` wrap each method; `@BeforeAll` and `@AfterAll` wrap the class and must be `static` unless you opt into `@TestInstance(Lifecycle.PER_CLASS)`. `@Nested` inner classes group related cases with their own setup, and `@ExtendWith` plugs in extensions (Mockito, Testcontainers, Spring). A `@ParameterizedTest` runs once per argument set from `@ValueSource`, `@CsvSource`, `@EnumSource`, `@MethodSource` or `@NullAndEmptySource`; the `junit-jupiter` aggregate artifact includes the params module.

**AssertJ.** `assertThat(actual).isEqualTo(expected)` reads in the right order, chains (`.contains`, `.hasSize`, `.extracting`), handles `Optional`, collections and exceptions (`assertThatThrownBy`), and fails with messages like `Expected size: 1 but was: 2 in: [10.00 NOK, 10.00 NOK]`. Custom assertions for domain types are a small step further (see item 7.2).

**Stubs, mocks, spies.** A *stub* answers calls with canned values: `when(orderRepository.findById(42L)).thenReturn(Optional.of(order))` supplies an indirect input. A *mock* is verified: `verify(orderRepository).save(...)` checks an indirect output, and `ArgumentCaptor` lets you assert on what was passed. Mockito uses one object for both roles. A *spy* wraps a real object and stubs selected methods; needing one usually means the unit under test is too large. With `@ExtendWith(MockitoExtension.class)`, `@Mock` fields are created and `@InjectMocks` builds the class under test through its constructor; the extension uses strict stubs, so a stub that no test path uses fails with `UnnecessaryStubbingException`, which keeps tests honest. Mockito 5 mocks final classes out of the box. On JDK 21 and later Mockito attaches its agent at runtime and warns that future JDKs will refuse this; the fix is to pass the agent to Surefire:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-dependency-plugin</artifactId>
  <executions>
    <execution>
      <goals>
        <goal>properties</goal>
      </goals>
    </execution>
  </executions>
</plugin>
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-javaagent:${org.mockito:mockito-core:jar}</argLine>
  </configuration>
</plugin>
```

**When mocking is a smell.** Mocking value objects (construct them), mocking types you do not own (JDBC, HTTP clients: use a container or a fake server), stubbing methods of the class under test through a spy, verifying every interaction so the test is a transcript of the implementation, and deep stubs (`when(a.getB().getC())`). Mock at architectural boundaries, the ports of your application (repositories, gateways, clocks, message publishers), and test domain logic with real objects.

**Testcontainers.** The `@Testcontainers` extension starts every `@Container` field: a `static` field is started once before the class and stopped after it, an instance field per test. `PostgreSQLContainer` exposes `getJdbcUrl()`, `getUsername()` and `getPassword()`, and the Ryuk sidecar removes containers when the JVM exits, even after a crash. Testcontainers 2.x moved the modules to `org.testcontainers:testcontainers-postgresql` and `org.testcontainers:testcontainers-junit-jupiter` (managed by `testcontainers-bom`) and the class to `org.testcontainers.postgresql.PostgreSQLContainer`, which no longer has a type parameter; the generic `org.testcontainers.containers.PostgreSQLContainer<?>` from 1.x is deprecated. A real PostgreSQL catches what H2 cannot: `ON CONFLICT`, `jsonb`, `timestamptz` semantics, constraint and isolation behaviour.

**Keeping it fast.** Unit tests run in milliseconds with no framework context; keep most tests there. Start one container per test class (static field) or per JVM (a shared static container in a base class), and reset data between tests with `TRUNCATE` or a rolled-back transaction. Put container tests in Failsafe (`*IT` classes, `mvn verify`) so `mvn test` stays quick, and enable JUnit's parallel execution for independent classes.

## Example: a unit test with a mock

The class under test loads an order, charges the customer and marks the order paid when the charge is approved:

```java
public PaymentResult pay(long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));
    PaymentResult result = paymentGateway.charge(order.customerId(), order.total());
    if (result.approved()) {
        orderRepository.save(order.markPaid());
    }
    return result;
}
```

```java
@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock
    private OrderRepository orderRepository;

    @Mock
    private PaymentGateway paymentGateway;

    @InjectMocks
    private OrderService orderService;

    @Test
    void chargesTheOrderTotalAndMarksTheOrderPaid() {
        Order order = new Order(42L, "alice", new BigDecimal("99.90"), OrderStatus.NEW);
        when(orderRepository.findById(42L)).thenReturn(Optional.of(order));
        when(paymentGateway.charge("alice", new BigDecimal("99.90"))).thenReturn(new PaymentResult(true, "ref-1"));

        PaymentResult result = orderService.pay(42L);

        assertThat(result.approved()).isTrue();
        ArgumentCaptor<Order> savedOrder = ArgumentCaptor.forClass(Order.class);
        verify(orderRepository).save(savedOrder.capture());
        assertThat(savedOrder.getValue().status()).isEqualTo(OrderStatus.PAID);
    }

    @Test
    void doesNotChargeWhenTheOrderDoesNotExist() {
        when(orderRepository.findById(7L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> orderService.pay(7L))
            .isInstanceOf(OrderNotFoundException.class)
            .hasMessage("No order with id 7");
        verifyNoInteractions(paymentGateway);
    }

    @ParameterizedTest(name = "approved={0} saves={1}")
    @CsvSource({"true, 1", "false, 0"})
    void savesOnlyApprovedPayments(boolean approved, int expectedSaves) {
        Order order = new Order(1L, "bob", new BigDecimal("10.00"), OrderStatus.NEW);
        when(orderRepository.findById(1L)).thenReturn(Optional.of(order));
        when(paymentGateway.charge("bob", new BigDecimal("10.00"))).thenReturn(new PaymentResult(approved, "ref-2"));

        orderService.pay(1L);

        verify(orderRepository, times(expectedSaves)).save(order.markPaid());
    }
}
```

Static imports: `assertThat` and `assertThatThrownBy` from `org.assertj.core.api.Assertions`; `when`, `verify`, `verifyNoInteractions` and `times` from `org.mockito.Mockito`.

## Example: an integration test with Testcontainers

`JdbcOrderRepository` implements `OrderRepository` with plain JDBC over a `DataSource` and an `INSERT ... ON CONFLICT (id) DO UPDATE` in `save`. The test runs it against a real PostgreSQL 16:

```java
@Testcontainers
class JdbcOrderRepositoryIntegrationTest {

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:16");

    private static JdbcOrderRepository orderRepository;

    @BeforeAll
    static void createSchema() throws SQLException {
        PGSimpleDataSource dataSource = new PGSimpleDataSource();
        dataSource.setUrl(POSTGRES.getJdbcUrl());
        dataSource.setUser(POSTGRES.getUsername());
        dataSource.setPassword(POSTGRES.getPassword());
        try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE orders (
                    id bigint PRIMARY KEY,
                    customer_id text NOT NULL,
                    total numeric(12, 2) NOT NULL,
                    status text NOT NULL
                )
                """);
        }
        orderRepository = new JdbcOrderRepository(dataSource);
    }

    @Test
    void savesAndReloadsAnOrder() {
        Order order = new Order(1L, "alice", new BigDecimal("99.90"), OrderStatus.NEW);

        orderRepository.save(order);
        orderRepository.save(order.markPaid());

        assertThat(orderRepository.findById(1L)).contains(order.markPaid());
    }

    @Test
    void returnsEmptyForAnUnknownId() {
        assertThat(orderRepository.findById(404L)).isEmpty();
    }
}
```

Test-scoped dependencies: `org.junit.jupiter:junit-jupiter`, `org.assertj:assertj-core`, `org.mockito:mockito-junit-jupiter`, `org.testcontainers:testcontainers-junit-jupiter`, `org.testcontainers:testcontainers-postgresql` and `org.postgresql:postgresql`. Running both classes with `mvn test`:

```text
[INFO] tc.postgres:16 - Container postgres:16 started in PT1.081545S
[INFO] Tests run: 2, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 2.950 s -- in com.example.orders.JdbcOrderRepositoryIntegrationTest
[INFO] Tests run: 4, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.340 s -- in com.example.orders.OrderServiceTest
```

The first run also pulls the image, which takes a minute; after that a container is up in about a second.

## Pitfalls

- Stubbing with `any()` everywhere. `when(gateway.charge(any(), any()))` passes even when the service charges the wrong customer; stub with the values you expect.
- `verifyNoMoreInteractions` and `verify` on every call. The test now fails on any refactor that changes call order or count without changing behaviour.
- Mocking the repository in a test whose purpose is the query. The SQL is the thing that can be wrong; use the container.
- A `@Container` instance field by habit. A fresh PostgreSQL per test method turns a two-second class into a two-minute one.
- Testcontainers 1.x against a current Docker Engine. On the machine used for this note, 1.21 failed with `Could not find a valid Docker environment` (the daemon rejected the old API version) while 2.0 worked; upgrade before debugging Docker.
- `Thread.sleep` to wait for asynchronous work. Flaky and slow; poll with a timeout instead.

## Check yourself

1. Why must `@BeforeAll` methods be `static` by default, and what does switching to `PER_CLASS` change about test isolation?
2. In the unit test, which `when` calls are stubs and which `verify` calls make the test a mock-based test? What would a spy add, and why is that a warning sign?
3. A colleague replaces the Testcontainers test with an H2 in-memory database "because it is faster". Name two things in `JdbcOrderRepository` that H2 would not test faithfully.
4. Your suite takes twelve minutes because each integration test class starts its own container. What are two ways to cut that without reducing coverage?

## Go deeper

- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) · lifecycle, parameterised tests, nested tests and the extension model.
- [AssertJ documentation](https://assertj.github.io/doc/) · every assertion type, plus how to write custom assertions.
- [Mockito](https://site.mockito.org/) · the Javadoc of the `Mockito` class is the real manual, including the Java 21 agent instructions.
- [Baeldung: Mockito Series](https://www.baeldung.com/mockito-series) · worked examples of captors, spies, `@InjectMocks` and common errors.
- [Testcontainers for Java](https://java.testcontainers.org/) · the JUnit 5 extension, database modules, reuse and the singleton container pattern.

---

Part of [Java](../README.md) · items 7.1, 7.3, 7.4
