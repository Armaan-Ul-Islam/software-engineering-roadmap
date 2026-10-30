# Software Engineering Roadmap

A curated roadmap for backend-leaning software engineers who want to be genuinely good, not just employable: checklists that say exactly what to learn, short explainers that teach the hard concepts with examples, and only the best links for each topic. Java and Spring are the worked examples; the ideas are language-neutral.

**Live tracker: [armaan-ul-islam.github.io/software-engineering-roadmap](https://armaan-ul-islam.github.io/software-engineering-roadmap/)**, or open [`index.html`](index.html) locally, to track progress, see the domains in reading order, read the notes in place, and jump to the resources. Progress stays in your browser; export it when you switch machines.

## 1. The map

The thirteen core domains, in the order the tracker's map and the sixty-day track read them. The order is a reading order, not a chain of prerequisites: nothing here depends on finishing something else first, so you can run several domains side by side or start wherever your gaps are. The number in the folder name only names the folder.

| # | Domain | What you get | Track days |
|---|--------|--------------|------------|
| 1 | [Foundations](01-foundations/README.md) | How computers run code, operating systems, networking, data structures, Linux, Git | 1 to 4 |
| 2 | [Web & HTTP](02-web-and-http/README.md) | DNS, TCP, TLS, HTTP semantics, caching, cookies, CORS, APIs, real-time | 5 to 10 |
| 3 | [Memory & Concurrency](03-memory-and-concurrency/README.md) | Stack and heap, GC, memory models, threads, locks, pools, virtual threads | 11 to 16 |
| 4 | [Databases](04-databases/README.md) | SQL, storage engines, indexes, query plans, transactions, MVCC, replication | 17 to 25 |
| 5 | [System Design](07-system-design/README.md) | Estimation, building blocks, distributed systems, resilience, architecture, interviews | 26 to 32 |
| 6 | [Cloud](09-cloud/README.md) | AWS and Azure fundamentals, networking, compute, sizing and cost estimation | 33 to 35 |
| 7 | [DevOps & Delivery](10-devops-and-delivery/README.md) | Git workflows, CI/CD, Docker, Kubernetes, observability, deployments, incidents | 36 to 38 |
| 8 | [Architecture & Craft](11-architecture-and-craft/README.md) | Readable code, SOLID, patterns, refactoring, testing strategy, DDD, API design | 39 to 41 |
| 9 | [Security](12-security/README.md) | Threat modelling, OWASP Top 10, authentication, OAuth2/OIDC, JWT, TLS, crypto | 42 to 45 |
| 10 | [DSA & Interviews](13-dsa-and-interview-prep/README.md) | Patterns, practice plans, Java interview idioms, behavioural interviews | 46 to 48 |
| 11 | [Java](05-java/README.md) | Modern language features, collections, streams, the JVM, tooling, testing | 49 to 51 |
| 12 | [Spring](06-spring/README.md) | Container, Boot, MVC, transactions, JPA/Hibernate, Security, testing, operations | 52 to 57 |
| 13 | [JavaScript & Frontend](08-javascript-and-frontend/README.md) | JavaScript, TypeScript, Node.js, browsers, React, wiring a SPA to Spring | 58 to 59 |

Two more domains are optional: they sit behind the **More** button in the tracker and outside the sixty-day track, for after the core or when a task at work needs them.

| Domain | What you get |
|--------|--------------|
| [AI Engineering](14-ai-engineering/README.md) | LLM fundamentals, prompting, RAG, tools and agents, evals, security, Spring AI |
| [Projects](15-projects/README.md) | Capstone builds that exercise everything above, with definitions of done |

Every domain README has the same shape: a summary, related domains, a "done when you can" list of observable abilities, the numbered checklist, and a curated resource list grouped into *start here*, books, courses and references.

## 2. How to use it

1. Start anywhere: with the sixty-day track if you want a schedule, or with the domain where your gaps are. Read its "done when you can" list first; it tells you what mastery looks like.
2. Work through the checklist in order. For each item: read the note in this repository if there is one, then the first external link. Tick the item only when you can explain it to a colleague without notes and have used it at least once.
3. When a section is done, build the matching project from the optional [Projects](15-projects/README.md) domain. Understanding that has not been exercised evaporates.
4. Revisit ticked items after a month. If you cannot re-explain one, untick it.
5. Keep your own notes in your own words. The notes here are a starting point, not a substitute.

Item IDs (`4.3`, `6.5.2`) are stable, so you can reference them in your own notes, in pull requests, or when asking for help.

## 3. Suggested paths

If you want a schedule rather than a map, start with the sixty-day track in section 4. The paths below are for working through whole domains; none of them is required before another.

1. **Backend core (about six months, part time).** The thirteen core domains in map order, finishing with Projects sections 1 and 2.
   1.1 If you already write Java daily, skim Foundations and start with Databases and Memory & Concurrency; they are where most working developers have gaps.
2. **Senior or interview preparation (8 to 12 weeks).** DSA & Interviews alongside System Design, then Architecture & Craft and the Security basics, with weekly mock interviews.
3. **Ship to production.** DevOps & Delivery, then Cloud, then Projects section 4.
4. **Full stack.** JavaScript & Frontend, then Projects section 3.
5. **AI features.** AI Engineering after Spring and Databases, then Projects section 5.

## 4. Time-boxed tracks

The full map is more than a year of learning. A track is a subset with a schedule, so you can finish a box instead of browsing a map. Tracks live in [`tracks/`](tracks/) and appear in the tracker's top bar; selecting one hides everything else and makes every progress bar measure the track.

- 4.1 [Sixty-day backend core](tracks/two-month-backend-core.md): 176 items scheduled Day 1 to Day 60 at two and a half to three hours a day, through all thirteen core domains in map order: Foundations, Web & HTTP, Memory & Concurrency, Databases, System Design, Cloud, DevOps & Delivery, Architecture & Craft, Security, DSA & Interviews, Java, Spring, JavaScript & Frontend, with the order service as the running lab and Day 60 for consolidation. Each item carries its Day badge in the tracker.

To add a track, copy the file's shape: a title, a summary blockquote, an `**Hours:**` line, an `## Items` section with one `### <domain-slug>` heading per domain followed by comma-separated item IDs, and whatever plan you like after it. Tables under a `## Day by day` heading become the schedule (`| Day | Items | Lab |`, items written as `Foundations 2.1, 2.2; Web & HTTP 1.1`). `python3 tools/build.py` validates that every ID exists, that every scheduled item is in the track, and that no day is skipped.

## 5. How to learn this well

- 5.1 **Active recall beats rereading.** After each note, close it and write the explanation from memory. The "Check yourself" questions exist for this.
- 5.2 **Space it out.** Revisit a topic after a day, a week, and a month. A flashcard tool such as [Anki](https://apps.ankiweb.net/) works well for definitions, numbers and commands.
- 5.3 **Build to learn.** Reading about MVCC teaches vocabulary; reproducing a lost update in two `psql` sessions teaches MVCC.
- 5.4 **Teach it back.** Explain the concept to someone, or write it up. If the explanation needs the notes, you are not done.
- 5.5 **Practise with feedback.** Mock interviews, code review, benchmarks and tests are feedback. Reading alone is not.
- 5.6 **Keep a mistakes log.** Every bug you caused and every interview question you missed goes in a file with the lesson. Review it monthly.

## 6. Hosting the tracker for free

The tracker is static files, so any static host works and none of them costs anything for a repository like this.

- 6.1 **GitHub Pages (what this repository uses).** The workflow in `.github/workflows/pages.yml` rebuilds `site/data.js` from the markdown and the progress files on every push to `main` and deploys the repository root to Pages. The site appears at `https://<user>.github.io/<repository>/` a minute or two after a push. Pages is free for public repositories.
- 6.2 **Cloudflare Pages or Netlify.** Both have free tiers that deploy from a private GitHub repository: connect the repository, leave the build command empty, set the output directory to `/`, and every push deploys. Both give you a free `*.pages.dev` or `*.netlify.app` address.
- 6.3 Progress stays in each visitor's browser either way. Use Export and Import in the top bar to move it between machines.

## 7. Saving your progress

Ticks are kept in your browser under a **profile** (pick a name in the top bar; no login, anyone can create one). To make them permanent and shared across devices:

- 7.1 Click **Save file** in the tracker; it downloads `<profile>.json`.
- 7.2 Put that file in the repository's [`progress/`](progress/) folder and commit it: `python3 tools/save_progress.py ~/Downloads/<profile>.json --commit` does the copy, rebuilds the data and commits; or upload the file through GitHub's *Add file* button in the `progress/` folder.
- 7.3 Push. The hosted site rebuilds within a minute and every browser that selects that profile starts from the saved state (the saved file is the baseline; local ticks are kept on top).
- 7.4 For a quick transfer without a commit, **Copy link** puts the whole progress of the profile into a link; opening it on another device loads it.

Several people can use one repository: one file per profile.

## 8. Spaced repetition

`python3 tools/export_anki.py` turns every note's "Check yourself" questions into an Anki deck (`anki/all-notes.tsv`); add `--track <slug>` for a track-only deck. The decks are committed, so you can also download them straight from GitHub. Import with tab-separated fields, HTML allowed, and the third field as tags.

## 9. What is in the repository

```
index.html             the tracker (open it directly; no build or server needed)
site/                  the tracker's script, styles, generated data, and a vendored markdown parser
NN-<domain>/README.md  the roadmap for one domain
NN-<domain>/notes/     short explainers for the concepts in that domain
tracks/                time-boxed subsets of the map with a schedule (selectable in the tracker)
anki/                  generated flashcard decks (tab-separated, importable into Anki)
progress/              one JSON file per profile with that person's saved progress
tools/build.py         regenerates site/data.js from the markdown and validates links and IDs
tools/check_notes.py   checks note structure and conventions
tools/link_notes.py    links each note into the roadmap items named in its footer
tools/check_links.py   checks every external link
tools/status.py        prints items, notes, coverage and per-track coverage
tools/export_anki.py   writes the Anki decks from the notes' Check yourself questions
tools/save_progress.py copies a downloaded progress file into progress/ and rebuilds
AGENTS.md              conventions for editing this repository (for people and for coding agents)
NOTES.md               backlog of content to add and open questions
```

After editing any roadmap or note, run:

```bash
python3 tools/build.py        # validate and regenerate site/data.js
python3 tools/check_notes.py  # check that every note follows the note conventions
python3 tools/link_notes.py   # add [notes] links to the roadmap items each note declares in its footer
python3 tools/check_links.py  # optional: check external links (writes tools/link-report.txt)
```

The same checks run in GitHub Actions on every push, and a second workflow rebuilds the data and deploys the tracker to GitHub Pages (see section 6).

## 10. Curation principles

- 10.1 Primary sources first: official documentation, specifications and the original paper or post, then excellent free courses and books, then practitioner blogs. Paid material is marked as paid.
- 10.2 One excellent link beats five decent ones. Every link should be something you would send to a colleague.
- 10.3 Checklist items are concrete and testable. "Explain why column order in a composite index matters", not "learn indexes".
- 10.4 Notes teach one concept each, with a real example, the pitfalls people actually hit, and questions to check understanding.
- 10.5 Nothing is included because it is popular. Things are removed when they go stale.

The sources this roadmap leans on most: the official documentation of PostgreSQL, Java, Spring and MDN; [roadmap.sh](https://roadmap.sh/); [ByteByteGo](https://bytebytego.com/); [Designing Data-Intensive Applications](https://dataintensive.net/); [Marco Behler's guides](https://www.marcobehler.com/guides); [Vlad Mihalcea](https://vladmihalcea.com/); [Baeldung](https://www.baeldung.com/); [Use The Index, Luke](https://use-the-index-luke.com/); [High Performance Browser Networking](https://hpbn.co/); [OSTEP](https://pages.cs.wisc.edu/~remzi/OSTEP/); [CMU 15-445](https://15445.courses.cs.cmu.edu/); the [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/); [Martin Fowler](https://martinfowler.com/); the [Google SRE books](https://sre.google/books/); [LeetCode](https://leetcode.com/) and [NeetCode](https://neetcode.io/); and [GeeksforGeeks](https://www.geeksforgeeks.org/) for breadth.

## 11. Contributing

Read [`AGENTS.md`](AGENTS.md) for the file conventions, then open a pull request. Good contributions: a better link than the one listed (say why), a note for an item that lacks one, a correction with a source, a project with a sharper definition of done.
