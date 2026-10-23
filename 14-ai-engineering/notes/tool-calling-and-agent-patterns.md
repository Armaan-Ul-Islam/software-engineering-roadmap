# Tool calling and agent patterns: the loop, the schemas and when a workflow is enough

> **In one sentence:** Tool calling is a protocol in which the model emits a structured request to call one of your functions, your code validates and executes it and returns the result, and the exchange repeats until the model answers; agent patterns are different ways of arranging that loop, and most production features need a fixed workflow rather than an open-ended agent.

**Why it matters:** The loop is where an LLM feature stops being a text box and starts touching your systems, so it is where the expensive mistakes live: a tool that executes whatever id the model invents, a loop that never terminates, three identical emails sent after a retry. It is also where over-engineering starts; "we built an agent" often describes a three-step workflow that would have been cheaper, faster and testable as plain code.

## The idea

**The loop.** You send the model the conversation plus a list of tool definitions. The model answers either with text or with one or more *tool calls*: the tool name, the arguments as JSON, and an id. Your code looks up the tool, validates the arguments against the schema and against the caller's permissions, executes it, and appends a *tool result* carrying the same id to the conversation. Then you call the model again. It may request more tools or produce the final answer. Three consequences follow. The model never executes anything; only your code touches your systems. Every call is a full round trip that costs latency and tokens, and the history grows with every result. And the model decides *whether* to call a tool from your descriptions, so the descriptions are prompt engineering.

**Tool schemas.** A tool is a name, a description and a JSON Schema for its parameters. Write the description to say *when* to call the tool, not only what it does. Use enums for closed sets, mark truly required parameters, describe each property, and keep the set of tools small; a dozen well-described tools beat forty vague ones. Anthropic's advice to "poka-yoke" tools applies: if the model keeps passing relative paths, require absolute ones in the schema rather than correcting it in the prompt.

**Parallel calls.** A model may emit several tool calls in one turn. Execute independent read-only calls concurrently and return all their results in the same turn; a missing result confuses the model and some providers reject the request. Serialise calls with side effects.

**Error handling.** Distinguish errors the model can act on from errors it cannot. "No order with id 8812" goes back as a tool result so the model can ask the user or try another id. A database timeout or an authorisation failure is your problem: retry in code, fail the request, or degrade (item 5.3), but do not ask the model to reason about your infrastructure. Cap the number of iterations and the total token budget per request, set a timeout per tool, and make side-effecting tools idempotent with a key derived from the request (item 4.5), because the loop will retry.

**Where the checks live.** Identity and authorisation never travel through the model. The executing code knows who is calling and checks permissions on every tool call; the model picks the order id, not the tenant. Spring AI's tool context passes such data to tools without showing it to the model.

**Spring AI.** A method annotated with `@Tool(description = ...)` becomes a tool, and `.tools(...)` on a `ChatClient` call registers the object. The framework runs the loop for you by default and returns the final text, and by default it feeds the message of a `RuntimeException` thrown by a tool back to the model while checked exceptions propagate to the caller. Those defaults, and the class that drives the loop, have moved between versions; read the tool-calling chapter for yours.

**Agent patterns.** Anthropic's "Building effective agents" distinguishes *workflows*, where code decides the sequence of model calls, from *agents*, where the model decides its own next step from tool results. The workflow patterns, in increasing freedom:

1. **Prompt chaining.** Fixed steps, each consuming the previous output, with programmatic gates between them (translate, then classify, then draft).
2. **Routing.** Classify the input, then dispatch to a specialised prompt, tool set or smaller model.
3. **Parallelisation.** Run independent calls at once and merge in code, either by *sectioning* a task or by *voting* (several attempts, majority or any-fail wins).
4. **Orchestrator-workers.** One model call breaks the task into subtasks that could not be predicted in advance, workers handle them, the orchestrator synthesises.
5. **Evaluator-optimizer.** One call generates, another critiques against clear criteria, and the loop repeats until the critic is satisfied.

Choose a workflow when the task is well understood, the steps are predictable, and you need bounded cost, bounded latency and something you can test case by case. Choose an agent when the steps genuinely cannot be enumerated (debugging a failing build, open-ended research) and mistakes are cheap to detect and undo. Start with a single well-prompted call with retrieval; add structure only when evaluation shows you need it.

## Example: a two-step tool-calling conversation

```text
User       "Is order 8812 delayed? If so, let the customer know."

Model   -> tool_call  id=call_1  get_order(orderId="8812")
Code       validates id format, checks the user may see order 8812, runs OrderTools.getOrder
Code    -> tool_result id=call_1  {"status":"SHIPPED","promisedDate":"2026-10-20","eta":"2026-10-27"}

Model   -> tool_call  id=call_2  send_customer_message(orderId="8812",
                                   text="Your order is delayed; the new estimate is 27 October.")
Code       side effect: shows recipient and text to the operator, waits for approval, sends once
           (idempotency key = conversation id + call_2)
Code    -> tool_result id=call_2  {"sent":true,"messageId":"m_5531"}

Model   -> text "Order 8812 is about a week late. I have told the customer the new estimate."
```

Two round trips, one confirmation, one audit log entry per tool call. If `get_order` had thrown `IllegalArgumentException("No order with id 8812")`, the message would have gone back as the tool result and the model would have asked the user to check the number instead of inventing a status.

## Example: a minimal `@Tool` method

```java
import org.springframework.ai.tool.annotation.Tool;

public class OrderTools {

    private final OrderRepository orderRepository;

    public OrderTools(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Tool(description = "Look up an order by its id and return its status, promised date and current ETA. "
            + "Call this before answering any question about delivery or delays.")
    public OrderStatus getOrder(String orderId) {
        return orderRepository.findStatus(orderId)
                .orElseThrow(() -> new IllegalArgumentException("No order with id " + orderId));
    }
}
```

```java
String answer = chatClient.prompt()
        .user(question)
        .tools(new OrderTools(orderRepository))
        .call()
        .content();
```

`OrderStatus` is a record of yours; the framework serialises it into the tool result. The description does two jobs: it tells the model what comes back and when to call the tool.

## Pitfalls

- No iteration cap. A confused model calls the same tool with the same arguments forever; bound iterations and tokens, and log when the cap is hit.
- Broad tools. "Run this SQL" or "execute this shell command" will be used for everything, cannot be gated, and cannot be audited by intent. Prefer narrow tools you can allow-list (item 4.4).
- Side effects without confirmation or idempotency. A retry after a timeout sends the email twice.
- Letting the model supply identity. If the tenant id is a tool parameter, the model will eventually pass the wrong one. Take it from the authenticated request.
- Returning whole tables as tool results. Context fills, cost rises, and the model loses the detail it needed. Page, filter and summarise in code.
- Vague descriptions. The model does not call the tool, or calls the wrong one, and nothing errors. Test tool selection with an evaluation set (item 5.1).
- Building an agent for a three-step task. It is slower, dearer and impossible to test deterministically; write the workflow.

## Check yourself

1. Who executes a tool call, and what does that imply about where authorisation checks and idempotency live?
2. A tool throws because the order id does not exist; another tool times out against the database. Which error goes back to the model and which does not, and why?
3. Classify "translate the ticket, detect its sentiment, draft a reply" and "work out why the nightly build failed and fix it" as workflow or agent, and name the patterns you would use.
4. The model emits three calls in one turn: two read-only lookups and one refund. How do you execute them, and what does the model receive back?

## Go deeper

- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) · the workflow patterns above, the case for simplicity, and the appendix on designing tools.
- [Spring AI: Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html) · `@Tool`, tool context, exception handling defaults and how the loop is driven in your version.
- [Claude Developer Platform: Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) · one provider's precise description of the request and result messages in the loop; other providers document the same shape.
- [OWASP GenAI Security Project](https://genai.owasp.org/) · the risks of excessive agency and what least privilege means for tools (item 4.4).

---

Part of [AI Engineering](../README.md) · items 4.1, 4.2
