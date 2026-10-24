# curl for HTTP debugging

> **In one sentence:** curl sends exactly the request you mean and shows exactly what came back, byte for byte and millisecond by millisecond, which makes it the fastest way to separate "the server is wrong" from "my client is wrong" from "the network is wrong".

**Why it matters:** Half of HTTP debugging is reproducing the problem outside the application, without the framework's defaults, the browser's cookies or the proxy's rewrites. A dozen curl options cover ninety percent of that work, a `--write-out` format file turns "it feels slow" into a per-stage latency budget, and knowing when curl is the wrong tool (DevTools for browser behaviour, tcpdump for anything below HTTP) saves the other half.

## The idea

**The dozen options that matter.**

| Option | What it does | Use it when |
|---|---|---|
| `-v` | prints request headers (`>`), response headers (`<`) and connection events (`*`) on stderr | always, first |
| `-i` | includes the response headers in the output, before the body | you want headers and body together |
| `-I` | sends `HEAD` and prints the headers | checking status, caching or redirects without the body; servers may treat `HEAD` differently from `GET` |
| `-X METHOD` | overrides the method | only when no other option implies it; `-d` already means `POST` |
| `-H 'Name: value'` | adds or replaces a header; `-H 'Accept:'` removes one | negotiation, auth, conditional requests |
| `-d 'a=1'`, `--data-urlencode`, `--data-binary @file` | sends a body, sets `POST` and `Content-Type: application/x-www-form-urlencoded` | forms; `--data-urlencode 'q=two words'` encodes for you; `-G` moves the data into the query |
| `--json '{...}'` | `-d` plus `Content-Type: application/json` and `Accept: application/json` (curl 7.82 and later) | JSON APIs |
| `-L` | follows redirects (`--max-redirs` caps them); 301, 302 and 303 switch `POST` to `GET` as browsers do, unless `-X` forced the method | following `Location` |
| `--resolve host:port:addr` | pins a hostname to an address without touching DNS or `/etc/hosts`, so SNI and `Host` stay correct | testing one backend behind a load balancer, a server before DNS cutover, or origin versus CDN |
| `-k`, `--insecure` | skips certificate verification | almost never; see below |
| `-w '...'`, `--write-out` | prints variables after the transfer | timings, `http_code`, `remote_ip`, `size_download`, or everything with `%{json}` |
| `-sS -o /dev/null` | silent, errors still shown, body discarded | measuring; the terminal must not be part of the timing |
| `--http1.1`, `--http2`, `--http2-prior-knowledge` | forces a protocol version | reproducing version-specific behaviour (item 8.1) |

Four more worth knowing: `-m 10` and `--connect-timeout 3` (never debug with infinite timeouts), `--fail-with-body` (non-zero exit on 4xx and 5xx while keeping the body, for scripts), `--retry 3` (retries connection failures and 408, 429, 500, 502, 503, 504) and `--trace-ascii -` (every byte in both directions, bodies included, when `-v` is not enough).

**Why not `-k`.** It makes curl accept any certificate, so the request succeeds while hiding the exact problem your clients will hit: wrong hostname, expired leaf, missing intermediate (item 3.3). Observed against `wrong.host.badssl.com`: without `-k`, exit code 60 and `SSL: no alternative certificate subject name matches target host name`; with `-k`, a 200 and no information. For a private CA use `--cacert ca.pem`; use `-k` only to read the headers of a server you already know is misconfigured, and then fix the server.

**Reading a verbose trace.** Each prefix is a layer. Trimmed real output:

```text
* Host www.rfc-editor.org:443 was resolved.
* IPv6: 2606:4700::6812:1451, 2606:4700::6812:1551
* IPv4: 104.18.21.81, 104.18.20.81
*   Trying [2606:4700::6812:1451]:443...
* Connected to www.rfc-editor.org (2606:4700::6812:1451) port 443
* ALPN: curl offers h2,http/1.1
* (304) (OUT), TLS handshake, Client hello (1):
* (304) (IN), TLS handshake, Server hello (2):
* (304) (IN), TLS handshake, Certificate (11):
* (304) (IN), TLS handshake, Finished (20):
* (304) (OUT), TLS handshake, Finished (20):
* SSL connection using TLSv1.3 / AEAD-CHACHA20-POLY1305-SHA256
* ALPN: server accepted h2
* Server certificate:
*  subject: CN=rfc-editor.org
*  expire date: Jan  8 12:18:06 2027 GMT
*  subjectAltName: host "www.rfc-editor.org" matched cert's "*.rfc-editor.org"
*  issuer: C=US; O=Google Trust Services; CN=WE1
*  SSL certificate verify ok.
* using HTTP/2
> GET /rfc/rfc9110.html HTTP/2
> Host: www.rfc-editor.org
> User-Agent: curl/8.7.1
> Accept: */*
>
< HTTP/2 200
< content-type: text/html
< etag: W/"0d9f5fb8eb38d3c08b055f9b0671d68b"
< alt-svc: h3=":443"; ma=86400
<
{ [1360 bytes data]
* Connection #0 to host www.rfc-editor.org left intact
```

The `*` lines answer the questions that come before HTTP: which addresses DNS returned and which one curl tried (IPv6 first), which protocols ALPN offered and which the server chose, which TLS version and cipher were negotiated, and the three certificate checks that fail in item 3.3 (name, dates, chain). The `>` lines are the request *as sent*, as useful for what is missing as for what is there: no `Accept-Encoding`, so no compression; no cookie, so no session. The `<` lines are lowercase because this is HTTP/2. `{ [1360 bytes data] }` is the body going to `-o`, and "left intact" means the connection stayed open for reuse.

**When to reach for something else.**

- HTTPie (`http`, `https`) for exploring JSON APIs by hand: `https PUT api.example.com/customers/42 If-Match:'"c42-v7"' creditLimit:=8000` is readable, and responses come formatted and coloured. It adds default headers of its own, though, so what you see is not what curl or your application sends; scripts and exact reproductions stay in curl.
- Browser DevTools when the problem is browser behaviour: cookies, CORS preflights (item 7.2), the cache (`from disk cache`, 304s), service workers, HTTP/3, and the per-resource waterfall with the queueing and rendering time that curl cannot see. "Copy as cURL" on any request brings it, headers and all, into the terminal.
- tcpdump or Wireshark when the problem is below HTTP: who sent the reset, retransmissions, SYNs without a SYN-ACK (full accept queue, firewall), connections closed mid-body, TLS alerts. `sudo tcpdump -i any -nn -w capture.pcap 'host 10.0.1.10 and tcp port 8080'`, then open the file in Wireshark. Encrypted payloads stay opaque unless the client wrote its keys to the file named by `SSLKEYLOGFILE`, which browsers and OpenSSL-based curl builds do.

## Example: a reusable `curl-format.txt` and an annotated run

Save this as `curl-format.txt`. The `\n` at the end of each line is required: curl strips literal newlines from a format file read with `@`.

```text
       status: %{http_code}  http/%{http_version}  redirects: %{num_redirects}\n
       remote: %{remote_ip}:%{remote_port}\n
     download: %{size_download} bytes\n
   namelookup: %{time_namelookup}\n
      connect: %{time_connect}\n
   appconnect: %{time_appconnect}\n
  pretransfer: %{time_pretransfer}\n
     redirect: %{time_redirect}\n
starttransfer: %{time_starttransfer}\n
        total: %{time_total}\n
```

```bash
curl -sS -o /dev/null -w @curl-format.txt https://www.rfc-editor.org/rfc/rfc9110.html
```

```text
       status: 200  http/2  redirects: 0
       remote: 2606:4700::6812:1451:443
     download: 1187554 bytes
   namelookup: 0.002766
      connect: 0.030403
   appconnect: 0.067111
  pretransfer: 0.067185
     redirect: 0.000000
starttransfer: 0.538848
        total: 0.692363
```

The variables are timestamps measured from the start of the command, so each stage is a subtraction:

| Stage | Formula | Here | Reading |
|---|---|---|---|
| DNS | `namelookup` | 2.8 ms | the resolver cache was warm; a cold lookup is often the slowest stage |
| TCP handshake | `connect - namelookup` | 27.6 ms | one round trip: this is the RTT to the edge |
| TLS handshake | `appconnect - connect` | 36.7 ms | one more round trip plus certificate verification (TLS 1.3, per the trace) |
| Time to first byte | `starttransfer - pretransfer` | 471.7 ms | one RTT plus server time: about 440 ms spent producing the response |
| Download | `total - starttransfer` | 153.5 ms | 1.2 MB over a connection still in slow start |

Only one of the five stages belongs to the server, and the fix for each is different (item 1.1 walks the stages; item 8.3 is the budget). Re-running with `--compressed` moves 1,187,554 bytes to 212,574 and the download stage to about 60 ms while the time to first byte stays at half a second, which says compression is worth doing and will not fix the slow server.

Two cautions. With `-L`, curl adds each hop's stage times together, so the numbers stop being a timeline (a run from `http://` showed `connect` larger than `appconnect`); use `time_redirect` for the cost of the hops and measure the final URL directly. And never conclude from one run:

```bash
for attempt in 1 2 3 4 5; do curl -sS -o /dev/null -w '%{time_total}\n' https://www.rfc-editor.org/; done | sort -n | sed -n '3p'
```

prints the median of five.

## Pitfalls

- `-X POST` with `-d`, or `-X GET` with `-d`. The first is redundant and makes `-L` re-`POST` to redirect targets where a browser would `GET`; the second sends a `GET` with a body and a form content type, which servers handle inconsistently. Let `-d` choose the method.
- `-I` to debug an endpoint whose `GET` is the problem. `HEAD` may take a different code path or be blocked. Use `-sS -o /dev/null -D -` to see a `GET`'s headers without its body.
- Shell quoting. `$` and `!` inside double quotes, apostrophes inside single-quoted JSON: put the body in a file and use `--json @body.json`.
- Comparing curl with the browser without the browser's headers (cookies, `Accept-Encoding`, `Origin`, `Accept-Language`). Use "Copy as cURL" and remove headers until the behaviour changes.
- Exit status. curl returns 0 for a 500 unless you pass `--fail` or `--fail-with-body`, and `%{http_code}` is `000` when no response arrived at all (observed on a 2-second timeout: `code=000 exit=28`). Check `%{exitcode}` and `%{errormsg}` in scripts.
- `-k` left in a script "temporarily". It stays, and the day the certificate breaks nobody notices.
- Timing with the body on the terminal, with `-L`, or once. `-o /dev/null`, the final URL, the median.

## Check yourself

1. A colleague's `curl -X POST -d @order.json -L https://shop.example/orders` behaves differently from the browser after a 302. Why, and what should the command be?
2. Your format file prints `starttransfer: 0.538` and `appconnect: 0.067`. Roughly how long did the server take, and what else is inside that number?
3. The service works from your laptop but fails behind the new load balancer. Which curl option lets you test each backend by hostname with correct TLS, and why is editing `/etc/hosts` worse?
4. A client reports "connection reset" a few times an hour and curl reproduces it once a day. Which tool do you reach for, what do you filter on, and what are you hoping to see?

## Go deeper

- [Everything curl](https://everything.curl.dev/) · the book; the chapters on verbose output and `--write-out` cover everything above in more depth.
- [curl: --write-out variables](https://everything.curl.dev/usingcurl/verbose/writeout.html) · the full list, including `%{json}` and `%header{name}`.
- [curl manpage](https://curl.se/docs/manpage.html) · every option, with the version it appeared in.
- [Daniel Stenberg: Unnecessary use of curl -X](https://daniel.haxx.se/blog/2015/09/11/unnecessary-use-of-curl-x/) · the author on the most common curl mistake.
- [Chrome DevTools: Network panel](https://developer.chrome.com/docs/devtools/network) · the timing waterfall and "Copy as cURL".
- [HTTPie CLI documentation](https://httpie.io/docs/cli) · the friendlier client, and what it changes about your requests.
- [tcpdump manual page](https://www.tcpdump.org/manpages/tcpdump.1.html) · the filter syntax, for the day HTTP is not the broken layer.

---

Part of [Web & HTTP](../README.md) · items 4.6, 8.3
