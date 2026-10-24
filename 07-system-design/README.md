# System Design

> Designing systems that stay correct and available under load: estimation, the building blocks (load balancers, caches, queues, databases, CDNs), distributed-systems fundamentals (replication, consistency, consensus, failure), resilience patterns, architecture styles, and the interview method. Anchored in Designing Data-Intensive Applications.

**Prerequisites:** [Web & HTTP](../02-web-and-http/README.md), [Databases](../04-databases/README.md), [Memory & Concurrency](../03-memory-and-concurrency/README.md)

**Done when you can:**

- Estimate QPS, storage and bandwidth for a feature on a whiteboard, and sanity-check the result against latency numbers you know by heart.
- Design a classic system (URL shortener, rate limiter, news feed, chat) in 45 minutes, state the trade-offs, and defend the choices under questioning.
- Explain CAP and PACELC without the usual mistakes, and name the consistency model a given database actually provides.
- Make a service survive partial failure with timeouts, retries with jitter, circuit breakers, idempotency and backpressure.
- Explain why exactly-once delivery is impossible and how the transactional outbox plus idempotent consumers achieve the same effect.
- Choose between a modular monolith and microservices for a real team, and list what it takes to operate each.

## Roadmap

### 1. Thinking in systems

- [ ] 1.1 Requirements: functional vs non-functional; availability targets (SLAs, SLOs, "the nines"), latency percentiles, consistency needs · [notes](notes/requirements-slos-and-the-nines.md) · [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/)
- [ ] 1.2 Back-of-the-envelope estimation: QPS, storage, bandwidth; the latency numbers to memorise; powers of two · [notes](notes/back-of-the-envelope-estimation.md) · [Latency Numbers Every Programmer Should Know](https://gist.github.com/jboner/2841832) · [Interactive latency numbers by year](https://colin-scott.github.io/personal_website/research/interactive_latency.html) · [System Design Primer](https://github.com/donnemartin/system-design-primer)
- [ ] 1.3 Scaling vocabulary: vertical vs horizontal, stateless vs stateful services, shared-nothing, the scale cube · [The Twelve-Factor App: Processes](https://12factor.net/processes)
- [ ] 1.4 Performance vs scalability vs availability vs reliability; tail latency and why p99 matters more than the mean · [notes](notes/latency-percentiles-and-tail-latency.md) · [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/) · [Gil Tene: How NOT to Measure Latency](https://www.youtube.com/watch?v=lJ8ydIuPFeU)
- [ ] 1.5 The fallacies of distributed computing and the failure modes behind each · [Fallacies of distributed computing](https://en.wikipedia.org/wiki/Fallacies_of_distributed_computing)

### 2. Building blocks

- [ ] 2.1 DNS, anycast and GeoDNS for global traffic steering · [Cloudflare: What is Anycast?](https://www.cloudflare.com/learning/cdn/glossary/anycast-network/)
- [ ] 2.2 Load balancers and reverse proxies: L4 vs L7, algorithms, health checks, connection draining, sticky sessions · [Cloudflare: What is load balancing?](https://www.cloudflare.com/learning/performance/what-is-load-balancing/) · [System Design Primer: Load balancer](https://github.com/donnemartin/system-design-primer#load-balancer)
- [ ] 2.3 API gateways and backends-for-frontends: authentication, rate limiting, routing, aggregation; what does not belong there · [microservices.io: API Gateway](https://microservices.io/patterns/apigateway.html)
- [ ] 2.4 CDNs and edge caching: push vs pull, cache keys, invalidation, edge compute · [web.dev: Content delivery networks](https://web.dev/articles/content-delivery-networks) · [Cloudflare: What is a CDN?](https://www.cloudflare.com/learning/cdn/what-is-a-cdn/)
- [ ] 2.5 Caching: cache-aside, read-through, write-through, write-behind; TTLs and eviction; hot keys; stampedes; keeping cache and database consistent · [notes](notes/caching-strategies.md) · [Cache stampede](https://en.wikipedia.org/wiki/Cache_stampede) · [Scaling Memcache at Facebook](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf)
- [ ] 2.6 Databases in a system: SQL vs NoSQL choice, read replicas, sharding, consistent hashing · [notes](notes/consistent-hashing.md) · [Tom White: Consistent Hashing](https://tom-e-white.com/2007/11/consistent-hashing.html) · [Designing Data-Intensive Applications, ch. 6](https://dataintensive.net/)
- [ ] 2.7 Message queues and event logs: Kafka vs RabbitMQ vs SQS; partitions, consumer groups, ordering, delivery semantics, dead-letter queues · [notes](notes/message-queues-vs-event-logs.md) · [Apache Kafka: Introduction](https://kafka.apache.org/intro) · [RabbitMQ: Reliability Guide](https://www.rabbitmq.com/docs/reliability)
- [ ] 2.8 Task queues, schedulers and workflow engines: delayed and priority jobs, cron at scale, durable execution · [Temporal documentation](https://docs.temporal.io/)
- [ ] 2.9 Search and indexing: inverted indexes, relevance, Elasticsearch/OpenSearch, autocomplete with tries · [Elasticsearch from the Bottom Up](https://www.elastic.co/blog/found-elasticsearch-from-the-bottom-up)
- [ ] 2.10 Object storage and file delivery: presigned URLs, multipart uploads, lifecycle policies · [Amazon S3: Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [ ] 2.11 Rate limiting: token bucket, leaky bucket, fixed and sliding windows; distributed limiters; 429 and `Retry-After` · [notes](notes/rate-limiting-algorithms.md) · [Stripe: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters) · [Cloudflare: Counting things, a lot of different things](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/)
- [ ] 2.12 Unique ID generation: UUID v4 vs v7, Snowflake IDs, database sequences; effects on indexes and ordering · [notes](notes/unique-id-generation.md) · [RFC 9562: UUIDs](https://www.rfc-editor.org/rfc/rfc9562.html) · [Twitter Snowflake](https://github.com/twitter-archive/snowflake)

### 3. Distributed systems fundamentals

- [ ] 3.1 Replication: single-leader, multi-leader, leaderless; synchronous vs asynchronous; failover and its anomalies · [notes](notes/replication-and-consensus-raft.md) · [Designing Data-Intensive Applications, ch. 5](https://dataintensive.net/) · [Kleppmann: Distributed Systems lectures](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB)
- [ ] 3.2 Partitioning: key-range vs hash, hot spots, secondary indexes, rebalancing, request routing · [notes](notes/partitioning-and-sharding-strategies.md) · [Designing Data-Intensive Applications, ch. 6](https://dataintensive.net/)
- [ ] 3.3 Consistency models: linearizability, sequential, causal, eventual; read-your-writes and monotonic reads · [notes](notes/consistency-models-cap-and-pacelc.md) · [Jepsen: Consistency Models](https://jepsen.io/consistency) · [Kleppmann: Please stop calling databases CP or AP](https://martin.kleppmann.com/2015/05/11/please-stop-calling-databases-cp-or-ap.html)
- [ ] 3.4 CAP and PACELC done right: what partition tolerance means, and the latency/consistency trade-off during normal operation · [notes](notes/consistency-models-cap-and-pacelc.md) · [PACELC design principle](https://en.wikipedia.org/wiki/PACELC_design_principle)
- [ ] 3.5 Time and ordering: unreliable clocks, NTP, Lamport and vector clocks, hybrid logical clocks · [notes](notes/clocks-ordering-and-lamport-timestamps.md) · [Lamport: Time, Clocks, and the Ordering of Events](https://lamport.azurewebsites.net/pubs/time-clocks.pdf) · [Designing Data-Intensive Applications, ch. 8](https://dataintensive.net/)
- [ ] 3.6 Consensus: why you need it, Paxos vs Raft, leader election, quorums, ZooKeeper and etcd, the cost of consensus · [notes](notes/replication-and-consensus-raft.md) · [Raft](https://raft.github.io/) · [The Secret Lives of Data: Raft visualised](https://thesecretlivesofdata.com/raft/) · [Designing Data-Intensive Applications, ch. 9](https://dataintensive.net/)
- [ ] 3.7 Distributed transactions: two-phase commit and its failure modes; sagas (choreography vs orchestration) and compensations · [notes](notes/transactional-outbox-and-sagas.md) · [microservices.io: Saga](https://microservices.io/patterns/data/saga.html) · [Pat Helland: Life Beyond Distributed Transactions](https://queue.acm.org/detail.cfm?id=3025012)
- [ ] 3.8 Delivery semantics: at-most-once, at-least-once, "exactly-once"; idempotent consumers; the transactional outbox and change data capture · [notes](notes/idempotency-retries-and-exactly-once.md) · [You Cannot Have Exactly-Once Delivery](https://bravenewgeek.com/you-cannot-have-exactly-once-delivery/) · [microservices.io: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) · [Debezium: Reliable data exchange with the outbox pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)
- [ ] 3.9 Distributed locks and leases: why they are hard, fencing tokens, the Redlock debate · [notes](notes/distributed-locks-and-fencing-tokens.md) · [Kleppmann: How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html)
- [ ] 3.10 Patterns of distributed systems: write-ahead log, replicated log, versioned values, heartbeats, leases, generation clocks, gossip · [Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/)

### 4. Resilience and operability

- [ ] 4.1 Timeouts, retries with exponential backoff and jitter, retry budgets, and how retry storms take systems down · [notes](notes/idempotency-retries-and-exactly-once.md) · [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
- [ ] 4.2 Circuit breakers, bulkheads, load shedding, graceful degradation; why fallbacks are dangerous · [notes](notes/resilience-patterns.md) · [Release It!](https://pragprog.com/titles/mnee2/release-it-second-edition/) · [AWS Builders' Library: Avoiding fallback in distributed systems](https://aws.amazon.com/builders-library/avoiding-fallback-in-distributed-systems/)
- [ ] 4.3 Backpressure and queues: bounded queues, admission control, Little's law, shedding load at the edge · [notes](notes/resilience-patterns.md) · [AWS Builders' Library: Using load shedding to avoid overload](https://aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/)
- [ ] 4.4 Idempotency keys for APIs and payments; deduplication windows; designing retry-safe operations · [notes](notes/idempotency-retries-and-exactly-once.md) · [Stripe: Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) · [Brandur: Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys)
- [ ] 4.5 Observability as a design input: structured logs, RED/USE metrics, traces, correlation IDs, SLO-based alerting · [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [ ] 4.6 Change as the main cause of incidents: canaries, feature flags, fast rollback, cell-based architecture · [AWS Builders' Library: Automating safe, hands-off deployments](https://aws.amazon.com/builders-library/automating-safe-hands-off-deployments/)
- [ ] 4.7 Chaos engineering and game days · [Principles of Chaos Engineering](https://principlesofchaos.org/)

### 5. Architecture styles

- [ ] 5.1 Monolith, modular monolith, microservices, serverless: costs, benefits, and the team each assumes · [notes](notes/monolith-vs-microservices.md) · [Fowler: MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html) · [Fowler: Microservice Premium](https://martinfowler.com/bliki/MicroservicePremium.html) · [Fowler & Lewis: Microservices](https://martinfowler.com/articles/microservices.html)
- [ ] 5.2 Service boundaries: bounded contexts, data ownership, the distributed monolith, the shared database trap · [notes](notes/monolith-vs-microservices.md) · [microservices.io: Decompose by subdomain](https://microservices.io/patterns/decomposition/decompose-by-subdomain.html)
- [ ] 5.3 Synchronous vs asynchronous communication; event-driven architecture; choreography vs orchestration · [notes](notes/event-driven-architecture-choreography-vs-orchestration.md) · [Fowler: What do you mean by "Event-Driven"?](https://martinfowler.com/articles/201701-event-driven.html)
- [ ] 5.4 CQRS and event sourcing: what they buy, what they cost, and when not to use them · [notes](notes/cqrs-and-event-sourcing-honestly.md) · [Fowler: CQRS](https://martinfowler.com/bliki/CQRS.html) · [Fowler: Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
- [ ] 5.5 Migration strategies: strangler fig, branch by abstraction, parallel run · [Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) · [Sam Newman: Monolith to Microservices](https://samnewman.io/books/monolith-to-microservices/)
- [ ] 5.6 Data-intensive architectures: batch vs stream processing, lambda and kappa, lakes and warehouses at a glance · [Designing Data-Intensive Applications, ch. 10-11](https://dataintensive.net/)
- [ ] 5.7 Multi-tenancy, multi-region and disaster recovery: RTO/RPO, active-active vs active-passive · [notes](notes/multi-region-and-disaster-recovery.md) · [AWS: Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html)

### 6. The design interview method

- [ ] 6.1 A repeatable framework: clarify requirements, estimate, high-level design, deep dives, trade-offs and failure modes · [notes](notes/system-design-interview-framework.md) · [Hello Interview: System Design in a Hurry](https://www.hellointerview.com/learn/system-design/in-a-hurry/introduction) · [System Design Primer: How to approach a system design interview question](https://github.com/donnemartin/system-design-primer#how-to-approach-a-system-design-interview-question)
- [ ] 6.2 Communicating a design: draw clearly, name trade-offs out loud, drive the conversation, handle pushback · [notes](notes/system-design-interview-framework.md) · [Hello Interview: Delivery](https://www.hellointerview.com/learn/system-design/in-a-hurry/delivery)
- [ ] 6.3 Classic problems to practise, in order of difficulty · [ByteByteGo](https://bytebytego.com/) · [ByteByteGo: System Design 101](https://github.com/ByteByteGoHq/system-design-101)
  - [ ] 6.3.1 URL shortener, pastebin, unique ID generator, key-value store · [notes](notes/case-study-url-shortener.md)
  - [ ] 6.3.2 Rate limiter, notification system, news feed, chat and messaging · [notes](notes/case-study-rate-limiter.md) · [notes](notes/case-study-news-feed.md)
  - [ ] 6.3.3 Search autocomplete, video streaming (YouTube/Netflix), file sync (Google Drive/Dropbox), proximity service (Uber/Yelp)
  - [ ] 6.3.4 Payment system, ticket booking and flash sales, ad click aggregation, distributed message queue, metrics monitoring, web crawler, email
- [ ] 6.4 Studying real architectures: engineering blogs and public postmortems · [High Scalability](https://highscalability.com/) · [Netflix Tech Blog](https://netflixtechblog.com/) · [Uber Engineering](https://www.uber.com/blog/engineering/) · [Cloudflare Blog](https://blog.cloudflare.com/)

## Resources

### Start here

- [Designing Data-Intensive Applications](https://dataintensive.net/) · Martin Kleppmann. The book this domain is built on; read it twice (paid).
- [ByteByteGo](https://bytebytego.com/) and the free [System Design 101](https://github.com/ByteByteGoHq/system-design-101) repository · Alex Xu's visual explanations; the YouTube channel covers most interview topics.
- [Hello Interview: System Design](https://www.hellointerview.com/learn/system-design/in-a-hurry/introduction) · free, current, and written by people who run these interviews.
- [System Design Primer](https://github.com/donnemartin/system-design-primer) · the classic open-source study guide with worked solutions.
- [AWS Builders' Library](https://aws.amazon.com/builders-library/) · how Amazon actually builds resilient systems; every article is worth reading.

### Books

- [System Design Interview, volumes 1 and 2](https://bytebytego.com/) · Alex Xu (paid); the worked case studies for section 6.
- [Release It!, 2nd edition](https://pragprog.com/titles/mnee2/release-it-second-edition/) · Michael Nygard; stability patterns from production incidents (paid).
- [Site Reliability Engineering](https://sre.google/books/) · Google; free online. SLOs, monitoring, incident response.
- [Understanding Distributed Systems](https://understandingdistributed.systems/) · Roberto Vitillo; a compact, practical introduction (paid).
- [Building Microservices, 2nd edition](https://samnewman.io/books/building_microservices_2nd_edition/) · Sam Newman (paid).
- [Database Internals](https://www.databass.dev/) · Alex Petrov; part two covers distributed systems (paid).

### Courses and videos

- [Martin Kleppmann: Distributed Systems lecture series](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB) · Cambridge undergraduate course; free, rigorous and clear. [Lecture notes (PDF)](https://www.cl.cam.ac.uk/teaching/2122/ConcDisSys/dist-sys-notes.pdf).
- [MIT 6.824 / 6.5840: Distributed Systems](https://pdos.csail.mit.edu/6.824/) · Robert Morris's lectures and labs (Raft in Go).
- [ByteByteGo on YouTube](https://www.youtube.com/@ByteByteGo) · short visual explainers.
- [Jordan has no life](https://www.youtube.com/@jordanhasnolife5163) · deep, opinionated system design walkthroughs.
- [Gaurav Sen](https://www.youtube.com/@gkcs) · classic system design interview videos.

### References

- [microservices.io](https://microservices.io/patterns/index.html) · Chris Richardson's pattern catalogue.
- [Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/) · Unmesh Joshi; the building blocks of consensus and replication, explained with code.
- [Jepsen analyses](https://jepsen.io/analyses) · what databases actually guarantee under failure.
- [Marc Brooker's blog](https://brooker.co.za/blog/) and [Dan Luu](https://danluu.com/) · thoughtful writing on distributed systems and performance.
- [Awesome Scalability](https://github.com/binhnguyennus/awesome-scalability) · a large curated reading list.
- [roadmap.sh: System Design](https://roadmap.sh/system-design) · visual overview.
