# Filters, interceptors and AOP: where cross-cutting code belongs

> **In one sentence:** A servlet filter sees every request as raw HTTP before Spring MVC knows which handler will run, a `HandlerInterceptor` sees the chosen controller method but not the response body, a `@ControllerAdvice` sees exceptions and bodies, and an AOP aspect sees calls to service methods however they were triggered, so the right home for a cross-cutting concern follows from what it needs to see and when it needs to act.

**Why it matters:** The same request log, correlation id, rate limit or audit trail can be written in four places, and three of them are wrong in ways that only show later: the correlation id missing from Spring Security's log lines, an audit entry written for a request that was rolled back, a timing aspect that never fires because the call never crossed a proxy. Choosing the layer deliberately keeps each concern in one place and keeps the request pipeline (item 3.1) something you can draw from memory.

## The idea

Four hooks, in the order a request meets them.

**Servlet filters** (`jakarta.servlet.Filter`) run in the container, around the `DispatcherServlet`, for every request including static resources and Spring Security's rejections. They see `HttpServletRequest` and `HttpServletResponse` and know nothing about controllers. Extend `OncePerRequestFilter`, which guarantees one execution per request even when the container dispatches again for an error page or an async completion, and override `shouldNotFilter` to skip paths. In Boot, every `Filter` bean is registered for `/*` and ordered by `@Order` or `Ordered`; a `FilterRegistrationBean` adds URL patterns, dispatcher types and an explicit order. Spring Security's chain is registered at order `-100` (`SecurityProperties.DEFAULT_FILTER_ORDER`), so anything that must run before authentication needs a smaller number. An exception thrown in a filter never reaches a `@ControllerAdvice`; the filter must write its own response.

**`HandlerInterceptor`** runs inside the `DispatcherServlet`, after the handler mapping has chosen the controller method. `preHandle` receives the handler (a `HandlerMethod` for controllers, so you can read annotations on the method or its class) and can stop the request by returning `false`; `postHandle` runs after the method but, for `@ResponseBody` controllers, after the body has been written, so it cannot change REST responses; `afterCompletion` always runs and receives the exception if there was one. Register interceptors in `WebMvcConfigurer.addInterceptors` with path patterns. Because they run inside the dispatcher, an exception from `preHandle` does reach the `HandlerExceptionResolver`s and therefore your `@ControllerAdvice`.

**`@ControllerAdvice`** holds `@ExceptionHandler`, `@InitBinder` and `@ModelAttribute` methods shared by many controllers and, when the class implements `ResponseBodyAdvice` or `RequestBodyAdvice`, hooks that inspect or wrap bodies around conversion. It is the right place for error shapes (item 3.3) and response envelopes, and the wrong place for anything that must happen when no controller is involved.

**AOP aspects** (`@Aspect`, with `spring-boot-starter-aop` on the classpath) advise calls to Spring beans through their proxies. A pointcut such as `@within(org.springframework.stereotype.Service)` matches every public method of every `@Service`, whether the call came from a controller, a Kafka listener, a scheduled job or a test. That independence from HTTP is the point: the duration, audit entry or retry policy of a business operation is a property of the operation, not of a URL. The limits are the proxy's (item 1.4): self-invocation is not advised, `final` methods are not advised, only beans are advised. `@Transactional`, `@Cacheable`, `@Async`, `@PreAuthorize` and Resilience4j's annotations are aspects you did not have to write; prefer them over custom advice whenever one fits.

### The decision table

| Concern | Put it in | Because |
|---|---|---|
| Correlation id and other MDC values | Filter ordered before Spring Security | Must cover Security's own log lines and its 401 responses; needs only the raw request |
| Request and response logging | Filter using `ContentCachingRequestWrapper` and `ContentCachingResponseWrapper` | Sees the bytes; bodies are readable only after the chain has run, so log in `finally` |
| Authentication and authorisation | Spring Security's filter chain, never a home-made filter or interceptor | Must run before any handler and populate `SecurityContextHolder`; method security extends it to services |
| CORS | `CorsFilter` via Spring Security's `cors()` (item 6.4) | Preflight requests have no handler and must be answered before authentication |
| Rate limiting | Filter: before Security when keyed by IP or API key, after it when keyed by the authenticated user | Rejecting with 429 and `Retry-After` should cost nothing; a per-user key needs the principal |
| Per-endpoint policy declared on the controller | `HandlerInterceptor` | Only it knows the `HandlerMethod` and its annotations |
| Consistent error bodies | `@ControllerAdvice` | Runs in the exception resolver chain |
| Timing and auditing of business operations | Aspect on service methods, or domain events | The unit of work is the service method, and it also covers non-HTTP entry points |
| Transactions, caching, retries, method security | The existing annotations | Already aspects, already tested |

## Example: a correlation-id filter that sets the MDC

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class CorrelationIdFilter extends OncePerRequestFilter {

    public static final String HEADER_NAME = "X-Correlation-Id";
    private static final String MDC_KEY = "correlationId";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        String correlationId = Optional.ofNullable(request.getHeader(HEADER_NAME))
                .filter(CorrelationIdFilter::isWellFormed)
                .orElseGet(() -> UUID.randomUUID().toString());
        MDC.put(MDC_KEY, correlationId);
        response.setHeader(HEADER_NAME, correlationId);
        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY);
        }
    }

    private static boolean isWellFormed(String candidate) {
        return candidate.length() <= 64
                && candidate.chars().allMatch(character -> Character.isLetterOrDigit(character) || character == '-');
    }
}
```

```properties
logging.pattern.level=%5p [cid=%X{correlationId:-}]
```

Every line logged while the request runs now carries the id, including Spring Security's:

```text
2026-10-24T10:15:02.113+02:00  INFO [cid=3f2a9c1e-5d0b-4c6a-9f1e-2b7d8e9a0c11] 41213 --- [nio-8080-exec-3] c.e.orders.OrderService : placing order for customer 42
```

Three details carry the design. The incoming header is validated because it ends up in every log line and every log index; an unbounded, attacker-chosen string is a log injection. The id is echoed in the response so a client can quote it in a support ticket. `MDC.remove` runs in `finally` because Tomcat reuses platform threads; a leaked value would label the next request. The MDC is a `ThreadLocal`, so `@Async` work loses it unless a `TaskDecorator` copies `MDC.getCopyOfContextMap()` onto the worker thread. With Micrometer Tracing (item 8.2) the trace id arrives in the MDC without any of this; the home-made filter is for services without tracing, or for an id the business already uses.

To confirm the order, start with `logging.level.org.springframework.boot.web.servlet.ServletContextInitializerBeans=DEBUG` and read the `Mapping filters:` line, which lists every filter with its `order=`.

## Example: an aspect that times service methods

```java
@Aspect
@Component
public class ServiceTimingAspect {

    private final MeterRegistry meterRegistry;

    public ServiceTimingAspect(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @Around("@within(org.springframework.stereotype.Service)")
    public Object time(ProceedingJoinPoint joinPoint) throws Throwable {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";
        try {
            return joinPoint.proceed();
        } catch (Throwable throwable) {
            outcome = "error";
            throw throwable;
        } finally {
            sample.stop(Timer.builder("service.method")
                    .tag("class", joinPoint.getSignature().getDeclaringType().getSimpleName())
                    .tag("method", joinPoint.getSignature().getName())
                    .tag("outcome", outcome)
                    .register(meterRegistry));
        }
    }
}
```

```text
service_method_seconds_count{class="OrderService",method="place",outcome="success"} 1842.0
service_method_seconds_sum{class="OrderService",method="place",outcome="success"} 171.3
service_method_seconds_count{class="OrderService",method="place",outcome="error"} 12.0
```

`register` returns the existing meter when one with the same name and tags exists, so building it in `finally` is cheap. The `class` and `method` tags are bounded by the size of the codebase, which keeps cardinality safe (item 8.1). The aspect fires for `orderService.place(...)` whether a controller, a `@KafkaListener` or a `@Scheduled` job called it, and does not fire for `this.validate(...)` inside the service. Rethrowing the `Throwable` leaves transaction rollback rules untouched. `@Observed` (item 8.2) does the same declaratively and adds a trace span.

## Pitfalls

- A plain `Filter` where `OncePerRequestFilter` was needed. It runs again on the error dispatch to `/error`, so "request received" is logged twice and timings are wrong.
- The correlation filter registered after Spring Security. Every 401 and every Security debug line is logged without an id. Order it below `-100` and verify with the `Mapping filters:` line.
- Trusting the incoming correlation header. Log injection and unbounded strings in every log line; validate length and characters, or generate your own.
- Auditing in a filter or interceptor. At that point you know the URL and the user, not the business outcome. Audit from the service, through an aspect or a domain event handled after commit (item 1.6), so a rolled-back cancellation is never recorded as one.
- `postHandle` to add headers to a REST response. The body is already committed; use `ResponseEntity`, a `ResponseBodyAdvice` or a filter.
- Expecting an aspect to see private or self-invoked methods. Spring AOP advises calls that cross the proxy; split the class or accept that the inner call is part of the outer measurement.
- Reading the request body in a filter without `ContentCachingRequestWrapper`. The stream is consumed, `@RequestBody` reads nothing, and the controller fails with 400.

## Check yourself

1. The operations team wants every log line, including Spring Security's, to carry the correlation id. Filter, interceptor or aspect, and at what order relative to `-100`?
2. "Record who cancelled which order" is an audit requirement. Why is a filter the wrong place even though it sees the user and the URL, and where would you put it so that a rolled-back cancellation is not recorded?
3. The timing aspect reports nothing for `OrderService.validate`, which `OrderService.place` calls. Why, and what are two ways to make it visible?
4. A limit of 100 requests per minute per API key must answer 429 as cheaply as possible. Where does it go, and what changes if the limit is per authenticated user?

## Go deeper

- [Spring: Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html) · the filters Spring MVC ships, including `OncePerRequestFilter` and the content caching wrappers.
- [Spring: Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html) · registering `HandlerInterceptor`s with path patterns, and the warning about using them for security.
- [Spring: AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html) · join points, pointcuts and advice, with the proxy model that explains self-invocation.
- [Spring Boot: Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html) · how Boot registers filter beans and `FilterRegistrationBean`, and the ordering rules.
- [Baeldung: HandlerInterceptor vs Filter](https://www.baeldung.com/spring-mvc-handlerinterceptor-vs-filter) · the two hooks side by side.
- [Spring: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) · the MVC side of CORS, which the security note (item 6.4) builds on.
- [Logback: Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html) · what the MDC is, how patterns read it, and why it is per thread.

---

Part of [Spring](../README.md) · item 3.4
