# Behavioural interviews with STAR

> **In one sentence:** A behavioural interview asks for evidence of how you have actually behaved, so prepare six to eight true stories from the last few years, tell each as Situation, Task, Action, Result with numbers, and know which questions each story answers so you are never improvising under pressure.

**Why it matters:** At many companies the behavioural round carries the same weight as a coding round, and at some (Amazon's Leadership Principles loop is the best-known) it decides the level of the offer. Engineers under-prepare because it feels like "just talking", and the result is a rambling answer with no outcome, which an interviewer writes up as "low impact, unclear ownership". The same structure is also how you write a good incident report or promotion case.

## The idea

**STAR, with proportions.** In a two to three minute answer:

- **Situation (about 15%).** Two sentences of context: the team, the system, what was at stake. Enough for the listener to care, no more.
- **Task (about 10%).** What *you* were responsible for, as distinct from the team.
- **Action (about 55%).** What you did, in first person singular, as a sequence of decisions: what you considered, what you chose and why, who you talked to, what you rejected. This is the part interviewers score.
- **Result (about 20%).** What happened, with a number, and what you learned or changed afterwards. Many interviewers probe the learning explicitly, so prepare it.

**The eight stories to prepare.** One story often answers several question types; build a grid of question against story and make sure every row has two candidates.

| Story | Questions it answers | What a strong version contains |
|---|---|---|
| Conflict with a colleague | "a disagreement with a peer", "a difficult person" | their legitimate point, how you found common ground, the working relationship afterwards |
| A failure or mistake | "a time you failed", "a bug you shipped" | a real failure with real cost, what you did in the first hour, the systemic fix |
| Leadership without authority | "led a project", "influenced without being the manager" | how you aligned people who did not report to you, a decision you owned |
| Ambiguity | "an unclear problem", "requirements kept changing" | how you narrowed the problem, what you decided to ship first and why |
| Impact | "your proudest achievement", "the biggest thing you delivered" | a before and after metric, the trade-off you made to get it |
| Learning fast | "a time you had to learn something quickly" | the technique you used to learn (not just "I read the docs"), the time it took |
| Disagreeing with a manager | "disagreed with a decision", "pushed back on your lead" | the data you brought, how you disagreed respectfully, whether you committed afterwards |
| Tight deadline | "under pressure", "prioritisation" | what you cut, who you told, what you protected (quality, tests, on-call) |

**Making it concrete.** Replace adjectives with measurements: "improved performance" becomes "cut the p95 of the search endpoint from 1.8 s to 400 ms"; "a large migration" becomes "14 services, 3 teams, 6 weeks". Include sizes (requests per second, rows, users, team members), money, time and counts of incidents. If you do not have the exact figure, estimate and say "roughly". The number is what makes the story believable and memorable.

**Preparation that works.** Write each story as six to ten bullets, not a script, and rehearse aloud until it takes two to three minutes. Choose stories where you were the protagonist, from the last two or three years, and where something was genuinely difficult. Read the company's published values or principles and check that each is covered by at least one story.

**The follow-up questions.** Interviewers probe to test that the story is true and that you reflect. Expect: "What would you do differently?", "What was the other person's view?", "How did you decide between the options?", "What exactly did *you* do, as opposed to the team?", "What did your manager say?", "Did the fix hold?", "Tell me about another time." Prepare an answer to each for every story; a candidate who has a thoughtful "what I would do differently" ready scores higher than one whose story has no flaws.

## Example: a failure story, written out

The question is "Tell me about a time something you shipped caused a problem." The story below is an illustrative composite, not a real incident, but every sentence is the kind you should be able to say about your own work.

**Situation.** "I was on a five-person team that owned the payment service for a subscription product, about 200,000 charges a month. I owned the retry logic for failed card charges."

**Task.** "Failed charges were a top cause of churn, so my task was to add a smart retry schedule that re-attempted a failed charge at better times over a week, with the goal of recovering a meaningful share of them."

**Action.** "I designed the schedule around the provider's decline codes and built it as a scheduled job. I tested it against the provider's sandbox and our contract tests passed. What I missed was that my idempotency key for a retry included the attempt timestamp, so the provider treated every retry as a new charge instead of a repeat of the original one. In production, for the roughly one percent of customers whose first retry succeeded on a card that had also recovered by itself, that meant a double charge. Our duplicate-charge alert fired after about six hours and I was on call. In the first thirty minutes I paused the job and wrote the query that identified every affected charge: 212 customers. I paired with a colleague to issue refunds through the provider API that evening and drafted the customer email with support. The next day I wrote the incident report, then fixed the key to be derived from the original charge id and added a contract test that asserts the provider returns the same charge id for a retried key. I also lowered the duplicate-charge alert threshold so it would fire within fifteen minutes rather than six hours."

**Result.** "All 212 customers were refunded within 24 hours and we had no chargebacks. The retry feature then went live a week later and recovered about three percent of failed charges per month, which was the original goal. The contract test caught a similar key bug in another integration a year later. What I changed in how I work: I now treat idempotency keys as part of the API contract and test them explicitly, and before any release that touches money I ask 'how will we know within fifteen minutes if this is wrong'."

Likely probes and short answers: "Why did the tests not catch it?" (the sandbox accepted repeated keys without deduplicating; the contract test now encodes the real behaviour). "What did your manager say?" (they asked for the timeline and the fix, and we agreed to add a review step for anything touching charges). "Would you ship it again the same way?" (yes with the test and the alert; the schedule design was sound, the release process was not).

## Pitfalls

- "We" with no "I". The interviewer cannot tell what you did. Say "the team did X; my part was Y".
- No result, or a result with no number. "It went well" scores as nothing happened.
- A failure that is not a failure ("I cared too much", "I worked too hard"). Interviewers have heard it and mark it down. Pick a real mistake with a real cost and a real fix.
- Blaming the other person in the conflict story. Show their legitimate point and what you learned about working with them.
- Over three minutes without pausing. Give the headline, then the detail, and let them steer.
- A memorised script. Under a probe it collapses. Rehearse from bullets so you can jump to any part.
- Exaggeration. The follow-up questions exist to expose it, and one caught exaggeration taints every other answer.
- Ignoring the company's stated values. If they publish principles, they are scoring against them; map your stories to them before the interview.

## Check yourself

1. Take your most recent project and write the Result section in two sentences with at least two numbers. Which number would the interviewer find most convincing, and why?
2. For the failure story above, what would you answer to "what was the root cause: the code, the test, or the process?" and how does the answer change what you say you learned?
3. Which of your eight stories answers both "a conflict with a colleague" and "disagreeing with a manager"? If none does, what story are you missing?
4. An interviewer interrupts your Situation after thirty seconds with "so what did you do?". What does that tell you about your pacing, and how do you recover?

## Go deeper

- [Tech Interview Handbook: Behavioral interview](https://www.techinterviewhandbook.org/behavioral-interview/) · the preparation method and a question bank to run your stories against.
- [Tech Interview Handbook: Questions to ask](https://www.techinterviewhandbook.org/questions-to-ask/) · the other half of the behavioural round: what you ask tells them how you think about teams.
- [Cracking the Coding Interview](https://www.crackingthecodinginterview.com/) · paid; the behavioural chapter has the project grid technique that this note's story table is based on.

---

Part of [DSA & Interviews](../README.md) · item 9.1
