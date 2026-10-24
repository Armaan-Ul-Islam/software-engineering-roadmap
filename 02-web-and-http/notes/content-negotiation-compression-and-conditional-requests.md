# Content negotiation, compression and conditional requests

> **In one sentence:** A resource has many possible representations (format, charset, encoding, version), and HTTP has one header family to choose one (`Accept*`, answered by `Content-Type`, `Content-Encoding` and `Vary`), one to frame it on the wire (`Content-Length` or chunked transfer), and one to send it only when necessary (`ETag` with `If-None-Match` for caches and `If-Match` for writes that must not overwrite someone else's).

**Why it matters:** These headers decide whether a 1.2 MB response is 200 KB on the wire, whether a shared cache hands a gzip body to a client that cannot read it, whether two users editing the same record silently overwrite each other, and whether an API client that asked for JSON gets an HTML error page it cannot parse. Each is a one-header mistake, and `If-Match` is the cheapest optimistic concurrency control you will ever get.

## The idea

**Negotiation.** The client states what it accepts; the server chooses, and labels what it sent.

| Request header | Response header | Negotiates |
|---|---|---|
| `Accept: application/json, text/html;q=0.9, */*;q=0.1` | `Content-Type: application/json` | media type; `q` ranks preferences from 0 to 1 |
| `Accept-Encoding: gzip, br, zstd` | `Content-Encoding: br` | compression of the representation |
| `Accept-Language: nb, en;q=0.8` | `Content-Language: nb` | language |
| `Accept-Charset` (obsolete; browsers stopped sending it) | the `charset=` parameter of `Content-Type` | character encoding |

When nothing acceptable exists the server may answer `406 Not Acceptable` or ignore `Accept` and send its default; RFC 9110 allows both. A request body in a type the server cannot parse gets `415 Unsupported Media Type`.

**`Content-Type` and charsets.** Text types need an explicit charset (`text/html; charset=utf-8`): without one the receiver guesses, and browsers guess a legacy encoding. `application/json` takes no charset parameter; RFC 8259 mandates UTF-8 and says the parameter has no meaning (sending it is harmless). Structured-syntax suffixes let generic code handle vendor types: `application/problem+json` (item 9.3) is JSON to any parser that reads the suffix. `X-Content-Type-Options: nosniff` (item 7.3) tells browsers to believe the header rather than sniff the bytes.

**`Vary`.** A response that depends on a request header must name that header in `Vary`, or a shared cache will serve it to the next client with a different header: the gzip body to a client that sent no `Accept-Encoding`, the Norwegian page to an English speaker. `Vary: Accept-Encoding` belongs on every compressible response and `Vary: Accept` on anything that negotiates format. The cache-key mechanics are item 5.2.

**Framing: `Content-Length` versus chunked.** The receiver must know where the body ends. Either the sender knows the size up front and sends `Content-Length: 62` (exactly right, or the connection hangs waiting for bytes that never come, or the next response on the connection is read as part of this body), or it does not and sends `Transfer-Encoding: chunked`: a hex length line, that many bytes, repeat, then a `0` chunk and optional trailers. Chunked is how streaming (item 10.2) and compression on the fly work, and it exists only in HTTP/1.1; HTTP/2 and HTTP/3 frame data themselves and forbid `Transfer-Encoding`. Servlet containers choose for you: a response that fits the output buffer gets a `Content-Length`, a larger one is chunked. Proxies may convert one into the other, which is why a filter that rewrites a body must fix the length. `Range: bytes=0-1023` with `206 Partial Content` and `Content-Range` applies the same framing idea to part of a representation; `Location` on 201 and 3xx is item 4.2.

**Compression.** `Content-Encoding` compresses the representation end to end: the client decompresses, intermediaries pass it through, and the compressed form is a *different representation* with a different strong `ETag`. gzip works everywhere; Brotli (`br`) compresses text noticeably better and is what CDNs serve for static assets, with its slow highest levels reserved for pre-compressing at build time; zstd is faster at the same ratio and reached Chrome and Firefox in 2024 (check Safari before relying on it). Three cases call for no compression:

1. Already compressed data (images, video, PDF, zip): the ratio is near zero and the CPU is wasted.
2. Small bodies: under about 1 KB the gzip framing can exceed the saving. Spring Boot's `server.compression.min-response-size` defaults to 2 KB.
3. Responses that mix a secret with attacker-influenced input over TLS: the BREACH attack recovers the secret from the compressed size, one byte at a time. Pages that embed a CSRF token next to reflected user input are the textbook case; do not compress them, or mask the token per request.

Compress at the reverse proxy or CDN in most deployments, or in the application with `server.compression.enabled=true` and `server.compression.mime-types` when nothing sits in front of Tomcat (which compresses with gzip only). Request bodies can be compressed too, but only when the server has agreed out of band; otherwise expect 415.

**Conditional requests.** A validator identifies one version of a representation: `ETag` (`"c42-v7"` is strong, `W/"c42-v7"` is weak, meaning semantically equivalent) or `Last-Modified` (one-second granularity). Two uses:

1. Caching (item 5.1): `GET` with `If-None-Match: "c42-v7"`; the server answers `304 Not Modified` with no body if the validator still matches. Weak comparison is allowed here, so a weak ETag is fine.
2. Optimistic concurrency: `PUT`, `PATCH` or `DELETE` with `If-Match: "c42-v7"`; the server applies the change only if the current ETag matches under strong comparison, and otherwise answers `412 Precondition Failed`. `If-None-Match: *` on a `PUT` means "create only if nothing is there yet", which stops two clients from both creating. `If-Unmodified-Since` is the date-based fallback, and `428 Precondition Required` tells a client that omitted the header that this resource insists on it.

The check and the write must be atomic on the server: `UPDATE customer SET ..., version = version + 1 WHERE id = ? AND version = ?`, and 412 when zero rows changed. Comparing in application code and writing in a second statement lets two requests both pass the check, which is exactly the lost update you were preventing.

## Example: a conditional PUT that loses the race

Two clients read the same customer; both get `ETag: "c42-v7"`.

```http
GET /customers/42 HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Encoding: gzip, br

```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 62
ETag: "c42-v7"
Cache-Control: private, no-cache
Vary: Accept-Encoding

{"id":42,"name":"Smith & Sons","creditLimit":5000,"version":7}
```

The body is below the server's compression threshold, hence no `Content-Encoding`; `Vary` is sent anyway because larger responses from this endpoint would be compressed. Client A raises the credit limit:

```http
PUT /customers/42 HTTP/1.1
Host: api.example.com
Content-Type: application/json
If-Match: "c42-v7"
Content-Length: 50

{"id":42,"name":"Smith & Sons","creditLimit":8000}
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 62
ETag: "c42-v8"

{"id":42,"name":"Smith & Sons","creditLimit":8000,"version":8}
```

Client B, a second later, renames the company from a form it loaded before A's change:

```http
PUT /customers/42 HTTP/1.1
Host: api.example.com
Content-Type: application/json
If-Match: "c42-v7"
Content-Length: 53

{"id":42,"name":"Smith & Sons AS","creditLimit":5000}
```

```http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json
Content-Length: 136

{"type":"about:blank","title":"Precondition Failed","status":412,"detail":"Customer 42 was modified by someone else. Reload and retry."}
```

Without `If-Match`, B's `PUT` would have succeeded and silently reset the credit limit to 5000. With it, B's client does a fresh `GET`, receives `"c42-v8"` and the new limit, merges or asks the user, and retries with `If-Match: "c42-v8"`. On the server this is one SQL statement with `WHERE version = 7`: the same mechanism as a version column under JPA, exposed over HTTP.

## Example: compression, measured

Against the HTML of RFC 9110 with the macOS system curl, whose `--compressed` offers `deflate, gzip`:

```bash
curl -sS -o /dev/null -w 'identity:   %{size_download} bytes, total %{time_total}s\n' https://www.rfc-editor.org/rfc/rfc9110.html
curl -sS --compressed -o /dev/null -w 'compressed: %{size_download} bytes, total %{time_total}s\n' https://www.rfc-editor.org/rfc/rfc9110.html
```

```text
identity:   1187554 bytes, total 0.748490s
compressed:  212574 bytes, total 0.559897s
```

The gzip copy is 82 % smaller. The time to first byte (about 0.5 s in both runs) did not change, because compression saves bytes, not server time; the download phase fell from about 0.2 s to 0.06 s. `-I --compressed` on the same URL shows `content-encoding: gzip`, `-H 'Accept-Encoding: br'` gets `content-encoding: br`, and offering only `zstd` gets an uncompressed response: the server does not support it and fell back to identity, which is what negotiation is for.

## Pitfalls

- An HTML error page for a JSON client. Proxies and containers produce HTML by default, and the client's JSON parser fails three layers away from the real error. Error handlers must honour `Accept`, and the proxy's error pages need a `Content-Type` the client can at least detect.
- A wrong or missing charset on a text type: bytes written as UTF-8 and read as ISO-8859-1 show `Ã¸` for `ø`. Declare `charset=utf-8` in the header, not only in an HTML `<meta>`.
- Missing `Vary: Accept-Encoding`. A shared cache stores the gzip copy and serves it to a client that cannot decode it, which sees binary garbage.
- Compressing images, compressing twice (application and proxy), or never checking. Look at `Content-Encoding` and `size_download` with curl, as above.
- Rewriting a body in a filter and leaving `Content-Length` alone: truncated responses, or clients that hang waiting for the rest.
- Weak ETags on write paths. `If-Match` uses strong comparison, so a `W/` validator fails every conditional write, and nginx turns a strong ETag into a weak one when it compresses on the fly. Derive the ETag from a version number, and keep the proxy from weakening it on the write path.
- The check-then-write race: the precondition belongs in the `UPDATE`'s `WHERE` clause (or under a lock), not in Java.
- Relying on `If-Modified-Since` for correctness. Two writes within one second look like none. Use ETags, and keep dates as a fallback for caches.

## Check yourself

1. A client sends `Accept: application/xml` to an endpoint that only produces JSON. Name the two legitimate responses and the one that is wrong.
2. Why does compressing a response change its strong ETag, and what does that do to `If-Match` when a proxy compresses on the fly?
3. Two users submit a form for the same record within a second. Write the header the second submission must carry, the status it gets, and the SQL that makes the server's check atomic.
4. Give three different reasons not to compress a particular response, one each about size, format and security.

## Go deeper

- [MDN: Content negotiation](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Content_negotiation) · the `Accept*` family and how servers choose, including the `q` rules.
- [MDN: HTTP headers](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers) · one page per header; `Content-Length`, `Transfer-Encoding`, `Range` and `Vary` are the ones to read next.
- [MDN: Compression in HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Compression) · end-to-end versus hop-by-hop compression, and the algorithms.
- [MDN: Conditional requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests) · both uses of validators, with sequence diagrams including the lost-update scenario above.
- [RFC 9110: Conditional Requests](https://www.rfc-editor.org/rfc/rfc9110.html#name-conditional-requests) · strong versus weak comparison, and the order in which several preconditions are evaluated.
- [RFC 8259: The JSON Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259.html) · section 11 is the sentence about `charset`.
- [BREACH](https://www.breachattack.com/) · why compressing a secret next to attacker-controlled input leaks it.
- [Spring Boot: Embedded web servers how-to](https://docs.spring.io/spring-boot/how-to/webserver.html) · the section on enabling response compression and its three properties.

---

Part of [Web & HTTP](../README.md) · items 4.3, 4.4, 4.5
