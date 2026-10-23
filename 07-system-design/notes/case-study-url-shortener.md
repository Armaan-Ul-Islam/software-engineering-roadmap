# Case study: a URL shortener

> **In one sentence:** A URL shortener is a key-value store with a public redirect endpoint, and every interesting decision in it (how codes are generated, 301 versus 302, where the cache sits, how clicks are counted) follows from the fact that it has a hundred reads for every write and the reads must never be slow or down.

**Why it matters:** It is the standard opening problem because it is small enough to finish in 45 minutes and still contains ID generation, caching, read scaling, HTTP semantics and analytics. Interviewers use it to see whether you apply a method (see item 6.1) or recite a diagram, and they probe the trade-offs below one by one.

## The idea

Apply the interview framework (see item 6.1) end to end: pin the requirements, let the numbers decide what is hard, design the API and data model, then spend the remaining time on the few decisions that actually matter here. For a shortener those are code generation, redirect semantics, and keeping the read path alive when everything else is not.

## Example: the worked design

### Requirements

Functional: given a long URL, return a short one (optionally a custom alias and an expiry); redirect a short URL to its long URL; report click counts per link. Out of scope after asking: user accounts beyond an API key, link editing, QR codes.

Non-functional: redirects are the product, so they must be fast (server time under 50 ms at p99) and highly available, and they must keep working if the write path is down; creation may be slower and may be unavailable briefly; codes should be short and not easily guessable; links must not be lost once created; read-heavy, roughly 100 reads per write.

### Estimates

100 million new links per month: 10^8 / 2.6 × 10^6 seconds ≈ 40 writes per second. Reads at 100:1: 4,000 redirects per second on average, 12,000 at a 3× peak. Storage: 100 million per month for five years is 6 × 10^9 links; at about 500 bytes each (long URL, code, owner, timestamps, indexes) that is 3 TB, large but within one well-provisioned relational primary. Bandwidth is irrelevant (6 MB/s at peak). Cache: redirects are heavily skewed to recent and popular links; even caching 20 percent of a day's distinct targets (0.2 × 3.5 × 10^8 × 500 bytes ≈ 35 GB) fits in a small Redis cluster, and the real hot set is far smaller.

The decision these numbers drive: writes are trivial and need no coordination beyond unique codes; reads need stateless servers and a cache; storage fits one primary with replicas now and partitions by code later if growth continues.

### API

- `POST /api/v1/urls` with `{"longUrl": "...", "customAlias": "launch", "expiresAt": "2027-01-01T00:00:00Z"}`, authenticated by API key, rate limited per key (see item 2.11). Returns 201 with `{"code": "15ftgG", "shortUrl": "https://sho.rt/15ftgG"}`; 409 if the alias is taken; 400 for an invalid or blocked URL.
- `GET /{code}` returns a redirect with `Location: <long URL>`, 404 for unknown codes, 410 for expired ones.
- `GET /api/v1/urls/{code}/stats` returns click counts by day.

### Data model

```sql
CREATE TABLE url (
    code        text        PRIMARY KEY,
    long_url    text        NOT NULL,
    owner_id    bigint      NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz,
    disabled    boolean     NOT NULL DEFAULT false
);

CREATE INDEX url_owner_idx ON url (owner_id, created_at);
```

The redirect path reads by primary key only, which is why a key-value store (DynamoDB, Cassandra keyed by code) is an equally good fit at larger scale. Click events are a stream (below), not rows in this table.

### ID generation

Seven base62 characters (`0-9`, `A-Z`, `a-z`) give 62^7 ≈ 3.5 × 10^12 codes, five hundred times the five-year need. Four ways to pick them:

1. Hash the long URL (SHA-256) and take the first seven base62 characters. Deterministic, so the same URL maps to the same code, which gives deduplication for free. But collisions are not rare at this scale: the birthday estimate n² / 2N with n = 6 × 10^9 and N = 3.5 × 10^12 predicts millions of them, so every insert must check and re-hash with a salt on conflict. And dedup across users means user A's stats include user B's clicks.
2. Counter plus base62. A database sequence or a Snowflake-style generator (see item 2.12) produces unique integers; encode them. No collisions, no check, trivially fast. But the codes are sequential, so anyone can enumerate every link ever created by counting. Fix with a bijective scramble of the integer before encoding, or by appending random characters, or by handing each application server a range of the counter (fetched from the database in blocks of, say, 10,000) so that the single counter is never a bottleneck or a point of failure.
3. Random seven-character code with a uniqueness check: generate, insert, retry on primary-key conflict. Unpredictable and simple. The chance of hitting an existing code is the fraction of the space used, about 0.2 percent after five years, so retries are rare.
4. A key generation service that pre-generates random unique codes into a table and hands them to the application servers in batches, moving the uniqueness check offline. Adds a component; worth it only when option 3's conflict rate or latency becomes measurable.

Option 3 is the usual answer for the interview, with option 2 plus scrambling as the one to mention when the interviewer asks about throughput or about avoiding the database check.

```java
public final class Base62 {

    private static final String ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

    public static String encode(long number) {
        StringBuilder result = new StringBuilder();
        do {
            result.append(ALPHABET.charAt((int) (number % 62)));
            number /= 62;
        } while (number > 0);
        return result.reverse().toString();
    }

    public static void main(String[] arguments) {
        System.out.println(encode(125) + " " + encode(1_000_000_000L) + " " + encode(3_521_614_606_207L));
    }
}
```

```text
21 15ftgG zzzzzzz
```

The last value is 62^7 − 1, the largest seven-character code.

### Redirect semantics

`301 Moved Permanently` lets browsers and intermediaries cache the redirect (301 and 308 are heuristically cacheable under RFC 9110), so repeat visits never reach your servers: less load, but no click analytics after the first visit, and no way to change or expire the destination for that visitor. `302 Found` (or `307 Temporary Redirect`, which also preserves the request method) is cacheable only with explicit freshness headers, so every click comes to you: full analytics and control, at the price of serving every request. Most shorteners with analytics use 302; use 301 only when the mapping is immutable and counting does not matter. Either way, set `Cache-Control` explicitly.

### Caching and scaling reads

Redirect servers are stateless behind a load balancer; add instances for throughput. Each looks the code up in Redis (cache-aside, TTL of hours, LRU eviction) and falls back to the database on a miss. Cache negative results for a short time so that unknown codes (bots probing, typos, enumeration attempts) do not hit the database. Because popularity follows a steep power law, hit rates above 95 percent are normal, and the database sees hundreds of reads per second rather than thousands. Write the cache entry on creation as well, so a freshly created link redirects immediately even if replicas lag. Read replicas handle the remaining misses; if the primary is lost, redirects keep working from cache and replicas while creation returns 503. Beyond one primary, partition by hash of the code (consistent hashing, see item 2.6); every redirect has the code, so no query crosses partitions.

### Analytics

Never write to the database on the redirect path. Emit a click event (code, timestamp, referrer, user agent, country derived from IP, never the raw IP) to a log such as Kafka and return the redirect immediately. A stream processor aggregates counts per code per hour into an analytics store; a Redis `INCR` per code can provide an approximate live counter if the product wants one. This keeps the hot path at one cache read and one fire-and-forget publish, and makes analytics outages invisible to users.

## Pitfalls

Each of these is a question an interviewer will ask and a mistake if the design has no answer.

- Custom aliases versus generated codes share one namespace. Reserve generated codes to exactly seven characters and require aliases to differ in length, or keep a reserved-word list (`api`, `admin`) and check availability in the same insert.
- Expiry. Check `expires_at` on read and return 410; delete expired rows in a background job, not synchronously.
- A viral link. One code receives 100,000 requests per second; a single Redis key becomes the bottleneck. A small in-process cache on each redirect server for the hottest codes, or replicating the key under several suffixes, fixes it (see item 2.5).
- Consistency after creation. A user creates a link and clicks it 200 ms later; a read from a lagging replica returns 404. Writing the cache on creation, or routing reads for very new codes to the primary, gives read-your-writes.
- Availability of redirects versus creation. The redirect path depends only on cache plus any replica; the creation path depends on the primary. Say so explicitly; it is why they are separated.
- Abuse. Validate and normalise URLs, check them against a malware blocklist, rate limit creation per API key, and make codes unpredictable so links cannot be enumerated.
- Deduplication. Returning the existing code for a repeated long URL saves storage but merges analytics across users; if you offer it, scope it per owner with an index on `(owner_id, sha256(long_url))`.
- Observability. Redirect p99 latency, cache hit rate, 404 and 410 rates, click-stream lag (see item 4.5).

## Check yourself

1. Why does hashing the long URL need collision handling at this scale, and what second problem does it create for per-user analytics?
2. A product manager wants every click counted. Which redirect status do you use, and what does it cost you compared with the alternative?
3. The database primary is down for ten minutes. Describe what users of existing links and users creating links each experience, and which design choices made that so.
4. Codes are generated from a database sequence encoded in base62. What can an attacker do, and what are two fixes that keep the sequence?

## Go deeper

- [System Design Primer: Design Pastebin.com (or Bit.ly)](https://github.com/donnemartin/system-design-primer/blob/master/solutions/system_design/pastebin/README.md) · a full worked solution with estimates in the same style.
- [RFC 9110: HTTP Semantics, redirection 3xx](https://www.rfc-editor.org/rfc/rfc9110.html#name-redirection-3xx) · the exact caching and method-preservation rules for 301, 302, 307 and 308.
- [ByteByteGo: System Design 101](https://github.com/ByteByteGoHq/system-design-101) · visual summaries of this and the other classic problems.
- [Twitter Snowflake](https://github.com/twitter-archive/snowflake) · the ID generator to mention when the counter becomes the bottleneck.

---

Part of [System Design](../README.md) · item 6.3.1
