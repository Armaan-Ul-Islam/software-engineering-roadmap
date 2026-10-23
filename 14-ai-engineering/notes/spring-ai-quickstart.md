# Spring AI quickstart: ChatClient, advisors and where the pieces live

> **In one sentence:** Spring AI gives a Spring Boot application a portable `ChatClient` over any supported model provider, plus advisors for cross-cutting behaviour, structured output mapping, tool calling, a `VectorStore` abstraction and evaluation helpers; the provider is chosen by a starter and a few properties, and because the API has moved between release lines, the reference documentation for your exact version is part of the toolkit.

**Why it matters:** Most Java teams meet LLMs through Spring AI, and most of their first-week problems are not about models at all: a tutorial written for a milestone release whose artifact names no longer resolve, a `ChatClient` bean that silently bypasses observability, a vector store table that is no longer created automatically. Knowing what the framework provides, how a request is wired, and which parts are volatile saves that week.

## The idea

**What Spring AI provides.**

1. **Model abstractions.** `ChatModel`, `EmbeddingModel` and friends, with one implementation per provider (hosted APIs and local runtimes alike). Your code targets the abstraction; the starter picks the implementation.
2. **`ChatClient`.** A fluent API over a `ChatModel`: `prompt()`, `system(...)`, `user(...)`, then `call()` for a synchronous answer or `stream()` for a reactive one, and finally `content()` for text or `entity(Class)` for a Java object. Nothing is sent until the terminal method runs; `call()` only selects the mode.
3. **Advisors.** Interceptors around the model call, like servlet filters for prompts. The reference ships advisors for conversation memory, for retrieval-augmented generation against a `VectorStore`, and for logging requests and responses; you can write your own for redaction, guardrails or caching. Order matters, and the memory advisor needs a conversation id on every call.
4. **Structured output.** `entity(...)` derives a JSON schema from your type, instructs the model, and parses the answer. It is documented as best effort, so validate (item 2.2).
5. **Tool calling.** `@Tool` methods registered with `.tools(...)`; the framework drives the loop (item 4.1).
6. **Vector stores and ETL.** A `VectorStore` interface with implementations for PostgreSQL with pgvector and many others, portable metadata filter expressions, and document readers and splitters for ingestion (item 3.2).
7. **MCP** client and server starters (item 4.3), **evaluation** helpers of the LLM-judge kind (item 5.1), and **observability** through Micrometer for every model call when you use the autoconfigured client.

**How a request is wired.** You import the `spring-ai-bom` and add one provider starter named `spring-ai-starter-model-<provider>`. The starter autoconfigures a `ChatModel` from properties and a prototype-scoped `ChatClient.Builder`. You inject the builder, set defaults (system prompt, advisors, tools), build a `ChatClient`, and call it from a service or controller. Swapping providers means swapping the starter and the properties; the calling code does not change, although provider-specific options and feature coverage (tool calling, native structured output) do.

**Configuration selects the provider.** Each provider has a property namespace, `spring.ai.<provider>.*`, with the API key or base URL and chat options such as the model id and temperature. Model ids change often; copy the current one from the provider's model list rather than from a blog post. For local development and tests, a local runtime such as Ollama has its own starter and a base URL instead of a key (item 7.4).

**The parts most likely to change.** At the time of writing there are three maintained lines (1.0.x, 1.1.x and 2.0.x, the last requiring Spring Boot 4). Between them, the advisor API, the class that drives the tool-calling loop, the MCP annotations, structured-output options and the vector store schema defaults have all changed. Pin versions through the BOM, read the upgrade notes before moving, and treat any snippet older than your version, including the one below, as the shape rather than the letter.

## Example: a minimal chat endpoint

Dependencies, with the version managed in one place:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.ai</groupId>
            <artifactId>spring-ai-bom</artifactId>
            <version>${spring-ai.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.ai</groupId>
        <artifactId>spring-ai-starter-model-openai</artifactId>
    </dependency>
</dependencies>
```

Configuration (the property names follow the provider; this is the OpenAI starter's namespace):

```properties
spring.ai.openai.api-key=${OPENAI_API_KEY}
# copy the current model id from the provider's model list
spring.ai.openai.chat.options.model=replace-me
```

The endpoint:

```java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ChatController {

    private final ChatClient chatClient;

    public ChatController(ChatClient.Builder chatClientBuilder) {
        this.chatClient = chatClientBuilder
                .defaultSystem("You are the support assistant for Acme. Answer in at most three sentences.")
                .build();
    }

    @PostMapping("/chat")
    public String chat(@RequestBody String question) {
        return chatClient.prompt()
                .user(question)
                .call()
                .content();
    }
}
```

```shell
curl -s -X POST localhost:8080/chat -H 'Content-Type: text/plain' -d 'What are your opening hours?'
```

That is the whole wiring: the starter built the model, the builder came from autoconfiguration, and the controller holds a client with a default system prompt. Everything else is added at the builder (default advisors, default tools) or per call (`.tools(...)`, `.advisors(...)`, `.entity(...)`). To see what is actually sent, enable the logging advisor and set its logger to `DEBUG`; the first time you read a real request, including the format instructions `entity()` appends, is the moment the framework stops being magic.

## Pitfalls

- Copying pre-1.0 snippets. Artifact names and packages were renamed before the 1.0 release; if a dependency does not resolve, check the current naming in the reference rather than hunting for an old repository.
- Creating your own client with `ChatClient.create(chatModel)` or `ChatClient.builder(chatModel)` as a bean. It bypasses the autoconfigured builder, so observability and any builder customisers are silently ignored. Inject `ChatClient.Builder` instead.
- Expecting the vector store table to appear. Schema initialisation is opt-in (`initialize-schema`) in current versions, a documented breaking change from earlier ones; the embedding dimension must also match your model.
- Adding the memory advisor without a conversation id. Every request looks like a new conversation and nothing is remembered.
- Treating `entity()` as validated. It is a parser with a prompt; validate the result like any input.
- Mixing Spring Boot and Spring AI lines that do not support each other. Check the compatibility statement on the getting-started page before upgrading either.
- Letting the framework hide the tool loop and the prompt. Turn on request logging in development and tracing in production (item 5.2).

## Check yourself

1. What does the provider starter autoconfigure, and which single type do you inject into your own class to get a `ChatClient`?
2. Why does defining `ChatClient.create(chatModel)` as a bean lose observability, and what is the supported alternative?
3. Which parts of a Spring AI application would you expect to touch when moving between release lines, and how do you find out before you upgrade?
4. How would you run the same `/chat` endpoint against a local model for integration tests, and what would you change to do it?

## Go deeper

- [Spring AI Reference](https://docs.spring.io/spring-ai/reference/) · the reference for your version; the version selector at the top is the first thing to check.
- [Spring AI: Getting Started](https://docs.spring.io/spring-ai/reference/getting-started.html) · the BOM, starters, supported Spring Boot versions and upgrade notes.
- [Spring AI: ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html) · the fluent API, defaults, advisors and the entity mapping shown above.
- [Spring AI: Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html) · how the advisor chain works and how to write your own.
- [Spring Initializr](https://start.spring.io/) · generates a project with the right BOM and starter for the provider you pick.

---

Part of [AI Engineering](../README.md) · item 7.1
