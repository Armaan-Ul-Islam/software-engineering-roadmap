# HTTP caching: Cache-Control, validators, Vary and CDNs

> **In one sentence:** A response is either fresh (served from cache without asking) or stale (revalidated with a cheap conditional request), the server decides which with `Cache-Control` and validators, and `Vary` plus the private/shared distinction decide who is allowed to reuse it.

**Why it matters:** The two caching incidents every team eventually has are "users see someone else's data" (a per-user response stored by a shared cache) and "we deployed an hour ago and users still run the old JavaScript" (HTML or assets cached with no way to invalidate). Both are header mistakes, and both are prevented by the same five directives.

## The idea

**Freshness.** A cached response may be served without contacting the origin while its age is below its freshness lifetime: `max-age` seconds (or `s-maxage` for shared caches, which wins over `max-age` there). Caches report how old a copy is in the `Age` header. If the server sends no explicit lifetime but does send `Last-Modified`, caches may compute a **heuristic** lifetime (RFC 9111 suggests 10 % of the time since the last modification); browsers do this, which is how an API response with no `Cache-Control` ends up cached.

**Validation.** Once stale, a cache does not throw the copy away. It asks the origin whether it is still good: `If-None-Match: <etag>` or `If-Modified-Since: <date>`. The origin answers `304 Not Modified` with no body if so, and the cache refreshes the headers and serves the old body. An `ETag` is an opaque version identifier (a hash or a version number); `W/"..."` marks it weak, meaning "semantically the same", which is enough for caching but not for `If-Match` on writes (item 4.5).

**The directives you need.**

| Directive | Meaning |
|---|---|
| `max-age=N`, `s-maxage=N` | Fresh for N seconds in any cache / in shared caches only |
| `no-cache` | Store it, but revalidate before every reuse (it does *not* mean "do not cache") |
| `no-store` | Never write it to any cache; for sensitive data |
| `private` | Only the user's browser may store it; never a CDN or proxy |
| `public` | Shared caches may store it even though the request carried `Authorization` |
| `must-revalidate` | Once stale, never serve it without a successful revalidation |
| `immutable` | Will never change while fresh; browsers skip revalidation on reload |
| `stale-while-revalidate=N` | May serve the stale copy for N more seconds while refreshing in the background |
| `stale-if-error=N` | May serve the stale copy if the origin returns 5xx |

**Private vs shared caches.** The browser cache belongs to one user. CDNs and reverse proxies are shared: whatever they store, they serve to everyone whose request has the same cache key. Anything that depends on who is asking must be `private` (or `no-store`). A shared cache will not store a response to a request with an `Authorization` header unless the response explicitly says `public`, `s-maxage` or `must-revalidate`, which is a safety net, not a strategy; cookie-based sessions get no such protection.

**`Vary` and the cache key.** The key is the URL plus every request header named in `Vary`. `Vary: Accept-Encoding` keeps gzip and identity copies apart. `Vary: Origin` is required when a CORS response echoes the origin (item 7.2). `Vary: Cookie` or `Vary: *` makes shared caching pointless, since almost no two requests match.

**Strategies.** Fingerprinted assets (`app.3f9a2c1e.js`) get `public, max-age=31536000, immutable`; a new build produces a new name, so nothing ever needs invalidating. The HTML that references them gets `no-cache` with an `ETag`, so every page load makes one small conditional request and always learns the current filenames. Public API reads can use short `max-age` plus `stale-while-revalidate`; per-user API reads use `private, no-cache` with an `ETag` so the browser still gets 304s. **CDN purging** is for everything else: by URL, by tag, or everything. A purge empties the CDN but cannot reach browsers, which is the reason fingerprinting exists; `s-maxage` lets you give the CDN a long lifetime (you can purge it) and browsers a short one (you cannot).

## Example: three sets of headers

A fingerprinted library file from a CDN (`curl -sI https://cdnjs.cloudflare.com/ajax/libs/jquery/3.7.1/jquery.min.js`, trimmed):

```http
HTTP/2 200
content-type: application/javascript; charset=utf-8
cache-control: no-transform, public, s-maxage=30672000, max-age=30672000, immutable
age: 2654445
last-modified: Tue, 29 Aug 2023 04:36:11 GMT
vary: Accept-Encoding
```

The version is in the URL, so the lifetime is about a year, `immutable` stops reload-triggered revalidation, and `age: 2654445` shows this edge node has been serving the same copy for a month.

A per-user API response that must never be shared but should still produce 304s:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: private, no-cache
ETag: "orders-v17-c9e2"
Vary: Accept-Encoding
```

A public list that tolerates 30 seconds of staleness and prefers speed over freshness during refreshes:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: public, max-age=30, stale-while-revalidate=60
ETag: W/"products-page1-8a1f"
Vary: Accept-Encoding
```

## Example: a conditional request that returns 304

```bash
curl -sI https://www.rfc-editor.org/rfc/rfc9111.html | grep -i etag
```

```text
etag: W/"67c426a73321f73db9ffdf2508376ec5"
```

```bash
curl -sI https://www.rfc-editor.org/rfc/rfc9111.html -H 'If-None-Match: W/"67c426a73321f73db9ffdf2508376ec5"'
```

```text
HTTP/2 304
date: Fri, 23 Oct 2026 18:32:58 GMT
```

The second response has no body and only the headers the cache should update. The sequence a browser runs for `no-cache` HTML is exactly this: a request with `If-None-Match`, a 304 most of the time, and a full 200 only when the content changed. The round trip is still paid; the bytes are not. That is the trade `no-cache` makes against `max-age`, and `immutable` is the opposite end of the same dial.

## Pitfalls

- No `Cache-Control` at all on API responses. Browsers apply heuristic freshness when `Last-Modified` is present, and back/forward navigation can show stale data. Always say something, even if it is `no-store`.
- `no-cache` on something you meant to keep out of caches. It still gets stored. Use `no-store` for anything sensitive, and `private` for anything per-user.
- A per-user page behind a CDN with `public` or `s-maxage`. User B sees user A's account. Check the response of every authenticated endpoint for `private` or `no-store`, and make sure the CDN does not cache responses that carry `Set-Cookie`.
- Long `max-age` on HTML or on un-fingerprinted assets. There is no way to take it back; users keep the old version until it expires. Fingerprint, or keep HTML on `no-cache`.
- Purging the CDN and declaring victory. Browsers still hold their copies for the full `max-age`. If you had to purge an un-fingerprinted asset, the fix is a new URL.
- `Vary: *`, `Vary: Cookie` or `Vary: User-Agent`. Hit rates collapse. Vary only on headers that actually change the representation, and normalise them at the edge.
- Forgetting `Vary: Origin` on CORS responses. A shared cache serves the `Access-Control-Allow-Origin` meant for one origin to another, which fails for the second origin and is a cross-origin leak when combined with credentials.
- Weak ETags on write paths. `W/` validators are fine for `If-None-Match`, but `If-Match` for optimistic concurrency needs strong ones, and some servers emit weak ETags automatically when compressing.

## Check yourself

1. A response has `Cache-Control: max-age=600` and arrives from a CDN with `Age: 450`. How long will the browser consider it fresh, and what happens at the end of that time?
2. Explain the difference between `no-cache`, `no-store` and `private` by naming, for each, who is allowed to store the response and when it may be reused.
3. You deploy a fix to `app.js` but users keep running the old code. The CDN was purged. Which header on which response caused this, and what is the permanent fix?
4. Why does a response that varies by `Origin` need `Vary: Origin`, and what goes wrong in a shared cache without it?

## Go deeper

- [MDN: HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching) · the clearest walk through freshness, validation and the directives, with diagrams.
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html) · the rules caches actually follow; sections 3 (storing) and 4 (constructing responses) settle arguments.
- [web.dev: Prevent unnecessary network requests with the HTTP Cache](https://web.dev/articles/http-cache) · the fingerprinting strategy and a decision flowchart.
- [web.dev: stale-while-revalidate](https://web.dev/articles/stale-while-revalidate) and [RFC 5861](https://www.rfc-editor.org/rfc/rfc5861.html) · the background-refresh directives and what they cost.
- [Cloudflare: What is a CDN?](https://www.cloudflare.com/learning/cdn/what-is-a-cdn/) · where shared caches sit and how purging works.

---

Part of [Web & HTTP](../README.md) · items 5.1, 5.2, 5.3
