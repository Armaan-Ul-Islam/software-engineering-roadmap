# Project spec: a URL shortener measured under load

> **In one sentence:** Build a URL shortener on Spring Boot, PostgreSQL and Redis, decide 301 versus 302 with evidence, keep click analytics off the redirect path, load-test it to a p99 under 10 ms at 1,000 requests per second, then add a read replica and reproduce the lag anomaly it introduces.

**Why it matters:** The shortener is the standard warm-up system-design question because every decision in it is measurable: how IDs are generated, what a cache buys, which status code the browser caches, and what a replica costs in consistency. Most candidates can draw the boxes; few have the graphs. This project gives you the graphs.

## The idea

One Spring Boot service, `shortly`, with three endpoints and two stores. PostgreSQL is the source of truth; Redis is a cache-aside in front of it for the redirect path. Clicks are recorded asynchronously so that the hot path does one cache read and nothing else.

Scope:

- 1.1 `POST /links` with a target URL returns a code; `GET /{code}` redirects; `GET /links/{code}/stats` returns clicks per day.
- 1.2 Codes come from a database sequence encoded in Base62 (short, unique, no coordination), with a random-code variant as a comparison.
- 1.3 `GET /{code}` answers `302 Found` with `Cache-Control: no-store`, so every click reaches the service; the README explains what `301` would change.
- 1.4 Redis holds `code -> target` with a TTL, plus a short negative entry for unknown codes so scanners do not reach PostgreSQL.
- 1.5 Clicks are queued in memory and inserted in JDBC batches by a background thread; the loss window on crash is stated, not hidden.
- 1.6 Phase two adds a PostgreSQL streaming replica and routes `GET` queries to it.

Concepts exercised: Web & HTTP 4.2, 5.1, 5.3; Databases 3.1, 3.3, 7.1, 7.2, 7.5, 9.2; Spring 3.2, 4.1, 4.3, 8.1, 8.5; System Design 2.5, 2.6, 2.12.

## Example: the data model, the code generator and the redirect

```sql
CREATE TABLE links (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    target_url  text        NOT NULL CHECK (length(target_url) <= 2048),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz
);

CREATE TABLE clicks (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    link_id     bigint      NOT NULL REFERENCES links (id),
    clicked_at  timestamptz NOT NULL DEFAULT now(),
    referrer    text,
    user_agent  text
);
CREATE INDEX clicks_link_id_clicked_at_idx ON clicks (link_id, clicked_at);
```

The stats query is `SELECT date_trunc('day', clicked_at) AS day, count(*) FROM clicks WHERE link_id = $1 AND clicked_at >= now() - interval '30 days' GROUP BY day ORDER BY day`, served entirely by the composite index.

```java
public final class Base62 {

    private static final String ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

    static String encode(long id) {
        StringBuilder code = new StringBuilder();
        long remaining = id;
        do {
            code.append(ALPHABET.charAt((int) (remaining % 62)));
            remaining /= 62;
        } while (remaining > 0);
        return code.reverse().toString();
    }
}
```

`encode(1_000_000_000L)` is `15FTGg`: six characters cover more than 56 billion links. The redirect itself, compiled against Spring Framework 7.0:

```java
@GetMapping("/{code}")
ResponseEntity<Void> redirect(@PathVariable String code) {
    return linkLookup.targetFor(code)
        .map(target -> ResponseEntity.status(HttpStatus.FOUND)
            .location(URI.create(target))
            .header("Cache-Control", "no-store")
            .<Void>build())
        .orElseGet(() -> ResponseEntity.notFound().build());
}
```

Milestones, each ending in a committed test:

1. **Create and redirect on PostgreSQL alone.** Validate the target (only `http` and `https`, no credentials in the URL, length limit). Test (Testcontainers): `POST` then `GET` returns `302` with the exact `Location`; an unknown code returns `404`; a `javascript:` target is rejected with `400`.
2. **301 versus 302, with evidence.** Temporarily return `301`, open the link twice in a browser, and show in DevTools that the second click never leaves the browser cache. Test: a unit test pins the status to `302` and the `Cache-Control: no-store` header, with a comment linking to the README section that explains why.
3. **ID generation.** Sequence plus Base62 as above; compare with a 7-character random code and retry on unique violation. Test: encode and decode round-trip for `0`, `61`, `62` and `Long.MAX_VALUE`; 100,000 generated codes are distinct.
4. **Redis cache-aside.** Read-through on miss, TTL of one hour, negative entries of one minute for misses, eviction on update or delete. Test: the second `GET` for a code performs no SQL (count statements with a `DataSource` proxy or a repository wrapper); a code that was deleted is gone from Redis in the same request.
5. **Clicks off the hot path.** A bounded `ArrayBlockingQueue` drained by one thread into `INSERT ... VALUES` batches of 500. Test: 10,000 redirects produce 10,000 click rows within five seconds (Awaitility), and the redirect's p99 does not change with click recording on or off.
6. **Load test and graphs.** k6 at 1,000 requests per second for five minutes against a warm cache, Micrometer counters for cache hits and misses tagged `result`, HikariCP metrics (`hikaricp_connections_active`) and PostgreSQL's `pg_stat_database` for transactions per second. Graph the hit ratio and the database load in Grafana or export them to a CSV in the README.
7. **Read replica.** A second PostgreSQL container as a streaming replica, an `AbstractRoutingDataSource` that sends read-only transactions to it. Test: create a link and immediately read its stats from the replica; with a replica paused (`SELECT pg_wal_replay_pause()`), the read misses. Fix by reading from the primary for ten seconds after a write, or by serving the redirect from the cache that was written on create, and make the test pass.

Definition of done:

- 2.1 p99 redirect latency under 10 ms at 1,000 requests per second on a laptop, with cache hit ratio and database load graphed.
- 2.2 The README states the 301 versus 302 decision with the DevTools evidence, the ID-generation choice with its enumeration trade-off, and the click-loss window on crash.
- 2.3 The replication-lag anomaly is reproduced by a committed test and fixed, with the fix explained.

Stretch goals:

- 3.1 Replace the in-memory click queue with Redis Streams or Kafka and make click recording survive a crash; measure the latency cost.
- 3.2 Custom aliases with a reserved-word list, and expiry enforced by both the cache TTL and a scheduled sweep.
- 3.3 Run the load test with the cache disabled and find the request rate at which PostgreSQL alone falls over; this is the number that justifies Redis.

## Pitfalls

- Returning `301` and then wondering why click counts are low. Browsers cache permanent redirects, so later clicks never reach you and you can never change the target.
- Open redirects. Accepting any string as a target turns your domain into a phishing proxy; allow only `http` and `https`, reject `javascript:` and `data:`, and consider a deny-list of your own hosts.
- Sequential codes leak volume and make enumeration trivial. State it in the README; if it matters, use random codes with a unique index and a retry.
- Writing the click in the redirect transaction. It doubles the latency and makes the hot path depend on write throughput; queue it.
- A cache TTL longer than the link's expiry. Compute the TTL from `expires_at` or evict on expiry.
- Measuring p99 with k6 on the same laptop as the service and the database without saying so. Record CPU usage during the run and state that the number is a lower bound on contention, not a production figure.
- Routing every read to the replica, including the read right after a write. Read-your-writes breaks first; milestone 7 exists to make you feel it.

## Check yourself

1. Which component answers a redirect for a hot link at steady state, and what has to happen for PostgreSQL to see that request at all?
2. A product manager asks for "permanent" links so that the browser stops hitting your servers. What do you lose, and how would you give them most of what they want without `301`?
3. Why does a sequence-based ID need no coordination between instances, and what would a Snowflake-style ID add?
4. Your replica lags by two seconds. Which endpoint breaks, for whom, and which of the two fixes in milestone 7 would you ship first?

## Go deeper

- [System Design Primer: Pastebin design](https://github.com/donnemartin/system-design-primer/blob/master/solutions/system_design/pastebin/README.md) · the sibling design, with capacity estimates to compare against your measurements.
- [Redis documentation](https://redis.io/docs/latest/) · TTLs, eviction and the data types you might use for clicks.
- [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · why a small pool wins the load test.
- [Grafana k6](https://grafana.com/docs/k6/latest/) · constant-arrival-rate scenarios for milestone 6.

---

Part of [Projects](../README.md) · item 2.1
