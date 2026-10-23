# What happens when you type a URL

> **In one sentence:** Loading a page is a chain of round trips (DNS, TCP, TLS, request, response, then the same again for every other origin the page uses), and you can measure where each millisecond goes with one `curl` command.

**Why it matters:** This is the backbone every other topic in this domain hangs from, and the question interviewers use to find out whether you understand the network your code runs on. In production it is the difference between "the API is slow" and "we pay a 100 ms DNS lookup and two handshakes on every call because the client does not reuse connections".

## The idea

Nothing on the web happens in less than one round trip (RTT), the time for a packet to reach the server and an answer to come back. Within one region that is a few milliseconds; across an ocean it is 70 to 150 ms, bounded by the speed of light in fibre. Bandwidth has grown enormously; latency has not. So the walkthrough below is best read as a count of round trips.

1. **Parse the URL.** The browser splits `https://example.com/path?q=1` into scheme, host, port (443 implied), path and query. If the host is on the HSTS list, an `http://` URL is upgraded to `https://` before anything is sent (see item 7.3).
2. **Resolve the name.** Browser cache, then the operating system's resolver cache, then a recursive resolver (your ISP, `1.1.1.1`, `8.8.8.8`). If the resolver has the record cached: one round trip to the resolver. If not: the resolver walks root, TLD and authoritative servers on your behalf, which can take 50 to 150 ms. Picked up by item 2.1.
3. **Open a TCP connection.** SYN, SYN-ACK, ACK: one round trip before any byte of payload. Picked up by item 3.1.
4. **Negotiate TLS.** TLS 1.3 needs one more round trip (TLS 1.2 needed two). The client also spends CPU time verifying the certificate chain. ALPN inside the handshake decides whether the connection speaks HTTP/1.1 or HTTP/2. Picked up by items 3.2 and 3.3.
5. **Send the request, wait for the first byte.** The request goes out; the time until the first response byte arrives is one round trip plus whatever the server took. That server part is the only stage your application code controls. Picked up by items 4.1 and 4.2.
6. **Download the body.** Small responses arrive in the same round trip. Large ones are paced by TCP slow start: a new connection can send roughly 14 KB (ten segments) before it must wait for acknowledgements, then doubles each round trip. A 300 KB page costs several round trips on a fresh connection even on fast fibre.
7. **Render.** The browser parses HTML, discovers stylesheets, scripts, fonts and images, and fetches them. Resources on the same origin reuse the connection (HTTP/1.1 opens up to six, HTTP/2 multiplexes one); every new origin repeats steps 2 to 4. Stylesheets and synchronous scripts block rendering until they arrive. Picked up by items 5.1 to 5.3 (what the cache can skip) and 8.1 to 8.3 (what the protocol version changes).

The `Set-Cookie` headers in the response (item 6.1), the `Access-Control-*` headers on cross-origin fetches (item 7.2) and the reverse proxy or load balancer that answered instead of your application (items 11.2 and 11.3) all live inside steps 5 and 7.

## Example: measuring every stage with curl

```bash
curl -sv -o /dev/null https://example.com/ --write-out '
   namelookup: %{time_namelookup}
      connect: %{time_connect}
   appconnect: %{time_appconnect}
starttransfer: %{time_starttransfer}
        total: %{time_total}
 http_version: %{http_version}
'
```

Observed from a laptop (lines trimmed to the ones that matter):

```text
* Host example.com:443 was resolved.
* IPv4: 172.66.147.243, 104.20.23.154
* Connected to example.com (2606:4700:10::ac42:93f3) port 443
* ALPN: curl offers h2,http/1.1
* (304) (OUT), TLS handshake, Client hello (1):
* (304) (IN), TLS handshake, Server hello (2):
* (304) (IN), TLS handshake, Certificate (11):
* (304) (IN), TLS handshake, Finished (20):
* (304) (OUT), TLS handshake, Finished (20):
* SSL connection using TLSv1.3 / AEAD-CHACHA20-POLY1305-SHA256
* ALPN: server accepted h2
*  SSL certificate verify ok.
* using HTTP/2
> GET / HTTP/2
> Host: example.com
< HTTP/2 200
< content-type: text/html; charset=utf-8
< age: 2732
< cf-cache-status: HIT
< alt-svc: h3=":443"; ma=86400

   namelookup: 0.002413
      connect: 0.051195
   appconnect: 0.110012
starttransfer: 0.155030
        total: 0.155252
 http_version: 2
```

The `--write-out` variables are cumulative from the start of the command, so each stage is a subtraction:

| Stage | Calculation | Observed | What it tells you |
|---|---|---|---|
| DNS | `namelookup` | 2 ms | The resolver had it cached. A first run minutes earlier showed 92 ms. |
| TCP handshake | `connect - namelookup` | 49 ms | One round trip to the nearest edge server. This is your RTT. |
| TLS handshake | `appconnect - connect` | 59 ms | One more round trip plus certificate verification. TLS 1.3, as the `-v` lines show. |
| Time to first byte | `starttransfer - appconnect` | 45 ms | One round trip plus server time. `cf-cache-status: HIT` and `age: 2732` say a CDN answered from cache, so server time was close to zero. |
| Download | `total - starttransfer` | under 1 ms | 577 bytes fit in the first flight. |

Read it as a budget: of 155 ms, 153 ms were spent before the application saw the request, and the RTT (about 49 ms) was paid three times. Reuse the connection and the next request costs one RTT instead of three. That is why connection pools, keep-alive and HTTP/2 are the cheapest optimisations you will ever make, and why `alt-svc: h3` is the server offering to merge the TCP and TLS round trips into one next time (see item 8.2).

## Pitfalls

- Measuring once, with a warm DNS cache, and concluding DNS is free. Run from a fresh resolver or a different network; the first lookup is often the slowest stage.
- Blaming the application for time to first byte. Subtract `appconnect` first; a 300 ms TTFB with a 120 ms RTT leaves 180 ms for the server, not 300.
- Forgetting that every extra origin repeats steps 2 to 4. A page that pulls scripts from five domains pays five DNS lookups and five handshakes, in parallel but still before anything renders.
- Redirect chains. `http://example.com` to `https://example.com` to `https://www.example.com` is three connections before the real request. Each hop is a full DNS, TCP and TLS cycle unless the host repeats.
- Testing from your laptop and deploying in a data centre, or the reverse. The RTT to a database or a downstream API from inside the data centre is often under 1 ms; from your desk it is 30 ms. Numbers only mean something next to the RTT they were measured with.
- Comparing against a backend directly when a CDN or proxy is in front. `cf-cache-status`, `age` and `via` headers tell you who really answered. Use `curl --resolve example.com:443:10.0.0.5` to point the same hostname at a specific backend and compare.

## Check yourself

1. A request takes 400 ms with `connect` at 100 ms and `appconnect` at 300 ms. How long was the TLS handshake, and what TLS version does that suggest?
2. Your service calls a downstream API 50 times per request through a client that opens a new connection each time. Using the numbers above, roughly how much time would connection reuse save?
3. Why can a 2 MB response take ten round trips to download on a fresh connection even when bandwidth is not the limit?
4. The browser reports a slow page, but `curl` from your laptop shows 150 ms. Name three stages of the walkthrough that `curl -o /dev/null` does not measure at all.

## Go deeper

- [What happens when...](https://github.com/alex/what-happens-when) · the full walkthrough, from the keyboard interrupt to the painted pixels.
- [HPBN: Primer on Latency and Bandwidth](https://hpbn.co/primer-on-latency-and-bandwidth/) · why latency, not bandwidth, dominates, with the speed-of-light arithmetic.
- [HPBN: Building Blocks of TCP](https://hpbn.co/building-blocks-of-tcp/) · the handshake and slow start behind stages 3 and 6.
- [curl: --write-out variables](https://everything.curl.dev/usingcurl/verbose/writeout.html) · the complete list of timing variables used above.
- [Chrome DevTools: Network panel](https://developer.chrome.com/docs/devtools/network) · the same breakdown per resource, in the browser, including the queueing and rendering time that curl cannot see.

---

Part of [Web & HTTP](../README.md) · item 1.1
