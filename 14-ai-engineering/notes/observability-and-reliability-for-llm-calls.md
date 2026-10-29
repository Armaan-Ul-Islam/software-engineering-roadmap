# Observability and reliability for LLM calls: traces, timeouts, retries and fallbacks

> **In one sentence:** Treat a model call as a slow, expensive and occasionally unavailable remote dependency: trace every call with the prompt version, tokens, latency and outcome attached, give it a timeout, retry only the retryable failures with backoff and jitter, break the circuit when the provider is struggling, and decide before launch what the feature does when no answer comes back.

**Why it matters:** "The assistant gave a wrong answer yesterday" is undiagnosable without a trace that says which prompt version, which model, which retrieved chunks and how many tokens were involved. Providers return 429 and 5xx responses as a matter of routine, and a naive retry loop across a fleet of instances turns a provider's bad minute into your outage. These are the same disciplines you apply to any upstream service, with two LLM-specific twists: requests are long (tens of seconds is normal) and every retry costs money.

## The idea

**What to trace.** One span per model call, a child of the incoming request's trace, carrying: provider and operation (chat, embeddings), requested and responding model, prompt version (item 2.1), input, cached and output token counts, finish reason, time to first token and total latency, estimated cost (item 2.4), and the error class if it failed. Tool executions are child spans (item 4.1); the retrieval step is a span that records the chunk ids it returned (item 3.3). With that, a bad answer is a query over traces, not a guess.

The OpenTelemetry semantic conventions for generative AI define the attribute names, for example `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` and `gen_ai.response.finish_reasons`. The conventions are marked as in development and some names have been renamed between releases, so pin the version you follow and read the current page. Prompt and completion *content* is the most useful thing to have in a trace and the most sensitive: it contains personal data, it is large, and retention rules apply (item 6.3). The conventions make content capture opt-in; capture it in development, and in production sample it, redact it, or store it in a separate store with a short retention. Langfuse and the general-purpose tracing backends (Jaeger, Tempo, Grafana, Datadog, and others) all render these spans; Spring AI emits Micrometer observations for every model call when you use the autoconfigured client (item 7.1), with the attributes listed in its observability chapter.

**Timeouts.** Set a short connect timeout and a request timeout sized per feature from the measured p99 plus a margin: a classification that takes two seconds and a long summary that takes forty need different values. With streaming, add an idle timeout between chunks, which catches a stalled stream long before the overall deadline. A call with no timeout holds a thread, a connection and a user indefinitely.

**Retries.** Retry on 429 (rate limited), on 500, 502, 503 and 504, on the "overloaded" status some providers use, and on connection failures and timeouts. Honour a `Retry-After` header when one is present. Use exponential backoff with jitter, a small attempt cap (three is typical) and an overall deadline. Never retry a 400 (your request is wrong), 401 or 403, a request-too-large response, a content-policy rejection, or a response that parsed fine but was wrong: that last case is the validate-and-correct loop (item 2.2), which sends different input and is a different mechanism. A streaming response that breaks midway restarts from zero; the partial text is discarded. Every retry is billed, so retries are part of the cost budget.

**Fallbacks between models.** A second model from the same family, an older version, or the same task on another provider. A fallback is a second behaviour: structured output support, tool calling and prompt sensitivity differ, so the fallback path needs its own eval cases (item 5.1) or it is an untested code path that runs only during incidents.

**Circuit breakers and bulkheads.** After a configured failure rate or slow-call rate in a sliding window, stop calling the provider for a cool-off period and go straight to the fallback or the degraded path; then let a few trial calls through. A bulkhead caps concurrent in-flight calls so that a slow provider cannot exhaust your thread pool or burn your rate limit on requests that will time out anyway. Resilience4j provides both, and its Spring Boot integration configures them from properties.

**Graceful degradation.** Decide per feature. A generated summary can be absent with a visible "summary unavailable". A triage can fall back to a rules-based classifier or a human queue. An agent in the middle of a plan should stop and report, not retry the half-done plan. Put every feature behind a flag so it can be switched off during an incident without a deploy, and make non-interactive work asynchronous so a provider outage becomes a delay rather than an error.

## Example: a traced call with bounded retries

The client below uses the Java HTTP client against an OpenAI-compatible endpoint and the OpenTelemetry API. `ChatRequest`, `ChatResponse` and `ProviderException` are your own types; `ChatResponse.parse` reads the usage object (item 2.4).

```java
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

public final class ResilientChatClient {

    private static final int MAX_ATTEMPTS = 3;
    private static final Duration BASE_DELAY = Duration.ofMillis(500);
    private static final Duration MAX_DELAY = Duration.ofSeconds(8);

    private final HttpClient httpClient;
    private final Tracer tracer;
    private final URI endpoint;
    private final String apiKey;
    private final Duration requestTimeout;

    public ResilientChatClient(Tracer tracer, URI endpoint, String apiKey, Duration requestTimeout) {
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        this.tracer = tracer;
        this.endpoint = endpoint;
        this.apiKey = apiKey;
        this.requestTimeout = requestTimeout;
    }

    public ChatResponse complete(ChatRequest chatRequest) throws InterruptedException {
        Span span = tracer.spanBuilder("chat " + chatRequest.model())
                .setSpanKind(SpanKind.CLIENT)
                .setAttribute("gen_ai.operation.name", "chat")
                .setAttribute("gen_ai.request.model", chatRequest.model())
                .setAttribute("app.prompt.version", chatRequest.promptVersion())
                .startSpan();
        try (Scope scope = span.makeCurrent()) {
            int attempt = 0;
            while (true) {
                attempt++;
                try {
                    HttpResponse<String> httpResponse = httpClient.send(toHttpRequest(chatRequest), HttpResponse.BodyHandlers.ofString());
                    int status = httpResponse.statusCode();
                    if (status == 200) {
                        ChatResponse chatResponse = ChatResponse.parse(httpResponse.body());
                        span.setAttribute("gen_ai.response.model", chatResponse.model());
                        span.setAttribute("gen_ai.usage.input_tokens", chatResponse.inputTokens());
                        span.setAttribute("gen_ai.usage.output_tokens", chatResponse.outputTokens());
                        span.setAttribute("app.llm.attempts", attempt);
                        return chatResponse;
                    }
                    if (!isRetryableStatus(status) || attempt == MAX_ATTEMPTS) {
                        span.setStatus(StatusCode.ERROR, "provider returned " + status);
                        throw new ProviderException(status, httpResponse.body());
                    }
                    span.addEvent("retrying after status " + status);
                    Thread.sleep(delayBefore(attempt, httpResponse.headers().firstValue("Retry-After")));
                } catch (IOException exception) {
                    if (attempt == MAX_ATTEMPTS) {
                        span.recordException(exception);
                        span.setStatus(StatusCode.ERROR);
                        throw new ProviderException(exception);
                    }
                    span.addEvent("retrying after " + exception.getClass().getSimpleName());
                    Thread.sleep(delayBefore(attempt, Optional.empty()));
                }
            }
        } finally {
            span.end();
        }
    }

    private HttpRequest toHttpRequest(ChatRequest chatRequest) {
        return HttpRequest.newBuilder(endpoint)
                .timeout(requestTimeout)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(chatRequest.toJson()))
                .build();
    }

    private static boolean isRetryableStatus(int status) {
        return status == 429 || status == 500 || status == 502 || status == 503 || status == 504 || status == 529;
    }

    private static Duration delayBefore(int attempt, Optional<String> retryAfterHeader) {
        Optional<Duration> serverHint = retryAfterHeader
                .filter(value -> !value.isEmpty() && value.chars().allMatch(Character::isDigit))
                .map(Long::parseLong)
                .map(Duration::ofSeconds);
        if (serverHint.isPresent()) {
            return serverHint.get();
        }
        long exponentialMillis = Math.min(MAX_DELAY.toMillis(), BASE_DELAY.toMillis() * (1L << (attempt - 1)));
        return Duration.ofMillis(ThreadLocalRandom.current().nextLong(exponentialMillis + 1));
    }
}
```

Three details carry the weight. The timeout on the `HttpRequest` surfaces as an `IOException` (`HttpTimeoutException`), so a stalled call is retried like a connection failure. The delay is *full jitter*: a random value between zero and the exponential cap, so a thousand instances that all received a 429 in the same second do not all retry in the same later second. And the span records the attempt count and every retry as an event, so the tail of your latency histogram is explained by the traces that sit in it.

Around this client sits the circuit breaker and bulkhead. With Resilience4j's Spring Boot starter, the properties below open the breaker when half of the last twenty calls failed or were slow, wait thirty seconds, then let five trial calls through:

```properties
resilience4j.circuitbreaker.instances.chat-provider.sliding-window-size=20
resilience4j.circuitbreaker.instances.chat-provider.failure-rate-threshold=50
resilience4j.circuitbreaker.instances.chat-provider.slow-call-duration-threshold=20s
resilience4j.circuitbreaker.instances.chat-provider.slow-call-rate-threshold=50
resilience4j.circuitbreaker.instances.chat-provider.wait-duration-in-open-state=30s
resilience4j.circuitbreaker.instances.chat-provider.permitted-number-of-calls-in-half-open-state=5
resilience4j.bulkhead.instances.chat-provider.max-concurrent-calls=25
```

A resulting trace for a request that hit one 429, read from a tracing backend:

```text
POST /tickets/8812/triage                                    2.9 s
  retrieve-similar-tickets      chunk_ids=[c17,c40,c41]      0.08 s
  chat <model>                  attempts=2 input=2840 cached=2560 output=212  2.7 s
    event: retrying after status 429  (+0.6 s)
  validate-and-map                                           0.01 s
```

## Pitfalls

- Retrying everything. A 400 retried three times is three billed failures and a hidden bug; a wrong-but-valid answer retried is the same answer again.
- Backoff without jitter. Synchronised retries across instances are how a provider's bad minute becomes your bad hour.
- One timeout for every feature. Sized for the longest summary, it lets a two-second classification hang for forty; sized for the classification, it kills every summary.
- A fallback model nobody evaluated. It differs in structured output support or tone, and the first time it runs is during an incident.
- Prompt and completion content in the general trace store. Personal data with the default retention, searchable by everyone with dashboard access.
- Tracing the model call but not the retrieval. Half of all wrong answers are retrieval misses (item 3.3), and without the chunk ids they are invisible.
- Treating the retry loop and the validation loop as one. Transport failures resend the same request; validation failures send a corrected one. Mixing them produces either infinite loops or missed corrections.
- No flag to switch the feature off. During a provider outage the only lever is a deploy.

## Check yourself

1. Which of these should be retried, and why: a 429 with `Retry-After: 7`, a 400 saying the JSON schema is invalid, a timeout on a streaming response after half the answer arrived, a 200 whose JSON fails validation?
2. Explain how full jitter differs from plain exponential backoff and what failure it prevents in a service with many instances.
3. Your tracing backend shows p95 latency of 9 seconds for a feature whose model calls take 2.5 seconds at p95. Using the span attributes above, how would you find the cause?
4. A colleague proposes falling back to another provider's model when the primary returns 5xx. What has to be true of the prompt, the output handling and the eval suite before that is safe?

## Go deeper

- [OpenTelemetry: Semantic conventions for generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) · the attribute names for spans, metrics and events, and the opt-in rules for content capture.
- [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) · the reasoning behind jitter, retry budgets and why retries amplify outages, with simulations.
- [Langfuse](https://langfuse.com/) · an open-source tracing and evaluation tool built around the span shape described above.
- [Spring AI Reference](https://docs.spring.io/spring-ai/reference/) · the observability chapter lists the observations, metrics and attributes the framework emits for model, embedding and vector store calls.

---

Part of [AI Engineering](../README.md) · items 5.2, 5.3
