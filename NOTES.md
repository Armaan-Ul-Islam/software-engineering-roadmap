# Backlog and working notes

Ideas, gaps, and reminders captured while building the roadmap. Keep entries short and
actionable. Remove an entry when it is done.

## 0. Status (2026-10-24, end of the first build session)

| Measure | Value |
|---|---|
| Domains | 15 |
| Checklist items | 728 |
| Explainer notes | 227 (about 349,000 words) |
| Items with a linked note | 415 of 728 (57%) |
| Two-month track items with a note | 101 of 113 (89%) |
| Anki cards | 908 (all notes), 256 (two-month track) |
| External links checked | about 2,300 unique URLs; all reachable except hosts that block scripts (see 3.0) |
| Live site | https://armaan-ul-islam.github.io/software-engineering-roadmap/ (GitHub Pages, deployed by `.github/workflows/pages.yml` on every push to `main`) |
| Commits | 39 local; the last push was commit 33, so `git push` publishes the rest |

- 0.1 Waves 1 and 2 (one writer per domain) and wave 3 batch 1 (the five two-month-track domains) are complete. Every note passed `tools/check_notes.py`, local-link validation and an external link check; the writers compiled and ran the Java, SQL and shell examples; at least one note per domain and per batch was read in full during review.
- 0.2 Remaining writing: wave 3 batches 2 and 3, listed in section 4 (the domains marked "to do"). About 70 notes and 6 project specs. Each batch of five writers costs roughly one million tokens.
- 0.3 Decisions: do not aim for a note on every item; after wave 3, invest in hands-on labs (1.10) and the Anki habit rather than more breadth; the tracker, the two-month track and the "done when you can" lists are the real gates.
- 0.4 How to run another batch: start one writer per domain with `tools/note-writer-brief.md` plus the domain's list from section 4; afterwards run `python3 tools/check_notes.py`, `python3 tools/link_notes.py`, `python3 tools/build.py`, `python3 tools/export_anki.py` (both decks), `python3 tools/check_links.py <domain>/notes`, and commit per domain with a one-sentence message and no trailers. Writers should write each file as soon as it is finished; spend limits have interrupted two batches, and finished files survive.
- 0.5 Progress profiles: the tracker keeps ticks per profile in the browser; `progress/<profile>.json` committed to the repository is the baseline for every device (Save file in the tracker, then `python3 tools/save_progress.py <download> --commit`). No profile files exist yet.

## 1. Content to add

- 1.1 Worked system-design case studies beyond the URL shortener (rate limiter, news feed, chat, notification system, payment flow, ticket booking).
- 1.2 A "reading order" for Designing Data-Intensive Applications mapped to roadmap items.
- 1.3 Java release notes digest: one page per LTS (17, 21, 25) listing the features that change how you write code.
- 1.4 Spring Boot 4 / Spring Framework 7 migration notes (JSpecify nullness, API versioning, Jackson 3, resilience annotations in core).
- 1.5 Hands-on labs for databases: reproduce every isolation anomaly in PostgreSQL with two psql sessions.
- 1.6 Hands-on lab for concurrency: reproduce a visibility bug, a deadlock, and a thread-pool starvation, then fix each.
- 1.7 Cloud cost worksheets: a spreadsheet-style estimate for a typical Spring Boot + PostgreSQL + Redis deployment on AWS and on Azure.
- 1.8 Frontend: a minimal React + Vite app wired to a Spring Boot API, with CORS and auth done both ways (cookie session and bearer token).

- 1.9 Explainer notes still to write: see section 4.
- 1.10 Hands-on labs as a layer on top of the notes: reproduce-and-fix exercises (every isolation anomaly in two `psql` sessions, a deadlock, a visibility bug, a thread-pool starvation, a lost update under JPA) with the exact commands and the expected observation.
- 1.11 An exporter that turns every note's "Check yourself" questions into an Anki deck (question on the front, the note's title and path on the back).

## 2. Open questions

- 2.1 Whether to add per-item time estimates. Decision so far: no, they are guesswork and clutter the checklist.
- 2.2 Whether to add a licence. Suggestion: CC BY-SA 4.0 for the text and MIT for the tooling, so people can reuse the notes with attribution.
- 2.3 Whether to support progress sync beyond browser storage (for example a JSON file committed to the repo). Export/import exists; revisit if it becomes annoying.

## 3. Maintenance reminders

- 3.0 Link checks of 2026-10-24: about 2,300 unique links across roadmaps and notes, all reachable except hosts that block scripts (vladmihalcea.com, medium.com, leetcode.com, netflixtechblog.com, uber.com, cwe.mitre.org, itrevolution.com). Those are listed as BLOCKED by `tools/check_links.py`; spot-check them in a browser occasionally.

- 3.1 Re-check links quarterly with `python3 tools/check_links.py`; MDN, Spring, and Microsoft Learn move pages often.
- 3.2 When a new Java LTS or Spring Boot major ships, review the Java and Spring roadmaps for outdated items.

## 4. Third wave of notes

Batch 1 (4.2, 4.3, 4.4, 4.6, 4.7) is done. Batches 2 and 3 are the lines marked "to do". Each line is `file name · items`. The item numbers exist in the domain README. Writers follow `tools/note-writer-brief.md`.

- 4.1 01-foundations (to do): ip-addressing-subnets-and-nat (3.2); cpu-scheduling-and-why-too-many-threads-hurt (2.2); shell-scripting-with-safety-rails (5.4); ssh-keys-agents-and-tunnels (5.5); debugging-as-a-method (7.3); regular-expressions-you-actually-use (7.4); time-dates-and-time-zones (7.5).
- 4.2 02-web-and-http (done): urls-and-percent-encoding (1.3); connection-management-timeouts-and-pools (3.1, 3.4); content-negotiation-compression-and-conditional-requests (4.3, 4.4, 4.5); curl-for-http-debugging (4.6, 8.3); openapi-contract-first (9.4); graphql-and-grpc-vs-rest (9.5); webhooks-done-right (9.6).
- 4.3 03-memory-and-concurrency (done): completablefuture-in-depth (5.2); coordination-primitives-latches-barriers-semaphores (4.4); concurrent-collections (4.7); threadlocal-and-scoped-values (4.8); reference-types-and-caches (2.6); reactive-streams-and-backpressure (5.7); testing-concurrent-code (6.2); amdahls-law-and-scalability-limits (6.4).
- 4.4 04-databases (done): sql-joins-explained (1.2); window-functions-and-ctes (1.3); postgresql-data-types-that-matter (1.4, 8.4); upserts-and-merge (1.5); gin-gist-brin-and-other-index-types (3.4, 3.6); finding-slow-queries-with-pg-stat-statements (4.5, 4.6); partitioning-vs-sharding (7.4); redis-as-a-cache (9.2); choosing-a-database (9.1, 9.5); jdbc-fundamentals (10.1).
- 4.5 05-java (to do): autoboxing-integer-cache-and-numeric-pitfalls (1.1); strings-string-pool-and-text-blocks (1.2); jackson-serialisation-pitfalls (3.5); reflection-annotations-and-how-frameworks-work (3.4); java-io-and-nio-essentials (3.2); jfr-and-async-profiler-in-practice (8.3, 8.4); java-versions-what-changed-8-to-25 (6.4); property-based-and-mutation-testing (7.5); lombok-records-and-what-they-generate (9.4); java-logging-with-slf4j-and-logback (3.6).
- 4.6 06-spring (done): spring-events-async-and-scheduling (1.6, 4.4); restclient-webclient-and-http-interface-clients (3.5); filters-interceptors-and-aop-where-cross-cutting-code-belongs (3.4); jdbcclient-and-jdbctemplate (4.1, 4.2); hibernate-write-performance-and-batching (5.7); spring-kafka-essentials (9.1); caching-with-cacheable (8.5); resilience-with-resilience4j-and-spring (8.4); virtual-threads-in-spring-boot (3.7); tracing-with-micrometer-and-opentelemetry (8.2).
- 4.7 07-system-design (done): requirements-slos-and-the-nines (1.1); unique-id-generation (2.12); partitioning-and-sharding-strategies (3.2); clocks-ordering-and-lamport-timestamps (3.5); distributed-locks-and-fencing-tokens (3.9); event-driven-architecture-choreography-vs-orchestration (5.3); cqrs-and-event-sourcing-honestly (5.4); case-study-rate-limiter (6.3.2); case-study-news-feed (6.3.2); multi-region-and-disaster-recovery (5.7).
- 4.8 08-javascript-and-frontend (to do, node-streams-and-backpressure already done): building-an-http-api-with-fastify (3.4, 3.5); testing-javascript-with-vitest (3.6, 6.11); validating-at-the-boundary-with-zod-and-openapi-types (2.4, 8.4); dom-and-events (4.3); web-performance-and-core-web-vitals (4.6); react-forms-routing-and-state-management (6.6, 6.8, 6.9); rendering-strategies-csr-ssr-and-server-components (6.10); serving-and-deploying-a-spa-with-spring-boot (8.1, 8.5).
- 4.9 09-cloud (to do): secrets-and-key-management-in-the-cloud (2.3, 9.1); accounts-subscriptions-and-landing-zones (1.3, 2.4); private-connectivity-and-the-edge (3.4, 3.5); well-architected-review-in-practice (1.5, 8.5); cloud-observability-cloudwatch-azure-monitor-and-otel (8.1, 8.2); managed-nosql-and-caches (6.3); cloud-security-posture-basics (9.2, 9.3).
- 4.10 10-devops-and-delivery (to do): pull-requests-commits-and-versioning (1.2, 1.3); continuous-delivery-pipelines-and-promotion (2.4, 6.4); supply-chain-security-sboms-and-signing (2.5, 2.6, 3.6); helm-kustomize-and-gitops (4.7); systemd-and-journald-essentials (7.3); dora-metrics-and-the-sre-mindset (8.3, 8.4).
- 4.11 11-architecture-and-craft (to do): code-smells-catalogue (1.6, 3.5); composition-over-inheritance-and-tell-dont-ask (2.4, 2.5); tdd-as-a-design-practice (5.5, 5.6); contract-testing-with-pact (5.4, 8.3); strangler-fig-and-refactoring-at-scale (4.3, 4.4); c4-diagrams-and-technical-writing (9.3, 9.5); architecture-trade-offs-and-fitness-functions (7.5, 7.6); estimation-and-saying-no (9.6).
- 4.12 12-security (to do): owasp-api-security-top-10 (2.12, 4.3); mfa-passkeys-and-account-recovery (3.3, 3.5); mtls-and-service-to-service-auth (7.4); security-headers-explained (9.4, 7.5); input-validation-and-file-uploads (9.5); logging-privacy-and-gdpr-for-developers (10.1, 10.2); secure-sdlc-and-asvs (1.3, 1.4).
- 4.13 13-dsa-and-interview-prep (to do): patterns-intervals-and-greedy (2.6, 5.5); patterns-tries-and-union-find (3.4, 3.5); patterns-shortest-paths-and-minimum-spanning-trees (4.3); patterns-bit-manipulation-and-math (5.6); patterns-strings-and-matrices (2.7, 2.8); java-and-spring-interview-questions-self-check (8.2, 8.3); low-level-design-interviews (8.4); mock-interviews-and-deliberate-practice (1.5, 7.3).
- 4.14 14-ai-engineering (to do): prompting-and-context-engineering (2.1, 2.3); cost-and-latency-engineering-for-llm-features (2.4, 5.4); observability-and-reliability-for-llm-calls (5.2, 5.3); document-ingestion-pipelines (3.4); local-models-and-testing-llm-features (7.3, 7.4); ai-assisted-development-as-a-skill (7.5).
- 4.15 15-projects (to do; specs in the shape of the two existing ones): http-server-from-sockets-spec (1.1); key-value-store-with-wal-spec (1.3); url-shortener-spec (2.1); authentication-service-spec (2.3); observability-stack-spec (4.4); rag-over-your-repositories-spec (5.1).
