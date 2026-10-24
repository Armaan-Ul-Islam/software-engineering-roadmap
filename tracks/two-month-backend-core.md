# Two-month backend core

> The highest-value 113 items for a working Java/Spring developer, plus one project, sized for nine to ten weeks at about 15 hours a week. Finish this box and you can reason about indexes, transactions, concurrency, Spring's data layer and security, and the core of system design from first principles.

**Hours:** about 150

## Items

### web-and-http
3.2, 3.4, 4.1, 4.2, 4.2.1, 4.2.2, 4.2.3, 4.3, 4.5, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 7.1, 7.2, 8.1

### databases
1.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5

### memory-and-concurrency
2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.4, 5.5, 5.6

### spring
1.4, 2.2, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.10, 6.1, 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.4, 7.6, 8.3

### system-design
1.1, 1.2, 1.4, 2.2, 2.5, 2.6, 2.7, 2.11, 3.1, 3.3, 3.4, 3.7, 3.8, 4.1, 4.2, 4.3, 4.4, 6.1, 6.3.1

### projects
2.2, 2.2.1, 2.2.2

## How to work the track

- 1.1 For each item: read the note if there is one, then the first external link. Do the exercise or reproduce the example. Tick the item only when you can explain it to a colleague without notes and have used it once.
- 1.2 Keep a mistakes log. Every surprise goes in with the lesson; review it at the end of each week.
- 1.3 The project is not optional. It is where the database, concurrency and Spring items turn into skill, and its milestones are scheduled below so that each one uses what you learned that week.
- 1.4 Everything outside the track is deliberately deferred. When a task at work needs one of those items, read it then; otherwise it is the next box.

## Review and retention

The box is only worth running if the concepts are still there in month four. Build review into the schedule:

- 2.1 Flashcards: `python3 tools/export_anki.py --track two-month-backend-core` writes `anki/two-month-backend-core.tsv`, one card per "Check yourself" question in the track's notes (about 200 cards). Import it into Anki and review for ten minutes a day. Say the answer out loud, then open the note to check; grade yourself honestly.
- 2.2 Weekly review (30 minutes, end of each week): re-read your mistakes log, re-explain the week's three hardest items from memory, untick anything you cannot re-explain.
- 2.3 Teach-back: once a week, explain one item to a colleague or write it up in your own words. The items that resist explanation go back on the list.
- 2.4 Week 10 is consolidation as much as new material: redo the Anki cards you failed most, and run the mock interview using your own project as the case.

## Week by week

| Week | Focus | Items | Project milestone |
|---|---|---|---|
| 1 | Web & HTTP: semantics, caching, cookies, CORS, TLS, HTTP/2 | Web & HTTP 3.2 to 8.1 | Set up the order service skeleton with PostgreSQL in Docker Compose |
| 2 | Databases: indexes and query plans | Databases 1.6, 3.1 to 4.6 | Load 1 million orders; make the slow query fast with EXPLAIN |
| 3 | Databases: transactions, isolation, MVCC, locking, pooling | Databases 5.1 to 7.5 | Milestone 1: reproduce the lost update, fix it with `@Version` and a retry |
| 4 | Concurrency: GC basics, the memory model, races and locks | Memory & Concurrency 2.1 to 4.5 | Milestone 2: idempotency keys, proven with concurrent duplicate requests |
| 5 | Concurrency: atomics, concurrent collections, pools, virtual threads | Memory & Concurrency 4.6 to 5.6 | Size the service's pools from a load test |
| 6 | Spring: data access and transactions | Spring 1.4, 2.2, 4.1 to 4.5 | Milestone 3: the transactional outbox and relay |
| 7 | Spring: JPA and Hibernate internals | Spring 5.1 to 5.10 | Milestone 4: the idempotent Kafka consumer |
| 8 | Spring: Security and testing | Spring 6.1 to 8.3 | Milestone 5: retries and the dead-letter topic; test suite complete |
| 9 | System design: estimation, building blocks, consistency | System Design 1.1 to 3.8 | Write the README: design, trade-offs, measurements |
| 10 | System design: resilience, the interview method, one case study | System Design 4.1 to 6.3.1 | Mock design interview using your own service as the case |

At 15 hours a week this is 150 hours. At 10 hours a week the same track takes 15 weeks; drop week 10 and the Security items if you must fit nine weeks.
