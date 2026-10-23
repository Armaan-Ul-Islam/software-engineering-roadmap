# Caching strategies

> **In one sentence:** A cache trades freshness for speed, so every caching decision is really a decision about who writes the cache, when entries die, what happens when a popular entry dies, and how stale you can afford to be relative to the database.

**Why it matters:** The database behind most slow systems is fine; it is the cache miss pattern that kills it. A single expiring hot key can send ten thousand identical queries to the database in the same second, and a careless write path can leave the cache serving a stale value for hours. Interviewers ask about cache consistency because almost every candidate gets the write ordering wrong.

## The idea

**Who loads and who writes.** Four patterns, differing in which component talks to the database:

| Pattern | Read miss | Write | Typical use |
|---|---|---|---|
| Cache-aside (lazy loading) | Application reads the database and puts the value in the cache. | Application writes the database, then deletes (or updates) the cache entry. | Default for most services; Redis or Memcached in front of a relational database. |
| Read-through | The cache itself loads from the database (a loader function). | As cache-aside, or combined with write-through. | Caffeine `LoadingCache`, Spring `@Cacheable`, CDN pull. |
| Write-through | As read-through. | Application writes the cache; the cache synchronously writes the database before acknowledging. | Data that must never be stale in the cache; costs write latency. |
| Write-behind (write-back) | As read-through. | Application writes the cache; the cache writes the database later, in batches. | Counters, metrics, anything where losing the last seconds is acceptable. |

Cache-aside is the usual answer because it is simple and the cache can be unavailable without stopping writes. Write-behind is the only pattern that can lose acknowledged data; use it knowingly.

**TTL and eviction.** A time-to-live bounds staleness and is your safety net against every bug below. Eviction decides what to drop when memory is full: LRU, LFU, or Caffeine's W-TinyLFU, which keeps frequently used entries from being pushed out by a scan. Redis configures this with `maxmemory-policy` (`allkeys-lru`, `allkeys-lfu`, `volatile-ttl`, `noeviction` and others); `noeviction` turns a full cache into write errors, which surprises people in production.

**Stampedes.** When a popular key expires, every request that misses recomputes it at once. A thousand concurrent misses for the same key produce a thousand identical database queries, the database slows, more requests miss, and the system falls over. Fixes, usually combined:

1. Request coalescing (single flight): only one loader per key per process runs; other callers wait for its result. Caffeine's `LoadingCache` does this for you.
2. A lock in the shared cache (`SET key:lock value NX PX 5000`) so only one process across the fleet recomputes; the others wait briefly or serve the old value.
3. Probabilistic early expiry: each reader recomputes slightly before expiry with a probability that rises as expiry approaches, so the recompute is spread out and one process usually refreshes before anyone misses. The formula from Vattani, Chierichetti and Lowenstein is `now − recomputeTime × beta × ln(random) ≥ expiry`.
4. Serve stale while revalidating in the background, and jitter TTLs so keys written together do not expire together.

**Hot keys.** Consistent hashing spreads keys across cache nodes, but one key lives on one node; a celebrity's profile can saturate that node alone. Replicate the key under several suffixes (`profile:42:0` to `profile:42:7`) and read a random copy, or add a small in-process cache in front of the shared one for the hottest entries.

**Cache and database consistency.** Every ordering has a race:

- Update cache, then database: if the database write fails, the cache holds a value that never existed. With two writers A (v1) and B (v2): A caches v1, B caches v2, B stores v2, A stores v1. Cache says v2, database says v1.
- Update database, then update cache: A stores v1, B stores v2, B caches v2, A caches v1. The cache holds v1 until the TTL.
- Delete cache, then update database: a reader misses between the two steps, reads the old row and repopulates it.
- Update database, then delete cache: a reader misses and reads the old row; the writer stores the new row and deletes the key; the reader then writes the old value into the cache. This needs the reader's database read to be slower than the whole write, which is rare on a primary but likely when reads go to a lagging replica.

The practical answer is the last ordering (write database, then delete the key) with a TTL as a backstop, because it only goes wrong in a narrow window and never caches a value that was not at some point committed. If that window matters, use the lease mechanism from the Facebook Memcache paper (the cache hands the missing reader a token, and a delete invalidates outstanding tokens so the stale repopulation is refused), or version the values and only replace an entry with a higher version.

## Example: cache-aside with stampede protection in Java

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Function;

interface RemoteCache<T> {
    Optional<T> get(String key);
    void set(String key, T value, Duration timeToLive);
}

public final class CoalescingCacheAside<V> {

    public record Entry<V>(V value, Instant expiresAt, Duration recomputeTime) {}

    private final RemoteCache<Entry<V>> remoteCache;
    private final Function<String, V> loader;
    private final Duration timeToLive;
    private final double beta;
    private final ConcurrentHashMap<String, CompletableFuture<V>> inFlight = new ConcurrentHashMap<>();

    public CoalescingCacheAside(RemoteCache<Entry<V>> remoteCache, Function<String, V> loader, Duration timeToLive, double beta) {
        this.remoteCache = remoteCache;
        this.loader = loader;
        this.timeToLive = timeToLive;
        this.beta = beta;
    }

    public V get(String key) {
        Optional<Entry<V>> cached = remoteCache.get(key);
        if (cached.isPresent() && !shouldRecomputeEarly(cached.get())) {
            return cached.get().value();
        }
        CompletableFuture<V> myLoad = new CompletableFuture<>();
        CompletableFuture<V> inProgress = inFlight.putIfAbsent(key, myLoad);
        if (inProgress != null) {
            // Another thread is already loading: serve the still-valid value if we have one, else wait for it.
            return cached.map(Entry::value).orElseGet(inProgress::join);
        }
        try {
            V value = loadAndStore(key);
            myLoad.complete(value);
            return value;
        } catch (RuntimeException exception) {
            myLoad.completeExceptionally(exception);
            throw exception;
        } finally {
            inFlight.remove(key, myLoad);
        }
    }

    private V loadAndStore(String key) {
        Instant started = Instant.now();
        V value = loader.apply(key);
        Duration recomputeTime = Duration.between(started, Instant.now());
        remoteCache.set(key, new Entry<>(value, Instant.now().plus(timeToLive), recomputeTime), timeToLive);
        return value;
    }

    private boolean shouldRecomputeEarly(Entry<V> entry) {
        // 1 - nextDouble() lies in (0, 1]; ln(0) would be negative infinity.
        double draw = 1.0 - ThreadLocalRandom.current().nextDouble();
        double earlyMillis = entry.recomputeTime().toMillis() * beta * -Math.log(draw);
        return Instant.now().plusMillis((long) earlyMillis).isAfter(entry.expiresAt());
    }
}
```

`inFlight` coalesces concurrent misses within one process, so a thousand threads produce one database query. The early-recompute check refreshes a hot key before it expires; because it is probabilistic, one process usually does it while the others keep serving the old value (`beta` of 1.0 is the paper's default, higher refreshes earlier). Across a fleet of 50 instances you still get up to 50 loads per expiry, which is normally fine; add the shared lock from the list above if it is not.

## Pitfalls

- No TTL "because we invalidate on write". The first missed invalidation (a bug, a direct SQL fix, a failed delete) is then permanent.
- Caching the result of a failed load, or caching nothing for missing rows. The first poisons the cache; the second makes every lookup for a non-existent key hit the database. Cache negative results with a short TTL.
- Treating Spring `@Cacheable` as a distributed lock. By default it does not coalesce; set `sync = true` or use Caffeine's loader to avoid in-process stampedes.
- Reading from a replica and then writing the cache. Replication lag makes the "database then delete" race common instead of rare.
- Forgetting that eviction is not expiry. Under memory pressure, Redis drops entries that are nowhere near their TTL; hit rate collapses with no error anywhere.

## Check yourself

1. Why does "update the database, then delete the cache key" still have a race, and under which deployment does that race become likely?
2. A key expires every 60 s and takes 400 ms to recompute under load. Describe what happens at the 60 s mark with and without request coalescing.
3. When is write-behind acceptable, and what exactly can you lose?
4. One product page is viewed 200,000 times per second during a launch. Why does consistent hashing not help, and what does?

## Go deeper

- [Scaling Memcache at Facebook](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf) · leases, stale sets and thundering herds at scale; the paper behind the consistency advice above.
- [Cache stampede](https://en.wikipedia.org/wiki/Cache_stampede) · the three mitigations with the probabilistic early expiry formula.
- [Caffeine](https://github.com/ben-manes/caffeine) · the in-process cache for Java: W-TinyLFU eviction, loading with coalescing, refresh-ahead.

---

Part of [System Design](../README.md) · item 2.5
