# RestClient, WebClient and HTTP interface clients

> **In one sentence:** `RestClient` is the synchronous HTTP client for Spring 6.1 and later, `WebClient` is the same idea for reactive applications, an HTTP interface client turns a Java interface annotated with `@HttpExchange` into a proxy over either of them, and whichever you pick, the timeouts and the connection pool live in the underlying client library and must be set explicitly because the defaults are infinite or tiny.

**Why it matters:** Most outages caused by a dependency are not caused by it failing but by it slowing down: a partner API that takes sixty seconds to answer, called with no read timeout, holds a Tomcat thread and often a database connection per call until the whole service stops. The client is also where retries get added without thought, turning a partner's bad minute into a self-inflicted outage. Knowing the three client types and where their knobs are is a daily skill.

## The idea

**`RestClient`** (Spring Framework 6.1, Boot 3.2) is a fluent, synchronous client built on the same infrastructure as `RestTemplate`: a `ClientHttpRequestFactory` for the connection, `HttpMessageConverter`s for bodies, `ClientHttpRequestInterceptor`s for cross-cutting work. A call reads as the request it makes:

```java
Shipment shipment = restClient.get()
        .uri("/v1/shipments/{shipmentId}", shipmentId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Shipment.class);
```

`retrieve()` throws `HttpClientErrorException` for 4xx and `HttpServerErrorException` for 5xx (both extend `RestClientResponseException`, which carries the status and the response body) and wraps I/O failures, including timeouts, in `ResourceAccessException`. `onStatus(...)` on one request, or `defaultStatusHandler(...)` on the builder, replaces that behaviour; `exchange(...)` hands you the raw response for full control. `toEntity(Class)` returns a `ResponseEntity` when you need headers, and `body(new ParameterizedTypeReference<List<Shipment>>() {})` handles generics. Boot auto-configures a `RestClient.Builder` with the message converters and Micrometer observation already set. It is prototype-scoped, so inject it and build one `RestClient` per remote system; a built `RestClient` is immutable and thread-safe.

**`WebClient`** lives in `spring-webflux` and returns `Mono` and `Flux`. It is the right client inside a WebFlux application, and for streaming bodies or thousands of concurrent outbound calls where a thread per call is unaffordable. In a Spring MVC application, `webClient.get()...block()` is a synchronous call with extra machinery and a second thread pool (Reactor Netty's event loop) to understand when something goes wrong; use `RestClient`. With virtual threads (item 3.7) the "too many blocked threads" argument for `WebClient` in MVC applications largely disappears.

**HTTP interface clients** (Spring Framework 6.0) declare the API as an interface: `@HttpExchange` at type level for the shared path and headers, `@GetExchange`, `@PostExchange` and friends on methods, and `@PathVariable`, `@RequestParam`, `@RequestHeader` and `@RequestBody` on parameters. `HttpServiceProxyFactory` creates the implementation over an adapter: `RestClientAdapter`, `WebClientAdapter` or `RestTemplateAdapter`. The interface documents the contract, is trivial to fake in tests, and keeps URL building out of the service. Spring Framework 7 adds `@ImportHttpServices` to register groups of these interfaces declaratively.

**Timeouts and pools** are not Spring settings. They belong to the `ClientHttpRequestFactory` and the library behind it, which Boot detects from the classpath: Apache HttpComponents, Jetty, Reactor Netty, then the JDK's own `HttpClient`. The connect timeout bounds the TCP handshake; the read timeout bounds the wait for a response; the pool bounds concurrency per host and in total (Apache HttpClient 5 defaults to 25 connections overall and 5 per route, a limit you hit the first time a partner is slow). Without a read timeout, the wait is unbounded in every library. Boot 3.4 added `ClientHttpRequestFactoryBuilder` and `ClientHttpRequestFactorySettings` for setting these in code, and `spring.http.client.connect-timeout`, `spring.http.client.read-timeout` and `spring.http.client.factory` for the auto-configured builder.

**Retries** are for idempotent requests only (`GET`, `PUT`, `DELETE`, or a `POST` carrying an idempotency key), with a small attempt count, exponential backoff with jitter, and a total budget: three attempts at a five-second read timeout is a fifteen-second worst case that the caller must be able to live with. Retrying a 4xx is pointless, retrying a 503 without honouring `Retry-After` makes the partner's day worse, and retrying a timed-out `POST` creates duplicate orders. Use Resilience4j or Spring Framework 7's `@Retryable` (item 8.4) rather than a hand-written loop.

**Metrics.** A `RestClient` built from Boot's builder records the `http.client.requests` timer with the tags `method`, `uri`, `status`, `outcome` and `client.name` (the host). The `uri` tag is the template string you passed to `uri(...)`, so pass `"/v1/shipments/{shipmentId}"` with a variable, never a concatenated path, or every id becomes its own time series; Boot 3.x stops recording after `management.metrics.web.client.max-uri-tags` (100) distinct values and logs a warning. A failed connection or timeout records an `exception` tag naming the exception class.

**`RestTemplate`** is not deprecated and still receives fixes, but new features land in `RestClient`, and the Spring team's guidance is to use `RestClient` for new synchronous code. Migration can be gradual: `RestClient.create(restTemplate)` reuses an existing template's converters and interceptors.

## Example: a RestClient with timeouts and an interface client for a partner API

```java
@ConfigurationProperties("partner.shipping")
public record ShippingPartnerProperties(String baseUrl, String apiKey) {
}
```

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingPartnerProperties.class)
public class ShippingPartnerConfiguration {

    @Bean
    RestClient shippingRestClient(RestClient.Builder builder, ShippingPartnerProperties properties) {
        ClientHttpRequestFactorySettings settings = ClientHttpRequestFactorySettings.defaults()
                .withConnectTimeout(Duration.ofSeconds(2))
                .withReadTimeout(Duration.ofSeconds(5));
        return builder
                .baseUrl(properties.baseUrl())
                .requestFactory(ClientHttpRequestFactoryBuilder.detect().build(settings))
                .defaultHeader("X-Api-Key", properties.apiKey())
                .defaultStatusHandler(HttpStatusCode::is5xxServerError, (request, response) -> {
                    throw new ShippingPartnerUnavailableException(response.getStatusCode());
                })
                .build();
    }

    @Bean
    ShippingPartnerApi shippingPartnerApi(RestClient shippingRestClient) {
        return HttpServiceProxyFactory.builderFor(RestClientAdapter.create(shippingRestClient))
                .build()
                .createClient(ShippingPartnerApi.class);
    }
}
```

```java
@HttpExchange(url = "/v1", accept = MediaType.APPLICATION_JSON_VALUE)
public interface ShippingPartnerApi {

    @GetExchange("/shipments/{shipmentId}")
    Shipment shipment(@PathVariable String shipmentId);

    @GetExchange("/shipments")
    List<Shipment> shipments(@RequestParam("status") ShipmentStatus status);

    @PostExchange("/shipments")
    ResponseEntity<Shipment> create(@RequestBody CreateShipmentRequest request,
                                    @RequestHeader("Idempotency-Key") String idempotencyKey);
}
```

A caller that treats 404 as "not found" rather than as an error:

```java
@Service
public class ShipmentLookup {

    private final ShippingPartnerApi shippingPartnerApi;

    public ShipmentLookup(ShippingPartnerApi shippingPartnerApi) {
        this.shippingPartnerApi = shippingPartnerApi;
    }

    public Optional<Shipment> find(String shipmentId) {
        try {
            return Optional.of(shippingPartnerApi.shipment(shipmentId));
        } catch (HttpClientErrorException.NotFound exception) {
            return Optional.empty();
        }
    }
}
```

What this buys: a partner that stops answering costs each caller at most two seconds to connect plus five to wait, then a `ResourceAccessException` that a circuit breaker (item 8.4) can count. A 5xx becomes a domain exception with no stack of `RestClient` internals. The `Idempotency-Key` on `create` is what makes retrying it safe. After some traffic, `/actuator/prometheus` shows (abridged):

```text
http_client_requests_seconds_count{client_name="shipping.example.com",method="GET",outcome="SUCCESS",status="200",uri="/v1/shipments/{shipmentId}"} 1842.0
http_client_requests_seconds_count{client_name="shipping.example.com",method="GET",outcome="CLIENT_ERROR",status="404",uri="/v1/shipments/{shipmentId}"} 37.0
http_client_requests_seconds_max{client_name="shipping.example.com",method="GET",outcome="SUCCESS",status="200",uri="/v1/shipments/{shipmentId}"} 0.412
```

Test the wiring with `@RestClientTest` and `MockRestServiceServer` (item 7.1), which binds to the auto-configured builder and lets you assert the exact request, including the `Idempotency-Key` header.

## Pitfalls

- No read timeout. Every client library waits forever by default. Set connect and read timeouts on every `RestClient`, and set them per partner, because a payment provider and a geocoder deserve different budgets.
- `RestClient.create()` inside a method. Each call builds a new client with no pool and no metrics. Build once, inject everywhere.
- `uri("/v1/shipments/" + id)`. The id lands in the `uri` metric tag and, if it contains `/` or `?`, in the wrong place in the URL. Templates with variables are encoded and tagged correctly.
- Retrying everything. A retry on `HttpClientErrorException` cannot succeed; a retry on a timed-out `POST` without an idempotency key duplicates the side effect; three retries from each of fifty instances turn one slow partner into a flood.
- `block()` on a `WebClient` in a Spring MVC service. You now run two HTTP stacks and two thread models for no gain; `RestClient` does the same job on the request thread.
- Dropping the error body. `RestClientResponseException.getResponseBodyAsString()` usually contains the partner's explanation. Log it at the point where you translate the exception, minus anything personal.
- One shared `RestClient` for several partners. They need different base URLs, headers, timeouts and error handlers; sharing couples their failure modes.

## Check yourself

1. A partner's p99 latency rises from 200 ms to 40 s. With no read timeout, what happens to an MVC service with 200 Tomcat threads and a 10-connection HikariCP pool, and which two settings bound the damage?
2. You retry `POST /shipments` three times on `ResourceAccessException`. What can go wrong on the partner's side, and which header makes the retry safe?
3. Why does `uri("/v1/shipments/" + id)` hurt both your metrics and your correctness, and what does `uri("/v1/shipments/{shipmentId}", id)` change?
4. Your MVC service calls four downstream APIs per request. A colleague proposes `WebClient` to "make it non-blocking". What question do you ask first, and what would you try instead on Java 21?

## Go deeper

- [Spring: REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html) · `RestClient`, `WebClient`, `RestTemplate` and HTTP interface clients in one chapter, with the request factory options.
- [Spring Boot: Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html) · what the auto-configured builders set up and how to customise the request factory.
- [Spring Boot: Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) · the `http.client.requests` tags and the `max-uri-tags` guard.
- [Spring: Resilience Features](https://docs.spring.io/spring-framework/reference/core/resilience.html) · the Framework 7 `@Retryable` support that pairs with these clients.
- [AWS Builders' Library: Timeouts, retries and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) · the clearest explanation of why naive retries amplify outages.

---

Part of [Spring](../README.md) · item 3.5
