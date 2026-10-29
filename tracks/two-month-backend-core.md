# Sixty-day backend core

> Sixty days, Day 1 to Day 60, at two and a half to three hours a day. The language-neutral material comes first (operating system and network basics, HTTP, databases, concurrency), then system design with the security, delivery and architecture essentials every backend engineer shares, and only then Java and Spring, which turn the earlier days into a working, tested order service.

**Hours:** about 165 (two and a half to three hours a day for 60 days)

## Items

### foundations
2.1, 2.2, 2.3, 3.3, 3.4, 4.1, 4.3, 7.3, 7.5

### web-and-http
1.1, 3.2, 3.4, 4.1, 4.2, 4.2.1, 4.2.2, 4.2.3, 4.3, 4.5, 4.6, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 8.1, 9.2, 9.3, 11.1

### databases
1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5

### memory-and-concurrency
2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.4, 5.5, 5.6

### system-design
1.1, 1.2, 1.4, 2.2, 2.5, 2.6, 2.7, 2.11, 3.1, 3.3, 3.4, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 6.1, 6.2, 6.3.1

### security
2.1, 2.3, 2.11, 3.1, 5.1, 5.2, 6.1, 6.2

### devops-and-delivery
3.2, 3.4, 5.1, 5.2, 6.2

### architecture-and-craft
2.3, 5.2, 5.3, 7.2

### java
1.3, 1.5, 1.6, 1.7, 1.8, 1.10, 2.2, 2.6, 8.1, 8.5

### spring
1.4, 2.2, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.10, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.4, 7.6, 8.3

### projects
2.2, 2.2.1, 2.2.2

## The shape of the sixty days

The order is deliberate: everything a backend engineer needs regardless of language comes first, and the framework comes last, when you can already explain what it does under the hood.

| Days | Part | What you can do at the end of it |
|---|---|---|
| 1 to 5 | Common ground: operating system, network and data-structure basics | Explain what a thread costs, what a socket is, and what "the index is a hash table" means |
| 6 to 12 | Web & HTTP | Design an HTTP API whose status codes, caching, cookies and CORS behave correctly |
| 13 to 22 | Databases | Read a query plan, choose an index, and reproduce every isolation anomaly in two `psql` sessions |
| 23 to 30 | Memory and concurrency | Reproduce a visibility bug, a deadlock and a pool starvation, and fix each |
| 31 to 38 | System design | Run a design interview end to end, with estimates, trade-offs and failure modes |
| 39 to 42 | Security, delivery and architecture essentials | Explain injection, CSRF, OAuth2 grants, JWT validation, container memory and expand-contract |
| 43 to 46 | Java | Write idiomatic Java 21 and read a thread dump |
| 47 to 59 | Spring, built into the order service | Ship a tested service with correct transactions, idempotency and an outbox |
| 60 | Consolidation | Re-explain the hardest items from memory and pass your own mock interview |

## How to work the plan

- 1.1 One day is two and a half to three hours: read the note for each item if there is one, then the first external link, then do the exercise or the lab named for that day. Tick an item only when you can explain it to a colleague without notes and have used it once.
- 1.2 Keep a mistakes log from Day 1. Every surprise goes in with the lesson; re-read it on every review day.
- 1.3 The labs are where understanding is formed. The database and concurrency labs are plain `psql` and plain Java, so they need nothing from the Spring days; the order service in Days 46 to 59 reuses them.
- 1.4 The project (Projects 2.2 and its two "done when" items) is not optional. Its milestones are spread over the Spring days so that each one uses what you learned that day.
- 1.5 Everything outside the track is deliberately deferred. When a task at work needs one of those items, read it then; otherwise it is the next box.
- 1.6 At two hours a day the same plan takes 80 days. If you must fit sixty days at two hours, drop Days 39 to 42 and the Java part (Days 43 to 45), and read Spring item 2.1 on Day 46 instead.

## Review and retention

- 2.1 Flashcards: `python3 tools/export_anki.py --track two-month-backend-core` writes `anki/two-month-backend-core.tsv`, one card per "Check yourself" question in the track's notes. Import it into Anki and review for ten minutes a day from Day 2. Say the answer out loud, then open the note to check; grade yourself honestly.
- 2.2 Review days (Day 12, 22, 30, 38, 42, 46, 59) end with thirty minutes of review: re-read the mistakes log, re-explain the three hardest items of the part from memory, untick anything you cannot re-explain.
- 2.3 Teach-back: once a week, explain one item to a colleague or write it up in your own words. The items that resist explanation go back on the list.
- 2.4 Day 60 is consolidation: redo the Anki cards you failed most, and run the mock design interview using your own order service as the case.

## Day by day

Item numbers refer to the domain README; the tracker shows only these items when the track is selected.

### Part 1: common ground (Days 1 to 30)

| Day | Items | Lab or exercise |
|---|---|---|
| 1 | Foundations 2.1, 2.2 | Run `top` while a CPU-bound and an I/O-bound program compete; explain the difference you see |
| 2 | Foundations 2.3, 4.1 | Compare RSS and virtual size of a running JVM; write the Big-O of three functions you wrote this month |
| 3 | Foundations 3.3, 3.4 | Watch a handshake with `tcpdump`; find a listening port and its accept queue with `ss -ltn` |
| 4 | Foundations 4.3, 7.5 | Break a `HashMap` with a bad `hashCode`; convert a DST-crossing interval between two zones |
| 5 | Foundations 7.3 | Set up the lab: Docker, PostgreSQL 16, Java 21, a `psql` client; start the mistakes log |
| 6 | Web & HTTP 1.1, 3.2 | Trace a page load in DevTools; inspect a TLS handshake with `openssl s_client` |
| 7 | Web & HTTP 3.4, 4.6 | Set connect and read timeouts against a server that sleeps; measure each phase with `curl --write-out` |
| 8 | Web & HTTP 4.1, 4.2, 4.2.1, 4.2.2, 4.2.3 | Write the status code and retry policy table for an order API |
| 9 | Web & HTTP 4.3, 4.5, 9.3 | Implement an `ETag` round trip with `curl`; write one Problem Details error response |
| 10 | Web & HTTP 5.1, 5.2, 5.3 | Decide `Cache-Control` for an asset, an API list and a user profile; justify each |
| 11 | Web & HTTP 6.1, 6.2, 6.3, 7.1, 7.2 | Make a preflighted CORS request fail, then fix the server headers |
| 12 | Web & HTTP 8.1, 9.2, 11.1 | Review day: design the resource model of the order API on paper |
| 13 | Databases 3.1, 3.2 | Create a composite index and show which `WHERE` clauses use it with `EXPLAIN` |
| 14 | Databases 3.3, 3.4 | Add a partial and a covering index; observe an index-only scan |
| 15 | Databases 1.6, 3.5, 3.6 | Make the planner ignore your index three ways; replace `OFFSET` with keyset pagination |
| 16 | Databases 4.1, 4.2 | Load one million orders; read `EXPLAIN (ANALYZE, BUFFERS)` for a nested loop and a hash join |
| 17 | Databases 4.3, 4.4 | Skew the statistics and watch the plan change; rewrite an N+1 loop as one set-based query |
| 18 | Databases 4.5, 4.6 | Enable `pg_stat_statements`; find and fix the top query by total time |
| 19 | Databases 5.1, 5.2, 5.3 | Reproduce the dirty, non-repeatable and phantom read definitions in two `psql` sessions |
| 20 | Databases 5.4, 6.1 | Reproduce write skew; see it fail under `SERIALIZABLE`; inspect `xmin` and `xmax` |
| 21 | Databases 6.2, 6.3, 6.4 | Reproduce a lost update and a deadlock; fix the lost update four ways |
| 22 | Databases 5.5, 5.6, 6.5, 6.6, 7.5 | Review day: build a queue table with `SKIP LOCKED`; size a HikariCP pool from first principles |
| 23 | Memory & Concurrency 2.1, 2.2, 2.3 | Run a program with `-Xlog:gc*` under G1 and ZGC; read the pauses |
| 24 | Memory & Concurrency 2.5, 3.1 | Write a leak with a static map; find it in a heap dump |
| 25 | Memory & Concurrency 3.2, 3.3, 3.4 | Reproduce a visibility bug with a plain boolean flag; fix it with `volatile` |
| 26 | Memory & Concurrency 4.1, 4.2, 4.3 | Reproduce a lost increment with 1,000 threads; fix with `synchronized`, then with a lock |
| 27 | Memory & Concurrency 4.4, 4.5 | Write a two-lock deadlock; find it in a thread dump; fix with lock ordering |
| 28 | Memory & Concurrency 4.6, 4.7, 4.8 | Replace the lock with `AtomicLong` and `LongAdder`; measure; hit the `compute` pitfall |
| 29 | Memory & Concurrency 5.1, 5.2 | Starve a fixed pool with blocking tasks; compose three `CompletableFuture`s with a timeout |
| 30 | Memory & Concurrency 5.4, 5.5, 5.6 | Review day: port the pool example to virtual threads and observe pinning |

### Part 2: system design and the shared essentials (Days 31 to 42)

| Day | Items | Lab or exercise |
|---|---|---|
| 31 | System Design 1.1, 1.2, 1.4 | Write SLOs and a back-of-the-envelope estimate for the order service |
| 32 | System Design 2.2, 2.5 | Design the cache for the order read path; name the stampede fix |
| 33 | System Design 2.6, 2.7 | Choose SQL or NoSQL and a queue for three described workloads; justify each |
| 34 | System Design 2.11, 3.1 | Implement a token bucket in 40 lines; list the failover anomalies of single-leader replication |
| 35 | System Design 3.3, 3.4 | Classify five systems you use by consistency model; apply PACELC to each |
| 36 | System Design 3.7, 3.8 | Draw the saga for "place order, reserve stock, charge card"; mark where exactly-once is impossible |
| 37 | System Design 4.1, 4.2, 4.3, 4.4 | Write the timeout, retry and circuit-breaker policy for every outbound call of the order service |
| 38 | System Design 5.1, 5.2, 6.1, 6.2, 6.3.1 | Review day: design the URL shortener in 45 minutes, out loud, with a timer |
| 39 | Security 2.1, 2.3, 2.11 | Find an IDOR and an injection in a small sample app; explain why `SameSite` alone is not enough |
| 40 | Security 3.1, 5.1, 5.2 | Hash a password with Argon2id and time it; draw the Authorization Code with PKCE flow |
| 41 | Security 6.1, 6.2; DevOps & Delivery 5.1, 5.2 | Decode a JWT and write its validation checklist; define RED metrics for the order API |
| 42 | DevOps & Delivery 3.2, 3.4, 6.2; Architecture & Craft 2.3, 7.2 | Review day: write a multi-stage Dockerfile with `MaxRAMPercentage`; plan an expand-contract column rename |

### Part 3: Java and Spring, built into the order service (Days 43 to 60)

| Day | Items | Lab, exercise or project milestone |
|---|---|---|
| 43 | Java 1.3, 1.5, 1.6 | Break `equals` and `hashCode` in a `HashSet`; model order states as a sealed type with a `switch` |
| 44 | Java 1.7, 1.8, 1.10 | Write a PECS-correct `copy` method; convert a checked-exception API to a result type |
| 45 | Java 2.2, 2.6 | Watch a `HashMap` resize and treeify; rewrite a nested loop as a stream and compare readability |
| 46 | Java 8.1, 8.5 | Review day: take a thread dump of the Day 27 deadlock; generate the order service skeleton (Spring Boot, PostgreSQL and Kafka in Docker Compose) |
| 47 | Spring 1.4, 2.2 | Break a `@Transactional` method with self-invocation; list which auto-configurations fired and why |
| 48 | Spring 4.1, 4.2 | Configure HikariCP with the Day 22 size; write the order queries with `JdbcClient` first |
| 49 | Spring 4.3, 4.4 | Reproduce the three `@Transactional` bugs; place the transaction boundaries of the order service |
| 50 | Spring 4.5, 5.1, 5.2 | Flyway migrations for orders, items and the idempotency table; entities with sequence identifiers |
| 51 | Spring 5.3, 5.4, 5.5 | Map the order-to-lines association; log SQL and remove every N+1; turn Open Session in View off |
| 52 | Spring 5.6, 5.7 | DTO projections for the order list; batch the inserts and verify with Hibernate statistics |
| 53 | Spring 5.8, 5.10 | Milestone 1 (Projects 2.2.1): reproduce the lost update under JPA, fix with `@Version` and a retry |
| 54 | Spring 6.1, 6.2, 6.3 | List every filter in the security chain; protect the order endpoints with method security |
| 55 | Spring 6.4, 6.5 | Milestone 2 (Projects 2.2.2): idempotency keys, proven with concurrent duplicate requests; JWT resource server |
| 56 | Spring 7.1, 7.2; Architecture & Craft 5.2, 5.3 | Write the controller and service tests; decide which collaborators to mock and why |
| 57 | Spring 7.4, 7.6 | Milestone 3: the transactional outbox and relay, tested with Testcontainers for PostgreSQL and Kafka |
| 58 | Spring 8.3 | Milestone 4: the idempotent consumer; probes and graceful shutdown; read Spring item 9.1 if Kafka is new |
| 59 | Projects 2.2 | Review day: Milestone 5, retries and the dead-letter topic; write the README with design, trade-offs and measurements |
| 60 | Consolidation | Redo the failed Anki cards; mock design interview using your own order service as the case |
