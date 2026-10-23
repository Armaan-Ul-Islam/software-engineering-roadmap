# Rate limiting algorithms

> **In one sentence:** A rate limiter decides, per client and per unit of time, which requests to refuse so that the rest can be served; the algorithms differ in how they treat bursts and how much state they keep, and the distributed version is only correct if the check-and-decrement is atomic.

**Why it matters:** Rate limiting is how a multi-tenant API keeps one customer's retry loop from becoming everyone's outage, and it is the first system design interview question most people meet. The hard parts are not the algorithm but the details around it: what the client is told, where the counter lives, and what happens when two gateway instances read the same counter at the same time.

## The idea

**Token bucket.** A bucket holds up to `capacity` tokens and is refilled at `rate` tokens per second. A request takes one token (or more, for expensive calls) and is refused when the bucket is empty. It allows bursts up to `capacity` and a long-run average of `rate`. State per client: two numbers (tokens, last refill time), refilled lazily when a request arrives. This is the default choice; Stripe's limiter, Guava's `RateLimiter` and Bucket4j all implement it.

**Leaky bucket.** Requests enter a queue that drains at a fixed rate; when the queue is full, new requests are dropped. Output is perfectly smooth, which is what you want when protecting a downstream with no burst tolerance, at the cost of queueing delay. NGINX's `limit_req` module works this way. Used as a pure meter (no queue), it is equivalent to a token bucket.

**Fixed window counter.** One counter per client per window ("per minute"), reset at the boundary. Cheapest possible state, but a client can send the full limit at 00:59 and again at 01:00: twice the limit in two seconds.

**Sliding window log.** Store the timestamp of every accepted request; on each request, drop timestamps older than the window and count the rest. Exact, and memory grows with the limit (a 10,000 per minute client costs 10,000 timestamps).

**Sliding window counter.** Keep the current and previous fixed-window counts and weight the previous one by how much of it still overlaps the sliding window: `previous × (1 − elapsedFraction) + current`. With a limit of 100 per minute, 80 requests in the previous minute and 30 so far at 15 seconds into this one, the estimate is 80 × 0.75 + 30 = 90, so the request is allowed. Two counters per client, no boundary burst, and an approximation Cloudflare measured as accurate enough for production.

**What to return.** HTTP 429 Too Many Requests (RFC 6585) with a `Retry-After` header saying when to try again, in seconds. Add rate-limit headers to every response, not only refusals, so well-behaved clients can pace themselves: the de facto `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset` (GitHub and many others), or the fields from the IETF `RateLimit` header draft, which has changed names between versions and is still a draft. Keep 429 for client quotas; a server that is overloaded regardless of who is calling should return 503, because the two tell the client different things.

**Distributed limiting and its race.** Behind a load balancer each gateway instance sees a fraction of a client's traffic, so a local bucket per instance enforces `limit × instances`. The shared counter lives in Redis, and the naive implementation is wrong:

```text
instance 1: GET quota:alice    -> 99
instance 2: GET quota:alice    -> 99
instance 1: 99 < 100, allow, SET quota:alice 100
instance 2: 99 < 100, allow, SET quota:alice 100   (101 requests admitted)
```

Make the read-modify-write one atomic operation: `INCR` returns the new value, so "allow if `INCR` result ≤ limit" is race-free for a fixed window; for a token bucket, run the whole refill-and-take as a Lua script, which Redis executes atomically. Set the key's expiry in the same script or transaction, otherwise a crash between `INCR` and `EXPIRE` leaves a counter that never resets. The remaining cost is one Redis round trip per request (around a millisecond inside a region); if that is too much, keep a small local bucket and synchronise with Redis every few hundred milliseconds, accepting a small overshoot.

**Where to enforce.** At the edge or CDN for volumetric abuse by IP, cheap and coarse. At the API gateway for the product's quotas per API key or tenant, where identity is known and the shared store lives. Inside services for protecting a specific expensive operation or a downstream dependency (a bulkhead, see item 4.2). Layers compound: the outer ones drop cheaply, the inner ones are precise. Clients should also honour `Retry-After`, the only limiter that reduces traffic rather than dropping it.

## Example: a token bucket in Java

```java
import java.util.concurrent.TimeUnit;

public final class TokenBucket {

    private final long capacity;
    private final double refillPerNanosecond;
    private double availableTokens;
    private long lastRefillNanos;

    public TokenBucket(long capacity, double refillPerSecond) {
        this.capacity = capacity;
        this.refillPerNanosecond = refillPerSecond / TimeUnit.SECONDS.toNanos(1);
        this.availableTokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    public synchronized boolean tryAcquire(int tokens) {
        refill();
        if (availableTokens >= tokens) {
            availableTokens -= tokens;
            return true;
        }
        return false;
    }

    public synchronized long secondsUntilAvailable(int tokens) {
        refill();
        double missing = Math.max(0, tokens - availableTokens);
        return (long) Math.ceil(missing / (refillPerNanosecond * TimeUnit.SECONDS.toNanos(1)));
    }

    private void refill() {
        long now = System.nanoTime();
        availableTokens = Math.min(capacity, availableTokens + (now - lastRefillNanos) * refillPerNanosecond);
        lastRefillNanos = now;
    }

    public static void main(String[] arguments) {
        TokenBucket bucket = new TokenBucket(5, 1.0);
        int allowed = 0;
        int denied = 0;
        for (int request = 0; request < 7; request++) {
            if (bucket.tryAcquire(1)) {
                allowed++;
            } else {
                denied++;
            }
        }
        System.out.println("allowed=" + allowed + " denied=" + denied + " retryAfter=" + bucket.secondsUntilAvailable(1) + "s");
    }
}
```

```text
allowed=5 denied=2 retryAfter=1s
```

The burst of five is admitted, the sixth and seventh are refused, and `secondsUntilAvailable` is what goes into `Retry-After`. `System.nanoTime` rather than wall-clock time, because the wall clock jumps when NTP corrects it.

## Example: the same bucket in Redis

Keys and arguments: the bucket key, then capacity, refill per second, the current time in milliseconds, and the tokens requested. Redis runs the script as one atomic step, so two gateway instances cannot interleave inside it.

```lua
local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local capacity = tonumber(ARGV[1])
local refillPerSecond = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])
local tokens = tonumber(bucket[1]) or capacity
local updated = tonumber(bucket[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - updated) / 1000 * refillPerSecond)
local allowed = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / refillPerSecond * 2000))
return allowed
```

The expiry is twice the time a bucket takes to refill completely, so idle clients cost no memory. Pass the time in as an argument so every instance's clock skew only affects its own calls, and use `EVALSHA` so the script body is not sent on every request.

## Pitfalls

- A limiter per instance behind a load balancer. The effective limit is multiplied by the instance count, and it changes every time you scale.
- Limiting by IP alone. Corporate NATs and mobile carriers put thousands of users behind one address; use the API key or user when you have one, IP only as the outer layer.
- Returning 429 with no `Retry-After` and no remaining-quota header. Clients then retry immediately, and your limiter becomes the thing that generates the load.
- A hot key for one tenant. All of one customer's requests hit the same Redis key; at very high rates, that single key becomes the bottleneck. Shard the counter and sum, or move that tenant to a local approximate bucket.
- Fixed windows when the limit protects something real. The boundary burst is 2× the limit; a database that survives 100 writes per second may not survive 200 in two seconds.

## Check yourself

1. A client is allowed 100 requests per minute. Under a fixed window, how many can it get through in a two-second span, and which algorithm with the same two counters fixes this?
2. Why is `GET`, compare, `SET` wrong in Redis even though each command is atomic, and what are two correct replacements?
3. Your API sits behind six gateway instances with in-memory token buckets of 1,000 per minute. What limit are clients actually experiencing, and what happens during a scale-out?
4. When should an overloaded service return 503 instead of 429, and why does the distinction matter to the client's retry logic?

## Go deeper

- [Stripe: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters) · the token bucket in production, plus concurrency limiters and load shedders as the other two layers.
- [Cloudflare: Counting things, a lot of different things](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/) · the sliding window counter and why its approximation is good enough.
- [RFC 6585: Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585) · the definition of 429 and its relation to `Retry-After`.
- [RateLimit header fields for HTTP (IETF draft)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-ratelimit-headers/) · the standardisation effort for the quota headers.
- [Bucket4j](https://github.com/bucket4j/bucket4j) · a Java token-bucket library with local and distributed (Redis, Hazelcast, JDBC) backends.

---

Part of [System Design](../README.md) · item 2.11
