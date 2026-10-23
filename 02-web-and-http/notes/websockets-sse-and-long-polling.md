# WebSockets, Server-Sent Events and long polling

> **In one sentence:** Polling, long polling, Server-Sent Events and WebSockets are four ways to get data to a browser as it happens, ordered from "plain HTTP that every proxy understands" to "a persistent two-way socket that your whole infrastructure has to know about"; pick the simplest one whose latency and direction fit.

**Why it matters:** Real-time features are chosen by demo ("WebSockets look cool") and fail in production by infrastructure: a load balancer that closes idle connections after 60 seconds, a proxy that buffers the event stream, a deployment that drops ten thousand sockets at once, or a server that buffers messages for a slow client until it runs out of memory. Each technique has a known list of these consequences.

## The idea

**Polling.** The client asks every N seconds. Ordinary cacheable `GET`s, nothing to configure, works through every proxy and firewall. Latency is up to N, and most requests return nothing. Right for data that changes rarely or where a minute of delay is fine.

**Long polling.** The client asks; the server holds the request open until there is data or a timeout, answers, and the client immediately asks again. Latency drops to one round trip after the event. Still plain HTTP, so it works everywhere, but every message costs a full request and response, and a held request occupies whatever the server uses per request: a thread in a thread-per-request server (item 11.1), so 10,000 waiting clients need 10,000 threads or an asynchronous servlet (`DeferredResult` in Spring MVC). The server's hold time must be shorter than every idle timeout between it and the client (load balancers commonly default to around 60 seconds), or the proxy returns a 504 before the server answers.

**Server-Sent Events (SSE).** One long-lived `GET` whose response has `Content-Type: text/event-stream` and never ends; the server writes events as text frames. One direction only (server to client), text only, but with features the others make you build yourself: the browser's `EventSource` reconnects automatically, sends `Last-Event-ID` so the server can resume, and honours a server-specified `retry` delay. Over HTTP/1.1 each stream is a connection, and browsers allow six per origin, so a dashboard with seven tabs stalls; over HTTP/2 the streams multiplex onto one connection. Proxies must not buffer the response (nginx: `proxy_buffering off`, or the `X-Accel-Buffering: no` response header), and the server must send a comment line (`: keep-alive`) more often than the shortest idle timeout on the path. Right for feeds, notifications, progress and anything else that flows one way.

**WebSockets.** Start as an HTTP/1.1 request with `Upgrade: websocket`; the server answers `101 Switching Protocols` and the TCP connection stops being HTTP and becomes a framed, full-duplex, binary-or-text socket. Lowest overhead per message, both directions, right for chat, collaborative editing, games and anything with frequent client-to-server traffic. Costs: every hop must understand the upgrade (nginx needs `proxy_http_version 1.1` plus the `Upgrade` and `Connection` headers forwarded; over HTTP/2 the upgrade does not exist and needs RFC 8441); nothing is HTTP any more, so no caching, no status codes, no automatic reconnection or resume (you write heartbeat, reconnect and replay logic yourself); authentication happens once at the handshake (browsers cannot set headers on a WebSocket, so it is the cookie or a token in the URL or first message); and the server becomes stateful.

**The infrastructure consequences**, which apply to SSE and WebSockets alike:

- **Timeouts.** Every proxy, load balancer and NAT device has an idle timeout. Heartbeats (SSE comments, WebSocket ping frames) must beat the shortest one.
- **Scaling.** A connection lives on one instance, but an event can originate anywhere. Fan-out needs a broker (Redis pub/sub, a message queue) that every instance subscribes to; sticky sessions do not solve it. Connection counts, not request rates, become the capacity metric.
- **Deployments.** Restarting an instance drops all of its connections at once and ten thousand clients reconnect at once. Drain connections before shutdown (item 11.3) and add jitter to client reconnect delays.
- **Backpressure.** A slow client cannot read faster than its network allows. If the server keeps queueing messages for it, memory grows until the process dies. Bound the per-connection queue and drop, coalesce or disconnect when it fills.
- **Thread model.** Thousands of idle connections on a thread-per-connection server pin thousands of threads. Use an asynchronous or event-loop server (Netty, Spring WebFlux) or virtual threads for the connection-holding part.

## Example: an SSE stream

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no

: keep-alive

id: 1042
event: order-updated
data: {"orderId":"9f3b2c","status":"shipped"}

id: 1043
event: order-updated
data: {"orderId":"a71e04","status":"paid"}

retry: 5000

```

Each event is one or more `field: value` lines ending with a blank line. `id` is what the browser echoes in `Last-Event-ID` when it reconnects, so the server can replay 1044 onwards; `event` selects the handler on the client (`eventSource.addEventListener('order-updated', …)`); `retry` tells the client to wait five seconds before reconnecting; a line starting with `:` is a comment, which is the heartbeat. Multi-line payloads use several `data:` lines, joined with newlines.

## Example: a WebSocket handshake

The request and response, observed with `curl --http1.1` against a public echo server, using the sample key from RFC 6455:

```http
GET / HTTP/1.1
Host: echo.websocket.org
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==

```

```http
HTTP/1.1 101 Switching Protocols
upgrade: websocket
connection: Upgrade
sec-websocket-accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=

```

The `Sec-WebSocket-Accept` value proves the server understood the WebSocket handshake rather than echoing headers: it is the SHA-1 of the client's key concatenated with a fixed GUID, base64-encoded. You can check it yourself:

```bash
printf '%s' 'dGhlIHNhbXBsZSBub25jZQ==258EAFA5-E914-47DA-95CA-C5AB0DC85B11' | openssl dgst -sha1 -binary | base64
```

```text
s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

After the 101, the bytes on the wire are WebSocket frames, not HTTP. Run the same curl without `--http1.1` against an HTTP/2 server and you get a `200` with a body and no upgrade: HTTP/2 has no `Upgrade` header, so the handshake silently degrades to an ordinary request. That is the single most common "WebSockets work locally but not behind the load balancer" cause.

## Pitfalls

- Choosing WebSockets for one-way data. You inherit reconnection, resume, heartbeats and a stateful server to replace what SSE gives you for free.
- A server timeout longer than the proxy's. Long polls return 504 from the proxy; event streams die every 60 seconds and reconnect in a storm. Know the idle timeout of every hop.
- Buffering proxies. SSE events arrive in batches minutes late, or never. `proxy_buffering off` (or `X-Accel-Buffering: no`) for the stream location, and check any CDN in front.
- SSE over HTTP/1.1 with several tabs. The six-connection limit per origin is shared across tabs; the seventh stream waits forever. Serve over HTTP/2 or put the stream on its own hostname.
- Unbounded send queues. One client on a bad connection takes down the instance for everyone. Bound the queue per connection and decide in advance what to do when it fills.
- Fan-out through sticky sessions. Affinity keeps a client on one instance; it does nothing to deliver an event produced on another. You need a broker.
- Token in the WebSocket URL. It ends up in access logs along the whole path. Prefer the session cookie (same-site rules apply) or send the token as the first message over the socket and close if it does not arrive.
- No jitter on reconnect. A deploy disconnects everyone at once, everyone reconnects at the same second, and the new instance falls over. Randomise the delay and back off.

## Check yourself

1. A page shows build progress for a job that runs a few minutes. Which technique, and what three headers or settings make it survive a proxy?
2. Why can a WebSocket handshake fail silently when the client reaches the server over HTTP/2, and what two ways fix it?
3. Your event service runs on four instances behind a load balancer. An order is updated by a request handled on instance 2; the user's SSE connection is on instance 4. Describe the path the event must take.
4. Define backpressure for a WebSocket server and give two policies for a client that cannot keep up.

## Go deeper

- [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) and [Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) · the client API, the stream format and the reconnection behaviour.
- [MDN: WebSockets API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API) · the browser side; the authentication constraint is explained there.
- [HPBN: WebSocket](https://hpbn.co/websocket/) · framing, the handshake, and the performance characteristics against HTTP alternatives.
- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html) · section 1.3 is the handshake above; section 5 the framing.
- [nginx: WebSocket proxying](https://nginx.org/en/docs/http/websocket.html) · the three directives a reverse proxy needs.
- [Spring Framework: WebSockets](https://docs.spring.io/spring-framework/reference/web/websocket.html) · the server side in Spring MVC, including STOMP over WebSocket and the broker relay for fan-out.

---

Part of [Web & HTTP](../README.md) · item 10.1
