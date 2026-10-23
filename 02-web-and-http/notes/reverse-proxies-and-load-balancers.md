# Reverse proxies and load balancers

> **In one sentence:** A reverse proxy owns the client connection (TLS, buffering, timeouts, retries) and hands your application a clean HTTP/1.1 request plus headers describing the original client, a load balancer spreads those requests across instances at layer 4 or layer 7, and your application is only correct if it knows which of those headers to trust.

**Why it matters:** Nearly every production request reaches your service through at least one proxy, and the proxy changes what the service sees: the client IP becomes the proxy's, `https` becomes `http`, and a slow upload becomes a fast one. Redirect loops, rate limits that throttle the load balancer instead of the abuser, 504s for requests that actually succeeded, and deploys that drop in-flight requests are all symptoms of not knowing what sits in front of you.

## The idea

**What a reverse proxy does.** It terminates the client's connection and opens its own to an upstream. Along the way it:

1. **Terminates TLS**, so certificates live in one place and the application speaks plain HTTP on a private network.
2. **Buffers.** By default nginx reads the whole request body before forwarding it and reads the response as fast as the upstream produces it, so a client on a slow mobile link occupies a cheap proxy connection instead of an expensive application thread. The exception is streaming (SSE, large downloads), where buffering must be turned off per location.
3. **Enforces timeouts** independently of the application: connect, read (silence from upstream) and send. When the proxy's read timeout is shorter than the application's processing time, the client gets a 504 while the application finishes the work and nobody is told.
4. **Reuses connections** to the upstream, routes by host and path, serves static files, compresses, rate-limits, and absorbs bad requests before they reach you.

**The headers your application needs.** Because the proxy is now the client, it forwards the original facts in headers: `X-Forwarded-For` (client IP; each proxy appends its *own* client's IP, so the value is a list), `X-Forwarded-Proto` (`https`), `X-Forwarded-Host` and `X-Forwarded-Port`, or the standardised `Forwarded: for=203.0.113.9;proto=https;host=api.example.com` (RFC 7239), which is less widely used. The application uses them to build absolute URLs and redirects, to set `Secure` cookies, to log and rate-limit by real client IP, and to answer `request.isSecure()` correctly.

**Trust is the whole problem.** Any client can send `X-Forwarded-For: 10.0.0.1` itself. A proxy that *appends* produces `X-Forwarded-For: 10.0.0.1, 203.0.113.9`; the only entry you can trust is the one your own proxy added, which is the right-most, and only if the request really came through your proxy. So the application must know the addresses of its proxies and accept forwarded headers only from them. In Spring Boot that is `server.forward-headers-strategy=native` (Tomcat's `RemoteIpValve`, which trusts proxies matching `server.tomcat.remoteip.internal-proxies`, by default the private address ranges) or `framework` (Spring's `ForwardedHeaderFilter`). Never enable either on a service that is reachable without a proxy.

**Load balancing.**

| | Layer 4 | Layer 7 |
|---|---|---|
| Works on | TCP/UDP connections and packets | HTTP requests |
| Can route by | IP and port | host, path, headers, cookies |
| TLS | passes through (or terminates and re-encrypts) | usually terminates |
| Per-connection or per-request | per connection: one HTTP/2 client lands on one backend | per request: streams from one connection are spread |
| Client IP | preserved via the PROXY protocol, or lost | `X-Forwarded-For` |
| Cost | very low, kernel-level | higher, but it understands what it is balancing |

Algorithms: round robin (default), weighted, least connections (better when request durations vary), and hashing on IP or a header (when affinity matters). **Health checks** are active (the balancer probes a URL on a schedule) or passive (it stops sending to a backend after N failures for T seconds). The probe must reflect "can serve requests" without depending on every downstream system, or a database blip takes the whole fleet out of rotation at once. **Sticky sessions** pin a client to one backend with a cookie or hash so in-memory session state keeps working; they also undermine balancing, complicate deploys and make the backend a single point of failure for that user, which is why externalised sessions (item 6.2) are preferred. **Connection draining** (deregistration delay) is the step at deploy time where the balancer stops sending new requests to an instance but lets in-flight ones finish; the application must match it with graceful shutdown (Spring Boot: `server.shutdown=graceful` with `spring.lifecycle.timeout-per-shutdown-phase`), and long-lived connections (item 10.1) need to be closed deliberately because they never finish on their own.

## Example: nginx in front of a Spring Boot service

```nginx
upstream orders_app {
    server 10.0.1.10:8080 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8080 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

server {
    listen 443 ssl;
    http2 on;
    server_name api.example.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    client_max_body_size 10m;

    location / {
        proxy_pass http://orders_app;
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;

        proxy_connect_timeout 5s;
        proxy_read_timeout    60s;
    }

    location /events {
        proxy_pass http://orders_app;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host            $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering  off;
        proxy_read_timeout 1h;
    }
}
```

Line by line, the parts that matter:

- `max_fails`/`fail_timeout` are passive health checks: after three failures the backend is skipped for 30 seconds. Active probes are a separate feature in most balancers.
- `keepalive 32` plus `proxy_http_version 1.1` and an empty `Connection` header keep a pool of open connections to each backend; without all three, nginx opens and closes a TCP connection to Tomcat for every request.
- `http2 on` (nginx 1.25.1 or newer) terminates HTTP/2 from clients while the upstream stays on HTTP/1.1, which is the normal arrangement (item 8.1).
- `$proxy_add_x_forwarded_for` appends `$remote_addr` to any incoming `X-Forwarded-For`, which preserves the chain and is exactly why the application must trust only the last entry.
- `X-Forwarded-Proto $scheme` is what lets the application know the client used HTTPS; without it, redirects come back as `http://` and `Secure` cookies are never set.
- `proxy_read_timeout 60s` must be longer than the slowest request you are willing to serve; the `/events` location raises it for streams and disables buffering so events are not held back.
- `client_max_body_size` defaults to 1 MB; uploads above it fail with 413 at the proxy and never reach your logs.

On the Spring Boot side, with the proxies on a private network:

```properties
server.forward-headers-strategy=native
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
```

Now `HttpServletRequest.getRemoteAddr()` returns the client's address, `getScheme()` returns `https`, and a deploy that drains for 30 seconds at the balancer meets an application that finishes in-flight requests for 30 seconds.

## Pitfalls

- Trusting `X-Forwarded-For` from anyone. Rate limits, geo rules and audit logs are then controlled by the attacker, who sets the header to whatever they like. Trust only your proxies' entry.
- Redirect loops or `http://` redirects behind TLS termination. The application sees plain HTTP, "upgrades" to HTTPS, the proxy forwards it as plain HTTP again. Forward `X-Forwarded-Proto` and enable the forward-headers strategy.
- Proxy timeout shorter than the application's. The client gets a 504 and retries; the application completes both. Align timeouts, and make long operations asynchronous (202 plus a status URL) rather than raising timeouts.
- Retrying non-idempotent requests at the proxy. nginx does not retry `POST` on another upstream by default; turning that on (`non_idempotent`) without idempotency keys is how duplicate orders happen (item 4.1).
- Health checks that test the world. A probe that pings the database and three downstream APIs marks every instance unhealthy at the same moment during an incident, turning a slowdown into an outage.
- Forgetting `Host`. nginx sends the upstream name by default; Spring then builds URLs with `orders_app` in them and virtual hosting on the backend breaks.
- Buffering on a streaming location. SSE and chunked responses arrive late or in bursts; `proxy_buffering off` where you stream, and only there.

## Check yourself

1. A request arrives with `X-Forwarded-For: 198.51.100.7, 203.0.113.9, 10.0.0.5` from your proxy at `10.0.0.5`. Which address is the client, and under what assumption?
2. Your service redirects every HTTPS request to the same URL in an endless loop, but only in production. Which header is missing, and which two settings fix it?
3. Explain why an L4 balancer may send all of one HTTP/2 client's traffic to a single backend and an L7 balancer does not.
4. Design the shutdown sequence for an instance behind a load balancer so that no client sees an error, including the clients holding SSE connections.

## Go deeper

- [nginx: Beginner's Guide](https://nginx.org/en/docs/beginners_guide.html) · the configuration model; read before copying server blocks.
- [nginx: ngx_http_proxy_module](https://nginx.org/en/docs/http/ngx_http_proxy_module.html) and [ngx_http_upstream_module](https://nginx.org/en/docs/http/ngx_http_upstream_module.html) · every directive above, with defaults.
- [MDN: X-Forwarded-For](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/X-Forwarded-For) and [Forwarded](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Forwarded) · the header semantics and the security notes on trusting them.
- [Spring Boot: Embedded web servers how-to](https://docs.spring.io/spring-boot/how-to/webserver.html) and [Graceful shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html) · the forward-headers strategies and the drain-matching shutdown.
- [Cloudflare: What is load balancing?](https://www.cloudflare.com/learning/performance/what-is-load-balancing/) · algorithms and health checks in plain language.

---

Part of [Web & HTTP](../README.md) · items 11.2, 11.3
