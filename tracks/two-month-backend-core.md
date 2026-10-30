# Sixty-day backend core

> Sixty days, Day 1 to Day 60, at two and a half to three hours a day, through all thirteen core domains in the order the map shows them: the language-neutral ground first (operating system and network basics, HTTP, memory and concurrency, databases), then system design, cloud, delivery, architecture and security, then interview practice, and only then Java, Spring and the frontend, which turn the earlier days into a working, tested order service.

**Hours:** about 165 (two and a half to three hours a day for 60 days)

## Items

### foundations
2.1, 2.2, 2.3, 2.5, 3.3, 3.4, 4.1, 4.3, 5.3, 7.3, 7.5

### web-and-http
1.1, 3.2, 3.4, 4.1, 4.2, 4.2.1, 4.2.2, 4.2.3, 4.5, 4.6, 5.1, 5.2, 5.3, 6.1, 6.2, 7.1, 7.2, 9.2, 9.3, 11.1

### memory-and-concurrency
2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 5.1, 5.2, 5.5

### databases
1.6, 2.1, 2.2, 3.1, 3.2, 3.3, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4, 6.5, 7.5

### system-design
1.1, 1.2, 1.4, 2.2, 2.5, 2.6, 2.7, 2.11, 3.1, 3.3, 3.4, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 6.1, 6.2, 6.3.1

### cloud
1.1, 2.1, 2.2, 3.1, 3.3, 4.2, 5.2, 6.2, 8.4

### devops-and-delivery
1.1, 2.1, 2.3, 3.1, 3.2, 3.4, 5.1, 5.2, 6.1, 6.2

### architecture-and-craft
1.1, 1.2, 2.1, 2.3, 5.2, 5.3, 6.2, 7.2, 9.2

### security
1.1, 2.1, 2.3, 2.10, 2.11, 3.1, 5.1, 5.2, 5.3, 6.1, 6.2, 9.1

### dsa-and-interview-prep
1.1, 2.1, 2.2, 2.3, 2.5, 3.2, 4.1, 6.1, 7.1

### java
1.3, 1.5, 1.6, 1.7, 1.8, 1.10, 2.6, 8.1, 8.5

### spring
1.4, 2.2, 3.1, 4.1, 4.3, 4.4, 4.5, 5.1, 5.2, 5.4, 5.5, 5.8, 6.1, 6.3, 6.5, 7.1, 7.4, 8.3

### javascript-and-frontend
1.6, 1.7, 3.1, 4.4, 8.2, 8.3

## The shape of the sixty days

Every core domain gets its own block of days, in the order of the map. The order is a reading order, not a chain of prerequisites: no block assumes another, so if a task at work needs Spring in week two, jump there and come back. Two to three items a day plus one lab keeps the plan honest at two and a half to three hours. The two optional domains (AI Engineering, Projects) stay outside the sixty days; the order service that the Spring block builds is the one described in the Projects domain, used here as a lab rather than as a tracked item.

| Days | Block | What you can do at the end of it |
|---|---|---|
| 1 to 4 | Foundations | Explain what a thread costs, what a socket is, what `fsync` promises, and why a bad `hashCode` ruins a `HashMap` |
| 5 to 10 | Web & HTTP | Design an HTTP API whose status codes, caching, cookies and CORS behave correctly |
| 11 to 16 | Memory & Concurrency | Reproduce a visibility bug, a lost update, a deadlock and a pool starvation, and fix each |
| 17 to 25 | Databases | Read a query plan, choose an index, and reproduce every isolation anomaly in two `psql` sessions |
| 26 to 32 | System Design | Run a design interview end to end, with estimates, trade-offs and failure modes |
| 33 to 35 | Cloud | Size and price a Spring Boot plus PostgreSQL deployment and explain who is responsible for what |
| 36 to 38 | DevOps & Delivery | Ship through a pipeline into a right-sized container and change a schema without downtime |
| 39 to 41 | Architecture & Craft | Name why a class is hard to change, write a test that survives refactoring, and record a decision |
| 42 to 45 | Security | Find an IDOR, an injection and a CSRF hole; explain OAuth2 grants and validate a JWT by hand |
| 46 to 48 | DSA & Interviews | Work a problem out loud with the protocol, and start a daily practice habit that lasts past Day 60 |
| 49 to 51 | Java | Write idiomatic Java 21, model a domain with sealed types, and read a thread dump |
| 52 to 57 | Spring | Ship a tested order service with correct transactions, locking, idempotency and security |
| 58 to 59 | JavaScript & Frontend | Explain the event loop, call the order service from a browser, and get CORS and authentication right |
| 60 | Consolidation | Re-explain the hardest items from memory and pass your own mock interview |

## How to work the plan

- 1.1 One day is two and a half to three hours: read the note for each item if there is one, then the first external link, then do the lab named for that day. Tick an item only when you can explain it to a colleague without notes and have used it once.
- 1.2 Keep a mistakes log from Day 1. Every surprise goes in with the lesson; re-read it on every review day.
- 1.3 The labs are where understanding is formed. The database and concurrency labs are plain `psql` and plain Java; the Spring block reuses them inside the order service.
- 1.4 Blocks are independent. If work needs a block early, do it early; the only days that assume earlier days are the Spring block (it reuses the database and concurrency labs) and Day 60.
- 1.5 From Day 49, keep DSA running alongside the main block: one problem from your chosen list, twenty minutes, before the day's items. That is the "run the domains together" part of the plan, and it is what makes the practice habit survive Day 60.
- 1.6 Everything outside the track is deliberately deferred. When a task at work needs one of those items, read it then; otherwise it is the next box.
- 1.7 At two hours a day the same plan takes about 80 days. If you must fit sixty days at two hours, drop the Cloud block (Days 33 to 35) and the JavaScript block (Days 58 to 59), and read the Cloud items 1.1 and 4.5 on Day 37 instead.

## Review and retention

- 2.1 Flashcards: `python3 tools/export_anki.py --track two-month-backend-core` writes `anki/two-month-backend-core.tsv`, one card per "Check yourself" question in the track's notes. Import it into Anki and review for ten minutes a day from Day 2. Say the answer out loud, then open the note to check; grade yourself honestly.
- 2.2 Review days (the last day of every block) end with thirty minutes of review: re-read the mistakes log, re-explain the three hardest items of the block from memory, untick anything you cannot re-explain.
- 2.3 Teach-back: once a week, explain one item to a colleague or write it up in your own words. The items that resist explanation go back on the list.
- 2.4 Day 60 is consolidation: redo the Anki cards you failed most, and run the mock design interview using your own order service as the case.

## Day by day

Item numbers refer to the domain README; the tracker shows only these items when the track is selected, with a Day badge on each.

### Days 1 to 4: Foundations

| Day | Items | Lab or exercise |
|---|---|---|
| 1 | Foundations 2.1, 2.2, 7.3 | Run `top` while a CPU-bound and an I/O-bound program compete; explain the difference you see. Start the mistakes log |
| 2 | Foundations 2.3, 2.5 | Compare RSS and virtual size of a running JVM; write 100 MB with and without `fsync` and time both |
| 3 | Foundations 3.3, 3.4, 5.3 | Watch a handshake with `tcpdump`; find a listening port and its accept queue with `ss -ltn`; extract the top ten IPs from an access log with `awk`, `sort` and `uniq` |
| 4 | Foundations 4.1, 4.3, 7.5 | Review day: break a `HashMap` with a bad `hashCode`; convert a DST-crossing interval between two zones; set up the lab (Docker, PostgreSQL 16, Java 21, `psql`) |

### Days 5 to 10: Web & HTTP

| Day | Items | Lab or exercise |
|---|---|---|
| 5 | Web & HTTP 1.1, 3.2 | Trace a page load in DevTools; inspect a TLS handshake with `openssl s_client` |
| 6 | Web & HTTP 3.4, 4.6, 11.1 | Set connect and read timeouts against a server that sleeps; measure each phase with `curl --write-out`; find where a Tomcat request thread blocks |
| 7 | Web & HTTP 4.1, 4.2, 4.2.1, 4.2.2, 4.2.3 | Write the status code and retry policy table for an order API |
| 8 | Web & HTTP 4.5, 9.2, 9.3 | Implement an `ETag` round trip with `curl`; design the order API's resources on paper; write one Problem Details error response |
| 9 | Web & HTTP 5.1, 5.2, 5.3 | Decide `Cache-Control` for an asset, an API list and a user profile; justify each |
| 10 | Web & HTTP 6.1, 6.2, 7.1, 7.2 | Review day: make a preflighted CORS request fail, then fix the server headers; decide cookie session or bearer token for the order API and write down why |

### Days 11 to 16: Memory & Concurrency

| Day | Items | Lab or exercise |
|---|---|---|
| 11 | Memory & Concurrency 2.1, 2.2, 2.3 | Run a program with `-Xlog:gc*` under G1 and ZGC; read the pauses |
| 12 | Memory & Concurrency 2.5, 3.1 | Write a leak with a static map; find it in a heap dump; explain why the CPU can reorder your stores |
| 13 | Memory & Concurrency 3.2, 3.3, 3.4 | Reproduce a visibility bug with a plain boolean flag; fix it with `volatile`; publish an object unsafely and then safely |
| 14 | Memory & Concurrency 4.1, 4.2, 4.3 | Measure what 10,000 platform threads cost; reproduce a lost increment with 1,000 threads; fix with `synchronized`, then with a lock |
| 15 | Memory & Concurrency 4.5, 4.6, 4.7 | Write a two-lock deadlock; find it in a thread dump; fix with lock ordering; replace the lock with `AtomicLong` and `LongAdder` and hit the `compute` pitfall |
| 16 | Memory & Concurrency 5.1, 5.2, 5.5 | Review day: starve a fixed pool with blocking tasks; compose three `CompletableFuture`s with a timeout; port the pool example to virtual threads and observe pinning |

### Days 17 to 25: Databases

| Day | Items | Lab or exercise |
|---|---|---|
| 17 | Databases 2.1, 2.2, 3.1 | Watch the buffer pool with `pg_buffercache`; kill PostgreSQL mid-write and watch WAL recovery; walk a B-tree lookup with `EXPLAIN` |
| 18 | Databases 3.2, 3.3 | Create a composite index and show which `WHERE` clauses use it; add a partial and a covering index; observe an index-only scan |
| 19 | Databases 1.6, 3.5, 3.6 | Make the planner ignore your index three ways; replace `OFFSET` with keyset pagination; build an index `CONCURRENTLY` and break it |
| 20 | Databases 4.1, 4.2 | Load one million orders; read `EXPLAIN (ANALYZE, BUFFERS)` for a nested loop and a hash join |
| 21 | Databases 4.3, 4.4 | Skew the statistics and watch the plan change; rewrite an N+1 loop as one set-based query |
| 22 | Databases 4.5, 4.6, 7.5 | Enable `pg_stat_statements`; find and fix the top query by total time; size a HikariCP pool from first principles |
| 23 | Databases 5.1, 5.2, 5.3 | Reproduce the dirty, non-repeatable and phantom read definitions in two `psql` sessions |
| 24 | Databases 5.4, 6.1, 6.5 | Reproduce write skew; see it fail under `SERIALIZABLE`; inspect `xmin` and `xmax`; leave a transaction open and watch `VACUUM` fall behind |
| 25 | Databases 6.2, 6.3, 6.4 | Review day: reproduce a lost update and a deadlock; fix the lost update four ways; build a queue table with `SKIP LOCKED` |

### Days 26 to 32: System Design

| Day | Items | Lab or exercise |
|---|---|---|
| 26 | System Design 1.1, 1.2, 1.4 | Write SLOs and a back-of-the-envelope estimate for the order service |
| 27 | System Design 2.2, 2.5, 2.11 | Design the cache for the order read path; name the stampede fix; implement a token bucket in 40 lines |
| 28 | System Design 2.6, 2.7, 3.1 | Choose SQL or NoSQL and a queue for three described workloads; list the failover anomalies of single-leader replication |
| 29 | System Design 3.3, 3.4, 3.7 | Classify five systems you use by consistency model; apply PACELC to each; draw the saga for "place order, reserve stock, charge card" |
| 30 | System Design 3.8, 4.1, 4.2 | Mark where exactly-once is impossible in the saga; write the timeout, retry and circuit-breaker policy for every outbound call of the order service |
| 31 | System Design 4.3, 4.4, 5.1, 5.2 | Bound every queue in the order service and apply Little's law; design its idempotency keys; draw its service boundaries and name the shared-database trap |
| 32 | System Design 6.1, 6.2, 6.3.1 | Review day: design the URL shortener in 45 minutes, out loud, with a timer |

### Days 33 to 35: Cloud

| Day | Items | Lab or exercise |
|---|---|---|
| 33 | Cloud 1.1, 2.1, 2.2 | Draw the shared responsibility line for a managed PostgreSQL; write the least-privilege policy the order service needs; replace a stored secret with a workload identity |
| 34 | Cloud 3.1, 3.3, 4.2 | Sketch the VPC with public and private subnets for the order service; decide load balancer and compute option, and say what Kubernetes would add |
| 35 | Cloud 5.2, 6.2, 8.4 | Review day: load test the order service, turn the numbers into instance sizes and pool sizes, and price the design on both clouds |

### Days 36 to 38: DevOps & Delivery

| Day | Items | Lab or exercise |
|---|---|---|
| 36 | DevOps & Delivery 1.1, 2.1, 2.3 | Write the GitHub Actions pipeline for the order service: build, unit tests, Testcontainers tests, image |
| 37 | DevOps & Delivery 3.1, 3.2, 3.4 | Write a multi-stage Dockerfile; run the JVM with `MaxRAMPercentage` under a memory limit and watch it get OOM-killed, then fix it |
| 38 | DevOps & Delivery 5.1, 5.2, 6.1, 6.2 | Review day: define RED metrics and a correlation ID for the order API; plan an expand-contract column rename; pick rolling or canary for the first release and say why |

### Days 39 to 41: Architecture & Craft

| Day | Items | Lab or exercise |
|---|---|---|
| 39 | Architecture & Craft 1.1, 1.2, 2.3 | Rename every abbreviation in a class you own; find its deepest and shallowest module; draw the dependency direction and invert one |
| 40 | Architecture & Craft 2.1, 5.2, 5.3 | Find one SOLID violation that matters and one that does not; rewrite a test so it survives a refactoring; replace a mock with a fake |
| 41 | Architecture & Craft 6.2, 7.2, 9.2 | Review day: model the order as an aggregate with its invariants; draw the hexagon for the order service; write the ADR for cookie session versus bearer token |

### Days 42 to 45: Security

| Day | Items | Lab or exercise |
|---|---|---|
| 42 | Security 1.1, 2.1, 2.3 | Draw the trust boundaries of the order service; find an IDOR and an injection in a small sample app |
| 43 | Security 2.10, 2.11, 3.1 | Get a script past a naive template; explain why `SameSite` alone is not enough; hash a password with Argon2id and time it |
| 44 | Security 5.1, 5.2, 5.3 | Draw the Authorization Code with PKCE flow; explain why the Implicit grant died; decide opaque or JWT access tokens for the order API |
| 45 | Security 6.1, 6.2, 9.1 | Review day: decode a JWT and write its validation checklist; move every secret of the order service out of the repository and the image |

### Days 46 to 48: DSA & Interviews

| Day | Items | Lab or exercise |
|---|---|---|
| 46 | DSA & Interviews 1.1, 6.1, 7.1 | Pick NeetCode 150 or Grind 75 and set up the tracking sheet; solve two easy problems out loud with the protocol |
| 47 | DSA & Interviews 2.1, 2.2, 2.3 | Three problems, one per pattern, timed at 25 minutes each |
| 48 | DSA & Interviews 2.5, 3.2, 4.1 | Review day: three problems, one per pattern; write the daily twenty-minute habit into your calendar from Day 49 |

### Days 49 to 51: Java

| Day | Items | Lab or exercise |
|---|---|---|
| 49 | Java 1.3, 1.5, 1.6 | Break `equals` and `hashCode` in a `HashSet`; model order states as a sealed type with a `switch` |
| 50 | Java 1.7, 1.8, 1.10 | Write a PECS-correct `copy` method; convert a checked-exception API to a result type; remove every `isPresent` from a class |
| 51 | Java 2.6, 8.1, 8.5 | Review day: rewrite a nested loop as a stream and compare readability; take a thread dump of the Day 15 deadlock; walk the three-incident workflow on paper |

### Days 52 to 57: Spring, built into the order service

The lab is the order service described in the Projects domain (Spring Boot, PostgreSQL and Kafka in Docker Compose). It is a lab here, not a tracked item; its "done when" tests are the milestones below.

| Day | Items | Lab, exercise or project milestone |
|---|---|---|
| 52 | Spring 1.4, 2.2, 3.1 | Generate the order service skeleton; break a `@Transactional` method with self-invocation; list which auto-configurations fired and why; trace one request through the `DispatcherServlet` |
| 53 | Spring 4.1, 4.3, 4.4 | Configure HikariCP with the Day 22 size; reproduce the three `@Transactional` bugs; place the transaction boundaries of the order service |
| 54 | Spring 4.5, 5.1, 5.2 | Flyway migrations for orders, items and the idempotency table; entities with sequence identifiers; watch the persistence context flush |
| 55 | Spring 5.4, 5.5, 5.8 | Milestone 1: log SQL and remove every N+1; turn Open Session in View off; reproduce the lost update under JPA, fix with `@Version` and a retry |
| 56 | Spring 6.1, 6.3, 6.5 | Milestone 2: list every filter in the security chain; protect the order endpoints with method security; JWT resource server; idempotency keys proven with concurrent duplicate requests |
| 57 | Spring 7.1, 7.4, 8.3 | Review day, milestone 3: controller and repository tests with slices and Testcontainers; probes and graceful shutdown; publish order events through an outbox table if time allows |

### Days 58 to 60: JavaScript & Frontend, then consolidation

| Day | Items | Lab or exercise |
|---|---|---|
| 58 | JavaScript & Frontend 1.6, 1.7, 3.1 | Predict the output of a microtask-versus-task puzzle, then run it; block the Node event loop with a CPU task and measure the damage |
| 59 | JavaScript & Frontend 4.4, 8.2, 8.3 | Review day: call the order service from a Vite page with `fetch`; make CORS work in development and production; authenticate it both ways (cookie session, then bearer token through a BFF) |
| 60 | Consolidation | Redo the failed Anki cards; mock design interview using your own order service as the case; write the README with design, trade-offs and measurements |
