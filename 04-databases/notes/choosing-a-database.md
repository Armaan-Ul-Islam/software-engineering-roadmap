# Choosing a database

> **In one sentence:** Every database buys one set of strengths by giving something up (joins, transactions, consistency, ad hoc queries or operational simplicity), so the choice starts from the access patterns, consistency needs, scale and team you actually have, and for most backend systems the answer is PostgreSQL until a specific, measured requirement says otherwise.

**Why it matters:** The database is the component you cannot swap in a sprint: it holds the state, it shapes the code and migrating it is a project of its own. Teams that pick a document store "for flexibility" discover joins; teams that pick Cassandra "for scale" at a million rows discover operations; teams that stay on PostgreSQL discover that it does JSON, search, queues and time series well enough for far longer than expected. Interviewers ask "which database, and why" to see whether you reason from requirements or from fashion.

## The idea

**The landscape, and what each family trades away.**

| Family | Examples | Model and strength | What it gives up |
|---|---|---|---|
| Relational | PostgreSQL, MySQL, SQL Server, Oracle | Tables, joins, constraints, ACID transactions, ad hoc queries, mature tooling | Horizontal write scaling is manual (item 7.4); schema changes are migrations |
| Key-value | Redis, Memcached, DynamoDB | Get and put by key at very low latency; trivially scaled by key | No joins, no queries beyond the key (or indexes you maintain yourself); limited transactions |
| Document | MongoDB, Couchbase | A whole aggregate (an order with its lines) as one JSON document; flexible schema; easy to shard by document | Cross-document joins and multi-document transactions are weak or costly; duplicated data is kept consistent by you |
| Wide-column | Cassandra, ScyllaDB, HBase | Very high write throughput and linear scaling; data laid out per query (partition key plus clustering key) | One table per query pattern; no joins or ad hoc queries; eventual consistency by default; compaction and tombstones to operate (item 2.3) |
| Graph | Neo4j, Amazon Neptune | Relationships are first class; variable-depth traversals are cheap | Aggregates, bulk analytics and scaling past one machine are hard |
| Search | Elasticsearch, OpenSearch, Meilisearch | Inverted indexes: relevance ranking, facets, fuzzy matching (item 9.4) | Not a system of record: eventually consistent, no transactions, reindex when mappings change |
| Time series and analytics | TimescaleDB, InfluxDB, ClickHouse | Append-heavy ingestion, compression, time-bucketed aggregates, retention by age | Updates and deletes of individual rows are slow or unsupported; narrow query patterns |

**A decision checklist.**

1. **Access patterns.** Write down the ten most frequent queries and the five most complex. Do they join? Filter on arbitrary columns? Traverse relationships? Aggregate over time? A store that cannot express a query you need forces you to denormalise and to maintain the copy forever.
2. **Consistency needs.** Which invariants must hold at every instant (a balance never negative, one booking per room per slot)? Those need transactions and constraints in one place (items 5.2 to 5.4, 8.3). Which may lag by seconds (a search index, a feed, a counter)? Those tolerate eventual consistency and can live in a derived store.
3. **Scale, measured.** Data volume and growth, read and write rates, latency targets. A single well-provisioned PostgreSQL server handles terabytes of data and tens of thousands of simple transactions per second; the great majority of systems never outgrow one primary with replicas (item 7.1). Plan for the next two years, not for a hypothetical.
4. **Operational maturity.** Backups and tested restores (item 7.6), failover (item 7.3), upgrades, monitoring, and who is on call. A managed service changes this calculation; a self-hosted cluster does not run itself.
5. **Team and ecosystem.** What the team can debug at three in the morning; the quality of the driver, the ORM, the migration tool and the local development story in your language.
6. **The cost of being wrong.** How would you get the data out? A relational schema exports to anything; data modelled as per-query tables in a wide-column store does not come back without a rewrite.

**Why PostgreSQL is the right default.** It covers more of the landscape than any other single system: `jsonb` with GIN indexes for document-shaped data (items 1.4, 3.4, 8.6), full-text search with ranking (item 9.4), queues with `SKIP LOCKED` (item 6.6), `LISTEN`/`NOTIFY`, range types and exclusion constraints, recursive CTEs for graphs of moderate depth (item 1.3), partitioning and BRIN indexes for time series (items 3.4, 7.4), and extensions such as PostGIS, TimescaleDB, pgvector and Citus. It does all of it with real transactions, constraints and a planner that answers questions nobody anticipated when the schema was designed. One database for several roles also removes the hardest problem of polyglot persistence: keeping two stores consistent with each other.

**When it is not.** When the workload genuinely is one of the specialised shapes, at a scale you have measured: hundreds of thousands of writes per second across many nodes (wide-column), sub-millisecond reads of simple values at very high rates (key-value, item 9.2), relevance-ranked search with facets over a large corpus (search engine), deep variable-length traversals as the main operation (graph), or billions of time-series points with compression and downsampling (time series or columnar analytics). The tell is that PostgreSQL has been tried for the job and falls short on a number, not that an article said it would. Then add the specialised store beside PostgreSQL, keep PostgreSQL as the system of record, and feed the other store from it through change data capture or an outbox (item 5.6).

| Decision | Choose | Because |
|---|---|---|
| Business records with rules and reports | PostgreSQL | joins, constraints, transactions, ad hoc queries |
| Hot values read millions of times a minute | Redis beside PostgreSQL | latency and offload; the database stays the truth (item 9.2) |
| Full-text search with facets and relevance tuning | PostgreSQL FTS first, then Elasticsearch or OpenSearch | FTS covers simple cases; a search engine when ranking and facets dominate |
| Very high write rates of independent events | TimescaleDB, ClickHouse or Cassandra, by query shape | append-optimised storage, compression, retention |
| Relationship-heavy traversals as the core feature | A graph database, or recursive CTEs if depth is bounded | traversal cost grows with depth in SQL |
| Scaling writes past one machine | Partition first, then Citus or application sharding (item 7.4) | sharding costs every query its key |

## Example: three mini-cases

**Case 1: a B2B invoicing product.** 2,000 tenants, a few million invoices a year, strict rules (invoice numbers unique and gapless per tenant, totals equal to the sum of lines, VAT by period), reporting with arbitrary filters, seven years of retention. Checklist: joins and ad hoc queries everywhere, invariants that must hold immediately, modest scale, a small team. Choice: PostgreSQL, one database, tenants separated by a `tenant_id` column (with row-level security) or by schema, constraints for the invariants, the audit log partitioned by month. A document store would copy customer and product data into every invoice and turn the reports into batch jobs; nothing here needs more than one primary.

**Case 2: an IoT platform ingesting 200,000 sensor readings per second** from a million devices, queried as "the last hour for device X" and "the daily average per site", 13 months of retention, readings never updated. Checklist: append-only writes at a rate a single PostgreSQL primary does not sustain comfortably, queries always by device and time, no cross-row invariants, eventual consistency acceptable. Choice: a time-series store. TimescaleDB if the team knows PostgreSQL and its compression and hypertables meet the rate; otherwise Cassandra or ScyllaDB when the dominant query is per-device lookup, ClickHouse when it is site-wide analytics. Devices, sites and users stay in PostgreSQL. The trade accepted: no ad hoc joins over the readings, and a second system to operate.

**Case 3: an e-commerce site adding product search** with typo tolerance, facets (brand, size, price band) and relevance ranking over two million products, next to its PostgreSQL order system. Checklist: orders need transactions and stay where they are; search needs an inverted index with analysers and faceting, may lag the catalogue by seconds and is not a system of record. Choice: PostgreSQL full-text search plus `pg_trgm` while the ranking requirements are simple; Elasticsearch or OpenSearch when facets, synonyms and relevance tuning outgrow it, fed from PostgreSQL through an outbox (item 5.6) so that a missed update is repaired by reindexing. The trade accepted: a second, eventually consistent store that must be rebuildable from the first.

## Pitfalls

- Choosing for scale you do not have. The costs of a distributed store (no joins, eventual consistency, operations) are paid from the first day; the benefits arrive at a volume most systems never reach.
- "Schemaless" as flexibility. The schema moves into the application code, every reader must handle every historical shape, and nothing stops a typo in a field name (item 8.6).
- Two systems of record. If both stores can be updated independently they will disagree; one store owns each fact and the others are derived and rebuildable.
- Picking by benchmark. Vendor benchmarks measure the workload the vendor chose, with the vendor's consistency settings; measure yours, with your data distribution.
- Confusing a cache with a database. Redis in front of PostgreSQL is a cache; Redis as the only copy of the data is a database with Redis's persistence trade-offs (item 9.2).
- Ignoring the exit. Before adopting a store, know how you would get the data out and into something else.

## Check yourself

1. A team proposes MongoDB for an order system "because orders are documents". Which checklist points would you walk through with them, and what finding would make the choice right?
2. Name three workloads for which people often add a second system, and the PostgreSQL feature that covers each at moderate scale.
3. What is the operational and consistency price of adding Elasticsearch beside PostgreSQL, and how do you keep the two in step?
4. In case 2, which measurement would justify leaving PostgreSQL for the readings, and what would you keep in PostgreSQL regardless?

## Go deeper

- [Designing Data-Intensive Applications, chapter 2](https://dataintensive.net/) · relational, document and graph models compared on their merits, with the history of why each exists.
- [Martin Fowler: NoSQL Distilled](https://martinfowler.com/books/nosql.html) · the short book on aggregate-oriented data models and polyglot persistence.
- [Things I Wished More Developers Knew About Databases](https://rakyll.medium.com/things-i-wished-more-developers-knew-about-databases-2d0178464f78) · the operational realities behind any choice.
- [Jepsen: Consistency Models](https://jepsen.io/consistency) · what "eventually consistent" and its stronger relatives actually promise, with analyses of real databases.
- [PostgreSQL: Full Text Search](https://www.postgresql.org/docs/current/textsearch.html) · how far the default goes before a search engine is needed.

---

Part of [Databases](../README.md) · items 9.1, 9.5
