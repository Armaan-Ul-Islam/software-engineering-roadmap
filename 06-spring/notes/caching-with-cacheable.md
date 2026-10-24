# Caching with @Cacheable

> **In one sentence:** `@Cacheable` wraps a method in a proxy that looks a key up in a named cache and calls the method only on a miss, so the hard parts are not the annotation but the key, the time to live, who evicts what on a write, and whether the cache lives in the process (Caffeine) or is shared by every instance (Redis).

**Why it matters:** A cache added to fix a slow endpoint is the most common source of "the data is wrong, but only sometimes": a stale price after an update, one tenant seeing another tenant's result because the key forgot the tenant, a heap that grows forever because nothing expires. The annotation makes caching look free; the cost shows up as inconsistency, and "how do you invalidate it?" is the interview question that separates people who have run a cache from people who have added one.

## The idea

**The mechanism.** `@EnableCaching` registers an interceptor that advises beans with cache annotations, exactly like `@Transactional` (item 1.4): the call must come through the proxy, so a self-invocation is never cached and private methods are never intercepted. Boot auto-configures a `CacheManager` for the provider it finds on the classpath, but only once `@EnableCaching` is present.

**The annotations.**

| Annotation | Behaviour |
|---|---|
| `@Cacheable(cacheNames, key, condition, unless, sync)` | Look the key up; on a miss call the method and store the result. `condition` is evaluated before the call (arguments only), `unless` after it (`#result` is available). `sync = true` lets one thread compute a missing key while the others wait, which prevents a stampede on a cold cache |
| `@CachePut` | Always call the method and store the result under the key |
| `@CacheEvict(key)` or `@CacheEvict(allEntries = true)` | Remove one entry or every entry; `beforeInvocation = true` evicts even when the method throws |
| `@Caching` | Several of the above on one method |
| `@CacheConfig` | Class-level defaults for `cacheNames` and the key generator |

**Keys.** Without `key`, `SimpleKeyGenerator` builds the key from all parameters: one parameter is used as is, several become a `SimpleKey`, none becomes `SimpleKey.EMPTY`. Whatever ends up in the key needs correct `equals` and `hashCode`; an object without them never hits. `key` is a SpEL expression: `#sku`, `#order.id`, `#root.methodName`, `#p0`; `#result` exists only in `unless` and in `@CachePut` and `@CacheEvict` keys. Parameter names in SpEL need the `-parameters` compiler flag, which Boot's build plugins set. Both Caffeine and Redis store a marker for `null` results by default, so a miss in the database is remembered as "does not exist" until the TTL runs out; `unless = "#result == null"` prevents that. `Optional` return values are unwrapped: the cache stores the value or the null marker.

**Providers.** Boot picks the provider from the classpath (`spring.cache.type` overrides): Caffeine for an in-process cache, Redis for one shared by all instances, plus JCache, Hazelcast and others, and a plain `ConcurrentHashMap` when nothing else is present. In-process is the fastest and simplest, and every instance has its own copy, so an eviction on one instance does not reach the others; data that must be consistent across instances right after a write needs Redis, or a short TTL and tolerance. Redis adds a network hop per lookup, serialisation of every value and a shared failure mode. `spring.cache.cache-names` with `spring.cache.caffeine.spec=maximumSize=10000,expireAfterWrite=10m` configures Caffeine for the simple case, and `spring.cache.redis.time-to-live=10m` does the same for Redis. One specification for every cache is rarely right, which is where code comes in.

**TTL and size.** Every cache needs a bound: `maximumSize` (Caffeine evicts by frequency and recency) and `expireAfterWrite` (stale after a known time), or `expireAfterAccess` for session-like data. A cache without a TTL is a second database with no invalidation story. Choose the TTL per cache from how stale the business can tolerate the data: exchange rates for an hour, product details for ten minutes, feature flags for thirty seconds.

**Serialisation with Redis.** The default value serialiser is JDK serialisation: it requires `Serializable`, breaks when a class changes and is unreadable in `redis-cli`. Configure `GenericJackson2JsonRedisSerializer` through `RedisCacheConfiguration.serializeValuesWith(...)` and cache records with stable shapes. Never cache JPA entities: they are detached, their lazy collections throw, and they drag the object graph in with them.

**Metrics.** Boot registers `cache.gets` (tagged `result=hit` or `miss`), `cache.puts`, `cache.evictions` and `cache.size` per cache. Caffeine reports them only when its builder has `recordStats()`; a Redis cache manager needs `enableStatistics()`. The hit ratio is what justifies the cache; a cache with a twenty percent hit ratio costs more than it saves.

**What not to cache.** Anything per user unless the user is part of the key; anything that must be read-your-writes consistent across instances when the cache is in-process; large lists keyed by filter parameters (low hit ratio, high memory, no sensible eviction); results that are cheap to compute; entities.

## Example: Caffeine with per-cache TTLs and eviction on update

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    public static final String PRODUCTS = "products";
    public static final String EXCHANGE_RATES = "exchangeRates";

    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager cacheManager = new CaffeineCacheManager();
        cacheManager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(1_000)
                .expireAfterWrite(Duration.ofMinutes(1))
                .recordStats());
        cacheManager.registerCustomCache(PRODUCTS, Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(10))
                .recordStats()
                .build());
        cacheManager.registerCustomCache(EXCHANGE_RATES, Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofHours(1))
                .recordStats()
                .build());
        return new TransactionAwareCacheManagerProxy(cacheManager);
    }
}
```

`setCaffeine` gives any cache name that was not registered explicitly a bounded default instead of Caffeine's unbounded one, so a typo in a `cacheNames` value cannot grow forever. `TransactionAwareCacheManagerProxy` defers puts and evicts that happen inside a transaction until after it commits; reads are unaffected. Defining your own `CacheManager` switches Boot's cache auto-configuration off, so the `spring.cache.*` properties no longer apply.

```java
public record ProductView(String sku, String name, BigDecimal price, boolean active) {

    static ProductView from(Product product) {
        return new ProductView(product.getSku(), product.getName(), product.getPrice(), product.isActive());
    }
}
```

```java
@Service
public class ProductCatalogue {

    private final ProductRepository productRepository;

    public ProductCatalogue(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Cacheable(cacheNames = CacheConfiguration.PRODUCTS, key = "#sku", unless = "#result == null", sync = true)
    public ProductView findBySku(String sku) {
        return productRepository.findBySku(sku).map(ProductView::from).orElse(null);
    }

    @Transactional
    @CacheEvict(cacheNames = CacheConfiguration.PRODUCTS, key = "#sku")
    public void changePrice(String sku, BigDecimal newPrice) {
        Product product = productRepository.findBySku(sku).orElseThrow(() -> new ProductNotFoundException(sku));
        product.changePrice(newPrice);
    }
}
```

The read caches a record, not the entity, keyed by the natural identifier the callers already have. The write evicts rather than puts: evicting cannot store a wrong value, and the next read repopulates from the committed row. Because the cache manager is transaction-aware, the eviction runs after the commit; without that, the eviction would happen when `changePrice` returns, before the transaction commits, and a concurrent `findBySku` in that gap would read the old price and cache it for ten minutes.

The same two caches on Redis, keeping Boot's auto-configured `RedisCacheManager` and customising it:

```java
@Bean
RedisCacheManagerBuilderCustomizer redisCacheCustomizer() {
    RedisCacheConfiguration productsConfiguration = RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10))
            .serializeValuesWith(RedisSerializationContext.SerializationPair
                    .fromSerializer(new GenericJackson2JsonRedisSerializer()));
    return builder -> builder
            .withCacheConfiguration(CacheConfiguration.PRODUCTS, productsConfiguration)
            .transactionAware()
            .enableStatistics();
}
```

After some traffic, `/actuator/prometheus` shows the ratio that matters (abridged):

```text
cache_gets_total{cache="products",result="hit"} 18213.0
cache_gets_total{cache="products",result="miss"} 1427.0
cache_evictions_total{cache="products"} 212.0
cache_size{cache="products"} 1391.0
```

## Pitfalls

- Calling a `@Cacheable` method from another method of the same class. The proxy is bypassed, so a `refreshAll` loop that calls `findBySku` hits the database every time.
- A key that forgets a dimension. A cache keyed by `#sku` in a multi-tenant or multi-currency system serves tenant A's price to tenant B; put every input that changes the answer into the key.
- Caching entities. Lazy collections throw `LazyInitializationException` on the second read, and the cached object no longer tracks the row.
- No TTL and no size. The `simple` provider Boot falls back to has neither; it is fine for tests and a leak in production.
- Evicting on one instance. With Caffeine in a cluster the other instances serve the old value until their TTL expires; either accept that window, shorten it, or move to Redis.
- `@CachePut` or `@CacheEvict` before the commit. A rollback leaves the put value in the cache, and a concurrent reader can repopulate the evicted key with stale data; use a transaction-aware cache manager.
- Caching misses forever. Without `unless = "#result == null"`, a product looked up a minute before it was created stays "missing" for the whole TTL.
- Changing a cached class with Redis still holding the old shape. The next read fails to deserialise; include a version in the key prefix (`spring.cache.redis.key-prefix`) and bump it on incompatible changes.

## Check yourself

1. `productCatalogue.findBySku` is cached, yet `productCatalogue.refreshAll`, which loops over SKUs and calls `findBySku`, hits the database for every SKU. Why?
2. Two instances run with Caffeine. A price changes on instance A. What does instance B serve, for how long, and what are two ways to shorten that?
3. Describe the interleaving that leaves a stale price in the cache for a full TTL when `@CacheEvict` runs as the method returns, and what the transaction-aware proxy changes.
4. Which of these would you cache, with what key and TTL: a product by SKU, a search result list by filter, the current user's permissions, a currency conversion table?

## Go deeper

- [Spring Boot: Caching](https://docs.spring.io/spring-boot/reference/io/caching.html) · provider detection, the `spring.cache.*` properties and the customiser hooks.
- [Spring Framework: Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html) · every annotation attribute, the SpEL context and the synchronised cache rules.
- [Caffeine](https://github.com/ben-manes/caffeine) · the library; the wiki explains size-based and time-based eviction and the statistics.
- [Caffeine: Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction) · what `maximumSize`, `expireAfterWrite` and `expireAfterAccess` actually do.
- [Spring Data Redis: Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html) · `RedisCacheConfiguration`, TTLs, serialisers, key prefixes and statistics.

---

Part of [Spring](../README.md) · item 8.5
