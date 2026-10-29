# Pull requests, Conventional Commits and release versioning

> **In one sentence:** A pull request gets a good review when it is small, does one thing and explains why; a commit message that follows the Conventional Commits grammar lets a tool derive the next semantic version and the changelog from history; and a version is just an annotated tag on a commit that already passed the pipeline.

**Why it matters:** Reviewers skim a 1,200-line pull request and approve it, and read a 120-line one and find the bug. A team that cannot say which commit is running in production, or whether upgrading a library from 2.3 to 3.0 can break them, spends hours on questions that a tag and a version number answer in seconds. Interviewers ask "how do you version a service" to find out whether you have thought about what a version promises to its consumers.

## The idea

**A reviewable pull request.** Google's guide gives the test: the reviewer should be able to understand the change in one sitting and say with confidence that it improves the codebase. That is usually under a few hundred changed lines, one logical change (a refactor is not mixed with the feature that needed it), and a description that states the problem, the approach, what was considered and rejected, and how it was tested. The title is the future commit subject. Screenshots or a log excerpt for anything observable. Link the ticket; do not make the reader open it to learn what the change is for.

**Stacked changes.** When a feature genuinely needs 800 lines, split it into a chain of pull requests where each one targets the previous branch: `refactor extract PricingPolicy` then `feat add volume discount policy` then `feat expose discount in API`. Each is reviewed on its own diff; merging the first rebases the second onto `main`. GitHub shows the correct diff when the base branch is set to the parent branch, and tools such as `git rebase --update-refs` (Git 2.38 and later) keep the whole chain in sync after a fix lands at the bottom. Stacks only work with short-lived branches (item 1.1).

**Conventional Commits.** The subject line has a grammar: `type(scope)!: description`, with an optional body and footers such as `BREAKING CHANGE:` or `Closes ORD-412`. The types that matter are `feat` (a new capability, bumps the minor version), `fix` (bumps the patch version), and `!` or a `BREAKING CHANGE` footer (bumps the major version). Other types (`chore`, `docs`, `refactor`, `test`, `build`, `ci`) do not appear in the changelog by default. The payoff is automation: a release tool reads the commits since the last tag, computes the version, writes the changelog and creates the tag. The cost is that squash-merging a pull request makes the pull request title the only commit that counts, so the title must follow the grammar, and a linter in CI must enforce it, because a grammar nobody enforces is noise.

**Semantic versioning.** `MAJOR.MINOR.PATCH`: MAJOR for incompatible changes to the public API, MINOR for backwards-compatible additions, PATCH for backwards-compatible fixes. A pre-release such as `2.0.0-rc.1` sorts before `2.0.0`. The important consequence is for consumers: a version range like `^2.3.0` or Maven's `[2.3,3)` is a promise that any 2.x is a drop-in. That promise is only as good as the publisher's discipline, and for a deployed service with no library consumers the major number mostly tells humans "the contract changed"; the image that actually runs is identified by its commit SHA or digest (item 6.4).

**Tags and release notes.** A release is a tag on a commit the pipeline already verified. Use annotated tags (`git tag -a`): they are objects with an author, a date and a message, can be signed, and `git describe` finds them by default; lightweight tags are bare pointers. `git describe --tags` on any later commit prints `v2.0.0-1-g819fd39`, meaning one commit after `v2.0.0` at `819fd39`, which is the natural build version for snapshots. Release notes are written for the people who upgrade: what changed for them, what they must do, what broke. A generated changelog is the raw material, not the finished text.

**Release branches, when you really need them.** Trunk-based teams release from `main`. A release branch is justified when a version must be supported after `main` has moved on: an on-premise product with customers on 2.x while 3.x is developed, or a mobile client waiting for store review. Cut it from `main`, never merge it back, fix on `main` and cherry-pick to the branch, and tag releases on the branch. Every release branch you keep alive is a second place every fix has to land.

## Example: from commits to a version, with real output

A repository with one release and three commits after it:

```bash
$ git log --oneline
000f05c feat(api)!: require an Idempotency-Key header on POST /orders
6ff5fdd fix(pricing): round VAT per line instead of per order
0cbcbfc feat(export): add CSV export of invoices
726fa40 chore: initial project skeleton

$ git describe --tags
v1.0.0-3-g000f05c
```

The third commit's full message, with the footer that a release tool reads:

```text
feat(api)!: require an Idempotency-Key header on POST /orders

BREAKING CHANGE: clients that omit the header now receive 400 Bad Request.
```

Deriving the version by hand, exactly as `semantic-release` or `release-please` would: one `fix` (patch), one `feat` (minor), one breaking change (major). The highest wins, so `1.0.0` becomes `2.0.0`. The changelog is the subjects since the last tag, grouped by type:

```bash
$ git log v1.0.0..HEAD --pretty=format:'- %s'
- feat(api)!: require an Idempotency-Key header on POST /orders
- fix(pricing): round VAT per line instead of per order
- feat(export): add CSV export of invoices
```

Tagging the release and checking what the tag is:

```bash
$ git tag -a v2.0.0 -m "Release 2.0.0"
$ git tag -n1
v1.0.0          First production release
v2.0.0          Release 2.0.0
$ git cat-file -t v2.0.0
tag
$ git describe --tags
v2.0.0
```

One more commit on `main` and `git describe --tags` prints `v2.0.0-1-g819fd39`: the next deploy from `main` is "2.0.0 plus one commit", which is what a `/actuator/info` endpoint should report, next to the commit SHA.

The pull request that carried the breaking commit would look like this in its description:

```text
Require an Idempotency-Key header on POST /orders

Problem: retried POSTs after a timeout create duplicate orders (incident 2026-09-14).
Change: reject POST /orders without an Idempotency-Key with 400; store the key for 24 h
        and return the original response on a repeat.
Not done here: the client library change ships in orders-client 3.0 (separate PR, stacked on this one).
Tested: IdempotencyFilterIT covers first call, repeat, expired key and a different body under the same key.
Rollout: flag idempotency-required, off by default (item 1.1); enable per client after they upgrade.
```

A reviewer can judge the design from the description before reading a line of code, and the ticket, the incident and the follow-up are all one click away.

## Pitfalls

- The 40-file pull request that "had to be one change". It almost never had to be; the refactor, the feature and the test fixture change can land as three. If a reviewer asks for a split, the author lost less time than the reviewer would have spent.
- Review comments about formatting. A formatter and a linter in CI settle those; human review time goes to design, naming, missing tests and failure modes.
- Conventional Commits without enforcement. After three months, half the commits say `fixed stuff` and the generated changelog is useless. Lint the pull request title in CI and squash-merge, or lint every commit.
- Bumping the major version for an internal refactor, or not bumping it for a removed endpoint. The number is a message to consumers; sending the wrong message is worse than sending none.
- Lightweight tags for releases. No date, no author, no signature, invisible to `git describe` without `--tags`; and anyone can move them silently.
- Tagging before the pipeline is green. The tag names a commit; if that commit fails verification you now have a published version that was never built.
- A release branch that is merged back into `main`. Conflicts, duplicated commits and a history nobody can read; cherry-pick from `main` to the branch instead.
- Version in `pom.xml` that disagrees with the tag. Let the release tool set both from one source, or derive the version from `git describe` at build time.

## Check yourself

1. Which of these commits, alone, would change `3.4.1` to `3.5.0`, to `3.4.2`, and to `4.0.0`: `fix(auth): expire sessions on password change`, `feat(auth)!: drop the legacy /login form`, `feat(report): add PDF export`? What happens when all three are in the same release?
2. A pull request contains an extracted interface, a new implementation behind it and a configuration switch. Describe how you would stack it into three pull requests and what each reviewer sees.
3. Why does `git describe --tags` on a commit after a release give a better build identifier than the version in `pom.xml`, and what does `-3-g000f05c` mean?
4. Your team squash-merges. Where must the Conventional Commits grammar be enforced for a changelog generator to work, and why is enforcing it on individual commits not enough?

## Go deeper

- [Google: Code Review Developer Guide](https://google.github.io/eng-practices/review/) · both halves, the reviewer's standard and how to write a change that gets reviewed; short and precise.
- [Conventional Commits](https://www.conventionalcommits.org/) · the full grammar, including how `!` and `BREAKING CHANGE` interact with semantic versioning.
- [Semantic Versioning](https://semver.org/) · the specification, including pre-release and build metadata ordering rules.
- [Trunk Based Development](https://trunkbaseddevelopment.com/) · the release-branch pattern for trunk-based teams, with the cherry-pick rule.

---

Part of [DevOps & Delivery](../README.md) · items 1.2, 1.3
