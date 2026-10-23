# HTTP methods, status codes and idempotency

> **In one sentence:** A method's safety and idempotency tell every intermediary and client whether a request may be cached, prefetched or retried without asking you, and a status code tells them what to do next; get either wrong and caches, retries and monitoring all misbehave at once.

**Why it matters:** Retries are the default behaviour of load balancers, HTTP client libraries and browsers, and they decide whether to retry by looking at the method. A `POST` that creates an order is never retried for you; a `PUT` that is not really idempotent is retried into a double write. Status codes are the contract with generated clients, caches and alerting; "200 with an error body" quietly breaks all three.

## The idea

**Anatomy.** A request is a start line (`GET /orders/42 HTTP/1.1`), header fields, a blank line, and an optional body. A response is a status line (`HTTP/1.1 200 OK`), headers, blank line, body. HTTP/2 and HTTP/3 carry the same semantics in binary frames (`:method`, `:path`, `:status` pseudo-headers) and lowercase all header names, but nothing in this note changes with the version.

**Safe, idempotent, neither.** RFC 9110 defines the two properties by *intended effect on the server*, not by what the response looks like:

- **Safe**: no state change is requested. `GET`, `HEAD`, `OPTIONS`, `TRACE`. Caches may store the response, browsers may prefetch, crawlers may follow. A `GET /orders/42/cancel` that cancels is a bug waiting for a link prefetcher.
- **Idempotent**: sending the request N times has the same effect as once. All safe methods plus `PUT` and `DELETE`. The *response* may differ (the second `DELETE` returns 404); the *state* does not.
- **Neither**: `POST`, and `PATCH` unless the patch document happens to be idempotent (`"status": "paid"` is; `"increment": 1` is not).

**Why retries depend on it.** When a connection drops after the request was sent, the client cannot know whether the server processed it. For an idempotent request the answer does not matter: send it again. Reverse proxies and client libraries encode exactly this rule (nginx's `proxy_next_upstream` refuses to retry `POST` by default; most HTTP clients retry only idempotent methods automatically). To make a `POST` safely retryable you add idempotency yourself: an `Idempotency-Key` header whose value the server stores with the first result and replays on repeats. Payment APIs have done this for years and there is an IETF draft standardising it.

**Status codes that matter**, including the usual confusions:

| Code | Means | Commonly confused with |
|---|---|---|
| 200 | Done, here is the representation | 201 for a creation (send `Location`); 204 when there is no body to return |
| 202 | Accepted, will be processed later; give a status URL | 200 claiming completion that has not happened |
| 301 / 308 | Moved permanently; 308 keeps the method and body | 301 lets browsers turn `POST` into `GET` |
| 302 / 307 | Moved temporarily; 307 keeps the method | 302 also lets `POST` become `GET`; 303 means "do a `GET` over there" (the post-redirect-get pattern) |
| 304 | Not modified; your cached copy is still good | Nothing, but it must carry no body |
| 400 | The request is malformed (bad JSON, missing required field) | 422: syntactically fine, semantically invalid ("end date before start date") |
| 401 | Not authenticated: who are you? Must send `WWW-Authenticate` | 403: authenticated, but not allowed |
| 403 | Forbidden; retrying with the same credentials will not help | 404 when you prefer not to reveal the resource exists (acceptable, but be consistent) |
| 404 | Not here, maybe never was | 410: gone on purpose, clients and crawlers may drop it |
| 405 | Method not allowed; must send `Allow` | 404 on a known path with the wrong method |
| 409 | Conflict with current state: duplicate, stale version, invalid state transition | 400 or 500 for "already exists" |
| 412 | A precondition (`If-Match`) failed; the resource changed under you | 409; both are defensible, 412 when the client used conditional headers |
| 415 | Unsupported media type in the request | 400 for "we only speak JSON" |
| 429 | Too many requests; send `Retry-After` | 503 for rate limiting (503 says the server is unhealthy) |
| 500 | Unhandled failure in the application | Anything you could classify as 4xx |
| 502 / 504 | The proxy could not reach the upstream / the upstream timed out | 500 on the upstream itself; 502 and 504 say the proxy never got a valid answer |
| 503 | Overloaded or in maintenance; temporary; send `Retry-After` | 500; clients treat 503 as retryable and 500 as a bug |

**Why "200 with an error body" breaks clients.** Caches store it (it is a successful `GET`). Retry logic does not fire (it keys on 5xx and 429). Dashboards show 100 % success during an outage. Generated clients deserialise the error into the success type and throw a confusing parsing exception three layers away. The status line exists so that software that does not understand your JSON can still make the right decision.

## Example: raw request and response

Over a TLS connection to `example.com` (`printf ... | openssl s_client -quiet -connect example.com:443 -servername example.com`):

```http
GET / HTTP/1.1
Host: example.com
User-Agent: curl/8.7.1
Accept: */*
Connection: close

```

```http
HTTP/1.1 200 OK
Date: Fri, 23 Oct 2026 18:30:58 GMT
Content-Type: text/html; charset=utf-8
Transfer-Encoding: chunked
Connection: close
Age: 2743
cf-cache-status: HIT

241
<!doctype html><html lang=en><head><meta charset=utf-8>...</html>

0

```

`Transfer-Encoding: chunked` means no `Content-Length`: the body arrives as hex-length-prefixed chunks (`241` bytes here) ending with a zero-length chunk. `Age: 2743` and `cf-cache-status: HIT` say a shared cache answered, which is only legal because `GET` is safe.

Three responses you should be producing and are probably not:

```http
HTTP/1.1 201 Created
Location: /orders/9f3b2c
Content-Type: application/json

{"id":"9f3b2c","status":"pending"}
```

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 30
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429,"detail":"Limit of 100 requests per minute exceeded."}
```

```http
HTTP/1.1 503 Service Unavailable
Retry-After: 120
Content-Length: 0

```

`Retry-After` is the difference between a client that backs off politely and one that hammers you harder the moment you are in trouble. The `application/problem+json` body shape is item 9.3.

## Pitfalls

- Treating `PUT` as "update" and `POST` as "create". `PUT` means "store this representation at this URL" and must be idempotent; a `PUT` that appends to a list or increments a counter will be retried into corruption.
- Side effects on `GET`. Link prefetchers, crawlers and browser back/forward caches will trigger them. Anything that changes state is a `POST`, `PUT`, `PATCH` or `DELETE`.
- Redirecting a `POST` with 302 and expecting the method to survive. Use 307 or 308; use 303 when you want the client to `GET` a result page.
- Using 401 for "logged in but not allowed". Clients respond to 401 by re-authenticating, so your users get a login loop. That is 403.
- 500 for validation errors. It pages the on-call engineer for the user's typo and hides real failures in the noise.
- Returning 404 for a soft-deleted or expired resource when you want clients to stop asking. 410 lets caches and crawlers drop it.
- Omitting `Allow` on 405, `WWW-Authenticate` on 401 and `Location` on 201. The codes are defined with those headers; generated clients and browsers rely on them.
- Retrying `POST` at the proxy "for resilience". Without an idempotency key this is how duplicate orders happen.

## Check yourself

1. A client sends `DELETE /orders/42`, the connection resets, and the retry returns 404. Was the operation idempotent? Was it successful?
2. Your API returns `{"ok": false, "error": "..."}` with status 200. List four separate pieces of infrastructure that make a wrong decision because of it.
3. A user who is logged in requests another tenant's invoice. Which status code, and what is the argument for returning a different one?
4. You must let clients retry order creation safely. Describe the request header, what the server stores, and what it returns on the second attempt.

## Go deeper

- [RFC 9110: HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) · sections 9.2 (safe and idempotent methods) and 15 (status codes) are the definitions everything above is built on.
- [MDN: HTTP request methods](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods) · one page per method with the properties table.
- [MDN: HTTP response status codes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status) and [Redirections](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Redirections) · the whole catalogue, and the 301/302/303/307/308 table.
- [MDN: Retry-After](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Retry-After) · the header that makes 429 and 503 useful.
- [Stripe: Idempotent requests](https://docs.stripe.com/api/idempotent_requests) and [draft-ietf-httpapi-idempotency-key-header](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) · the production pattern for retryable `POST`, and its standardisation.

---

Part of [Web & HTTP](../README.md) · items 4.1, 4.2
