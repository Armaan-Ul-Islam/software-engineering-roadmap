# Backlog and working notes

Ideas, gaps, and reminders captured while building the roadmap. Keep entries short and
actionable. Remove an entry when it is done.

## 1. Content to add

- 1.1 Worked system-design case studies beyond the URL shortener (rate limiter, news feed, chat, notification system, payment flow, ticket booking).
- 1.2 A "reading order" for Designing Data-Intensive Applications mapped to roadmap items.
- 1.3 Java release notes digest: one page per LTS (17, 21, 25) listing the features that change how you write code.
- 1.4 Spring Boot 4 / Spring Framework 7 migration notes (JSpecify nullness, API versioning, Jackson 3, resilience annotations in core).
- 1.5 Hands-on labs for databases: reproduce every isolation anomaly in PostgreSQL with two psql sessions.
- 1.6 Hands-on lab for concurrency: reproduce a visibility bug, a deadlock, and a thread-pool starvation, then fix each.
- 1.7 Cloud cost worksheets: a spreadsheet-style estimate for a typical Spring Boot + PostgreSQL + Redis deployment on AWS and on Azure.
- 1.8 Frontend: a minimal React + Vite app wired to a Spring Boot API, with CORS and auth done both ways (cookie session and bearer token).

## 2. Open questions

- 2.1 Whether to add per-item time estimates. Decision so far: no, they are guesswork and clutter the checklist.
- 2.2 Whether to support progress sync beyond browser storage (for example a JSON file committed to the repo). Export/import exists; revisit if it becomes annoying.

## 3. Maintenance reminders

- 3.1 Re-check links quarterly with `python3 tools/check_links.py`; MDN, Spring, and Microsoft Learn move pages often.
- 3.2 When a new Java LTS or Spring Boot major ships, review the Java and Spring roadmaps for outdated items.
