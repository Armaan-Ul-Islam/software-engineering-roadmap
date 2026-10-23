# Structured output: schemas, Java records and validation at the boundary

> **In one sentence:** Ask the model for JSON that matches a schema derived from a Java record, then treat what comes back exactly like a request body from an unknown client: parse it, validate it with Bean Validation and your own semantic checks, and when it fails, retry once or twice with the error message fed back.

**Why it matters:** Free-text output is where LLM features die during integration. The regex that parsed fifty demo answers breaks on the fifty-first, the category comes back as "Billing issue" instead of `BILLING`, a long list is cut off mid-array, and the invented field `refundAmount` gets persisted because nobody checked for unknown properties. Structured output plus validation at the boundary turns a fuzzy component into something the rest of the service can depend on.

## The idea

Downstream code needs to branch on the result, store it, join it to other data and show it in a UI. Prose cannot be branched on, and even "just answer with the category" drifts between runs and between model versions. So you ask for a machine-readable shape and you verify it.

There are two ways to get JSON out of a model, and most stacks use both:

1. **Prompt-based.** The prompt includes the JSON schema and an instruction to answer with JSON only. Models comply most of the time. Spring AI's `entity(Class)` works this way: it derives a JSON schema from your type, appends format instructions to the prompt and parses the answer. The reference documentation describes it as a best effort and recommends combining it with schema validation.
2. **Constrained decoding.** The provider restricts sampling so that every generated token keeps the output valid against a grammar derived from your schema. This guarantees valid JSON that conforms to the schema features the provider supports (types, required properties, enums). Providers honour only a subset of JSON Schema, and numeric ranges, string lengths and patterns are often ignored, so check their documentation. Newer Spring AI versions can delegate to the provider's native structured output; the option names vary between versions.

Neither mechanism guarantees that the content is *true*. An order id can be well-formed and non-existent. A summary can be a valid string and wrong. The schema is a contract about shape; validation at the boundary is about meaning.

**Mapping to a Java record.** The record is the single source of truth. Its components become properties, Java types become JSON types, an enum becomes an `enum` constraint, a `List` becomes an array. Keep the record small and flat; nested optional structures multiply the ways the model can go wrong. Give every enum an escape value such as `OTHER` so the model is never forced to guess, and tell it in the prompt when to use it.

**Validating at the boundary.** Run the parsed record through Bean Validation (`jakarta.validation`) exactly as you would a controller's request body, then add semantic checks in code: referenced ids exist, numbers add up, dates fall in range, quoted text actually appears in the source.

**Retrying with feedback.** When parsing or validation fails, do not simply resend the prompt. Send the model its previous answer together with the specific errors ("urgency must be between 1 and 5, was 7"). Bound the attempts, typically two or three, and have a fallback: queue for a human, use a default, or return an honest error. Log every retry; the rate of invalid first answers is a quality signal for your evaluation suite (item 5.1).

## Example: a record, its schema and the validate-and-retry loop

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public enum TicketCategory { BILLING, DELIVERY, TECHNICAL, OTHER }

public record TicketTriage(
        @NotNull TicketCategory category,
        @Min(1) @Max(5) int urgency,
        @NotBlank @Size(max = 200) String summary,
        @NotNull List<@NotBlank String> mentionedOrderIds) {
}
```

The schema this record implies, and which you send to the model:

```json
{
  "type": "object",
  "properties": {
    "category": { "type": "string", "enum": ["BILLING", "DELIVERY", "TECHNICAL", "OTHER"] },
    "urgency": { "type": "integer", "description": "1 (low) to 5 (critical)" },
    "summary": { "type": "string", "description": "At most 200 characters" },
    "mentionedOrderIds": { "type": "array", "items": { "type": "string" } }
  },
  "required": ["category", "urgency", "summary", "mentionedOrderIds"],
  "additionalProperties": false
}
```

Note that `@Min`, `@Max` and `@Size` appear only as descriptions. Many providers ignore numeric and length keywords during constrained decoding, which is exactly why the same constraints are enforced in Java.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.ArrayList;
import java.util.List;
import org.springframework.ai.chat.client.ChatClient;

public final class TicketTriageService {

    private static final int MAX_ATTEMPTS = 3;
    private static final String SYSTEM_PROMPT = """
            Classify the support ticket. Answer with JSON only, matching this schema.
            Use category OTHER when unsure. List an order id only if it appears verbatim in the ticket.
            """;

    private final ChatClient chatClient;
    private final Validator validator;
    private final ObjectMapper objectMapper = new ObjectMapper()
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    private final String schemaJson;

    public TicketTriageService(ChatClient chatClient, Validator validator, String schemaJson) {
        this.chatClient = chatClient;
        this.validator = validator;
        this.schemaJson = schemaJson;
    }

    public TicketTriage triage(String ticketText) {
        String correction = "";
        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            String json = chatClient.prompt()
                    .system(SYSTEM_PROMPT + schemaJson)
                    .user(ticketText + correction)
                    .call()
                    .content();
            try {
                TicketTriage candidate = objectMapper.readValue(json, TicketTriage.class);
                List<String> problems = validate(candidate, ticketText);
                if (problems.isEmpty()) {
                    return candidate;
                }
                correction = feedback(json, problems);
            } catch (JsonProcessingException exception) {
                correction = feedback(json, List.of("not valid JSON for the schema: " + exception.getOriginalMessage()));
            }
        }
        throw new TriageUnavailableException("no valid triage after " + MAX_ATTEMPTS + " attempts");
    }

    private List<String> validate(TicketTriage candidate, String ticketText) {
        List<String> problems = new ArrayList<>();
        for (ConstraintViolation<TicketTriage> violation : validator.validate(candidate)) {
            problems.add(violation.getPropertyPath() + " " + violation.getMessage());
        }
        for (String orderId : candidate.mentionedOrderIds()) {
            if (!ticketText.contains(orderId)) {
                problems.add("mentionedOrderIds contains '" + orderId + "', which does not appear in the ticket");
            }
        }
        return problems;
    }

    private static String feedback(String previousJson, List<String> problems) {
        return "\n\nYour previous answer was:\n" + previousJson
                + "\nIt was rejected because:\n- " + String.join("\n- ", problems)
                + "\nReturn corrected JSON only.";
    }
}
```

`TriageUnavailableException` is your own unchecked exception. Jackson rejects an unknown enum value such as `"Billing issue"` and any unexpected property with a `JsonProcessingException`, so hallucinated fields never reach your domain model. The `urgency` of 7 passes parsing and is caught by `@Max(5)`. The invented order id passes both and is caught by the semantic check. All three produce a specific correction for the next attempt. With constrained decoding switched on, the first branch almost never triggers, and the loop still earns its place for the other two.

## Failure modes to expect

| Failure | How it shows up | What to do |
|---|---|---|
| Truncation | Output token limit hit; JSON ends mid-array; parse error | Check the finish reason, raise the output limit, shorten the schema, or paginate the input |
| Wrong enum value | Synonym or different casing: `"billing"`, `"Billing issue"` | Keep enums in the schema, give the model the exact values, fail parsing on unknown values |
| Hallucinated fields | Extra properties the model thought were helpful | `FAIL_ON_UNKNOWN_PROPERTIES` and `additionalProperties: false` |
| Wrong type | `"urgency": "high"` or `"3"` | Strict parsing, feed the error back |
| Markdown fences | ```` ```json ```` around the body | Prefer constrained decoding; otherwise strip them deliberately and log it |
| Plausible but false content | Valid id that does not exist, summary that invents a refund | Semantic validation against your data and against the source text |

## Pitfalls

- Trusting constrained decoding to mean "validated". It guarantees shape, not truth, and only for the schema keywords the provider supports.
- Parsing with a lenient `ObjectMapper`. Spring Boot's auto-configured mapper ignores unknown properties by default; use a strict one at this boundary.
- Retrying without feedback. Resending the identical prompt mostly reproduces the identical mistake.
- Schemas with deep nesting and many optional fields. Every optional branch is a place for the model to be creative; flatten and split into several calls if needed.
- Forcing a choice. An enum without `OTHER` or a required field that may not be inferable from the input guarantees confident nonsense.
- Treating the record as the contract with the frontend. Map the model's record to your API's DTO so the prompt can change without breaking clients.

## Check yourself

1. Constrained decoding guarantees the output matches the schema. Name two failures it cannot prevent and the layer where each is caught in the example.
2. Why should the retry message include the model's previous output and the specific errors rather than just the original prompt again?
3. Your record declares `@Min(1) @Max(5) int urgency` and the provider ignores `minimum` and `maximum`. Trace what happens when the model returns 7.
4. The output arrives wrapped in ```` ```json ```` fences. Should you strip them silently, fail the attempt, or change the request? What does each choice cost?

## Go deeper

- [OpenAI: Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) · one provider's constrained-decoding implementation and its supported JSON Schema subset; other providers document theirs similarly.
- [Spring AI: Structured Output Converter](https://docs.spring.io/spring-ai/reference/api/structured-output-converter.html) · how `entity()` derives the schema, and the note that it is best effort.
- [JSON Schema](https://json-schema.org/) · the specification the schemas above follow.
- [Jakarta Bean Validation 3.1](https://jakarta.ee/specifications/bean-validation/3.1/) · the constraint annotations and how violations are reported.

---

Part of [AI Engineering](../README.md) · item 2.2
