# Brief: writing explainer notes (used for every note-writing wave; paths are relative to the repository root)

Repository: the repository root (a git repo; do NOT commit, do NOT push, do NOT edit any README.md or any file outside the notes folder you are assigned).

## What a note is

A note teaches exactly one concept to a working backend developer in five to ten minutes, with a concrete example, the pitfalls people actually hit, and questions that test understanding. Quality matters more than anything: a note with one precise, runnable example beats a note with five vague paragraphs. The person reading these wants to become a genuinely strong engineer, not to skim.

## Read these first, in this order

1. AGENTS.md (sections 3 and 4: note conventions and the curation bar)
2. TEMPLATE-note.md
3. The three exemplar notes that set the standard. Match their depth, tone and structure:
   - 04-databases/notes/transaction-isolation-levels-and-anomalies.md
   - 06-spring/notes/transactional-in-depth.md
   - 03-memory-and-concurrency/notes/java-memory-model-happens-before.md
4. Your domain's README.md, to see the exact wording of the items your notes belong to and the links already curated there.

## Structure of every note (exactly these sections, in this order)

```
# Title

> **In one sentence:** ...

**Why it matters:** two or three sentences on where this bites in real systems or interviews.

## The idea
## Example            (one or more; may be named, e.g. "## Example: reproduce a lost update")
## Pitfalls
## Check yourself     (numbered 1., 2., 3., 4.)
## Go deeper          (bulleted links, each with a short reason after " · ")

---

Part of [Domain Title](../README.md) · items 5.2, 5.3
```

The footer line is parsed by a tool. It must be the last line, exactly in that form: `Part of [<README title>](../README.md) · item 4.3` for one item or `· items 4.3, 4.5` for several. Use the domain README's `# Title` as the link text. The item IDs must exist in that README. If your note lives in a sub-folder (for example `notes/patterns/`), the link is `../../README.md`.

## Writing rules

- Length: roughly 600 to 1,400 words. Tables and code count. Cut anything that does not teach.
- Examples must be correct and, where code, runnable as written. Java examples use Java 21 syntax. SQL examples are PostgreSQL. Shell examples are for macOS or Linux. Include the output or observed behaviour where it helps.
- Variable, parameter and method names in code are full words: `connection`, `exception`, `index`, `orderRepository`. Never single letters or abbreviations like `ctx`, `e`, `i`, `svc`, `repo`, `cfg`. Explicit imports only, never wildcard imports. No comments that restate the code; a comment is only for a non-obvious why or a gotcha.
- Be accurate. Do not invent benchmark numbers, version numbers, flag names, or API names. When a behaviour depends on a version or a database, say which. If you are not sure of a detail, leave it out rather than guess.
- Plain, direct language. No marketing tone, no filler sentences, no "In today's fast-paced world". Short paragraphs. British or American spelling, but be consistent within a note (the exemplars use British spelling).
- Avoid em dashes; use commas, full stops or parentheses, matching the exemplars.
- Numbered lists that have sub-points use decimal numbering (1, 1.1, 1.1.1).
- Each note stands alone. Reference other items in the same domain by number ("see item 6.5") rather than linking to notes that may not exist.

## Links

- Prefer links that already appear in your domain's README. They have been checked.
- Add other links only if you are certain the URL exists and is the canonical page (official documentation, specifications, well-known practitioner blogs). Never guess a URL. Never link to a Medium post unless it is already in the README.
- Never link to notes in other domains. Linking to another note in your own batch is allowed only if you are writing that note in this same task.
- Do not link to YouTube videos unless the exact URL is already in your domain's README.

## Validation before you finish

Run, from the repository root:

```
python3 tools/link_notes.py --check
python3 tools/build.py --check
```

Fix every error or warning that mentions a file in your domain. Errors mentioning other domains may come from other writers working in parallel; ignore those. Do not run these tools without `--check` (the non-check mode edits README files, which is done centrally).

## Your report

When done, reply with: the list of files you wrote (path and one line each), any item IDs you could not match, and any factual point you were unsure about and left out. Keep the report under 300 words.

## Additions for later waves

- Your domain's `notes/` folder already contains notes from an earlier wave. List them first (`ls`) and read any whose topic touches yours, so you do not duplicate content; reference them by number of the item they cover ("see item 5.4") rather than linking, or link to them by relative path if the file exists.
- Every code fence needs a language tag: `java`, `sql`, `bash`, `yaml`, `json`, `javascript`, `typescript`, `http`, `xml`, `properties`, or `text` for program output, logs and ASCII diagrams. `python3 tools/check_notes.py <your-folder>` warns about untagged fences; fix them.
- The same structure, footer and validation rules apply. Items named in this task's list are guaranteed to exist in the README.
