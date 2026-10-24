# Partitioning and sharding strategies

> **In one sentence:** Partitioning splits a dataset across nodes by a key, and every consequence follows from that key: which queries stay on one node, where load concentrates, how secondary indexes have to be built, and what it costs to move data when nodes are added, so the choice of partition key is the design decision and everything else is mechanism.

**Why it matters:** Sharding is the point where a database stops being one thing you can query, join, constrain and back up, and becomes many things you must coordinate. Teams shard too early and pay that price for a dataset one primary would have held; teams that shard late pick the key under pressure and spend a year migrating off it. In an interview, "we shard it" without saying by what key and what happens to the queries without the key is the hand-wave that fails the deep dive.

## The idea

A partition (shard, region, tablet, vnode: every system has a word) is a subset of the data that lives on one node, usually replicated to a few others (see item 3.1). The goal is to spread data and load evenly; the enemy is skew, where a few partitions carry most of the work while the rest idle.

**Key-range partitioning.** Each partition owns a contiguous range of keys, like volumes of an encyclopaedia (A to F, G to M). Keys stay sorted, so range scans ("orders for this tenant in March") read one partition or a few adjacent ones. The weakness is that a key that increases with time (a timestamp, a sequence) sends every write to the last partition while the others do nothing. The fix is a prefix that spreads writes: `(sensor_id, timestamp)` puts each sensor's readings together and still allows a range scan per sensor. HBase, Bigtable, CockroachDB and MongoDB's range sharding work this way.

**Hash partitioning.** Hash the key and assign each partition a range of hash values (or use consistent hashing, see item 2.6). Keys spread evenly whatever their shape, so no partition is hot because of key order. The price is range queries: adjacent keys are now on different nodes, so a range scan asks every partition and merges. Cassandra's compromise is a compound primary key: the first part (partition key) is hashed to pick the node, the rest (clustering columns) is kept sorted inside the partition, so `WHERE tenant_id = ? AND created_at > ?` is one partition and one ordered scan.

**Hot spots.** Hashing spreads keys, not load. One key that gets a million writes a day (a celebrity's post, one tenant's import job) is still one partition's problem. When the hot key is known, split it: append a random suffix (`post:42:0` to `post:42:9`) so writes spread across ten partitions, and have reads fetch all ten and merge. Only do this for keys you have identified as hot, because it makes every read ten times more expensive.

**Secondary indexes.** A query that does not use the partition key (`WHERE colour = 'red'`) needs an index, and the index has to be partitioned too. Two ways:

1. Local (document-partitioned) index: each partition indexes its own rows. Writes stay on one partition. A read by the secondary key must ask every partition and merge (scatter-gather), so its latency is the slowest partition's latency (see item 1.4). MongoDB, Cassandra and Elasticsearch work like this; DynamoDB calls it a local secondary index.
2. Global (term-partitioned) index: the index is itself partitioned by the indexed value, so all `colour = 'red'` entries live in one place and a read hits one partition. A write to a row may now touch several index partitions, and systems usually update global indexes asynchronously, so they lag the data. DynamoDB's global secondary indexes are exactly this, eventually consistent and with their own capacity.

**Rebalancing.** Data must move when nodes are added or lost, and `hash mod N` is the wrong way to decide where, because changing N moves almost every key (see item 2.6). The working strategies:

1. Fixed number of partitions, many more than nodes: create 1,024 partitions on day one, spread them over 8 nodes, and when a ninth arrives, move whole partitions to it. Keys never change partition; only partitions change node. Simple and predictable; the partition count is hard to change later, so choose it for the size you expect in five years. Elasticsearch (shards per index), Riak and Couchbase do this.
2. Dynamic splitting: a partition that grows past a size threshold splits in two, and small ones merge. The partition count follows the data, which suits key-range partitioning where a range can become hot or huge. A new, empty table starts as one partition until it splits, so systems offer pre-splitting. HBase and MongoDB do this.
3. Consistent hashing with virtual nodes: each node owns many points on a ring, and adding a node takes a small slice from each of the others (see item 2.6). Cassandra and Dynamo-style stores.

Automatic rebalancing is dangerous under stress: an overloaded node looks dead, the system starts moving its data, and the extra traffic makes more nodes look dead. Mature systems propose a rebalance and let an operator confirm it.

**Request routing.** Something has to know which partition is where: every client (a partition map pushed to drivers, as Cassandra and Kafka clients do), a routing tier (`mongos`, Vitess's `vtgate`), or any node, which forwards the request or, like Redis Cluster, answers with a `MOVED` redirect. The map lives in a coordination service such as ZooKeeper or etcd (see item 3.6) or spreads by gossip.

**Operational cost.** Everything that was one statement becomes a project: cross-partition transactions and joins, unique constraints not scoped by the partition key, schema migrations on N databases, backups consistent across shards, per-partition skew monitoring, and the next resharding. The honest default is to delay: one primary with read replicas, good indexes and a cache carries a long way (see item 1.2); when sharding becomes necessary, partition by the key almost every query already has.

## Example: choosing a shard key for a multi-tenant SaaS

An invoicing product with 20,000 business tenants. Five tenants hold 30 percent of the rows. The query mix: list a tenant's invoices for a date range (most reads), fetch one invoice (the rest), insert invoices, enforce "invoice number unique within a tenant", and a rare back-office query for overdue invoices across all tenants. Every request carries the tenant from the token and the URL (`/tenants/{tenantId}/invoices/{invoiceId}`).

| Candidate key | List for a tenant and date range | Fetch one invoice | Insert | Per-tenant uniqueness | Cross-tenant report | Balance |
|---|---|---|---|---|---|---|
| `hash(invoice_id)` | Every shard, scatter-gather | One shard | One shard, even | Needs a global index or a lock service | Every shard | Perfectly even |
| Range on `created_at` by month | The shards for those months | Every shard unless the ID encodes the date | Only this month's shard | Every shard | Every shard | All writes on one shard |
| `hash(tenant_id)` | One shard | One shard (tenant is in the URL) | One shard | Local to the shard | Every shard | Skewed by the five large tenants |
| Directory `tenant_id → shard` | One shard | One shard | One shard | Local to the shard | Every shard | Whatever you decide |

**Bad choice one: hash of the invoice ID.** It looks ideal because it is perfectly even, and it is wrong because the dominant query has no invoice ID. Every list request becomes a scatter-gather across all shards, so its latency is the slowest shard's and its cost grows with the shard count, which is the opposite of what sharding was for. Per-tenant uniqueness needs a global index or a coordination step on every insert.

**Bad choice two: range on creation date.** It makes archiving old data trivial, which is why it tempts people, and it puts every write of the month on one shard while the others serve reads from history. The current shard is the system's write capacity, exactly as if there were one database, plus all the operational cost of having many.

**The choice: tenant.** Every hot query is single-shard, uniqueness is a local constraint, a tenant's data can be moved or isolated as a unit, and a noisy tenant hurts only the tenants that share its shard. The remaining problem is the five whales. Hashing cannot help: a tenant is a single key, and a single key is a single shard, so the shard holding a whale is hot and the whale cannot be moved alone. A directory does: a `tenant_shard` table maps each tenant to a shard, the application caches it, and placement is a decision instead of a hash. The whales get shards of their own, the 19,995 others are spread evenly, and moving a tenant is copy, dual-write, flip the directory row. The usual refinement is a fixed number of logical shards (say 1,024) mapped to a handful of physical databases, with tenants hashed to logical shards and the directory mapping logical shards to physical ones, so most moves are of logical shards rather than individual tenants.

Inside a shard, keep rows sorted by `(tenant_id, created_at)` so the date-range query is one index range scan. The cross-tenant report does not belong on the transactional shards at all: feed a reporting store from change data capture (see item 3.8) and run it there.

## Pitfalls

- Sharding by a key the main query does not have. Every read becomes scatter-gather, with the tail latency of the slowest shard.
- A low-cardinality key such as country or plan. Twelve values cannot spread over fifty shards, and one value usually dominates.
- A time-ordered key in a range-partitioned store with no prefix. All writes go to the newest partition; the symptom is one node at full CPU while the rest of the cluster sleeps.
- Expecting the hash to fix a hot key. Hashing distributes keys, not the traffic of one key; a single tenant or a viral post needs splitting or isolation.
- Rebalancing automatically under load. Moving data during an incident is how an incident becomes an outage; keep a human in the loop.
- Sharding before exhausting one primary with replicas, indexes and a cache. The costs arrive on day one; the benefit arrives when you need it, which may be never.

## Check yourself

1. A metrics store is range-partitioned on timestamp and one node is saturated while the others idle. What is happening, and what change to the key fixes it without losing the per-series range scan?
2. Explain the write path and the read path for a local secondary index and for a global one, and say which one DynamoDB's GSI corresponds to and what that implies for consistency.
3. Why does a fixed number of partitions make rebalancing cheap, and what decision does it force you to make up front?
4. In the SaaS example, why does hashing by tenant fail for the five largest tenants, and what does the directory add that the hash cannot provide?

## Go deeper

- [Designing Data-Intensive Applications, chapter 6](https://dataintensive.net/) · partitioning by key range and by hash, secondary indexes, rebalancing and routing; the chapter this note condenses.
- [Amazon DynamoDB: Using Global Secondary Indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html) · a production global index, with its consistency and capacity rules spelt out.
- [AWS Database Blog: Choosing the right DynamoDB partition key](https://aws.amazon.com/blogs/database/choosing-the-right-dynamodb-partition-key/) · hot partitions, write sharding with suffixes, and cardinality, from the people who operate it.
- [MongoDB: Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/) · cardinality, frequency and monotonic change as the three properties of a shard key, with range and hashed sharding compared.
- [Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) · section 6 on the three partitioning strategies they tried and why fixed, equal-sized partitions won.

---

Part of [System Design](../README.md) · item 3.2
