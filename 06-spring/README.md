# Spring

> Spring Framework and Spring Boot as used in production: the container, proxies and AOP, auto-configuration, MVC, transactions, Spring Data JPA and Hibernate internals, Spring Security, testing, observability, messaging and the operational side. Spring Boot 3.x and 4.x.

**Prerequisites:** [Java](../05-java/README.md), [Databases](../04-databases/README.md), [Web & HTTP](../02-web-and-http/README.md)

**Done when you can:**

- Explain what the container does at startup, how a bean becomes a proxy, and why a self-invoked `@Transactional` method does nothing.
- Debug an auto-configuration problem with the conditions evaluation report instead of guessing.
- Explain the persistence context, lazy loading, N+1 and its fixes, and pick the right fetch strategy for a given screen.
- Secure a REST API with Spring Security (stateless JWT resource server or session login) and explain every filter in the chain.
- Write fast, reliable tests with the right test slice and Testcontainers, and say what `@SpringBootTest` costs.
- Ship a Spring Boot service with health probes, metrics, tracing, graceful shutdown and sane configuration for containers.

## Roadmap

### 1. Spring Core: the container

- [ ] 1.1 Inversion of control and dependency injection: the problem they solve; constructor injection as the default · [Spring: The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html) · [Marco Behler: What is Spring Framework?](https://www.marcobehler.com/guides/spring-framework)
- [ ] 1.2 Defining beans: `@Configuration`/`@Bean`, component scanning and stereotypes, `@Qualifier`/`@Primary`, `ObjectProvider`, optional and collection injection · [Spring: Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [ ] 1.3 Scopes and lifecycle: singleton vs prototype vs request; `@PostConstruct`/`@PreDestroy`, `BeanPostProcessor`, `SmartLifecycle`, startup order · [Spring: Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html) · [Spring: Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [ ] 1.4 Proxies and AOP: JDK dynamic proxies vs CGLIB, `@Aspect` and pointcuts, the self-invocation problem, `final` methods · [notes](notes/transactional-in-depth.md) · [Spring: Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html) · [Spring: AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [ ] 1.5 Environment, profiles, properties and `@ConfigurationProperties`; relaxed binding; validating configuration at startup · [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [ ] 1.6 Application events, `@EventListener`, `@TransactionalEventListener`; `@Async` and `@Scheduled` and the executors behind them · [Spring: Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events) · [Spring: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [ ] 1.7 Circular dependencies and how to break them; `ApplicationContext` hierarchy; SpEL at a glance · [Spring: Spring Expression Language](https://docs.spring.io/spring-framework/reference/core/expressions.html)

### 2. Spring Boot

- [ ] 2.1 What Boot adds: starters, auto-configuration, opinionated defaults, embedded servers, the executable JAR · [Marco Behler: What is Spring Boot?](https://www.marcobehler.com/guides/spring-boot) · [Spring Boot Reference](https://docs.spring.io/spring-boot/index.html)
- [ ] 2.2 How auto-configuration works: `@Conditional*`, `AutoConfiguration.imports`, ordering, overriding a bean, the conditions evaluation report (`--debug`) · [Spring Boot: Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [ ] 2.3 Configuration precedence: properties, YAML, environment variables, command line, profiles, config trees and secrets · [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [ ] 2.4 Logging: Logback defaults, levels per package, structured JSON logging, MDC and correlation IDs · [Spring Boot: Logging](https://docs.spring.io/spring-boot/reference/features/logging.html)
- [ ] 2.5 Actuator: health groups and probes, info, metrics, env, loggers; securing the endpoints · [Spring Boot: Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [ ] 2.6 Packaging and running: layered JARs, buildpacks, Dockerfiles, graceful shutdown, JVM options in containers · [Spring Boot: Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html) · [Spring Boot: Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [ ] 2.7 Spring Initializr, DevTools, and upgrading across major versions (2 to 3 to 4) · [start.spring.io](https://start.spring.io/) · [Spring Boot wiki: release notes and migration guides](https://github.com/spring-projects/spring-boot/wiki)

### 3. Spring MVC and REST

- [ ] 3.1 The request lifecycle: `DispatcherServlet`, handler mappings, argument resolvers, message converters, exception resolvers · [Spring: DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- [ ] 3.2 Controllers: `@RestController`, request mapping, path/query/body binding, `ResponseEntity`, content negotiation, HTTP caching headers · [Spring: Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [ ] 3.3 Validation with Bean Validation (`@Valid`, groups, custom constraints) and consistent errors with `ProblemDetail` and `@ControllerAdvice` · [Spring: Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) · [Spring: Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [ ] 3.4 Filters vs interceptors vs AOP: where cross-cutting logic belongs; `OncePerRequestFilter`; CORS configuration · [Spring: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) · [Baeldung: HandlerInterceptor vs Filter](https://www.baeldung.com/spring-mvc-handlerinterceptor-vs-filter)
- [ ] 3.5 HTTP clients: `RestClient`, `WebClient`, HTTP interface clients; timeouts, connection pools, retries · [Spring: REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [ ] 3.6 File uploads, streaming responses, Server-Sent Events and WebSocket/STOMP support · [Spring: WebSockets](https://docs.spring.io/spring-framework/reference/web/websocket.html)
- [ ] 3.7 Embedded Tomcat tuning: threads, connection limits, keep-alive, request size; `spring.threads.virtual.enabled` · [Spring Boot: Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [ ] 3.8 API documentation and versioning: springdoc-openapi; Spring Framework 7's API versioning · [springdoc-openapi](https://springdoc.org/) · [Spring: API Versioning](https://docs.spring.io/spring-framework/reference/web/webmvc-versioning.html)

### 4. Data access and transactions

- [ ] 4.1 `DataSource` and HikariCP configuration; what a connection pool hides and what its metrics tell you · [Spring Boot: SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [ ] 4.2 `JdbcTemplate` and `JdbcClient`: when plain SQL is the right abstraction · [Spring: JdbcClient](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html#jdbc-JdbcClient) · [Marco Behler: JDBC guide](https://www.marcobehler.com/guides/jdbc)
- [ ] 4.3 `@Transactional` in depth: proxies and self-invocation, propagation, isolation, rollback rules (checked exceptions do not roll back), `readOnly`, timeouts, `TransactionTemplate` · [notes](notes/transactional-in-depth.md) · [Spring: Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html) · [Marco Behler: Spring Transaction Management](https://www.marcobehler.com/guides/spring-transaction-management) · [Vlad Mihalcea: Spring transaction best practices](https://vladmihalcea.com/spring-transaction-best-practices/)
- [ ] 4.4 Transaction boundaries in a layered application; `TransactionSynchronization`; transaction-bound events; why to avoid distributed transactions · [Spring: Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [ ] 4.5 Database migrations with Flyway or Liquibase in Boot; strategies for tests and production · [Spring Boot: Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)

### 5. JPA and Hibernate

- [ ] 5.1 The persistence context: entity states (transient, managed, detached, removed), first-level cache, flush modes, dirty checking · [Baeldung: JPA/Hibernate Persistence Context](https://www.baeldung.com/jpa-hibernate-persistence-context) · [Vlad Mihalcea: First-level cache](https://vladmihalcea.com/jpa-hibernate-first-level-cache/)
- [ ] 5.2 Entity mapping: identifier generation (`IDENTITY` vs `SEQUENCE` and batching), `@Version`, `equals`/`hashCode` for entities, embeddables · [Vlad Mihalcea: equals, hashCode and toString for entities](https://vladmihalcea.com/the-best-way-to-implement-equals-hashcode-and-tostring-with-jpa-and-hibernate/) · [Vlad Mihalcea: Identity, sequence and table generators](https://vladmihalcea.com/hibernate-identity-sequence-and-table-sequence-generator/)
- [ ] 5.3 Associations: `@ManyToOne` as the default, bidirectional sync methods, `@OneToMany` best practices, `@ManyToMany` pitfalls, cascade and `orphanRemoval` · [Vlad Mihalcea: The best way to map a @OneToMany](https://vladmihalcea.com/the-best-way-to-map-a-onetomany-association-with-jpa-and-hibernate/) · [Vlad Mihalcea: The best way to use @ManyToMany](https://vladmihalcea.com/the-best-way-to-use-the-manytomany-annotation-with-jpa-and-hibernate/)
- [ ] 5.4 Fetching: lazy vs eager, `LazyInitializationException`, N+1, `JOIN FETCH`, `@EntityGraph`, `@BatchSize`, `MultipleBagFetchException` · [Vlad Mihalcea: N+1 query problem](https://vladmihalcea.com/n-plus-1-query-problem/) · [Baeldung: Eager/Lazy Loading in Hibernate](https://www.baeldung.com/hibernate-lazy-eager-loading) · [Vlad Mihalcea: MultipleBagFetchException](https://vladmihalcea.com/hibernate-multiplebagfetchexception/)
- [ ] 5.5 Open Session in View: what it is, why Boot enables it by default, why to turn it off · [Vlad Mihalcea: The Open Session in View anti-pattern](https://vladmihalcea.com/the-open-session-in-view-anti-pattern/) · [Baeldung: Spring Open Session in View](https://www.baeldung.com/spring-open-session-in-view)
- [ ] 5.6 Queries: JPQL, Criteria, native queries, DTO projections, `Page` vs `Slice`, keyset pagination · [Spring Data JPA: Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) · [Vlad Mihalcea: DTO projections](https://vladmihalcea.com/the-best-way-to-map-a-projection-query-to-a-dto-with-jpa-and-hibernate/)
- [ ] 5.7 Write performance: JDBC batching, `persist` vs `merge` vs `saveAll`, flush and clear in bulk jobs, `@DynamicUpdate` · [Vlad Mihalcea: Batch processing with JPA and Hibernate](https://vladmihalcea.com/the-best-way-to-do-batch-processing-with-jpa-and-hibernate/)
- [ ] 5.8 Locking with JPA: `@Version` optimistic locking, `PESSIMISTIC_WRITE`, retrying on `OptimisticLockException` · [Baeldung: Optimistic Locking in JPA](https://www.baeldung.com/jpa-optimistic-locking) · [Baeldung: Pessimistic Locking in JPA](https://www.baeldung.com/jpa-pessimistic-locking)
- [ ] 5.9 Second-level and query caches: when they help; Hibernate statistics and SQL logging for finding problems · [Hibernate ORM documentation](https://hibernate.org/orm/documentation/)
- [ ] 5.10 Spring Data JPA: repositories, derived queries, `@Query`, `@Modifying`, specifications, auditing, custom fragments; when to drop to JDBC · [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) · [Baeldung: Spring Data JPA @Query](https://www.baeldung.com/spring-data-jpa-query)
- [ ] 5.11 Alternatives: Spring Data JDBC (aggregates, no lazy loading), jOOQ, MyBatis; choosing per module · [Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc.html) · [jOOQ](https://www.jooq.org/)

### 6. Spring Security

- [ ] 6.1 Architecture: the filter chain, `SecurityFilterChain` beans, `SecurityContextHolder`, `Authentication`, `AuthenticationManager`/`Provider`, `UserDetailsService`, `PasswordEncoder` · [Spring Security: Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html) · [Spring Security Architecture (topical guide)](https://spring.io/guides/topicals/spring-security-architecture) · [Marco Behler: Spring Security](https://www.marcobehler.com/guides/spring-security)
- [ ] 6.2 Authentication styles: form login with sessions, HTTP Basic, stateless bearer tokens; session fixation, remember-me, logout · [Spring Security: Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html)
- [ ] 6.3 Authorization: request matchers, method security with `@PreAuthorize`, roles vs authorities, custom expressions · [Spring Security: Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [ ] 6.4 CSRF and CORS in Spring Security: when CSRF protection is needed (cookie authentication) and when not (bearer tokens); SPA setups · [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) · [Spring Security: CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [ ] 6.5 OAuth2 and OpenID Connect: resource server with JWT validation, OAuth2 login and client, scopes to authorities, Spring Authorization Server · [Spring Security: OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) · [Spring Security: OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html) · [Spring Authorization Server](https://docs.spring.io/spring-authorization-server/reference/)
- [ ] 6.6 Password storage with `DelegatingPasswordEncoder` (bcrypt, Argon2), security headers, and testing security (`@WithMockUser`, request post-processors) · [Spring Security: Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html) · [Spring Security: Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)

### 7. Testing Spring applications

- [ ] 7.1 Test slices: `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@RestClientTest`; what each loads and what it leaves out · [Spring Boot: Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) · [rieckpil: Spring Boot testing guides](https://rieckpil.de/)
- [ ] 7.2 `@SpringBootTest`: web environments, `TestRestTemplate` and `WebTestClient`, context caching, and why one more mock bean slows the whole build · [Spring Boot: Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [ ] 7.3 `MockMvc` and `MockMvcTester` for controllers; testing validation and error responses · [Spring: MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html)
- [ ] 7.4 Testcontainers with `@ServiceConnection`; realistic data-layer tests; `@Sql` fixtures · [Spring Boot: Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [ ] 7.5 Test doubles: `@MockitoBean`, `@MockitoSpyBean`, `@TestConfiguration`; when a real bean is the better test · [Spring: Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [ ] 7.6 Testing transactions honestly: why `@Transactional` on tests hides lazy-loading bugs; `TestTransaction`; `TransactionTemplate` in tests · [Spring: Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)

### 8. Observability and operations

- [ ] 8.1 Micrometer metrics: counters, timers, gauges, tags and cardinality; Prometheus endpoint; HTTP, JVM and `DataSource` metrics out of the box · [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) · [Micrometer](https://micrometer.io/)
- [ ] 8.2 Tracing with Micrometer Tracing and OpenTelemetry; context propagation across threads and HTTP calls · [Spring Boot: Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [ ] 8.3 Kubernetes liveness and readiness probes, startup time, graceful shutdown, and locking down `/actuator` · [Spring Boot: Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [ ] 8.4 Resilience: timeouts everywhere, retries with backoff, circuit breakers and bulkheads (Resilience4j; Spring Framework 7's `@Retryable` and `@ConcurrencyLimit`) · [Resilience4j](https://resilience4j.readme.io/) · [Spring: Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html)
- [ ] 8.5 Caching with `@Cacheable`: providers (Caffeine, Redis), keys, TTLs, invalidation · [Spring Boot: Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)

### 9. Messaging and integration

- [ ] 9.1 Spring for Apache Kafka: producers, consumers and groups, acknowledgement modes, error handling and dead-letter topics, idempotent consumers · [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/)
- [ ] 9.2 Spring AMQP (RabbitMQ) and Spring Cloud Stream at a glance · [Spring AMQP](https://docs.spring.io/spring-amqp/reference/)
- [ ] 9.3 Reliable publishing: the transactional outbox with Spring Modulith events or Debezium · [Spring Modulith: Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [ ] 9.4 Spring Batch: jobs, steps, chunk processing, restartability · [Spring Batch](https://docs.spring.io/spring-batch/reference/)

### 10. Architecture with Spring

- [ ] 10.1 Package by feature, hexagonal structure in a Boot application, keeping Spring annotations out of the domain · [reflectoring: Hexagonal Architecture with Spring Boot](https://reflectoring.io/spring-hexagonal/)
- [ ] 10.2 Modular monoliths with Spring Modulith: module boundaries, verification tests, events, documentation · [Spring Modulith](https://docs.spring.io/spring-modulith/reference/)
- [ ] 10.3 Spring Cloud at a glance: config, gateway, discovery, circuit breakers; what Kubernetes replaced · [Spring Cloud](https://spring.io/projects/spring-cloud)
- [ ] 10.4 Reactive Spring (WebFlux, R2DBC) vs virtual threads: choosing for a new service · [Spring: WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [ ] 10.5 Spring AI at a glance: chat clients, structured output, tool calling, RAG with vector stores (details in AI Engineering) · [Spring AI Reference](https://docs.spring.io/spring-ai/reference/)
- [ ] 10.6 What changed in Spring Framework 7 and Boot 4: JSpecify nullness, API versioning, Jackson 3, resilience annotations, modular Boot artifacts · [Spring Blog](https://spring.io/blog)

## Resources

### Start here

- [Spring Boot Reference](https://docs.spring.io/spring-boot/index.html) and [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/) · the official docs are complete and current; read the chapters linked from the roadmap items.
- [Marco Behler's Spring guides](https://www.marcobehler.com/guides) · long-form explanations of the Framework, Boot, Security and transactions that build the mental model the docs assume.
- [Spring Academy](https://spring.academy/) · free official courses, including Spring Boot and Spring Security hands-on tracks.
- [Vlad Mihalcea's blog](https://vladmihalcea.com/blog/) · the JPA/Hibernate and transaction content in this roadmap is built on it.
- [Spring Security Architecture](https://spring.io/guides/topicals/spring-security-architecture) · the topical guide that makes the filter chain click.

### Books

- [Spring in Action, 6th edition](https://www.manning.com/books/spring-in-action-sixth-edition) · Craig Walls (paid).
- [Spring Start Here](https://www.manning.com/books/spring-start-here) · Laurențiu Spilcă; the clearest first book on the container and Boot (paid).
- [Spring Security in Action, 2nd edition](https://www.manning.com/books/spring-security-in-action-second-edition) · Laurențiu Spilcă (paid).
- [High-Performance Java Persistence](https://vladmihalcea.com/books/high-performance-java-persistence/) · Vlad Mihalcea (paid).
- [Java Persistence with Spring Data and Hibernate](https://www.manning.com/books/java-persistence-with-spring-data-and-hibernate) · Cătălin Tudose (paid).

### Courses and videos

- [Coffee + Software with Josh Long](https://www.youtube.com/@coffeesoftware) · Spring Tips and live coding from the Spring team's developer advocate.
- [Dan Vega](https://www.youtube.com/@DanVega) · practical Spring Boot videos, current with each release.
- [Spring Developer](https://www.youtube.com/@SpringSourceDev) · official channel with conference talks and release deep dives.
- [Laur Spilcă](https://www.youtube.com/@laurspilca) · Spring Security explained from first principles.
- [Spring I/O](https://www.youtube.com/@SpringIOConference) · the main Spring conference; talks are published every year.
- [Thorben Janssen](https://thorben-janssen.com/) · JPA and Hibernate tutorials.
- [rieckpil](https://rieckpil.de/) · Philip Riecks on testing Spring Boot applications properly.

### References

- [Spring Guides](https://spring.io/guides) · 15-minute hands-on guides for nearly every integration.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) and [Spring Security Reference](https://docs.spring.io/spring-security/reference/) · the primary sources for sections 5 and 6.
- [Hibernate ORM documentation](https://hibernate.org/orm/documentation/) · the user guide explains the persistence context and fetching in depth.
- [Baeldung: Spring tutorials](https://www.baeldung.com/spring-tutorial) · focused examples for almost every Spring feature; check the Boot version each article targets.
- [Spring PetClinic](https://github.com/spring-projects/spring-petclinic) · the reference sample application, kept current with each release.
- [roadmap.sh: Spring Boot](https://roadmap.sh/spring-boot) · visual overview.
