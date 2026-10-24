# Case study: a distributed rate limiter

> **In one sentence:** A rate limiter for an API fleet is a shared counter with a decision attached, and the design is decided by four questions the algorithm does not answer: where the check runs, how a counter stays atomic across gateways, what happens when the counter store is slow or gone, and how one tenant's traffic is kept from becoming the store's bottleneck.

**Why it matters:** The rate limiter is the first classic interview problem because it is small enough to finish and still forces every system design habit: requirements that conflict (accurate but never slow), an estimate that decides the topology, a race that only shows up with two instances, and a failure policy that is a business decision rather than a technical one. The algorithms themselves are covered in item 2.11; this note is the design around them, following the framework in item 6.1.

## The idea

Treat the limiter as a product with its own SLO, not as middleware. It sits on every request, so its latency budget is a few milliseconds and its availability must exceed the API's, yet it must also be accurate enough to stop one customer's retry loop from becoming everyone's outage. The design is a sequence of choices about which pressure wins where.

## Example: the worked design

### Requirements

Functional: limit requests per client (API key, falling back to user, falling back to IP) per rule; rules such as "1,000 requests per minute per API key on `/v1/*`" and "10 per minute per IP on `/v1/login`"; per-tenant overrides; rules changeable without a deploy; refused requests get 429 with `Retry-After` and quota headers; new rules can run in shadow mode (log what would be refused, refuse nothing). Out of scope after asking: exact monthly billing quotas and concurrency limits.

Non-functional: the check adds under 1 ms at p50 and under 5 ms at p99; the limiter must not take the API down (its own availability target is higher than the API's 99.95 percent); accuracy within a few percent is fine, exactness is not required; limits are enforced fleet-wide, not per gateway instance; one region per deployment, with limits per region acceptable.

### Estimates

The API serves 30,000 requests per second on average and 100,000 at peak. One counter operation per request means 100,000 operations per second at peak against the counter store. A single Redis instance handles on the order of 10^5 simple operations per second (see item 1.2), so one node is at its edge at peak; a cluster of three to four primaries, or local pre-aggregation for the heaviest tenants, is required from day one. Memory: 2 million clients active in any window at roughly 100 bytes each (two counters plus key overhead) is about 200 MB; trivial. The decision these numbers drive: the hot path is one Redis round trip, the store must be sharded by client, and the design must survive that round trip being slow.

### High-level design

```text
client ──▶ CDN / edge (per-IP volumetric limits, cheap, coarse)
             │
             ▼
        API gateway fleet ── limiter middleware ──▶ Redis Cluster (counters, sharded by client key)
             │                      ▲
             │                      │ rules pushed on change
             ▼                      │
        backend services       rules service + database (rules, overrides, shadow flags)
                                    │
                               metrics (allowed, refused, latency, fail-open) ──▶ dashboards and alerts
```

The gateway is the enforcement point because identity (API key, tenant) is known there and the shared store is reachable from every instance (see item 2.11 for the layering argument). The rules service owns configuration and pushes a compiled rule set to every gateway, so the hot path never reads rules remotely.

### Deep dive 1: the algorithm

Sliding window counter for per-key quotas: two integers per client, no boundary burst, accurate enough (see item 2.11). Token bucket where bursts above the steady rate are a product feature (bulk exports). Fixed window nowhere, because its 2× boundary burst is what a backend sized for the limit cannot absorb; sliding log nowhere, because memory grows with the limit. The choice is stored with the rule.

### Deep dive 2: the distributed counter

Two gateways reading and writing the same counter must not interleave, so the read-modify-write runs as one Lua script in Redis. For the sliding window counter the keys are the current and previous windows of this client and rule, and both carry a hash tag so that Redis Cluster places them in the same slot (a multi-key script must not span slots):

```text
rl:{tenant-7:rule-12}:29880512     current minute   (window index = floor(now / 60 s))
rl:{tenant-7:rule-12}:29880511     previous minute
```

```lua
local currentKey = KEYS[1]
local previousKey = KEYS[2]
local limit = tonumber(ARGV[1])
local windowMillis = tonumber(ARGV[2])
local elapsedMillis = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local previous = tonumber(redis.call('GET', previousKey) or '0')
local current = tonumber(redis.call('GET', currentKey) or '0')
local weight = (windowMillis - elapsedMillis) / windowMillis
local estimate = previous * weight + current
if estimate + cost > limit then
  return {0, math.max(0, math.floor(limit - estimate))}
end
local updated = redis.call('INCRBY', currentKey, cost)
if updated == cost then
  redis.call('PEXPIRE', currentKey, windowMillis * 2)
end
return {1, math.max(0, math.floor(limit - estimate - cost))}
```

The gateway computes the window index and `elapsedMillis` from its own clock and passes them in, so one instance's clock skew affects only its own calls; with 60-second windows a few milliseconds of skew is invisible. The expiry is set only when the key is created, and to two windows, so the previous-window key is still there when it is needed and idle clients cost nothing. The script returns the decision and the remaining quota in one round trip, and that round trip (around half a millisecond inside a region, see item 1.2) is the whole latency budget.

### Deep dive 3: what to return

On refusal: `429 Too Many Requests`, `Retry-After` in seconds (for a sliding window, the time until enough of the previous window has aged out, bounded by the window length), and the quota headers on every response, not only refusals, so clients can pace themselves (see item 2.11). A body naming the rule that fired, because "which limit did I hit?" is the first support question. Overload of the backend itself is 503, not 429: the client's retry logic treats the two differently and so should your dashboards.

### Deep dive 4: hot keys and sharding

Redis Cluster shards by key, so a tenant sending 20,000 requests per second is 20,000 operations per second on one node, whatever the cluster size, and that node also serves every other tenant whose keys hash there. Two remedies, in order of preference:

1. Local buckets with periodic synchronisation for tenants above a threshold (say 2,000 requests per second). Each gateway keeps an in-memory bucket for the tenant and reconciles with Redis every 100 ms, reporting what it consumed and reading the fleet total. Overshoot is bounded by instances × rate × 100 ms, a few percent, which the requirements allow. The threshold is itself a rule attribute.
2. Splitting the counter into N sub-keys, each enforcing limit/N, chosen by a hash of the gateway instance. Spreads the node load, but a tenant whose traffic is uneven across gateways is refused early; only for coarse volumetric limits.

Hot keys are detected from sampled decisions per shard, and a tenant crossing the threshold moves to the local-bucket path automatically.

### Deep dive 5: fail open or fail closed

Redis will be slow or unreachable at some point; the limiter call has a timeout of a few milliseconds and a circuit breaker so that a dead store does not add that timeout to every request (see item 4.2). What happens then is a decision per rule, recorded with the rule:

- Quota rules (1,000 per minute per key) fail open, degraded to a local per-instance limit of `limit / instances × 2` so that abuse is still bounded. Availability of the API matters more than a few minutes of overshoot.
- Security rules (login attempts, one-time codes, password resets) fail closed: the endpoint refuses with 503 while the store is down. A brute-force window is worse than a short login outage.

Every fail-open decision increments a metric, and the alert "fail-open active for more than one minute" is paged, because the API is running without its quotas and nobody would otherwise notice.

### Monitoring

Per rule and tenant: allowed and refused counts, and shadow-mode would-refuse counts (the signal that a new rule is safe to enable). For the limiter itself: decision latency p50 and p99 as seen by the gateway, Redis errors and timeouts, breaker state, fail-open count, hot keys and memory per shard. Alert on p99 above 5 ms, on fail-open, and on a tenant's refusal rate jumping without a change on their side, which usually means a retry loop (see item 4.1).

### Failure modes and scaling

Redis shard lost: its clients fail open or closed by rule until the replica is promoted; counters restart from zero, one window of overshoot and nothing worse. Gateway scale-out: effective limits do not change, because the counter is shared, which is what justified the shared store. Rules service down: gateways keep the last pushed rule set. Ten times the traffic: add Redis primaries and reshard (keys expire within two windows, so there is almost nothing to migrate) and lower the local-bucket threshold.

## Pitfalls

- Treating the limiter as free. Every request pays its round trip; without a tight timeout and a breaker, a slow Redis is a slow API.
- Choosing fail open or fail closed globally. It is a per-rule business decision, and the login endpoint and the search endpoint want opposite answers.
- Forgetting the hash tag. In Redis Cluster a script touching two keys in different slots fails; the tag is what makes the two window keys co-located.
- Hot tenants on a shared shard. Their traffic degrades every tenant that hashes to the same node; detect and move them to local buckets.
- Setting expiry outside the script. A crash between `INCR` and `EXPIRE` leaves a counter that never resets, and the tenant is refused until someone notices.

## Check yourself

1. Why does the estimate of 100,000 operations per second at peak change the design, and what two different mechanisms could absorb it?
2. Walk through what two gateways do when they call the Lua script for the same client in the same millisecond, and explain why neither can admit a request the other should have refused.
3. Redis becomes unreachable for three minutes at peak. Describe what a normal API client and an attacker brute-forcing logins each experience, and which decision in the design made that so.
4. A tenant with 30,000 requests per second is refused at random even though it is under its limit. Which deep-dive mechanism is the likely cause, and what is the fix?

## Go deeper

- [Stripe: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters) · the production design behind this one: request limiters, concurrency limiters, load shedders, and shadow mode.
- [Cloudflare: Counting things, a lot of different things](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/) · the sliding window counter at the edge and its accuracy.
- [Redis: Scripting with Lua](https://redis.io/docs/latest/develop/interact/programmability/eval-intro/) · the atomicity guarantees the counter depends on, and `EVALSHA`.
- [RFC 6585: Additional HTTP Status Codes](https://www.rfc-editor.org/rfc/rfc6585) · 429 and `Retry-After`.
- [Google SRE Book: Handling Overload](https://sre.google/sre-book/handling-overload/) · client-side throttling and the difference between quota and overload.

---

Part of [System Design](../README.md) · item 6.3.2
