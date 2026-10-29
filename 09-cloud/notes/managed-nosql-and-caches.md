# Managed NoSQL and caches: DynamoDB, Cosmos DB, ElastiCache and Azure Cache for Redis

> **In one sentence:** DynamoDB and Cosmos DB are key-value and document stores that give single-digit-millisecond reads at any scale as long as every access names a partition key, and they bill per unit of throughput rather than per instance; the managed Redis services are in-memory caches billed per node, which is why the first question for each is "what is the access pattern" and the second is "what does a unit cost".

**Why it matters:** Teams reach for DynamoDB or Cosmos DB expecting a cheaper PostgreSQL and discover that an unindexed query is a full scan billed per item, or that one hot customer throttles everyone. Caches are added to fix latency and then become a second source of truth with no expiry. Knowing the pricing unit of each service and the partition rules is what lets you choose them for the right reasons.

## The idea

### DynamoDB versus Cosmos DB

| | Amazon DynamoDB | Azure Cosmos DB |
|---|---|---|
| Model | Tables of items; each item has a partition key and an optional sort key; attributes are schemaless | Containers of items; several APIs (NoSQL, MongoDB, Cassandra, Gremlin, Table, PostgreSQL); the NoSQL API is the native one |
| Partitioning | Partition key chooses the physical partition; sort key orders items within it | Partition key chooses the logical partition (capped at 20 GB); the service maps logical to physical partitions |
| Indexes | Global secondary indexes (own key, own throughput) and local secondary indexes (same partition key, different sort key) | Every property indexed by default; indexing policy to exclude paths |
| Throughput unit | Read capacity units and write capacity units: one RCU is one strongly consistent read per second of an item up to 4 KB (two eventually consistent reads); one WCU is one write per second of up to 1 KB | Request units (RU): a point read of a 1 KB item costs 1 RU; writes and queries cost more depending on item size and index work |
| Capacity modes | Provisioned (with autoscaling) or on-demand (pay per request) | Provisioned, autoscale (scales between 10% and 100% of a maximum), or serverless (pay per RU consumed) |
| Consistency | Eventually consistent by default; strongly consistent reads on request; transactions across up to 100 items | Five levels: strong, bounded staleness, session (the default), consistent prefix, eventual |
| Item size limit | 400 KB | 2 MB |
| Change feed | DynamoDB Streams | Change feed |
| Global | Global tables (multi-region, active-active, last writer wins) | Multi-region replication with optional multi-region writes and conflict policies |

What they share: reads and writes that name the partition key are fast and cheap at any table size, and anything else (scans, filters without a key, cross-partition queries) costs throughput proportional to the data touched. Design the table from the queries backwards: list every access pattern first, then choose keys and indexes that serve each one with a key lookup. A relational schema with joins does not translate; one well-designed table with several item types ("single-table design") often does.

### The managed Redis services

| | Amazon ElastiCache | Azure Cache for Redis |
|---|---|---|
| Engines | Redis OSS, Valkey, Memcached | Redis |
| Shape | Node-based clusters (choose a node type, number of shards and replicas) or Serverless (pay per data stored and per request) | Tiers: Basic (one node, no SLA), Standard (primary and replica), Premium (clustering, persistence, VNet), Enterprise; Azure Managed Redis is the newer offering |
| Pricing unit | Node-hour by instance type, plus backup storage | Hourly by tier and cache size |
| TLS | In-transit encryption enabled per cluster, port 6379 | TLS on port 6380; the non-TLS port is disabled by default |
| Persistence | Optional snapshots | Premium and Enterprise tiers |

A cache is not a database: it may lose everything on a failover or an eviction, and the application must still work, more slowly, when it does. The common pattern is **cache-aside** (see item 7.3): read the cache, on a miss read the database and write the result into the cache with a time to live. Memory is the size driver: when `maxmemory` is reached the eviction policy decides what goes, and an `allkeys-lru` policy on a cache holding session state silently logs users out.

### The pricing arithmetic

A DynamoDB estimate starts from the access pattern. For the orders table: 500 reads per second of 3 KB items with eventually consistent reads, and 100 writes per second of 2 KB items.

- Reads: 3 KB rounds up to one 4 KB unit; eventually consistent halves the cost, so 500 × 1 ÷ 2 = **250 RCU**.
- Writes: 2 KB is two 1 KB units, so 100 × 2 = **200 WCU**.
- A global secondary index on `customerId` that projects the whole item doubles the write cost (every write updates the index) and adds its own read units.

Provisioned capacity for those numbers is cheap and predictable; on-demand charges per request at a higher unit price and makes sense for spiky or unknown traffic, which is also what the free tier and the calculators let you compare (see item 5.6). Cosmos DB's arithmetic is the same shape in RU: measure the RU charge of each operation (the SDK returns it with every response), multiply by the rate, and provision or autoscale to that, remembering that exceeding the provisioned rate returns HTTP 429 rather than slowing down.

## Example: an orders table, a key lookup and a cache in front of it

The access patterns: get an order by id; list a customer's orders newest first; find an order by its external payment reference.

| Item | `PK` (partition key) | `SK` (sort key) | Other attributes |
|---|---|---|---|
| Order | `CUSTOMER#42` | `ORDER#2026-10-29T09:14:02Z#a81f` | `orderId`, `status`, `total`, `paymentReference` |
| Order by id (GSI `byOrderId`) | `orderId` | | projected: `PK`, `SK` |
| Order by payment reference (GSI `byPaymentReference`) | `paymentReference` | | projected: `PK`, `SK` |

"List a customer's orders newest first" is a single `Query` on `PK = CUSTOMER#42` with `ScanIndexForward=false`, which reads only that customer's partition. The two lookups by id and by reference are key reads on the indexes. There is no scan anywhere.

```bash
aws dynamodb query --table-name orders \
  --key-condition-expression "PK = :customer AND begins_with(SK, :prefix)" \
  --expression-attribute-values '{":customer":{"S":"CUSTOMER#42"},":prefix":{"S":"ORDER#"}}' \
  --no-scan-index-forward --limit 20 --return-consumed-capacity TOTAL
```

The response's `ConsumedCapacity` is the number to put into the estimate. The Cosmos DB equivalent is a container with partition key `/customerId` and the query `SELECT * FROM orders o WHERE o.customerId = '42' ORDER BY o.createdAt DESC`, with the `x-ms-request-charge` header on the response giving the RU cost.

A cache-aside read in Spring, with a time to live, using the Spring Cache abstraction over Redis:

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public RedisCacheManager cacheManager(RedisConnectionFactory redisConnectionFactory) {
        RedisCacheConfiguration defaults = RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();
        return RedisCacheManager.builder(redisConnectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

```java
@Cacheable(cacheNames = "productCatalogue", key = "#productId")
public Product findProduct(String productId) {
    return productRepository.findById(productId).orElseThrow();
}
```

The connection to the managed service is configuration only: `spring.data.redis.host`, `spring.data.redis.port` (6380 on Azure), `spring.data.redis.ssl.enabled=true`, and the password from the vault (see item 2.3). Every entry expires after ten minutes, so a stale product is at most ten minutes stale and a lost cache is ten minutes of extra database load, not an outage.

## Pitfalls

- A hot partition. Every tenant writing to `PK = TENANT#big-customer` concentrates throughput on one partition and throttles that tenant while the table as a whole is idle. Spread hot keys with a suffix or redesign the key.
- `Scan` in production code. It reads the whole table, billed per item, and gets slower every month.
- Treating RU or capacity errors as outages. `ProvisionedThroughputExceededException` and HTTP 429 mean "provision more or back off"; the SDKs retry with backoff, and the alarm belongs on throttled requests.
- Cache entries without a time to live. The cache fills, eviction starts, and the data it serves is whatever was written first.
- The cache as the only copy. Session state or a shopping basket in Redis with no persistence is lost on the next failover; Basic tier on Azure is one node with no replica.
- Multi-region writes without a conflict policy. Last writer wins is a policy; make sure it is the one the business expects.
- Expecting SQL. No joins, no ad hoc reporting queries; export the change feed or stream to an analytical store for that.

## Check yourself

1. A table is keyed on `orderId` alone. Which of the three access patterns in the example becomes a scan, and how does the key design fix it without a second table?
2. Compute the provisioned capacity for 2,000 strongly consistent reads per second of 6 KB items and 300 writes per second of 500-byte items, and say which part of the design would double the write figure.
3. Your cache loses everything during a maintenance failover at 14:00. Describe what the Spring service in the example does for the next ten minutes, and what would have happened without `entryTtl`.
4. When would you choose Cosmos DB serverless or DynamoDB on-demand over provisioned capacity, and what signal in the metrics tells you to switch back?

## Go deeper

- [DynamoDB: Core components](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html) · tables, items, keys and indexes from the primary source; continue to the pages on read and write capacity.
- [Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/introduction) · the APIs, request units, partitioning and consistency levels.
- [Azure Architecture Center: Cloud Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/patterns/) · the cache-aside pattern and its failure modes, which apply to both clouds.
- [AWS Pricing Calculator](https://calculator.aws/) and [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) · turn the capacity arithmetic above into a monthly figure for your region.

---

Part of [Cloud](../README.md) · item 6.3
