# Working on this repository

This repository is a curated learning roadmap for backend-leaning software engineers.
It has three kinds of content, and each has a strict shape so that the tracker page
(`index.html`) can read it.

## 1. Layout

```
index.html              static tracker: progress, domain map, note reader (open directly in a browser)
site/                   app.js, styles.css, generated data.js, vendored marked.min.js
tools/build.py          parses the roadmaps + notes into site/data.js and validates links/IDs
tools/check_links.py    checks every external link in the markdown files
NN-<domain>/README.md   one roadmap per domain (the checklist + curated resources)
NN-<domain>/notes/*.md  short explainers ("notes") that teach one concept each
NOTES.md                backlog: ideas and gaps to fill later
```

Domain folders are numbered (`01-foundations`, `02-web-and-http`, ...). The number only
orders the domains; the slug after it is the identifier used by the tracker.

## 2. Roadmap README conventions

Every domain README has, in this order:

1. `# <Short title>` as the first line (keep it short, it is drawn in the map).
2. A blockquote (`> ...`) summarising the domain in one to three lines.
3. `**Prerequisites:**` followed by links to other domain READMEs, or `none`.
4. `**Done when you can:**` followed by a bulleted list of observable abilities.
5. `## Roadmap` containing numbered sections `### 1. Title`, `### 2. Title`, ...
6. `## Resources` with the curated reading/watching list, grouped by type.

Checklist items inside `## Roadmap` are one line each and look like this:

```
- [ ] 3.2 B-tree indexes and composite index column order · [notes](notes/b-tree-indexes.md) · [Use The Index, Luke](https://use-the-index-luke.com/)
  - [ ] 3.2.1 Covering and partial indexes · [PostgreSQL docs](https://www.postgresql.org/docs/current/indexes.html)
```

Rules:

- 2.1 IDs use decimal numbering (`3`, `3.2`, `3.2.1`). Write the full number on every level.
- 2.2 Never renumber existing items; progress in the tracker is keyed by `<domain>:<id>`. Append new items at the end of a section, or add a new section.
- 2.3 The first link of an item is the note in this repository when one exists (`[notes](notes/...)`). Then zero to three external links, best first.
- 2.4 Items are concrete and testable ("Explain why column order in a composite index matters"), not vague ("Learn indexes").
- 2.5 Separate text and links with ` · `.
- 2.6 Nest with two spaces per level. Keep nesting to three levels at most.
- 2.7 `- [x]` is allowed for personal progress but the tracker keeps its own state in the browser.

## 3. Note conventions

A note teaches exactly one concept and should be readable in five to ten minutes. Use the
template in `TEMPLATE-note.md`. Every note:

- 3.1 Starts with `# Title`, then `> **In one sentence:** ...`.
- 3.2 Has a concrete example (code with output, a worked scenario, a table, or an ASCII diagram). Prefer Java, SQL, HTTP, or JavaScript examples that run as written.
- 3.3 Names the pitfalls people actually hit.
- 3.4 Ends with "Check yourself" questions and a short "Go deeper" list.
- 3.5 Links back to its roadmap item (`Part of [Databases](../README.md) · item 3.2`).
- 3.6 Contains no filler, no marketing tone, and no unverified claims. When unsure about a detail, say so or leave it out.

## 4. Curation bar for external links

Prefer, in this order: primary documentation and specifications, free high-quality courses
and books, well-known practitioner blogs, then paid books and courses (mark them as paid).
Every link must be one you would send to a colleague. One excellent link beats five decent ones.
Do not link to content farms. Verify links with `python3 tools/check_links.py`.

## 5. Workflow

- 5.1 After editing any README or note, run `python3 tools/build.py`. It regenerates `site/data.js` and fails on broken local links or duplicate IDs. Commit the regenerated `site/data.js`.
- 5.2 Run `python3 tools/check_links.py` before committing a batch of new external links.
- 5.3 Commit messages are one plain sentence describing the change. No trailers.
- 5.4 Record ideas for later in `NOTES.md` instead of leaving half-written content in the roadmaps.
- 5.5 Lists with sub-points use decimal numbering (1, 1.1, 1.1.1) so each point can be referenced.
