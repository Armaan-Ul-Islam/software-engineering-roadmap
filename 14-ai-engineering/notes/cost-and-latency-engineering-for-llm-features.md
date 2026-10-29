# Cost and latency engineering for LLM features

> **In one sentence:** A model call is billed per input and output token and takes a time to first token that grows with the input plus a per-token time for the output, so every lever you have (token budgets, prompt caching, streaming, batching, routing to smaller models, usage budgets) either sends fewer tokens, reuses tokens already sent, hides the time the rest take, or stops the spend before it surprises you.

**Why it matters:** The demo costs nothing and answers in two seconds. The production feature runs twenty thousand times a day with a three-thousand-token prompt, and the first invoice is the moment the team learns that output tokens cost several times more than input tokens and that nobody capped `max_tokens`. Latency is the other half: a page that blocks for eight seconds waiting for a complete answer feels broken even when the answer is good. Both are engineering problems with measurable levers, and interviewers like them because the arithmetic is simple and most candidates have never done it.

## The idea

**The cost model.** Price per request is roughly `uncachedInputTokens * inputRate + cachedInputTokens * cachedRate + outputTokens * outputRate`, with rates per million tokens on the provider's pricing page. Three things are true on every price list at the time of writing, although the figures change often: output tokens cost several times more than input tokens, cached input tokens cost a fraction of uncached ones (some providers also charge a premium to write the cache), and batch endpoints are discounted. Do not hard-code rates; keep them in configuration with the date you copied them, and treat your computed cost as an estimate that the invoice corrects. Reasoning modes produce hidden output tokens that are billed; check the usage figures, not the visible answer length.

**The latency model.** Time to first token grows with the input, because the whole prompt is processed before the first output token, and cached prefixes skip most of that. After the first token, each output token takes roughly constant time, so total latency is dominated by the length of the answer. Queueing and rate limiting add a tail: a 429 followed by a backoff retry (item 5.3) can double a response time. Reasoning modes add their hidden tokens to the wait.

**The levers.**

1. **Token budgets.** Cap the input per feature: count tokens with the provider's tokeniser or counting endpoint, cut history and low-ranked chunks deliberately rather than letting the provider truncate, and reject inputs over the budget before sending them. Cap the output with `max_tokens` (the field name varies by provider) set per feature, and ask for compact formats: a JSON object instead of prose, a label instead of an explanation.
2. **Prompt caching.** Order the prompt so the stable part comes first (item 2.3). The cached tokens are cheaper and skip prefill, so time to first token drops as well. Verify it works by reading the cached-token count in each response; a prefix that is one byte different is a cache miss.
3. **Streaming.** Does not reduce total time but changes what the user experiences: the first words arrive in well under a second and the user reads while the model writes. It only helps when a human reads the output as it arrives. A structured answer that must be parsed whole gains nothing, and a stream that breaks halfway has to start over.
4. **Batching.** For work nobody is waiting on (nightly classification, backfills, eval runs), submit requests to the provider's batch endpoint, which returns results within a window of hours at a discount. Within a single request, several small items in one prompt ("classify these twenty tickets") saves repeated prefix tokens, but output truncation and position effects on quality are real, so measure before adopting it.
5. **Routing to smaller models.** Use the smallest model that passes the feature's eval (item 5.1). A cheap model classifies and extracts; the expensive one synthesises. Route by rule (feature, input length), by a cheap classifier, or by escalation: try the small model, and send the request to the large one only when validation fails or the small model answers `NOT_SURE`. Routing is a measured decision, never a feeling.
6. **Response caching.** Identical normalised inputs with the same prompt version and model can be served from a cache keyed by a hash of all three. Semantic caching (serving a stored answer to a similar question) is a retrieval system with its own false positives; treat it as one.

**Cost control in operation.** Read the usage object from every response and record input, cached and output tokens, tagged by feature, model, prompt version and tenant. Chart tokens per request (p50 and p95), cost per day per feature, and the cache hit ratio. A jump in tokens per request after a deploy means a prompt, a retriever or a history setting changed. Enforce budgets in code: a soft daily limit per feature that alerts, a hard limit that degrades (route to the small model, or switch the feature off with an honest message) instead of running up the bill; and per-user quotas, because one user pasting a three-hundred-page document in a loop can cost more than the rest of the tenant. Review the price list and the model landscape every few months; the cheapest adequate model changes.

## Example: reading usage and turning it into metrics

An OpenAI-compatible chat completion response carries the facts you need. Anthropic's API reports the same facts under different names (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`), and whether the cached figure is a subset of the input figure or separate from it differs between providers; read the usage section of the API reference before writing the arithmetic.

```json
{
  "id": "chatcmpl-...",
  "model": "...",
  "choices": [
    {"index": 0, "message": {"role": "assistant", "content": "{\"category\": \"BILLING\", ...}"}, "finish_reason": "stop"}
  ],
  "usage": {
    "prompt_tokens": 2840,
    "completion_tokens": 212,
    "total_tokens": 3052,
    "prompt_tokens_details": {"cached_tokens": 2560}
  }
}
```

The service records usage with Micrometer so the same numbers feed dashboards, alerts and the eval report:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;

public record TokenUsage(long inputTokens, long cachedInputTokens, long outputTokens) {
}

public record ModelRates(double inputPerMillion, double cachedInputPerMillion, double outputPerMillion) {

    public double estimatedCost(TokenUsage usage) {
        long uncachedInputTokens = usage.inputTokens() - usage.cachedInputTokens();
        return (uncachedInputTokens * inputPerMillion
                + usage.cachedInputTokens() * cachedInputPerMillion
                + usage.outputTokens() * outputPerMillion) / 1_000_000d;
    }
}

public final class UsageRecorder {

    private final MeterRegistry meterRegistry;

    public UsageRecorder(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void record(String feature, String model, String promptVersion, TokenUsage usage, ModelRates rates, Duration latency) {
        tokenCounter(feature, model, "input").increment(usage.inputTokens());
        tokenCounter(feature, model, "cached_input").increment(usage.cachedInputTokens());
        tokenCounter(feature, model, "output").increment(usage.outputTokens());
        Counter.builder("llm.cost.estimated")
                .tag("feature", feature).tag("model", model).tag("prompt_version", promptVersion)
                .register(meterRegistry)
                .increment(rates.estimatedCost(usage));
        Timer.builder("llm.latency")
                .tag("feature", feature).tag("model", model)
                .publishPercentiles(0.5, 0.95)
                .register(meterRegistry)
                .record(latency);
    }

    private Counter tokenCounter(String feature, String model, String kind) {
        return Counter.builder("llm.tokens")
                .tag("feature", feature).tag("model", model).tag("kind", kind)
                .register(meterRegistry);
    }
}
```

`ModelRates` is loaded from configuration, per model, with the date the figures were copied from the pricing page. The `prompt_version` tag is what lets you see that a prompt change doubled the output tokens before the invoice does.

## Example: where the tokens go

The ticket-triage feature runs 20,000 times a day. Each request carries a 2,560-token stable prefix (system prompt, schema, examples), about 280 tokens of ticket, and produces about 200 tokens of output. Token volumes per day under four configurations:

| Configuration | Uncached input | Cached input | Output |
|---|---|---|---|
| Baseline, no caching | 56.8 M | 0 | 4.0 M |
| Prefix cached (ordering fixed) | 5.6 M | 51.2 M | 4.0 M |
| Prefix trimmed to 1,200 tokens (fewer examples, eval unchanged) | 5.6 M | 24.0 M | 4.0 M |
| Output as a label plus one-sentence summary (about 60 tokens) | 5.6 M | 24.0 M | 1.2 M |

Multiply each column by the rate on your provider's pricing page to get money. The shape of the result is the lesson: the first change removes most of the input bill and a large share of the time to first token, and the last change, which is a prompt instruction, removes most of the output bill, which is the expensive column. The eval must pass after each step, or you have bought cheapness with quality.

Streaming, for the features where a person reads the answer, is a request flag and a different response shape. The provider sends server-sent events, one JSON fragment per chunk, and your service forwards them to the browser as they arrive:

```text
data: {"choices":[{"delta":{"content":"Double"}}]}

data: {"choices":[{"delta":{"content":" charge"}}]}

data: [DONE]
```

Usage figures for a streamed response arrive at the end, if the provider includes them at all; check the API reference for the flag that requests them.

## Pitfalls

- No `max_tokens` on a feature that should answer in one sentence. One runaway answer costs more than a day of normal traffic, and a long answer is also the slowest one.
- Hard-coded prices. They are wrong within months, and the estimate silently diverges from the invoice.
- Caching assumed rather than measured. A timestamp in the system prompt, and the cached-token count has been zero since the last deploy.
- Measuring latency only as a mean. The p95 is what users complain about, and retries after 429 responses live in the tail.
- Routing to a smaller model because it is cheaper, without running the eval against it. The savings are real and so is the quality drop; see both numbers on the same page.
- Batching items into one prompt and not checking `finish_reason`. The twentieth ticket got truncated and nobody noticed.
- Budgets that only alert. By the time a human reads the alert, the hard limit should already have degraded the feature.
- Per-tenant cost with no per-user quota. The abuse case is one account, not the average.

## Check yourself

1. A request has 3,000 input tokens of which 2,500 are a stable prefix, and 150 output tokens. Which single change most reduces cost, and which most reduces the time to first token? Are they the same change?
2. Streaming makes the assistant feel faster. For which of these does it help, and why: a chat answer read by a user, a JSON classification consumed by code, a summary rendered after the page loads?
3. You want to route eighty per cent of tickets to a cheaper model. Describe the measurement that justifies the routing rule and the signal that sends a ticket to the expensive model instead.
4. Tokens per request for one feature doubled overnight with no deploy. List three causes and the metric tag that distinguishes them.

## Go deeper

- [OpenAI: Latency optimization](https://platform.openai.com/docs/guides/latency-optimization) · the latency levers in one provider's words, including output length, streaming and parallelism.
- [OpenAI: Prompt caching](https://platform.openai.com/docs/guides/prompt-caching) · how one provider's automatic prefix caching works and how to structure prompts for it.
- [Anthropic documentation](https://docs.anthropic.com/) · the prompt caching and batch processing guides for the other major provider; note that caching is explicit there.
- [Artificial Analysis](https://artificialanalysis.ai/) · independent price, speed and quality comparisons across models, for the routing decision.

---

Part of [AI Engineering](../README.md) · items 2.4, 5.4
