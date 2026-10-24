# Connection management: keep-alive, pools, timeouts and TIME_WAIT

> **In one sentence:** Every new TCP connection costs a handshake (plus a TLS handshake and a cold congestion window) before the first byte, so HTTP clients keep connections in a pool; the pool's size, its four timeouts and the server's connection limits then decide whether a slow dependency merely slows you down or takes you down with it.

**Why it matters:** The two classic service-to-service outages are a client pool exhausted because one slow dependency holds every connection, and a client with no read timeout that hangs on a half-open connection until every request thread is waiting on it. Both are configuration, and the defaults of most HTTP clients get both wrong: no timeouts at all, or a pool of five connections per host.

## The idea

**What a connection costs** (item 3.1). The TCP handshake is one round trip before any payload; TLS 1.3 adds one more (item 3.2). Then slow start lets a new connection send about ten segments (roughly 14 KB) in its first round trip and doubles that each round trip, so a cold connection is slow for large responses even on a fast link. Each connection also holds a file descriptor and kernel buffers on both ends and, on the server, a connection slot. Inside a data centre with a 1 ms round trip this is cheap; across the internet at 30 to 100 ms the handshakes dominate the request. Reusing the connection makes every request after the first pay none of it.

**Keep-alive and pooling.** HTTP/1.1 connections are persistent unless someone sends `Connection: close`. One request is in flight per connection at a time (pipelining failed, item 8.1), so N concurrent requests need N connections, and a pool keeps idle ones keyed by route (scheme, host, port, proxy). Servers close idle connections after their own keep-alive timeout (Tomcat's `keepAliveTimeout` defaults to its `connectionTimeout`, 60 seconds; nginx's `keepalive_timeout` is 75 seconds; load balancers commonly use 60). A connection the server closed while it sat in your pool is **stale**: the next request on it fails with `NoHttpResponseException` or a connection reset. The defences are to validate a connection that has been idle for more than a moment before reusing it, to evict idle connections before the server would, to give connections a maximum lifetime so DNS changes and new backends get picked up, and to retry idempotent requests once on a stale-connection failure (item 4.1).

With HTTP/2 the pool shrinks to one or two connections per origin carrying up to `SETTINGS_MAX_CONCURRENT_STREAMS` (commonly 100) requests at once, and the blocking moves down to TCP (item 8.1).

**The four timeouts.** Each guards a different wait, and leaving any of them infinite is a bug.

| Timeout | Guards the wait for | Fires when | Sane value |
|---|---|---|---|
| Connect | the TCP handshake to complete | host down, firewall dropping SYNs, server accept queue full | 1 to 3 s inside a data centre; the OS default is far longer (Linux retries the SYN for about 127 s) |
| Pool acquisition (connection request) | a free connection in the pool | the pool is exhausted | well under a second; fail fast rather than queue |
| Socket (read) | the next byte on the socket | the server hung after accepting, or the network died silently | the dependency's p99.9 latency plus margin; never infinite |
| Response or total | the response head, or the whole exchange | slow server, slowly trickling body | what the caller can tolerate, and shorter than the caller's own timeout |

The socket timeout bounds the gap between bytes, not the total: a server that trickles one byte every 9 seconds never trips a 10-second socket timeout, which is why a total deadline exists too. The JDK `HttpClient` offers only two of the four, `connectTimeout` on the client and `timeout` on the request, and the request timeout covers the wait for the response headers, not the body.

**Head-of-line blocking at the pool.** With HTTP/1.1 a slow response occupies its connection until it finishes. With five connections per route and five slow calls in flight, the sixth request waits for the *pool*, not for the server, and nothing in its latency says so. Isolation is the cure: a separate pool, or at least a separate per-route limit, for each dependency, and a short acquisition timeout so that waiting shows up as an error instead of as latency.

**When the client pool is exhausted.** Requests queue for the acquisition timeout and then fail with `ConnectionRequestTimeoutException` (Apache HttpClient 5). In a thread-per-request server the queued threads are blocked, so all 200 Tomcat threads can end up waiting for the pool, and the service is down because a dependency was slow. Size the pool with Little's law: connections needed equals throughput times latency, so 200 requests per second at 250 ms needs about 50 connections, plus headroom for the p99. Apache HttpClient's default of five per route is a trap for a service that talks to one host.

**When the server runs out of connections.** Tomcat accepts up to `maxConnections` (8192 by default) and lets `acceptCount` (100) more wait in the kernel's accept queue; beyond that the kernel drops handshake packets, so the client sees a connect timeout, or a connection that seems to open and never answers, but not "connection refused". Running out of worker threads (`maxThreads`, 200) is different: the connection is accepted and the request waits for a thread, so the client sees a slow response and then a read timeout. File descriptor limits (`ulimit -n`) produce "Too many open files" on either side. As a rule of thumb, connect timeouts mean the server cannot accept and read timeouts mean it cannot process.

**TIME_WAIT on busy clients.** The side that closes a TCP connection first keeps the (source address, source port, destination address, destination port) tuple in `TIME_WAIT` for twice the maximum segment lifetime: 60 seconds on Linux (fixed in the kernel), 30 seconds on macOS (`net.inet.tcp.msl` is 15,000 ms). A client that opens and closes a connection per request to one destination burns a fresh ephemeral port each time. Linux offers 28,232 ports by default (`net.ipv4.ip_local_port_range` is 32768 to 60999), so about 470 new connections per second to one destination is the sustained ceiling before `connect` fails with `EADDRNOTAVAIL` ("Cannot assign requested address"); macOS has 16,384 ports and a 30-second wait, so about 540. The fix is the subject of this note: reuse connections. `net.ipv4.tcp_tw_reuse=1` helps outgoing connections on Linux; `tcp_tw_recycle` broke clients behind NAT and was removed in kernel 4.12. Count them with `ss -s` on Linux or `netstat -an -p tcp | grep -c TIME_WAIT` on macOS.

## Example: Apache HttpClient 5 configured on purpose

```java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

public final class PricingClientFactory {

    public static CloseableHttpClient create() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(5))
                .setValidateAfterInactivity(TimeValue.ofSeconds(1))
                .setTimeToLive(TimeValue.ofMinutes(5))
                .build();

        PoolingHttpClientConnectionManager connectionManager = PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(100)
                .setMaxConnPerRoute(50)
                .setDefaultConnectionConfig(connectionConfig)
                .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofMilliseconds(500))
                .setResponseTimeout(Timeout.ofSeconds(5))
                .build();

        return HttpClients.custom()
                .setConnectionManager(connectionManager)
                .setDefaultRequestConfig(requestConfig)
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .evictExpiredConnections()
                .build();
    }
}
```

Line by line: `setConnectTimeout` and `setSocketTimeout` are the first and third timeouts in the table. `setValidateAfterInactivity` checks a connection that has been idle for over a second before handing it out, which catches most stale connections, and `setTimeToLive` retires every connection after five minutes regardless. The pool allows 100 connections in total and 50 to any one route, sized from throughput times latency. `setConnectionRequestTimeout` is the pool acquisition timeout and `setResponseTimeout` the wait for the response head. The two `evict*` calls start a background thread that closes idle and expired connections, so the pool rather than the server decides when a connection dies. Without this configuration the library's defaults are 25 connections in total, 5 per route, three minutes for connect and for waiting on the pool, and no limit on reads.

Create one client per dependency and share it for the life of the application; `PoolingHttpClientConnectionManager.getTotalStats()` reports leased, pending, available and max, and belongs on a dashboard. The JDK client, for comparison:

```java
HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();
HttpRequest request = HttpRequest.newBuilder(URI.create("https://pricing.example.com/prices/A-100"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
```

It pools connections automatically, but it has no per-byte read timeout and no public pool-size API (the system property `jdk.httpclient.connectionPoolSize` defaults to 0, unbounded), and idle connections live for `jdk.httpclient.keepalive.timeout` seconds (30 in current JDKs). Spring's `RestClient` and `RestTemplate` sit on top of one of these clients: configure the client underneath, not the template.

## Example: the symptom of each misconfiguration

| Misconfiguration | What you observe |
|---|---|
| No connect timeout | When a host is unreachable, threads sit in `connect` for about two minutes each; thread exhaustion follows |
| No socket or response timeout | Threads blocked indefinitely in a socket read (`sun.nio.ch.NioSocketImpl.read` in Java 21 thread dumps); the service never recovers without a restart |
| Pool too small | Low CPU, rising latency, `ConnectionRequestTimeoutException`; throughput capped at pool size divided by latency |
| Pool too large | The dependency receives hundreds of concurrent requests, slows down and hits its own limits; you caused its outage |
| No acquisition timeout | Callers queue for a connection indefinitely; thread dumps show waits inside the pool rather than in socket reads |
| Idle connections kept longer than the server's keep-alive, no validation | The first request after a quiet period fails with `NoHttpResponseException` or a reset; the retry succeeds |
| `Connection: close`, or a new client per request | Every call pays the handshakes; `TIME_WAIT` piles up; `EADDRNOTAVAIL` at a few hundred connections per second |
| Server `maxConnections` or accept queue exceeded | Clients see connect timeouts, not refusals, while the server looks idle |
| Server threads exhausted | Connections are accepted, requests queue, clients see read timeouts, and the server's thread dump shows every worker waiting downstream |

## Pitfalls

- Trusting defaults. Apache HttpClient 5: five per route and no read timeout. JDK `HttpClient`: no read timeout at all. Every client needs the table above filled in explicitly.
- One client per request, or `new RestTemplate()` per call. Each creates its own pool, so nothing is ever reused, and `TIME_WAIT` grows until ports run out.
- One pool shared by all dependencies. The slowest one takes every connection and the fast ones starve. Separate clients, or per-route limits, per dependency.
- Timeouts longer than your caller's. The caller gives up and retries while you are still waiting, so one slow request becomes two, then four. Each hop's budget must be shorter than the previous hop's.
- Retrying on timeout without idempotency. A timed-out request may have been processed (item 4.1).
- Load balancer idle timeout shorter than the client's eviction. Connections die in the middle and the first request after a pause fails. Evict idle connections below the shortest timeout on the path.
- Connections that live forever. They pin one backend IP, so DNS failover and new instances behind a round-robin name are never used. Set a time to live.

## Check yourself

1. A service handles 300 requests per second and each call to the pricing API takes 200 ms at the median and 2 s at p99. How many connections does the pool need, and what exactly happens with the default of five per route?
2. A thread dump shows all 200 Tomcat threads inside a socket read in your HTTP client. Which timeout is missing, and why would a connect timeout not have helped?
3. The first request after every quiet minute fails with `NoHttpResponseException` and the retry succeeds. Explain the mechanism and name three settings that prevent it.
4. A batch job opens a new connection per request to one host and after a minute fails with "Cannot assign requested address". What state are the old connections in, which side holds them, and what are the two fixes?

## Go deeper

- [HPBN: Building Blocks of TCP](https://hpbn.co/building-blocks-of-tcp/) · the handshake, slow start and keep-alive: the cost model behind every number above.
- [MDN: Connection management in HTTP/1.x](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Connection_management_in_HTTP_1.x) · persistent connections, pipelining and domain sharding in one page.
- [Apache HttpClient 5: examples](https://hc.apache.org/httpcomponents-client-5.5.x/examples.html) · the pooling connection manager, timeouts and eviction as the project documents them.
- [JDK `java.net.http` module summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/module-summary.html) · the system properties (`jdk.httpclient.keepalive.timeout`, `jdk.httpclient.connectionPoolSize`) and, by omission, what the client does not offer.
- [Vincent Bernat: Coping with the TCP TIME-WAIT state on Linux](https://vincent.bernat.ch/en/blog/2014-tcp-time-wait-state-linux) · the definitive explanation of `TIME_WAIT`, `tcp_tw_reuse`, and why `tcp_tw_recycle` was wrong.
- [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) · how to choose timeouts and retries so they help rather than amplify failure.
- [Cloudflare: When TCP sockets refuse to die](https://blog.cloudflare.com/when-tcp-sockets-refuse-to-die/) · what happens to a connection whose peer vanished, and the kernel knobs that bound it.

---

Part of [Web & HTTP](../README.md) · items 3.1, 3.4
