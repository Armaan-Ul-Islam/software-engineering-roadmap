# Projects

> Build-to-learn capstones that force the roadmap's ideas into your hands. Each project names the concepts it exercises, a definition of done, and stretch goals. Finish three and you will out-perform most candidates; finish them all and you will be hard to beat.

**Prerequisites:** [Spring](../06-spring/README.md), [DevOps & Delivery](../10-devops-and-delivery/README.md)

**Done when you can:**

- Show a repository per project with a README that states the problem, the design, the trade-offs, and how to run it in one command.
- Demonstrate each project under load or during failure, not only on the happy path.
- Explain every dependency you pulled in and why a simpler option was rejected.
- Point to the measurements (latency, throughput, memory) that justified each design decision.

## Roadmap

### 1. Internals: small, deep, from scratch

- [ ] 1.1 An HTTP/1.1 server from raw sockets in Java: request parsing, keep-alive, a thread pool, static files; tested with `curl` and a load generator · [Beej's Guide to Network Programming](https://beej.us/guide/bgnet/) · [RFC 9112: HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html)
  - [ ] 1.1.1 Done when: passes a conformance smoke test with `curl -v`, serves 10k requests over 100 keep-alive connections without leaking threads or sockets
  - [ ] 1.1.2 Stretch: chunked transfer encoding, gzip, HTTP/1.1 pipelining, a virtual-thread variant compared under load
- [ ] 1.2 A thread pool with a bounded blocking queue, rejection policies and graceful shutdown; compared against `ThreadPoolExecutor` with JMH · [Java Concurrency in Practice](https://jcip.net/) · [JMH](https://github.com/openjdk/jmh)
  - [ ] 1.2.1 Done when: a stress test with latches proves no lost or duplicated tasks, and shutdown drains or rejects deterministically
- [ ] 1.3 A key-value store with a write-ahead log and crash recovery, then an in-memory index, then log compaction · [Database Internals](https://www.databass.dev/) · [Build your own X](https://github.com/codecrafters-io/build-your-own-x)
  - [ ] 1.3.1 Done when: `kill -9` during writes never loses an acknowledged write, and recovery time is measured
  - [ ] 1.3.2 Stretch: an LSM-tree with SSTables and bloom filters; a B-tree variant; compare read and write amplification
- [ ] 1.4 An LRU cache with TTL: single-threaded first, then thread-safe, then benchmarked against Caffeine · [Caffeine](https://github.com/ben-manes/caffeine)
- [ ] 1.5 A rate-limiter library: token bucket and sliding window, in-process and Redis-backed, with a Spring Boot filter · [Stripe: Scaling your API with rate limiters](https://stripe.com/blog/rate-limiters)
- [ ] 1.6 A toy SQL engine: parser, planner with `EXPLAIN`, nested-loop and hash joins over your key-value store · [CMU 15-445](https://15445.courses.cs.cmu.edu/)

### 2. Backend services: Spring Boot and PostgreSQL

- [ ] 2.1 URL shortener: Spring Boot, PostgreSQL, Redis cache, ID generation, 301 vs 302, click analytics; load-tested, then a read replica added · [System Design Primer: Pastebin design](https://github.com/donnemartin/system-design-primer/blob/master/solutions/system_design/pastebin/README.md)
  - [ ] 2.1.1 Done when: p99 redirect latency under 10 ms at 1,000 requests per second on a laptop, with cache hit ratio and database load graphed
- [ ] 2.2 Order management with real transactions: optimistic locking, idempotency keys, a transactional outbox to Kafka, a consumer with retries and a dead-letter topic · [notes](notes/order-management-with-outbox-spec.md) · [Brandur: Idempotency keys](https://brandur.org/idempotency-keys) · [Debezium: Outbox pattern](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/)
  - [ ] 2.2.1 Done when: a test reproduces a lost update under Read Committed and the fix (optimistic lock or `SELECT ... FOR UPDATE`) is proven by the same test
  - [ ] 2.2.2 Done when: duplicate requests with the same idempotency key return the original result, including under concurrency
- [ ] 2.3 An authentication service: session login and an OAuth2 resource server with Spring Security, Argon2 password storage, TOTP, rate limiting, audit log · [Spring Security Reference](https://docs.spring.io/spring-security/reference/) · [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
  - [ ] 2.3.1 Done when: every filter in the security chain is listed and explained in the README, and the OWASP ASVS level 1 authentication checks pass
- [ ] 2.4 Event-driven inventory with Kafka: partitions and ordering, exactly-once effects through an idempotent consumer, replay from offset, Micrometer dashboards · [Spring for Apache Kafka](https://docs.spring.io/spring-kafka/reference/)
- [ ] 2.5 A file service: presigned uploads to S3 or Blob Storage, a worker queue for thumbnails, lifecycle rules, resumable multipart uploads · [Amazon S3: Presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [ ] 2.6 A reporting API over 10 million rows: window functions, keyset pagination, `EXPLAIN`-driven indexing, partitioning · [Use The Index, Luke](https://use-the-index-luke.com/)
  - [ ] 2.6.1 Done when: every endpoint has a documented plan, and the slowest query improved by at least 10x from the first version, with before and after plans in the README

### 3. Frontend and full stack

- [ ] 3.1 A React + Vite dashboard for the order service: TanStack Query, forms, authentication through a BFF, Problem Details error handling, an OpenAPI-generated client · [react.dev](https://react.dev/learn) · [TanStack Query](https://tanstack.com/query/latest)
- [ ] 3.2 A Node.js (Fastify + TypeScript) microservice the Spring system calls; compare behaviour under load with a Java equivalent and write up the differences · [Fastify](https://fastify.dev/)
- [ ] 3.3 Live order updates with Server-Sent Events, then WebSockets; measure how many connections one instance holds and what breaks first · [MDN: Server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)

### 4. Operations and cloud

- [ ] 4.1 Containerise and compose: a multi-stage Dockerfile, JVM tuned to the container limits, Compose with PostgreSQL, Redis and Kafka, health checks · [Spring Boot: Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html)
- [ ] 4.2 CI/CD: a GitHub Actions pipeline with unit and Testcontainers tests, image scan, SBOM, image push, and deployment to a staging environment · [GitHub Actions documentation](https://docs.github.com/en/actions)
- [ ] 4.3 Kubernetes deployment: manifests or a Helm chart, probes, requests and limits, HPA, a rolling update that includes an expand-contract database migration, a PodDisruptionBudget · [Kubernetes documentation](https://kubernetes.io/docs/home/)
- [ ] 4.4 An observability stack: OpenTelemetry, Prometheus, Grafana, Tempo or Jaeger, Loki; SLOs with burn-rate alerts; one game day · [Grafana tutorials](https://grafana.com/tutorials/)
- [ ] 4.5 Deploy twice with Terraform: Azure (Container Apps and Azure Database for PostgreSQL) and AWS (ECS Fargate and RDS); price both; tear both down · [notes](notes/deploy-twice-and-price-it-spec.md) · [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials)
  - [ ] 4.5.1 Done when: the README has a cost table for both clouds at two traffic levels, and the measured RSS of the JVM matches the container memory you requested
- [ ] 4.6 Failure drills: kill the database, exhaust the connection pool, inject latency into Kafka; fix with timeouts, retries, circuit breakers and load shedding · [Principles of Chaos Engineering](https://principlesofchaos.org/)

### 5. AI-assisted features

- [ ] 5.1 Documentation Q&A over your own repositories with RAG: pgvector, hybrid search, an evaluation set run in CI · [Spring AI Reference](https://docs.spring.io/spring-ai/reference/)
- [ ] 5.2 An agent with tools over the order service (read-only tools, confirmation for writes) exposed through MCP; red-team it for prompt injection and write up the findings · [Model Context Protocol](https://modelcontextprotocol.io/)

### 6. Portfolio and write-ups

- [ ] 6.1 For every project: a README with the design, trade-offs, benchmarks, and a short ADR log · [ADR GitHub organisation](https://adr.github.io/)
- [ ] 6.2 One blog post or internal talk explaining a bug you found and fixed in one of the projects, in depth · [Google: Technical Writing Courses](https://developers.google.com/tech-writing)
- [ ] 6.3 One contribution (fix or documentation) to an open-source library you depend on · [Good First Issue](https://goodfirstissue.dev/)

## Resources

- [Build your own X](https://github.com/codecrafters-io/build-your-own-x) · tutorials for building databases, HTTP servers, shells, interpreters and more from scratch.
- [CodeCrafters](https://codecrafters.io/) · guided "build your own Redis/HTTP server/SQLite" challenges with tests (paid).
- [Project-based learning](https://github.com/practical-tutorials/project-based-learning) · a large list of tutorials organised by language.
- [roadmap.sh: Backend projects](https://roadmap.sh/backend/projects) · project ideas graded by difficulty.
- [RealWorld](https://github.com/gothinkster/realworld) · the same Medium clone implemented in dozens of stacks; useful for comparing frameworks.
- [Spring PetClinic](https://github.com/spring-projects/spring-petclinic) · a reference Spring Boot application to study before building your own.
