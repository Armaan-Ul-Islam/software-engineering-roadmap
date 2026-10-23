# Design documents and ADRs: deciding in writing

> **In one sentence:** A design document is a one-page argument (problem, constraints, options, decision, risks, rollout) written before the code so that reviewers can approve or reject it without a meeting, and an Architecture Decision Record is the short, numbered, immutable record of one such decision kept next to the code so that in two years someone can learn why, not just what.

**Why it matters:** The most expensive decisions in a system (the data model, the module boundaries, the pagination scheme, the message broker) are usually made in a hallway and recovered later by archaeology. Writing them down forces the author to find the holes before the code does, lets more people review asynchronously, and leaves a trail that survives the people. "Write a one-page design document or ADR that a reviewer can approve or reject without a meeting" is on this domain's done-list because it is what separates a senior engineer from a fast one.

## The idea

**The one-page design document.** The order of the sections is the order of the argument:

1. Problem and context: what is wrong or needed, for whom, with evidence. Numbers beat adjectives.
2. Goals and non-goals: what success looks like, and what this explicitly does not try to do. Non-goals stop scope creep in review.
3. Constraints: deadlines, budget, compliance, existing systems, the team's skills.
4. Options considered: at least two real ones, including "do nothing", each described well enough that a reader could argue for it, with trade-offs against the goals.
5. Decision and rationale: which option, and why, tied back to the goals and constraints.
6. Risks and mitigations: what could go wrong, how you would notice, what you would do.
7. Rollout and reversibility: migration steps, feature flags, how to roll back, what to measure.
8. Open questions.

Write one when a change is hard to reverse (a schema, a public API, a broker), crosses a team boundary, has more than one viable option, will take more than a week or two, or touches security or privacy. Do not write one for a bug fix, a refactoring behind existing tests, or anything you can demonstrate faster with a pull request.

**Reviewing a design document.** Share it early and say how baked it is. Review asynchronously in comments with a deadline (a week is plenty), name one person who decides, resolve every thread in the document, and record the outcome at the top. A document that comes back from review unchanged was not reviewed. The reviewer's questions are the same as for code, one level up: does it solve the stated problem, were the alternatives real, what happens when the risk materialises, how do we get out.

**The Architecture Decision Record.** Michael Nygard's format, which most teams use nearly unchanged:

- Title, with a sequence number: `ADR-0007: Use keyset pagination for the orders API`.
- Status: Proposed, Accepted, Deprecated, or Superseded by ADR-N.
- Context: the forces at play, stated neutrally: facts, constraints, measurements, the options that were open.
- Decision: "We will ...", in the active voice.
- Consequences: what becomes easier, what becomes harder, what we now must do. The negative ones are the valuable ones.

MADR adds an explicit "Considered options" list with pros and cons; use it when the options matter more than the forces. The lifecycle is what makes ADRs work: they live in the repository (`docs/adr/`), they are reviewed in a pull request like code, and once accepted they are never edited. A changed decision is a new ADR that supersedes the old one, with links both ways, so the log stays honest. Write one when a decision affects structure, dependencies, interfaces, non-functional properties or construction techniques; not for tabs versus spaces. Keep them alive with an index, a link from the module's README, and a place in onboarding. A design document argues for a decision not yet taken and goes stale; an ADR records one taken and is never stale, because it is a log entry.

## Example: a complete ADR

```markdown
# ADR-0007: Use keyset pagination for the orders API

Status: Accepted, 2026-10-24. Related: ADR-0004 (public API compatibility policy).

## Context

`GET /orders` paginates with `page` and `size`, implemented as `OFFSET` and `LIMIT`
in PostgreSQL. The orders table holds 48 million rows and grows by about 200,000
a day. The merchant portal and two partner integrations scan recent orders in
pages of 100.

Measured on the production replica: page 1 answers in 12 ms, page 5,000 in
2.1 s, because PostgreSQL reads and discards 500,000 rows before returning the
page. Partners have reported duplicated and skipped orders while scanning during
business hours: orders inserted at the top shift every later page.

Constraints: three consumers use the response shape, and ADR-0004 commits us to
additive changes only. Analytics show the portal's "jump to page" control is
used in 0.2 % of list requests. No consumer needs random access.

## Decision

We will paginate `GET /orders` by keyset. The collection is ordered by
`(created_at DESC, id DESC)`, covered by one composite index. Each response
carries `nextCursor`, an opaque base64 encoding of the last row's `created_at`
and `id`, which the client passes back as `?after=<cursor>&limit=100`. `limit`
is capped at 200. `page` and `size` remain supported for twelve months with
`Deprecation` and `Sunset` headers, and their usage is tracked per consumer.

## Consequences

- Every page costs the same: an index range scan from the cursor, measured at
  9 to 15 ms regardless of depth.
- No duplicates or gaps while scanning: the cursor pins a position by value,
  not by count.
- Random access to an arbitrary page is no longer possible. The portal replaces
  its page selector with "load more".
- Clients must treat the cursor as opaque; we may change its encoding without
  notice. Malformed cursors are rejected with a 400 Problem Details response.
- Sorting by other fields needs a composite index per supported sort and is out
  of scope. Other `sort` values are rejected with 400 until an ADR adds them.
- Two code paths exist for twelve months. Removal is gated on the usage metric
  reading zero for the deprecated parameters.
```

What makes this reviewable without a meeting: the context has numbers a reviewer can challenge, the decision is specific enough to implement, and the consequences name the things that got worse. A reviewer who disagrees can say which fact is wrong or which consequence is unacceptable; a reviewer who agrees can approve in two minutes.

## Pitfalls

- A design document that is a specification (every class and method listed) or an essay. The reader needs the argument, not the implementation plan.
- One option considered. The decision was already made and the document is theatre; reviewers notice and stop reading future documents.
- Writing the document after the code, to get approval for what exists. Review then becomes a fight over sunk cost.
- Editing an accepted ADR in place. The history is the point; supersede instead.
- ADRs for trivia, which bury the dozen that matter.
- ADRs in a wiki nobody opens. Keep them in the repository, next to the code they explain, reviewed in pull requests.
- Consequences that list only benefits. If nothing got worse, you have not understood the decision.
- No decider and no deadline, so the comment thread runs for a month and the decision is made by whoever is still typing.
- "Status: Proposed" for a year. Either accept it, reject it, or delete it.

## Check yourself

1. Which section of a design document most often reveals that the author has not really explored the problem, and what does the symptom look like?
2. Why are accepted ADRs immutable, and what exactly do you do when the decision changes?
3. Rewrite "We chose Kafka because it is the industry standard" as Context, Decision and Consequences that a reviewer could challenge fact by fact.
4. What is the difference between a design document and an ADR, and when does a design document produce zero ADRs?

## Go deeper

- [Malte Ubl: Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/) · the structure, the lifecycle and the cultural role of design documents at a company that runs on them.
- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) · the original ADR post; the template above is his.
- [ADR GitHub organisation](https://adr.github.io/) · templates, tooling and examples, including [MADR](https://adr.github.io/madr/), the variant with explicit options.
- [Joel Parker Henderson: Architecture Decision Record](https://github.com/joelparkerhenderson/architecture-decision-record) · a large collection of templates and real examples to compare against your own.
- [Google: Technical Writing Courses](https://developers.google.com/tech-writing) · the sentence-level skills that make a one-page document actually one page.

---

Part of [Architecture & Craft](../README.md) · items 9.1, 9.2
