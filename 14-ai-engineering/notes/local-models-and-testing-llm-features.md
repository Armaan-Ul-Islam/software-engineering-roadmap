# Local models and testing LLM features: raw HTTP, Ollama, record and replay

> **In one sentence:** A model API is a small JSON contract you can call with the plain Java HTTP client when a framework is more than you need, and you test the code around it in layers: fakes for the logic, recorded real responses for the integration, a local model through Ollama for end-to-end plumbing without keys or cost, and evals against the production model for quality.

**Why it matters:** Teams either put every test behind a paid API key (slow, flaky, expensive, and impossible on a laptop without network) or mock the client so thoroughly that the tests never see a real response shape, and the first production response with an unexpected `finish_reason` breaks parsing. Knowing what the wire format is, and which test layer answers which question, keeps the suite fast and honest. It also tells you when Spring AI or LangChain4j is pulling its weight and when a hundred lines of HTTP would have been simpler.

## The idea

**The wire format is small.** A chat completion request is a model id, a list of role-tagged messages and a few options; the response is a list of choices with a message, a finish reason and a usage object. Streaming adds server-sent events. Tool calling adds a `tools` array and tool-call entries in the reply (item 4.1). That is the whole surface most features use, and the OpenAI-compatible shape is spoken by many providers and by local runtimes, while Anthropic's Messages API has its own, similar shape.

**When a framework is overhead (item 7.3).** Reach for Spring AI (item 7.1) or LangChain4j (item 7.2) when you want provider portability, advisors, a vector store abstraction, a managed tool loop and observability wired in. Reach for a provider SDK or raw HTTP when the feature is one fixed prompt against one provider, when you need a provider feature the framework has not exposed yet (a new request parameter, batch endpoints, cache controls), when the framework's version churn costs more than the code it replaces, or when you are not in a Spring application at all. The official SDKs sit in between: typed requests, retries and streaming helpers without the abstraction layer. Whichever you pick, put your own small interface in front of it, because that interface is where the test layers plug in.

**Running models locally (item 7.4).** Ollama downloads open-weight models and serves them on `localhost:11434` with its own API and an OpenAI-compatible one under `/v1`. A laptop runs small models at usable speed; the larger ones need a GPU with enough memory. Spring AI has an Ollama starter configured by a base URL instead of an API key, and the OpenAI starter can also be pointed at Ollama's `/v1` endpoint. A local model is a different model: smaller, less reliable at structured output and tool calling, and with its own tokeniser, so what it tests is your plumbing (serialisation, streaming, parsing, error handling), not the quality of your prompt.

**The test layers.**

1. **Unit tests with a fake client.** Prompt assembly, output parsing, validation, the retry decision, the tool loop. The fake returns canned responses or throws; the tests are deterministic and run in milliseconds. This is where most tests live.
2. **Replay tests with recorded responses.** Real responses captured once from the production model and stored as JSON fixtures, keyed by a fingerprint of the request. They catch what fakes miss: the real usage fields, a `length` finish reason, tool-call JSON as the provider formats it, markdown fences around JSON. A changed prompt produces a new fingerprint and a clear "no recording" failure instead of a silently stale fixture. Re-record deliberately, review the diff, and commit it.
3. **Integration tests against a local model.** Start Ollama (locally, or in Docker; Testcontainers has a module for it) and run the real HTTP path end to end, including streaming. Assert on properties (parses, schema valid, finishes), never on wording. Tag these so the pull-request job can skip them where there is no runtime.
4. **Evals against the production model (item 5.1).** The only layer that measures quality, run on a schedule and gated.

## Example: a raw client and a replaying one behind the same interface

The interface and the records. The request serialises to the OpenAI-compatible JSON shape; the response is parsed leniently because providers add fields:

```java
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record ChatMessage(String role, String content) {
}

public record ChatCompletionRequest(String model, List<ChatMessage> messages, double temperature,
                                    @JsonProperty("max_tokens") int maxTokens) {
}

public record ChatCompletion(String id, String model, List<Choice> choices, Usage usage) {

    public record Choice(int index, ChatMessage message, @JsonProperty("finish_reason") String finishReason) {
    }

    public record Usage(@JsonProperty("prompt_tokens") long promptTokens,
                        @JsonProperty("completion_tokens") long completionTokens) {
    }
}

public interface ChatCompletionClient {

    ChatCompletion complete(ChatCompletionRequest chatCompletionRequest);
}
```

The raw implementation with the Java HTTP client. Base URL and key come from configuration, so the same class talks to a hosted provider or to Ollama:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HttpChatCompletionClient implements ChatCompletionClient {

    private final HttpClient httpClient = HttpClient.newHttpClient();
    private final ObjectMapper objectMapper = new ObjectMapper()
            .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    private final URI completionsUri;
    private final String apiKey;

    public HttpChatCompletionClient(String baseUrl, String apiKey) {
        this.completionsUri = URI.create(baseUrl + "/v1/chat/completions");
        this.apiKey = apiKey;
    }

    @Override
    public ChatCompletion complete(ChatCompletionRequest chatCompletionRequest) {
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(completionsUri)
                    .timeout(Duration.ofSeconds(60))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(chatCompletionRequest)))
                    .build();
            HttpResponse<String> httpResponse = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());
            if (httpResponse.statusCode() != 200) {
                throw new ProviderException(httpResponse.statusCode(), httpResponse.body());
            }
            return objectMapper.readValue(httpResponse.body(), ChatCompletion.class);
        } catch (JsonProcessingException exception) {
            throw new ProviderException("unreadable provider response", exception);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new ProviderException("interrupted while waiting for the provider", exception);
        }
    }
}
```

Retries, timeouts per feature and tracing belong around this class (item 5.3). The replaying client wraps any `ChatCompletionClient` and stores one fixture per distinct request under `src/test/resources`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;

public final class ReplayingChatCompletionClient implements ChatCompletionClient {

    public record Recording(ChatCompletionRequest request, ChatCompletion response) {
    }

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Path recordingDirectory;
    private final Optional<ChatCompletionClient> liveClient;

    public ReplayingChatCompletionClient(Path recordingDirectory, Optional<ChatCompletionClient> liveClient) {
        this.recordingDirectory = recordingDirectory;
        this.liveClient = liveClient;
    }

    @Override
    public ChatCompletion complete(ChatCompletionRequest chatCompletionRequest) {
        try {
            Path fixture = recordingDirectory.resolve(fingerprint(chatCompletionRequest) + ".json");
            if (Files.exists(fixture)) {
                return objectMapper.readValue(fixture.toFile(), Recording.class).response();
            }
            if (liveClient.isEmpty()) {
                throw new IllegalStateException("no recording at " + fixture
                        + "; run with LLM_RECORD=true to record it against the real provider");
            }
            ChatCompletion response = liveClient.get().complete(chatCompletionRequest);
            Files.createDirectories(recordingDirectory);
            objectMapper.writerWithDefaultPrettyPrinter()
                    .writeValue(fixture.toFile(), new Recording(chatCompletionRequest, response));
            return response;
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    private String fingerprint(ChatCompletionRequest chatCompletionRequest) throws IOException {
        try {
            byte[] canonicalJson = objectMapper.writeValueAsBytes(chatCompletionRequest);
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonicalJson);
            return HexFormat.of().formatHex(digest).substring(0, 16);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is required by the Java platform", exception);
        }
    }
}
```

A test factory reads `LLM_RECORD` from the environment: set, it passes the real `HttpChatCompletionClient` as `liveClient` and new fixtures appear on disk to be reviewed and committed; unset (the CI default), a missing fixture fails loudly. The request is part of the fixture so a reviewer can see what was asked. Headers are never recorded, so no key lands in the repository; prompts that contain personal data are anonymised before they become test input. The record and replay ideas apply unchanged behind Spring AI or LangChain4j: wrap the framework's model interface, or point the framework at a WireMock server that serves the same fixtures.

The local-model layer needs no code changes, only configuration and a running Ollama:

```bash
ollama pull <model name from the Ollama library>
curl -s http://localhost:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model": "<model name>", "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 5}'
```

The same `HttpChatCompletionClient` runs against it with `baseUrl=http://localhost:11434` and any non-empty key. With the Spring AI Ollama starter the equivalent is `spring.ai.ollama.base-url=http://localhost:11434` and the model name in `spring.ai.ollama.chat.options.model`.

## Pitfalls

- Asserting exact output strings against a live model, local or hosted. Outputs vary between runs and versions (item 1.2). Assert properties, or assert exact strings only against a recording.
- Treating a passing local-model test as evidence of quality. It proves the pipe, not the prompt; the production model is a different model.
- Fakes that return a tidier response than the provider ever does. Record at least one real response per feature so the parser meets `finish_reason: "length"` and fenced JSON before production does.
- Recordings that outlive the prompt. Fingerprint the whole request, including the model id, so a prompt edit cannot replay a stale answer.
- Secrets or personal data in fixtures. Never serialise headers; anonymise inputs before they become test data.
- The replay client falling through to the live provider in CI. Record mode must be opt-in and absent from the pipeline, or the suite becomes slow, paid and flaky again.
- A raw client with no timeout, retry or trace. The hundred lines you saved by skipping the framework are the lines from item 5.3; write them.
- Pointing the OpenAI-compatible client at Ollama and assuming feature parity. Structured output modes, tool calling and parameters differ by runtime and by model; check what the local model supports before writing a test that depends on it.

## Check yourself

1. A new finish reason or usage field appears in the provider's responses. Which test layer should catch the parsing problem first, and why would a hand-written fake not?
2. Why does the replay client hash the whole request rather than, say, the last user message? What goes wrong with the cheaper key?
3. You are adding a single "summarise this ticket" call to a service with no other AI features. Argue for raw HTTP, for a provider SDK and for Spring AI; what tips the decision?
4. Your integration tests pass against a local model and the feature fails in production with malformed JSON. Which of the four layers was missing or misused?

## Go deeper

- [Ollama](https://ollama.com/) · the runtime, the model library and the API documentation, including the OpenAI-compatible endpoints.
- [OpenAI API reference](https://platform.openai.com/docs/api-reference) · the chat completion request and response fields the records above map to; many providers and runtimes follow this shape.
- [Anthropic documentation](https://docs.anthropic.com/) · the Messages API, which has its own request and usage shape, and the official SDKs.
- [Spring AI Reference](https://docs.spring.io/spring-ai/reference/) · the Ollama chat model chapter and the properties used above.

---

Part of [AI Engineering](../README.md) · items 7.3, 7.4
