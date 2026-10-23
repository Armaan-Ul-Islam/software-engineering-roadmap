# Testing Spring Boot applications

> **In one sentence:** Pick the smallest context that exercises the code under test (a slice for one layer, `@SpringBootTest` for a full flow), keep that context identical across as many test classes as possible so Spring can reuse it, and run the real database in a Testcontainers container wired through `@ServiceConnection` rather than an in-memory stand-in.

**Why it matters:** A Spring test suite gets slow in one specific way: every test class that differs by a single mock bean or property forces a new application context, and each context costs seconds and a few hundred megabytes. Teams end up with a twenty-minute build and the conclusion that "Spring tests are slow". They are not; uncached contexts are. The second failure is testing against H2 and shipping SQL that PostgreSQL rejects.

## The idea

**Test slices** load one layer of the application and nothing else:

| Annotation | Loads | Leaves out | Typical use |
|---|---|---|---|
| `@WebMvcTest(OrderController.class)` | that controller, every `@ControllerAdvice`, `Filter`, `WebMvcConfigurer`, `Converter`, Jackson, Spring Security's auto-configuration, `MockMvc` | `@Service`, `@Repository`, `@Component` beans; the database | request mapping, binding, validation, error bodies, security rules |
| `@DataJpaTest` | `@Entity` classes, Spring Data repositories, `EntityManager`, `TestEntityManager`, Flyway or Liquibase | web layer, services | mappings, queries, constraints; runs each test in a transaction that is rolled back |
| `@JsonTest` | `ObjectMapper`, `@JsonComponent`s, `JacksonTester` | everything else | serialisation shapes, date formats |
| `@RestClientTest(PaymentsClient.class)` | the client, `RestClient.Builder`, `MockRestServiceServer` | everything else | outbound HTTP calls and their error handling |

Dependencies the slice does not load must be replaced: `@MockitoBean OrderService orderService` in a `@WebMvcTest` (Spring Framework 6.2 and Boot 3.4; `@MockBean` before that). `@DataJpaTest` replaces your `DataSource` with an embedded database by default; from Boot 3.4 the default (`Replace.NON_TEST`) leaves a Testcontainers-backed `DataSource` alone, and before that you needed `@AutoConfigureTestDatabase(replace = Replace.NONE)`. Note also that its rollback-per-test hides flush-time problems; call `TestEntityManager.flush()` when the test is about what gets written (item 7.6).

**`@SpringBootTest`** loads the whole application. `webEnvironment` decides how much of the web stack is real: `MOCK` (the default) gives a mock servlet environment for `MockMvc` with `@AutoConfigureMockMvc`; `RANDOM_PORT` starts the embedded server on a free port and provides `TestRestTemplate` (or `WebTestClient`, which needs WebFlux on the classpath); `DEFINED_PORT` uses the configured port; `NONE` skips the web layer. Use it for flows that cross layers: request in, rows in the database, event published.

**Context caching.** The test framework builds a key from everything that defines the context: the configuration classes, active profiles, `properties`, `@Import`s, `@TestPropertySource`, `@DynamicPropertySource`, and every bean override (`@MockitoBean`, `@MockitoSpyBean`). Test classes with the same key share one context for the whole JVM. A class with one extra `@MockitoBean` has a different key and gets its own context, so ten `@SpringBootTest` classes with ten different mock sets start the application ten times. The cache holds 32 contexts by default and evicts the least recently used one. Enable `logging.level.org.springframework.test.context.cache=DEBUG` to see `hitCount` and `missCount` after a run; a `missCount` close to the number of test classes is the diagnosis. The cure is uniformity: one abstract base class carrying the shared `@SpringBootTest`, `@Import` and mock declarations, fakes provided through a shared `@TestConfiguration` instead of per-class mocks, and no `@DirtiesContext`.

**Testcontainers.** `@ServiceConnection` (Boot 3.1 and later) on a container bean or a static `@Container` field makes Boot derive the connection properties (`spring.datasource.url`, username, password, or the Redis, Kafka and RabbitMQ equivalents) from the running container, replacing the `@DynamicPropertySource` boilerplate. Declaring the container as a `@Bean` in a `@TestConfiguration` ties its lifecycle to the cached context, so one PostgreSQL container serves every test class that shares the context. This is what Spring Initializr generates when you tick Testcontainers. `@Sql` loads fixtures per test or class, and Flyway runs your real migrations against the real engine on startup.

**`@TestConfiguration`** is a `@Configuration` that component scanning ignores. A nested static class inside a test is picked up automatically; a top-level one must be `@Import`ed. It is where fakes live: a fixed `Clock`, an in-memory `PaymentGateway`, a container bean. Prefer a fake you control over `@MockitoBean` when several classes need the same replacement; it keeps the cache key stable and the behaviour explicit.

## Example: a controller slice

The controller under test exposes `POST /api/orders`, takes `{"productId", "quantity"}` with `@Valid` constraints, and relies on the advice from item 3.3 for the error body.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returns201WithTheCreatedOrder() throws Exception {
        when(orderService.place(any())).thenReturn(new OrderResponse(7L, OrderStatus.NEW));

        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": 42, "quantity": 2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(7))
            .andExpect(jsonPath("$.status").value("NEW"));
    }

    @Test
    void returns400WhenQuantityIsNotPositive() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": 42, "quantity": 0}
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentType(MediaType.APPLICATION_PROBLEM_JSON))
            .andExpect(jsonPath("$.errors[0].field").value("quantity"));

        verifyNoInteractions(orderService);
    }
}
```

If Spring Security is on the classpath, the slice secures every request; add `.with(jwt())` or `@WithMockUser` and, for cookie-based chains, `.with(csrf())` (items 6.5 and 6.6). This class runs in well under a second once the JVM is warm.

## Example: a full flow against PostgreSQL

```java
@TestConfiguration(proxyBeanMethods = false)
public class TestcontainersConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
```

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestcontainersConfiguration.class)
@Sql("/fixtures/one-product.sql")
class OrderFlowIntegrationTest {

    @Autowired
    private TestRestTemplate restTemplate;

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void placesAnOrderAndPersistsIt() {
        ResponseEntity<OrderResponse> response = restTemplate.postForEntity(
                "/api/orders", new PlaceOrderRequest(42L, 2), OrderResponse.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        OrderResponse body = response.getBody();
        assertThat(body).isNotNull();
        assertThat(orderRepository.findById(body.id()))
                .hasValueSatisfying(order -> assertThat(order.getLines()).hasSize(1));
    }
}
```

Dependencies: `spring-boot-starter-test`, `spring-boot-testcontainers`, `org.testcontainers:postgresql`. On startup Boot starts the container, points the `DataSource` at its mapped port, Flyway applies the migrations, and the test talks to the real server over HTTP. Every other `@SpringBootTest` class that uses the same `@Import` and no extra overrides reuses this context and this container. Reading `order.getLines()` works here because the repository call runs in its own transaction and the collection is accessed through the entity returned by `findById`; a lazy collection read outside any transaction would throw, which is the honest behaviour you want tests to show (item 7.6).

## Pitfalls

- A `@MockitoBean` per test class "just for this one case". Each unique combination is a new context. Group mocks in a base class or replace them with a shared fake.
- `@DirtiesContext` as a cleanup strategy. It destroys the cached context after the class; use `@Sql` scripts or `@Transactional` test methods to reset data instead.
- H2 in tests, PostgreSQL in production. `jsonb`, `on conflict`, sequences with increments, and timestamp semantics differ; the suite is green and the deploy fails.
- A static `@Container` field combined with a cached context. Testcontainers stops the container after the class while the cached context still points at its old port, and the next class fails to connect. Use the `@TestConfiguration` bean, or a singleton container that is started once and never stopped (Ryuk removes it when the JVM exits).
- `@SpringBootTest` for a controller's validation rules. A `@WebMvcTest` runs in a fraction of the time and fails with a clearer message.
- Testing with `@Transactional` on the test class and never flushing. Constraint violations and lazy-loading errors only appear at flush or after commit, which the rollback skips.
- Asserting on log output or on mock interactions instead of on the response and the database. Those tests break on every refactoring and prove little.

## Check yourself

1. Two `@SpringBootTest` classes differ only in that one declares `@MockitoBean EmailSender`. How many contexts start, and how would you confirm it from the logs?
2. Which slice would you use to test that a `@Query` with `join fetch` returns initialised collections, and what single call makes the test honest about flush-time errors?
3. Why does `@ServiceConnection` on a `@TestConfiguration` bean cooperate with context caching better than `@DynamicPropertySource` with a static `@Container` field?
4. A validation test for a controller is written as a `@SpringBootTest` with `RANDOM_PORT`. What does it cost compared with a `@WebMvcTest`, and what does it prove that the slice cannot?

## Go deeper

- [Spring Boot: Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) · the slice annotations with the full list of what each includes.
- [Spring Boot: Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) · `@SpringBootTest`, web environments, `TestRestTemplate`, bean overriding and configuration detection.
- [Spring Boot: Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) · `@ServiceConnection`, the test configuration approach and development-time containers.
- [Spring: Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html) · exactly which attributes form the cache key.
- [rieckpil: Spring Boot testing guides](https://rieckpil.de/) · Philip Riecks' articles on slices, Testcontainers and keeping suites fast.

---

Part of [Spring](../README.md) · items 7.1, 7.2, 7.4, 7.5
