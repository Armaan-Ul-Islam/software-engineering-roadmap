# The IoC container and dependency injection

> **In one sentence:** The Spring container reads bean definitions, builds every singleton in dependency order, hands each bean its collaborators through its constructor, runs the lifecycle callbacks, and wraps the bean in a proxy where needed, so your classes only declare what they need and never look anything up.

**Why it matters:** Almost every "Spring is doing something weird" problem is a container question: a bean that was not created, two candidates for one type, a `@PostConstruct` that runs before you expected, a prototype that behaves like a singleton. Knowing the startup sequence turns those from mysteries into a five-minute read of one error message. Interviewers ask "what happens when a Spring Boot application starts" precisely because most people cannot answer past "it scans for annotations".

## The idea

Dependency injection is the simple half: a class declares its collaborators as constructor parameters and somebody else supplies them. Inversion of control is the consequence: the "somebody else" is the container, and it also decides when objects are created, in which order, and how long they live.

At startup the `ApplicationContext` works in two phases.

1. **Define.** Component scanning finds classes annotated with `@Component` and its stereotypes (`@Service`, `@Repository`, `@Controller`, `@Configuration`) under the base package; `@Bean` methods and auto-configuration add more. The result is a `BeanDefinition` per bean: class, scope, constructor arguments, init and destroy methods. No instance exists yet. `BeanFactoryPostProcessor`s (property placeholder resolution, `@Configuration` class parsing) may still change the definitions.
2. **Instantiate.** The container creates every non-lazy singleton. For each bean, in this order:
   - 2.1 Resolve the constructor arguments, creating those beans first (recursively), then call the constructor.
   - 2.2 Inject `@Autowired` fields and setters.
   - 2.3 Call the `Aware` interfaces (`BeanNameAware`, `ApplicationContextAware`).
   - 2.4 Run every `BeanPostProcessor.postProcessBeforeInitialization`, which is where `@PostConstruct` methods are invoked.
   - 2.5 Call `InitializingBean.afterPropertiesSet()` and any `@Bean(initMethod = ...)`.
   - 2.6 Run every `BeanPostProcessor.postProcessAfterInitialization`. This is where proxies are created: `@Transactional`, `@Async`, `@Cacheable` and `@Aspect` advice all replace the bean with a wrapper here (see item 1.4).

After all singletons exist, `SmartLifecycle.start()` runs for beans that implement it (ordered by phase), `ContextRefreshedEvent` is published, and in Boot the `ApplicationRunner`/`CommandLineRunner` beans run, followed by `ApplicationReadyEvent`. On shutdown the order reverses: `SmartLifecycle.stop()`, then `@PreDestroy`, `DisposableBean.destroy()` and `destroyMethod` for every singleton.

Two consequences of step 2.6 bite constantly. Inside the constructor and `@PostConstruct`, `this` is the raw object, not the proxy, so calling your own `@Transactional` method from there runs without a transaction. And a bean you keep a reference to from inside another bean's constructor may be the raw object if a proxy is only created later; always let the container inject, never cache beans by hand.

**Constructor injection is the default.** A single constructor needs no `@Autowired`. Fields can be `final`, the object is never half-initialised, a test can call `new`, and a circular dependency fails at startup with `BeanCurrentlyInCreationException` instead of being papered over (Boot has forbidden circular references by default since 2.6 for this reason). Field injection hides dependencies in the class body, requires reflection to test, and allows cycles. Setter injection is for genuinely optional collaborators.

**Choosing among candidates.** When several beans implement the interface, injection fails with `NoUniqueBeanDefinitionException`. Resolve it with `@Primary` on the usual choice, `@Qualifier("name")` at the injection point, or by naming the parameter like the bean (this needs the `-parameters` compiler flag, which the Spring Boot build plugins set). Spring Framework 6.2 added `@Fallback`, the inverse of `@Primary`: a bean chosen only when no other candidate exists.

**`ObjectProvider<T>`** is the lazy, optional, plural form of a dependency. `getIfAvailable()` returns null when no bean exists, `getIfUnique()` tolerates several candidates, `orderedStream()` iterates all of them, and `getObject()` on a prototype gives a fresh instance each time. Injecting `List<Handler>` gives every bean of that type ordered by `@Order`; `Map<String, Handler>` keys them by bean name. `Optional<T>` and `@Autowired(required = false)` also express optionality.

**Scopes.** `singleton` (one per container, not per JVM) is the default; `prototype` gives a new instance on every injection or lookup, and the container never calls destroy callbacks on prototypes. The web scopes (`request`, `session`, `application`) only exist in a web context. Injecting a shorter-lived bean into a singleton requires a scoped proxy (`@RequestScope` turns one on by default) or an `ObjectProvider` lookup; otherwise the singleton keeps the first instance forever.

## Example: one service, three wirings

```java
@Service
public class InvoiceService {                       // 1. field injection: avoid

    @Autowired
    private InvoiceRepository invoiceRepository;

    @Autowired
    private Clock clock;
}

@Service
public class InvoiceService {                       // 2. setter injection: only for optional parts

    private InvoiceRepository invoiceRepository;

    @Autowired
    public void setInvoiceRepository(InvoiceRepository invoiceRepository) {
        this.invoiceRepository = invoiceRepository;
    }
}

@Service
public class InvoiceService {                       // 3. constructor injection: the default

    private final InvoiceRepository invoiceRepository;
    private final Clock clock;

    public InvoiceService(InvoiceRepository invoiceRepository, Clock clock) {
        this.invoiceRepository = invoiceRepository;
        this.clock = clock;
    }

    public Invoice issue(Order order) {
        return invoiceRepository.save(Invoice.forOrder(order, clock.instant()));
    }
}
```

`Clock` is not a Spring class, so somebody has to define it once:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

The payoff shows in the test, which needs no container at all:

```java
InvoiceService invoiceService = new InvoiceService(new InMemoryInvoiceRepository(), Clock.fixed(Instant.parse("2026-10-24T10:00:00Z"), ZoneOffset.UTC));
```

## Example: why was my bean not created?

Forget the `TimeConfiguration` class and Boot fails fast with its failure analyser:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Parameter 1 of constructor in com.example.billing.InvoiceService required a bean of type 'java.time.Clock' that could not be found.

Action:

Consider defining a bean of type 'java.time.Clock' in your configuration.
```

Work through the causes in this order:

1. The class is outside the scanned package. Scanning starts at the package of the `@SpringBootApplication` class and goes down; a class in a sibling package is invisible.
2. The class has no stereotype annotation, or the `@Bean` method sits in a class that is itself not a bean.
3. A condition excluded it: `@Profile("prod")` with a different active profile, or a `@ConditionalOn...` that did not match. Start with `--debug` and read the conditions evaluation report (item 2.2).
4. You are in a test slice. `@WebMvcTest` loads controllers and web infrastructure only; services must be mocked (item 7.1).
5. The bean exists but under another type. `applicationContext.getBeanNamesForType(Clock.class)` or the Actuator `beans` endpoint (item 2.5) shows what the container actually holds.

## Pitfalls

- Doing real work in a constructor or `@PostConstruct`: opening connections, warming caches, calling remote systems. The context is half-built, `this` is not yet proxied, and a failure aborts startup with a confusing stack. Use `SmartLifecycle` or an `ApplicationRunner`, which run after everything is wired.
- Assuming `@Order` controls creation order. It orders collection injection and advice; creation order follows dependencies. Use `@DependsOn` for a dependency the constructor does not express, such as a bean that registers a JDBC driver.
- Injecting a prototype into a singleton and expecting a new instance per call. You get exactly one, created when the singleton was. Inject `ObjectProvider<Worker>` and call `getObject()`.
- `@Autowired` on a field in a class instantiated with `new`. The container never saw that object, so the field stays null. If you need to construct it yourself, pass the dependencies in.
- Two `@Configuration` classes defining a bean with the same name. Boot refuses by default (`BeanDefinitionOverrideException`); fix the name rather than enabling `spring.main.allow-bean-definition-overriding`.

## Check yourself

1. A `@Service` calls its own `@Transactional` method from `@PostConstruct`. Does a transaction start? Which step in the startup sequence explains the answer?
2. Two beans implement `PaymentGateway`. Name three ways to make injection unambiguous and say which you would choose for a default-plus-override situation.
3. Why does constructor injection make a circular dependency a startup error, and why is that preferable to the field-injection behaviour?
4. You inject a `@RequestScope` bean into a singleton service without a proxy. What does the service see on the second request?

## Go deeper

- [Spring: The IoC Container](https://docs.spring.io/spring-framework/reference/core/beans.html) · the reference chapter; read "Dependencies" and "Customizing the Nature of a Bean" after this note.
- [Spring: Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html) · `@Autowired`, `@Primary`, `@Qualifier` and `ObjectProvider` with exact semantics.
- [Spring: Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html) · scopes and scoped proxies, including why a singleton holding a prototype is wrong.
- [Marco Behler: What is Spring Framework?](https://www.marcobehler.com/guides/spring-framework) · builds the container from scratch, which makes the startup sequence obvious.

---

Part of [Spring](../README.md) · items 1.1, 1.2, 1.3
