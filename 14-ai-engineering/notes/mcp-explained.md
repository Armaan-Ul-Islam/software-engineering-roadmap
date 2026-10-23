# The Model Context Protocol, explained for backend developers

> **In one sentence:** MCP is a JSON-RPC protocol that standardises how an AI application discovers and calls tools, reads resources and fetches prompts from a server, so an integration with one of your systems is written once as a server and reused by every MCP-capable client instead of being rebuilt inside each assistant.

**Why it matters:** Before MCP, every assistant that wanted to reach your ticketing system needed its own adapter, in its own framework, with its own authentication. With MCP the team that owns the system ships one server, and IDE assistants, chat products and your own Spring agents connect to it. That convenience is also the risk: a protocol that makes it trivial to plug arbitrary tools into a model makes it trivial to assemble the combination of private data, untrusted content and outbound actions that leads to data theft (item 6.2).

## The idea

**Roles.** A *host* is the AI application (an IDE assistant, a chat product, your Spring service). Inside it, one *client* holds one connection to one *server*. A server exposes capabilities; the host decides which the model may use. Messages are JSON-RPC 2.0. A session starts with an `initialize` exchange in which both sides state the protocol version and the capabilities they support.

**What a server exposes.**

1. **Tools** are model-controlled: functions the model may ask to call, each with a name, a description and a JSON Schema for its input (`inputSchema`), optionally an `outputSchema` and *annotations* such as `readOnlyHint` and `destructiveHint`. The specification says clients must treat annotations as untrusted unless the server is trusted.
2. **Resources** are application-controlled data addressed by URI (a file, a database row, a log), listed with `resources/list` and fetched with `resources/read`. The host decides when to put a resource into the model's context.
3. **Prompts** are user-controlled templates (`prompts/list`, `prompts/get`) that a server offers for common tasks, such as "review this pull request", with arguments filled in by the host.

A server can also ask things of the client: *sampling* asks the host to run a model completion on the server's behalf, and *elicitation* asks the user for input mid-operation. Servers notify clients when their tool list changes.

**Transports.** *stdio*: the client launches the server as a subprocess and exchanges newline-delimited JSON-RPC over standard input and output; this is how local developer tools run. *Streamable HTTP*: the server is an independent process behind a single endpoint that accepts POSTed messages and may stream responses with server-sent events; a `Mcp-Session-Id` header carries session state. Streamable HTTP replaced the earlier HTTP-plus-SSE transport in the 2025-03-26 revision.

**MCP compared with plain tool calling.** Tool calling (item 4.1) is between your code and the *model*: the provider's API defines how tool definitions and tool calls look. MCP is between your code and the *systems*: it defines how your code discovers and invokes capabilities that someone else maintains. The two compose. The client calls `tools/list` on each server, translates the tool definitions into the model provider's tool format, and when the model emits a tool call, forwards it as `tools/call` and returns the result as the tool result. The model never speaks MCP. What you gain is reuse, dynamic discovery and a clean ownership boundary: the HR team runs the HR server. What you pay is another network hop and trust boundary, a protocol to keep up with, and the temptation to connect twenty servers and drown the model in a hundred tool definitions.

**Spring AI.** Spring AI ships client and server starters built on the MCP Java SDK, supporting stdio and the HTTP transports. On the client side, tools from connected servers appear as Spring AI tool callbacks that a `ChatClient` can use; on the server side, annotated methods become MCP tools. The annotation names and starter artifacts changed between the 1.x and 2.x lines, so follow the reference for your version.

## Example: a tool definition and one call, on the wire

A client asks the server what it offers:

```json
{ "jsonrpc": "2.0", "id": 1, "method": "tools/list" }
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "get_invoice",
        "description": "Fetch one invoice by its number. Returns status, amount and due date. Read-only.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "invoiceNumber": { "type": "string", "description": "For example INV-2024-00017" }
          },
          "required": ["invoiceNumber"]
        },
        "annotations": { "readOnlyHint": true, "destructiveHint": false }
      }
    ]
  }
}
```

The host hands `name`, `description` and `inputSchema` to the model as a tool definition. When the model calls it, the client sends:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": { "name": "get_invoice", "arguments": { "invoiceNumber": "INV-2024-00017" } }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [ { "type": "text", "text": "{\"status\":\"OVERDUE\",\"amount\":\"1250.00\",\"dueDate\":\"2026-10-10\"}" } ],
    "isError": false
  }
}
```

A failure inside the tool comes back the same way with `isError: true` and an explanatory text, so the model can react; a malformed request (unknown tool, invalid arguments) comes back as a JSON-RPC error instead. The content array may also carry images, embedded resources or links to resources, and a tool with an `outputSchema` adds a `structuredContent` object that clients should validate.

## Security

An MCP server is a network service that executes actions on behalf of whoever the model is working for, so the ordinary rules apply, plus a few specific ones.

- **Authentication.** For HTTP transports the specification defines an OAuth 2.1 based flow: the MCP server is a resource server, the client sends `Authorization: Bearer <token>` on every request, PKCE is mandatory, and the server must verify the token was issued for *it* (audience) and must never forward the client's token to upstream APIs. A server that calls another API gets its own token for that API. stdio servers take credentials from their environment.
- **Least privilege.** Expose few, narrow tools, read-only by default, scoped to the calling user's permissions, never a shared over-privileged service account for everyone. A `run_sql` tool is an exploit waiting for a prompt.
- **Human in the loop.** The specification itself says there should always be a human able to deny tool invocations, that clients should show tool inputs before sending them, and that servers must validate inputs, enforce access control and rate limit.
- **Untrusted content.** Tool descriptions and tool results are text that enters the model's context. A malicious or compromised server can inject instructions through either ("tool poisoning"), so vet servers like dependencies and treat results as data (item 6.1).
- **Auditing.** Log every `tools/call` with the user, the arguments and the result reference, on both client and server. Local HTTP servers must validate the `Origin` header and bind to localhost to prevent DNS rebinding from a web page.

## Pitfalls

- Making policy decisions from annotations. `readOnlyHint: true` from a third-party server is a claim, not a guarantee; confirm side effects based on your own knowledge of the tool.
- Connecting many servers and exposing every tool. Tool selection degrades and every request pays for the definitions; curate an allow-list per feature.
- Token passthrough. Forwarding the user's token from the MCP server to a downstream API breaks the audience check and creates a confused deputy.
- Running a stdio server fetched from the internet. It is arbitrary code with your credentials in its environment.
- Treating a tool result as trusted because it came from "our" server. Its content may originate from a document, an email or a web page.
- Pinning nothing. Protocol revisions and SDK majors have had breaking changes; pin versions and negotiate the protocol version explicitly.

## Check yourself

1. Trace a single question from the user to an MCP tool and back: which component translates `tools/list` into the model's tool definitions, and which one sends `tools/call`?
2. Why is `readOnlyHint: true` not a sufficient reason to skip confirmation for a tool from a server you did not write?
3. Your MCP server wraps an internal HR API. A client presents a valid access token that was issued for a different internal service. What must the server do, and what attack does that prevent?
4. When would you expose data as a resource rather than as a tool, and who decides when it enters the model's context in each case?

## Go deeper

- [Model Context Protocol](https://modelcontextprotocol.io/) · the specification, SDKs and the list of reference servers.
- [MCP specification, 2025-06-18 revision](https://modelcontextprotocol.io/specification/2025-06-18) · the normative text for tools, resources, prompts, transports and authorization; the JSON above follows it.
- [Spring AI: MCP](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html) · client and server starters, transports and how MCP tools meet `ChatClient`.
- [Simon Willison: The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) · why mixing tools from different servers is the dangerous part.

---

Part of [AI Engineering](../README.md) · item 4.3
