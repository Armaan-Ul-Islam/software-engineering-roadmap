# The Spring MVC request lifecycle

> **In one sentence:** A request passes through the servlet filter chain, then the `DispatcherServlet` finds a handler, resolves each controller parameter with an argument resolver, calls your method, turns the return value into a response with a message converter, and routes any exception through the exception resolvers, all on the same container thread unless you opt into async.

**Why it matters:** When you know which component handles each annotation you know where to put cross-cutting code, why a `@ControllerAdvice` cannot catch an exception thrown in a filter, why a `postHandle` interceptor cannot add a header to a JSON response, and why `ThreadLocal` state leaks or vanishes. It is also the mental model behind every `MockMvc` test you will write.

## The idea

```text
client
  |
  v
Tomcat worker thread (http-nio-8080-exec-N, or a virtual thread with spring.threads.virtual.enabled=true)
  |
  v
Servlet filters (jakarta.servlet.Filter), in registration order
  CharacterEncodingFilter -> Spring Security FilterChainProxy -> your OncePerRequestFilter -> ServerHttpObservationFilter
  |
  v
DispatcherServlet.doDispatch
  1. HandlerMapping            RequestMappingHandlerMapping matches path, method, consumes, produces
                               -> HandlerExecutionChain = HandlerMethod + HandlerInterceptors
  2. HandlerAdapter            RequestMappingHandlerAdapter will invoke the method
  3. interceptor.preHandle     may stop the request by returning false
  4. argument resolvers        one HandlerMethodArgumentResolver per parameter
                               @RequestBody -> HttpMessageConverter.read, then validation
  5. your controller method
  6. return value handler      @ResponseBody / ResponseEntity -> HttpMessageConverter.write
                               (content negotiation on the Accept header); body is now committed
  7. interceptor.postHandle    too late to touch the body or headers of a @ResponseBody response
  8. HandlerExceptionResolvers if anything above threw:
                               ExceptionHandlerExceptionResolver (@ExceptionHandler, @ControllerAdvice)
                               ResponseStatusExceptionResolver   (@ResponseStatus, ResponseStatusException)
                               DefaultHandlerExceptionResolver   (framework exceptions -> 400, 404, 405, 415...)
  9. interceptor.afterCompletion always runs
  |
  v
back out through the filters; unhandled exceptions reach Boot's /error (BasicErrorController) via an ERROR dispatch
```

**Filters** are servlet-level: they run for every request, before Spring MVC knows which handler will be called, and they see the raw `HttpServletRequest`. Spring Security, CORS, compression, request logging and correlation IDs (putting a request ID in the MDC) live here. Extend `OncePerRequestFilter` so the filter runs once even when the container dispatches the same request again for an error page or an async completion.

**Interceptors** (`HandlerInterceptor`) are Spring MVC-level: they know the `HandlerMethod`, so they can read annotations on the controller method, and they run only for requests the `DispatcherServlet` handles. `preHandle` is the useful hook; `postHandle` runs after the body has been written for `@ResponseBody` methods, so it cannot modify REST responses.

**Argument resolvers** turn one parameter each into a value. `@PathVariable` and `@RequestParam` go through the `ConversionService` (strings to `UUID`, `Instant`, enums). `@RequestBody` is read by the first `HttpMessageConverter` that supports the request `Content-Type` and the parameter type; with Jackson that is `MappingJackson2HttpMessageConverter` in Boot 3 (Spring Framework 7 and Boot 4 use Jackson 3 and `JacksonJsonHttpMessageConverter`). If no converter matches, the request fails with 415 before your method is called. You can add your own resolver for parameters like `@CurrentUser Account account`.

**Return value handlers** do the reverse. `@ResponseBody` (implied by `@RestController`) and `ResponseEntity` select a converter from the `Accept` header, defaulting to JSON; an unacceptable `Accept` yields 406. `ResponseEntity` is how you set status and headers, including caching: `ResponseEntity.ok().cacheControl(CacheControl.maxAge(Duration.ofMinutes(10))).eTag(version).body(dto)`, and `webRequest.checkNotModified(etag)` turns a matching `If-None-Match` into a 304 without a body.

**Exception resolvers** run in the order shown. `@ExceptionHandler` methods in a `@ControllerAdvice` win; otherwise `ResponseStatusException` and `@ResponseStatus` apply; otherwise Spring's own exceptions are mapped to the standard status codes. Anything else propagates to the container, which forwards to Boot's `/error`. Exceptions thrown inside a filter never reach these resolvers, because the `DispatcherServlet` has not run yet; a filter must handle its own errors (Spring Security does this in `ExceptionTranslationFilter`).

**Threads.** Everything in the diagram runs on the thread Tomcat assigned to the request, so `SecurityContextHolder`, `RequestContextHolder`, the MDC, and the transaction and persistence context bound by `@Transactional` are all available throughout. Returning `Callable`, `DeferredResult`, `CompletableFuture`, `SseEmitter` or `StreamingResponseBody` switches to servlet async mode: the Tomcat thread is released, your code runs on the MVC task executor, and when the result is ready the request is dispatched a second time (`DispatcherType.ASYNC`) through the filters registered for it and the `DispatcherServlet`, which then writes the response. Thread-bound state does not follow automatically. With `spring.threads.virtual.enabled=true` on Java 21 each request gets a virtual thread, which makes blocking cheap and async return types mostly unnecessary.

## Example: one method, annotated by step

```java
@RestController
@RequestMapping("/api/customers")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping(path = "/{customerId}/orders", consumes = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public OrderResponse place(
            @PathVariable UUID customerId,
            @RequestParam(defaultValue = "false") boolean dryRun,
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @Valid @RequestBody PlaceOrderRequest request,
            Authentication authentication) {
        return orderService.place(customerId, request, idempotencyKey, dryRun, authentication.getName());
    }
}
```

| Element | Step | Handled by |
|---|---|---|
| `@PostMapping(path, consumes)` | 1 | `RequestMappingHandlerMapping`; a wrong `Content-Type` is a 415 here, a wrong method a 405 |
| `@PathVariable UUID customerId` | 4 | `PathVariableMethodArgumentResolver`, converting the string with the `ConversionService`; a bad UUID becomes `MethodArgumentTypeMismatchException`, 400 |
| `@RequestParam(defaultValue)` | 4 | `RequestParamMethodArgumentResolver`; a required parameter that is missing becomes `MissingServletRequestParameterException`, 400 |
| `@RequestHeader` | 4 | `RequestHeaderMethodArgumentResolver`; missing header, 400 |
| `@Valid @RequestBody` | 4 | `RequestResponseBodyMethodProcessor` reads JSON through the Jackson converter, then validates; malformed JSON is `HttpMessageNotReadableException`, constraint violations are `MethodArgumentNotValidException` (item 3.3) |
| `Authentication authentication` | 4 | `PrincipalMethodArgumentResolver`, from `request.getUserPrincipal()`, which Spring Security populates |
| `@ResponseStatus(CREATED)` and the `OrderResponse` return value | 6 | `RequestResponseBodyMethodProcessor` sets 201 and writes the body with a converter chosen from `Accept` |

To watch the steps happen, set `logging.level.org.springframework.web=DEBUG`: the `DispatcherServlet` logs the mapped handler, the resolved arguments and the chosen converter for every request.

## Pitfalls

- Putting `@Transactional` on controllers. The transaction then spans JSON serialisation and holds a connection while the response is written; the boundary belongs on the service (item 4.3).
- Expecting `@ControllerAdvice` to handle exceptions from filters. It cannot. For Spring Security failures configure the `AuthenticationEntryPoint` and `AccessDeniedHandler` instead (item 6.1).
- Adding response headers in `postHandle`. For `@ResponseBody` methods the response is already committed. Use a `ResponseBodyAdvice`, set headers through `ResponseEntity`, or do it in a filter.
- A plain `Filter` instead of `OncePerRequestFilter`. It runs again on ERROR and ASYNC dispatches, so your "request started" log line appears twice and your timer measures nonsense.
- Reading the request body in a filter and then expecting `@RequestBody` to work. The stream is consumed once; wrap the request in `ContentCachingRequestWrapper` if a filter must see the body.
- Relying on `ThreadLocal` state (MDC, security context) in code that runs on another thread, whether from `@Async`, a `CompletableFuture` or an async return type. Propagate it explicitly, or stay on the request thread.

## Check yourself

1. A request arrives with `Content-Type: text/plain` for a method that declares `consumes = application/json`. Which step rejects it and with which status? Does your `@ControllerAdvice` see it?
2. Why can a `HandlerInterceptor` read an annotation on the controller method while a `Filter` cannot?
3. A controller returns `CompletableFuture<OrderResponse>`. Which thread runs the body of the future, and what happens to the `SecurityContext` there?
4. You need to add a request ID to every log line, including those written by Spring Security. Filter, interceptor or advice, and why?

## Go deeper

- [Spring: DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html) · processing sequence, special bean types and the exception resolver chain.
- [Spring: Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html) · every supported method argument and return value, with the component that handles it.
- [Spring: Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html) · the filters Spring MVC ships, including `OncePerRequestFilter` and the content caching wrappers.
- [Baeldung: HandlerInterceptor vs Filter](https://www.baeldung.com/spring-mvc-handlerinterceptor-vs-filter) · the two hooks side by side with the ordering made explicit.

---

Part of [Spring](../README.md) · items 3.1, 3.2
