# Web & HTTP

> What actually happens between a client and your server: DNS, TCP, TLS, HTTP semantics, caching, cookies, the browser security model, API styles, and real-time protocols.

**Prerequisites:** [Foundations](../01-foundations/README.md)

**Done when you can:**

- Narrate what happens when a URL is typed, down to the TCP and TLS handshakes, and say where each millisecond goes.
- Choose correct HTTP methods, status codes and headers for an API, and explain idempotency and safety to a teammate.
- Design a caching strategy with `Cache-Control`, `ETag` and a CDN, and debug a stale-content incident.
- Explain the same-origin policy and fix a CORS error without weakening security.
- Compare HTTP/1.1, HTTP/2 and HTTP/3 and say when the difference matters.
- Pick between WebSockets, Server-Sent Events, long polling and plain polling for a feature, and defend the choice.

## Roadmap

### 1. The big picture

- [ ] 1.1 From URL to pixels: DNS lookup, TCP handshake, TLS handshake, request, response, parsing and rendering · [notes](notes/what-happens-when-you-type-a-url.md) · [What happens when...](https://github.com/alex/what-happens-when) · [HPBN: Primer on Latency and Bandwidth](https://hpbn.co/primer-on-latency-and-bandwidth/)
- [ ] 1.2 Who sits between you and the user: browsers, proxies, reverse proxies, gateways, load balancers, CDNs · [MDN: An overview of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Overview)
- [ ] 1.3 URLs and URIs: scheme, host, port, path, query, fragment, percent-encoding, and the bugs they cause · [notes](notes/urls-and-percent-encoding.md) · [MDN: URIs](https://developer.mozilla.org/en-US/docs/Web/URI)

### 2. DNS

- [ ] 2.1 Resolution path: stub resolver, recursive resolver, root, TLD and authoritative servers; caching and TTLs · [notes](notes/dns-in-depth.md) · [How DNS works](https://howdns.works/) · [Cloudflare: What is DNS?](https://www.cloudflare.com/learning/dns/what-is-dns/)
- [ ] 2.2 Record types you will meet: A/AAAA, CNAME, MX, TXT, SRV, NS, SOA, and why the apex cannot be a CNAME · [notes](notes/dns-in-depth.md) · [Cloudflare: DNS records](https://www.cloudflare.com/learning/dns/dns-records/)
- [ ] 2.3 DNS for operations: TTL and failover, split-horizon, GeoDNS, health-checked records, DNS as a load balancer · [Cloudflare: DNS-based load balancing](https://www.cloudflare.com/learning/performance/what-is-dns-load-balancing/)
- [ ] 2.4 Debugging with `dig`, negative caching, and the resolver cache on your own machine · [notes](notes/dns-in-depth.md) · [Mess with DNS](https://messwithdns.net/) · [Julia Evans: How DNS works (comics)](https://wizardzines.com/comics/)

### 3. TCP, TLS and connections

- [ ] 3.1 TCP from the application's view: handshake cost, slow start, Nagle, keep-alive, and why connection reuse is the cheapest optimisation · [notes](notes/connection-management-timeouts-and-pools.md) · [HPBN: Building Blocks of TCP](https://hpbn.co/building-blocks-of-tcp/)
- [ ] 3.2 TLS: handshake, certificates and chains, SNI, ALPN, session resumption, what TLS 1.3 changed · [notes](notes/tls-handshake-and-certificates.md) · [Cloudflare: What happens in a TLS handshake?](https://www.cloudflare.com/learning/ssl/what-happens-in-a-tls-handshake/) · [HPBN: Transport Layer Security](https://hpbn.co/transport-layer-security-tls/) · [How HTTPS works](https://howhttps.works/)
- [ ] 3.3 Certificates in practice: CAs, Let's Encrypt and ACME, expiry, wildcard vs SAN, trust stores and the Java `cacerts` errors you will meet · [notes](notes/tls-handshake-and-certificates.md) · [Let's Encrypt: How it works](https://letsencrypt.org/how-it-works/)
- [ ] 3.4 Connection management: connect/read/write timeouts, pools, head-of-line blocking, and what happens when a pool is exhausted · [notes](notes/connection-management-timeouts-and-pools.md) · [MDN: Connection management in HTTP/1.x](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Connection_management_in_HTTP_1.x)

### 4. HTTP semantics

- [ ] 4.1 Request and response anatomy; methods; safe vs idempotent vs neither, and why retries depend on it · [notes](notes/http-methods-status-codes-and-idempotency.md) · [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) · [MDN: HTTP request methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods)
- [ ] 4.2 Status codes that matter, and the ones people misuse · [notes](notes/http-methods-status-codes-and-idempotency.md) · [MDN: HTTP response status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status)
  - [ ] 4.2.1 2xx and 3xx: 200 vs 201 vs 202 vs 204; 301/302/303/307/308 and method preservation · [MDN: Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections)
  - [ ] 4.2.2 4xx: 400 vs 422, 401 vs 403, 404 vs 410, 405, 406, 409, 412, 415, 429 · [MDN: 401 Unauthorized](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/401)
  - [ ] 4.2.3 5xx: 500 vs 502 vs 503 vs 504, `Retry-After`, and why "200 with an error body" breaks clients · [MDN: Retry-After](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After)
- [ ] 4.3 Headers and content negotiation: `Content-Type` and charsets, `Accept*`, `Content-Length` vs chunked transfer, `Range`, `Location` · [notes](notes/content-negotiation-compression-and-conditional-requests.md) · [MDN: Content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation) · [MDN: HTTP headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers)
- [ ] 4.4 Representations: JSON, form encoding, multipart uploads, streaming bodies, compression (gzip, Brotli, zstd) · [notes](notes/content-negotiation-compression-and-conditional-requests.md) · [MDN: Compression in HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression)
- [ ] 4.5 Conditional requests: `ETag`/`If-None-Match`, `If-Match` for optimistic concurrency over HTTP, `If-Modified-Since` · [notes](notes/content-negotiation-compression-and-conditional-requests.md) · [MDN: Conditional requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests)
- [ ] 4.6 Inspecting all of the above with `curl` (`-v`, `-I`, `--write-out`, `--resolve`) and browser DevTools · [notes](notes/curl-for-http-debugging.md) · [Everything curl](https://everything.curl.dev/) · [Chrome DevTools: Network panel](https://developer.chrome.com/docs/devtools/network)

### 5. Caching

- [ ] 5.1 `Cache-Control` directives, freshness lifetime, heuristic caching, validators and revalidation · [notes](notes/http-caching.md) · [MDN: HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching) · [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [ ] 5.2 Private vs shared caches, `Vary` and cache keys, CDNs, purging and the "stale content" incident · [notes](notes/http-caching.md) · [Cloudflare: What is a CDN?](https://www.cloudflare.com/learning/cdn/what-is-a-cdn/)
- [ ] 5.3 Strategies: immutable fingerprinted assets, `no-cache` vs `no-store`, `stale-while-revalidate`, caching API responses · [notes](notes/http-caching.md) · [web.dev: Prevent unnecessary network requests with the HTTP Cache](https://web.dev/articles/http-cache)

### 6. State: cookies, sessions, tokens

- [ ] 6.1 Cookies: `Secure`, `HttpOnly`, `SameSite`, `Domain`, `Path`, `Max-Age`; first-party vs third-party · [notes](notes/cookies-sessions-and-tokens.md) · [MDN: Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
- [ ] 6.2 Server-side sessions vs stateless tokens: trade-offs in revocation, scaling, and complexity · [notes](notes/cookies-sessions-and-tokens.md) · [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [ ] 6.3 Where a browser app should keep a token, and why "JWT in localStorage" is contested (deep dive in Security) · [notes](notes/cookies-sessions-and-tokens.md) · [OWASP: HTML5 Security Cheat Sheet, local storage](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html#local-storage)

### 7. The browser security model

- [ ] 7.1 The same-origin policy: what an origin is and what it protects · [notes](notes/cors-and-the-same-origin-policy.md) · [MDN: Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy)
- [ ] 7.2 CORS: simple vs preflighted requests, credentials, the headers, the common mistakes, and the correct server-side fix · [notes](notes/cors-and-the-same-origin-policy.md) · [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [ ] 7.3 Security headers at a glance: CSP, HSTS, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` (deep dive in Security) · [MDN: Content Security Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP) · [securityheaders.com](https://securityheaders.com/)
- [ ] 7.4 Mixed content, subresource integrity, and why `http://` assets on an `https://` page fail · [MDN: Mixed content](https://developer.mozilla.org/en-US/docs/Web/Security/Mixed_content)

### 8. HTTP versions and performance

- [ ] 8.1 HTTP/1.1 pipelining's failure, HTTP/2 multiplexing and header compression, and why server push died · [notes](notes/http1-http2-http3.md) · [HTTP/2 explained](https://http2-explained.haxx.se/) · [MDN: Evolution of HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Evolution_of_HTTP)
- [ ] 8.2 HTTP/3 and QUIC: why UDP, 0-RTT, connection migration, what changes for your server · [notes](notes/http1-http2-http3.md) · [HTTP/3 explained](https://http3-explained.haxx.se/) · [Cloudflare: What is HTTP/3?](https://www.cloudflare.com/learning/performance/what-is-http3/)
- [ ] 8.3 A latency budget: DNS, TCP, TLS, time to first byte, download; measuring each with `curl --write-out` and DevTools · [notes](notes/curl-for-http-debugging.md) · [curl: --write-out variables](https://everything.curl.dev/usingcurl/verbose/writeout.html)

### 9. API styles over HTTP

- [ ] 9.1 REST as Fielding defined it, the pragmatic REST everyone builds, and the Richardson maturity model · [notes](notes/rest-api-design-essentials.md) · [Fielding: REST dissertation, ch. 5](https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm) · [Richardson Maturity Model](https://martinfowler.com/articles/richardsonMaturityModel.html)
- [ ] 9.2 Designing resources: naming, nesting, pagination (offset vs cursor), filtering, sorting, versioning, partial updates · [notes](notes/rest-api-design-essentials.md) · [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/) · [Google API Improvement Proposals](https://google.aip.dev/)
- [ ] 9.3 Error responses with Problem Details (RFC 9457), and consistent validation errors · [notes](notes/rest-api-design-essentials.md) · [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
- [ ] 9.4 OpenAPI: describing an API, generating clients and servers, contract-first vs code-first · [notes](notes/openapi-contract-first.md) · [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) · [Swagger Editor](https://editor.swagger.io/)
- [ ] 9.5 GraphQL and gRPC: the problems they solve, their costs, and when plain REST remains the answer · [notes](notes/graphql-and-grpc-vs-rest.md) · [GraphQL: Learn](https://graphql.org/learn/) · [gRPC: Introduction](https://grpc.io/docs/what-is-grpc/introduction/)
- [ ] 9.6 Webhooks: delivery guarantees, retries, signatures, idempotent receivers · [notes](notes/webhooks-done-right.md) · [Stripe docs: Webhooks](https://docs.stripe.com/webhooks) · [Standard Webhooks](https://www.standardwebhooks.com/)

### 10. Real-time and streaming

- [ ] 10.1 Polling, long polling, Server-Sent Events, WebSockets: trade-offs and infrastructure impact (proxies, timeouts, scaling) · [notes](notes/websockets-sse-and-long-polling.md) · [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) · [MDN: WebSockets API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)
- [ ] 10.2 Streaming responses: chunked transfer, NDJSON, backpressure to slow clients · [MDN: Streams API concepts](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Concepts)

### 11. Servers, proxies and load balancers

- [ ] 11.1 What a web server does: thread-per-request (Tomcat) vs event loop (Netty, Node); where the request thread blocks · [Tomcat: HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html)
- [ ] 11.2 Reverse proxies: nginx basics, TLS termination, `X-Forwarded-For`/`Forwarded`, buffering and timeouts · [notes](notes/reverse-proxies-and-load-balancers.md) · [nginx: Beginner's Guide](https://nginx.org/en/docs/beginners_guide.html) · [MDN: X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For)
- [ ] 11.3 Load balancing: L4 vs L7, algorithms, health checks, sticky sessions, connection draining · [notes](notes/reverse-proxies-and-load-balancers.md) · [Cloudflare: What is load balancing?](https://www.cloudflare.com/learning/performance/what-is-load-balancing/)
- [ ] 11.4 Edge protection: rate limiting, WAFs, bot management (algorithms in System Design) · [Cloudflare: What is rate limiting?](https://www.cloudflare.com/learning/bots/what-is-rate-limiting/)

## Resources

### Start here

- [High Performance Browser Networking](https://hpbn.co/) · Ilya Grigorik's free book. Chapters 1-4 and 9-12 are the best explanation of TCP, TLS and HTTP for developers.
- [MDN HTTP guides](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides) · accurate, current, and readable. Use it as the reference while working through section 4 to 8.
- [What happens when...](https://github.com/alex/what-happens-when) · the classic end-to-end walkthrough, deeper than any interview answer.
- [Everything curl](https://everything.curl.dev/) · learn HTTP by driving it by hand.
- [Cloudflare Learning Center](https://www.cloudflare.com/learning/) · short, correct explainers on DNS, TLS, CDNs, load balancing and DDoS.

### Books

- [HTTP: The Definitive Guide](https://www.oreilly.com/library/view/http-the-definitive/1565925092/) · old but still the most thorough tour of HTTP/1.1 mechanics (paid).
- [Computer Networking: A Top-Down Approach](https://gaia.cs.umass.edu/kurose_ross/) · the application-layer chapters cover HTTP and DNS with exercises.
- [RESTful Web APIs](https://www.oreilly.com/library/view/restful-web-apis/9781449359713/) · Richardson and Amundsen; the thinking behind resource design (paid).

### Courses and videos

- [Hussein Nasser](https://www.youtube.com/@hnasr) · deep, practical videos on HTTP versions, proxies, TLS and backend networking.
- [Kurose & Ross video lectures](https://gaia.cs.umass.edu/kurose_ross/lectures.php) · free university-level networking lectures.
- [Julia Evans: wizard zines](https://wizardzines.com/) · the HTTP and DNS zines are the fastest way to fix a shaky mental model (some free comics, zines are paid).

### References

- RFCs: [9110 Semantics](https://www.rfc-editor.org/rfc/rfc9110.html), [9111 Caching](https://www.rfc-editor.org/rfc/rfc9111.html), [9112 HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html), [9113 HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html), [9114 HTTP/3](https://www.rfc-editor.org/rfc/rfc9114.html), [9000 QUIC](https://www.rfc-editor.org/rfc/rfc9000.html), [6265 Cookies](https://www.rfc-editor.org/rfc/rfc6265.html), [9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html).
- [roadmap.sh: API Design](https://roadmap.sh/api-design) and [roadmap.sh: Backend](https://roadmap.sh/backend) · visual overviews.
- [httpbin](https://httpbin.org/) · a request/response playground for experiments with headers, status codes and redirects.
- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/) · a complete, opinionated API style guide you can adopt as-is.
