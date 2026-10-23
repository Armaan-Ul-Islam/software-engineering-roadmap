# HTTP/1.1, HTTP/2 and HTTP/3

> **In one sentence:** Each HTTP version removed one layer of head-of-line blocking: HTTP/1.1 serves one response per connection at a time, HTTP/2 multiplexes many streams over one TCP connection but a single lost packet still stalls them all, and HTTP/3 moves to QUIC so that loss on one stream leaves the others running.

**Why it matters:** The semantics (methods, status codes, headers) are identical across versions, so the differences are easy to ignore until they bite: a WebSocket upgrade that silently fails over HTTP/2, a load balancer that sees one connection instead of fifty, header-name comparisons that break because HTTP/2 lowercases everything, or a latency budget built on handshakes that HTTP/3 no longer pays.

## The idea

**Head-of-line (HOL) blocking** is any situation where a message that is ready to go must wait behind one that is not.

1. **HTTP/1.1** allows one outstanding request per connection. Pipelining (sending several requests without waiting) was specified, but responses had to come back in order, a slow first response blocked the rest, and enough proxies mishandled it that every browser disabled it. The workaround was parallel connections, six per origin in browsers, plus domain sharding, sprite sheets and bundling to squeeze more into each. Every connection pays its own TCP and TLS handshakes and warms up its own congestion window.
2. **HTTP/2** replaces the text protocol with binary frames over a single connection per origin. Each request is a **stream** with an ID; frames from different streams interleave, so a slow response no longer blocks a fast one at the HTTP layer. **HPACK** compresses headers with a static table of common fields and a per-connection dynamic table, so a repeated `cookie:` or `authorization:` header costs a few bytes instead of a kilobyte. Header names are lowercase and the start line becomes pseudo-headers (`:method`, `:path`, `:authority`, `:status`). **Server push** let the server send resources the client had not asked for; in practice servers pushed things the browser already had cached, it was hard to configure and measured as neutral or harmful, and Chrome removed it in 2022. `103 Early Hints` plus `<link rel=preload>` took its place. HTTP/2 also dropped hop-by-hop mechanics: there is no `Connection`, `Transfer-Encoding` or `Upgrade` header, so a WebSocket handshake over HTTP/2 needs the separate extended `CONNECT` method of RFC 8441, which not every proxy implements.
3. **HTTP/2's remaining problem** is TCP. TCP delivers bytes in order, so when one segment is lost, every stream waits for the retransmission even though their own bytes have arrived. On lossy networks (mobile, Wi-Fi) a single HTTP/2 connection can be slower than six HTTP/1.1 connections, because loss on one of six only stalls one sixth of the work.
4. **HTTP/3** runs over **QUIC**, a transport built on UDP in user space. QUIC has streams of its own, each with independent loss recovery, so a lost packet delays only the stream it belonged to. TLS 1.3 is built into the transport: the handshake that took one TCP round trip plus one TLS round trip now takes one round trip in total, and a resumed connection can send a request in the first packet (0-RTT). Connections are identified by a connection ID rather than the IP and port tuple, so a phone moving from Wi-Fi to cellular keeps its connection. Headers use **QPACK**, a redesign of HPACK that tolerates out-of-order delivery. Clients discover HTTP/3 through an `Alt-Svc: h3=":443"` header on an earlier response or an `HTTPS` DNS record, and fall back to TCP when UDP 443 is blocked, which corporate networks still do.

**What changes for a backend developer.** Usually the proxy or load balancer terminates HTTP/2 and HTTP/3 and speaks HTTP/1.1 to your application, so your code sees no difference. What does change:

- Header names arrive lowercase. Code that compares `X-Request-Id` case-sensitively breaks; use the servlet API, which is case-insensitive.
- One client now holds one connection and sends everything over it, in bursts of up to a hundred concurrent streams. Per-connection limits, connection-count metrics and connection-based load balancing (item 11.3) all behave differently; an L4 balancer may send one busy client's entire load to a single backend.
- `Upgrade` does not exist in HTTP/2 or HTTP/3. A WebSocket client talking to an HTTP/2 endpoint without RFC 8441 gets an ordinary response, not a 101 (see item 10.1).
- New attack surface: HTTP/2 Rapid Reset (CVE-2023-44487) exhausted servers by opening and cancelling streams faster than they could be processed. Keep the proxy that terminates HTTP/2 current.
- HTTP/3 to the application itself is rare (Tomcat and Jetty do not speak QUIC); terminate it at the edge.

## Example: the same request over HTTP/1.1 and HTTP/2

```bash
curl --http1.1 -sv -o /dev/null https://example.com/
```

```text
* ALPN: curl offers http/1.1
* ALPN: server accepted http/1.1
> GET / HTTP/1.1
> Host: example.com
< HTTP/1.1 200 OK
< Content-Type: text/html; charset=utf-8
< Transfer-Encoding: chunked
```

```bash
curl --http2 -sv -o /dev/null https://example.com/
```

```text
* ALPN: curl offers h2,http/1.1
* ALPN: server accepted h2
* using HTTP/2
* [HTTP/2] [1] OPENED stream for https://example.com/
* [HTTP/2] [1] [:method: GET]
* [HTTP/2] [1] [:scheme: https]
* [HTTP/2] [1] [:authority: example.com]
* [HTTP/2] [1] [:path: /]
< HTTP/2 200
< content-type: text/html; charset=utf-8
< alt-svc: h3=":443"; ma=86400
```

Three differences to notice: ALPN inside the TLS handshake chose the version (item 3.2), the request became pseudo-headers on stream 1, and the response headers are lowercase with no `Transfer-Encoding` (framing is the transport's job now). The `alt-svc` header is the server advertising HTTP/3 on UDP 443 for the next 86400 seconds.

Two requests in parallel show the multiplexing. HTTP/1.1 reuses the connection but serialises; HTTP/2 opens a second stream on the same connection:

```text
$ curl --http1.1 -sv -o /dev/null -o /dev/null https://example.com/ https://example.com/s.js 2>&1 | grep -E 'Connected|Re-using|serially'
* Connected to example.com (2606:4700:10::6814:179a) port 443
* Found bundle for host: 0x7786c102a0 [serially]
* Re-using existing connection with host example.com

$ curl -Z --http2 -sv -o /dev/null -o /dev/null https://example.com/ https://example.com/s.js 2>&1 | grep -E 'Connected|stream|Multiplexed'
* Connected to example.com (2606:4700:10::6814:179a) port 443
* [HTTP/2] [1] OPENED stream for https://example.com/
* Multiplexed connection found
* [HTTP/2] [3] OPENED stream for https://example.com/s.js
```

HTTP/3 needs a curl built with a QUIC library; `curl --version` lists `HTTP3` under Features when it is. The macOS system curl is not:

```text
$ curl --http3 -sv https://cloudflare-quic.com/ -o /dev/null
curl: option --http3: the installed libcurl version doesn't support this
```

On a build that supports it, the same `-v` output shows no separate TCP connect and TLS handshake stages (the QUIC handshake carries TLS), ALPN offering `h3`, and a status line of `HTTP/3 200`; `--write-out '%{http_version}'` prints `3`. `curl --http3` tries QUIC directly, while `--http3-only` refuses to fall back, which is useful for checking that UDP 443 is actually reachable from a network.

## Pitfalls

- Assuming HTTP/2 is always faster. On a lossy link a single TCP connection can lose to six; HTTP/3 is the real fix for that case. Measure on the networks your users have.
- Keeping HTTP/1.1 workarounds. Domain sharding and bundling hurt under HTTP/2: sharding forces extra connections and defeats HPACK's dynamic table; huge bundles delay first use of code that could have streamed as separate files.
- Case-sensitive header handling. Logging, routing rules or security filters that look for `Authorization` with a capital A see nothing over HTTP/2.
- Connection-count assumptions. Rate limits per connection, "max connections per IP" protections and least-connections balancing all see one connection where they used to see dozens.
- WebSocket or `Upgrade` behind an HTTP/2 edge. The handshake needs HTTP/1.1 to the server or RFC 8441 support along the whole path; otherwise the client gets a 200 and no socket.
- Blocking UDP 443 and wondering why HTTP/3 "does not work". Clients fall back silently; `curl --http3-only` from inside the network shows the truth.

## Check yourself

1. Explain head-of-line blocking at the HTTP layer and at the TCP layer. Which version removed which, and what did it cost?
2. A browser on a train with 2 % packet loss loads a page with 40 small resources. Why might HTTP/1.1 with six connections beat HTTP/2 here, and why does HTTP/3 beat both?
3. Why did server push fail in practice, and what mechanism replaced it?
4. Your load balancer distributes by connection and one tenant's HTTP/2 client suddenly saturates a single backend. What changed, and what balancing strategy fixes it?

## Go deeper

- [HTTP/2 explained](https://http2-explained.haxx.se/) and [HTTP/3 explained](https://http3-explained.haxx.se/) · Daniel Stenberg's free books; short, authoritative, and written by the person who implemented both in curl.
- [HPBN: HTTP/2](https://hpbn.co/http2/) · framing, streams, HPACK and prioritisation with diagrams; the chapter to read once properly.
- [MDN: Evolution of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Evolution_of_HTTP) · the history in one page, from HTTP/0.9 to HTTP/3.
- [Chrome: Removing HTTP/2 server push](https://developer.chrome.com/blog/removing-push) · the data behind the decision and the recommended replacements.
- [curl: HTTP/3](https://curl.se/docs/http3.html) · how to get a curl build with QUIC support, and the current state of each backend.
- [RFC 9113: HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html), [RFC 9114: HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html) and [RFC 9000: QUIC](https://www.rfc-editor.org/rfc/rfc9000.html) · the specifications, for when a proxy and a client disagree.

---

Part of [Web & HTTP](../README.md) · items 8.1, 8.2
