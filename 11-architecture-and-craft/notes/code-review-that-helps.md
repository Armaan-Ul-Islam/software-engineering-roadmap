# Code review that helps: what to look for, how to say it, how to take it

> **In one sentence:** A review exists to improve the change and spread knowledge, so look for problems in order of how expensive they are to fix later (correctness, design, tests, readability, style last), say what you see as a reasoned suggestion or a question with its severity marked, keep changes small and turnaround short, and treat receiving review as a skill in its own right.

**Why it matters:** Code review is the most frequent engineering conversation you will have, and the one where tone problems compound fastest. Teams with slow or nitpicking reviews ship slowly and lose people; teams with rubber-stamp reviews ship bugs that four people approved. Google's standard is the one to internalise: approve a change once it definitely improves the overall health of the code, even if it is not perfect.

## The idea

**What to look for, in order.** Spend attention where a miss costs most.

1. Correctness. Read the description and the ticket first, then ask whether the code does that. Edge cases (empty, null, maximum), error paths, concurrency, input handling and authorisation, migrations that can fail half-way, queries without bounds. Pull the branch and run it when the change is more than trivial.
2. Design. Does it fit the system's structure and boundaries (items 7.2 and 7.3)? Is it in the right place? Does it add coupling or a premature abstraction (item 2.2)? Could it be simpler?
3. Tests. Is the changed behaviour covered? Do the tests assert behaviour rather than implementation (item 5.2)? Would they fail if the code were wrong?
4. Readability. Names (item 1.1), function size, comments that explain why, control flow a newcomer could follow.
5. Style and formatting. Last, and ideally never by a human: a formatter and a linter in CI settle these before review starts.

Also read the commit messages and the description: a reviewer should learn *why* from them, not reverse-engineer it from the diff.

**How to phrase a comment.** Comment on the code, not the author ("this method", not "you"). Give the reason, or the consequence, so the author learns something and can push back on the reasoning rather than on your authority. Offer a concrete alternative, and for small fixes use a suggestion block. Ask a question when you might be wrong; state a fact when you are sure (a bug is a bug). Mark the severity so the author knows what must change before merge and what is optional: `blocking`, `suggestion`, `nit`, `question`, `praise` is the Conventional Comments vocabulary and it works. Praise specific good decisions; it teaches as much as criticism and costs one line.

**Blocking versus non-blocking.** Block for correctness, security, data loss, and clear violations of agreed architecture or standards. Everything else is a suggestion the author may decline with a reason. "Approve with comments" is the right outcome when only nits remain; making the author wait another round for a variable name is how reviews become dreaded.

**Size and turnaround.** Small changes get better reviews: reviewers can hold a 200-line change in their head and find real bugs in it; at 1,000 lines they skim and approve. Split by commit or by stacked pull requests, each one a complete, tested step. Reviewers respond within a business day at the latest, ideally within hours, because a waiting change blocks a person. Authors help by describing what, why and how to test, by reviewing their own diff first, and by pushing fix-up commits during review rather than force-pushing a rewritten history that reviewers cannot diff against.

**Receiving review.** The comments are about the code. Assume good intent, ask for clarification before defending, and thank people for bugs found. If you disagree, explain once, with reasons; if the thread goes a third round, talk synchronously and write the outcome back into the thread. The reviewer is not always right, and "I did what the reviewer said" is not a defence for a change you do not understand. Reply to every comment, even if only "done", so the reviewer can see what changed.

**Redesign in review.** When the whole approach is wrong, say so in the first pass, at the top, before any line comments, and suggest a conversation. Then ask how it got this far: a design that gets rejected at review time should have been a design document (item 9.1) before the code.

## Example: three comments, rewritten

**On a line that indexes into a list.**

Unhelpful: *This is wrong.*

Helpful: *blocking: `orders.get(0)` throws `IndexOutOfBoundsException` when the customer has no orders, which is every new account (see `CustomerServiceTest.newCustomerHasNoOrders` for the setup). Could we return `Optional.empty()` here, or guard with `orders.isEmpty()`?*

What changed: the reader now knows what breaks, when, how to reproduce it, and two ways to fix it, and knows it must be fixed before merge.

**On a loop that searches a list of rules.**

Unhelpful: *Why didn't you use a Map here?*

Helpful: *suggestion (non-blocking): this loop with `if (rule.method() == method)` runs once per order; a `Map<ShippingMethod, ShippingCostRule>` built in the constructor would make the lookup direct and, more importantly, make the intent ("one rule per method") visible. Not a blocker at today's volumes, happy either way.*

What changed: the question that sounded like an accusation became a suggestion with a reason, a cost estimate, and explicit permission to decline.

**On a method named `processData`.**

Unhelpful: *Rename this.*

Helpful: *nit: `processData` does not tell me what comes out. From the body it computes the customers to remind about overdue invoices; something like `customersToRemindAboutOverdueInvoices` would let the next reader skip the body (item 1.1). Fine as a follow-up if you prefer.*

What changed: the author knows why the name matters, has a concrete candidate, and knows this will not hold up the merge.

## Pitfalls

- The nitpick storm: twenty comments on formatting and naming, none on the logic. The author fixes the twenty, the bug ships.
- The rubber stamp: "LGTM" ninety seconds after a 1,500-line change was opened. Four approvals of this kind add up to zero reviews.
- Redesign in review: challenging the fundamental approach after a week of implementation, in line comments, one at a time.
- Scope creep: "while you are here, could you also...". Open a ticket instead; the change under review should stay the change that was described.
- Ghosting: a change waits three days with no response. Say when you will get to it, or hand it to someone who can.
- The standoff: thirty comments between author and reviewer on one thread. After two rounds, talk, then summarise.
- "Approving to unblock": approval means you believe the change is good, not that you are tired.
- Reviewing the diff without the context. Open the IDE, look at the callers, run the tests. The diff shows what changed, not what it affects.
- Formatting debates with humans. Pick a formatter, run it in CI, and never discuss braces again.

## Check yourself

1. A 1,200-line change arrives. What do you do first, and what do you tell the author?
2. Order these by what you check first, and say why: a misnamed variable; a missing null check on an external API response; a test that asserts on mock interactions; inconsistent brace style.
3. You and the author still disagree after two rounds of comments. What is the next step, and what must happen in the thread afterwards?
4. Rewrite "Don't use exceptions for control flow here" as a helpful comment with a severity marker, a reason, and an alternative.

## Go deeper

- [Google: Code Review Developer Guide](https://google.github.io/eng-practices/review/) · the standard of review, what to look for, how to write comments, and how fast to respond; the reviewer's half of this note.
- [Google: The Change Author's Guide](https://google.github.io/eng-practices/review/developer/) · small changes, good descriptions and handling reviewer comments; the author's half.
- [Google: Small CLs](https://google.github.io/eng-practices/review/developer/small-cls.html) · why size is the single biggest lever on review quality, and how to split.
- [Conventional Comments](https://conventionalcomments.org/) · the `blocking`, `suggestion`, `nit`, `question`, `praise` labels and why severity in the comment itself helps both sides.
- [Michael Lynch: How to Do Code Reviews Like a Human](https://mtlynch.io/human-code-reviews-1/) · the phrasing techniques above, with before-and-after examples, in two parts.
- [Philipp Hauer: Code Review Guidelines for Humans](https://phauer.com/2018/code-review-guidelines/) · a practitioner's checklist for both roles, including the psychology of receiving feedback.

---

Part of [Architecture & Craft](../README.md) · item 9.4
