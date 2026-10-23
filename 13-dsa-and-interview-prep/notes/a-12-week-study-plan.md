# A 12-week interview study plan

> **In one sentence:** Twelve weeks at roughly ten hours a week is enough to work through NeetCode 150 or Grind 75 by pattern, add system design and behavioural preparation in the second half, and arrive at the interviews rested; the plan below says what to do each week, how to review, and how to know you are ready.

**Why it matters:** Preparation fails in two ways: random problems with no pattern progression (so the hundredth problem feels as hard as the tenth), or an unsustainable burst that burns out before the interviews start. A written plan with review days, mock interviews and a mistakes log fixes both, and tracking it gives you a measurable readiness signal instead of a feeling.

## The idea

**One list, finished.** Pick NeetCode 150 (grouped by pattern, with a video solution for every problem) or Grind 75 (you choose weeks and hours, it orders problems by relevance and difficulty). Do not mix lists or hop platforms; the value is in finishing one.

**Patterns in blocks, then mixed.** Learn a pattern's template (items 2 to 5), solve five to eight problems of that pattern in a row, then move on. From week 9, every weekend set is drawn randomly from everything so far, because the interview will not tell you the pattern.

**Timebox and log.** Twenty-five minutes on a medium. If you are stuck at twenty-five, read the solution, understand it, close it, and re-solve from scratch the next day and again a week later. Keep a mistakes log with three columns: problem, what went wrong (did not recognise the pattern, a bug, wrong complexity, ran out of time), and the one sentence to remember. Review days are spent on the log, not on new problems.

**The weekly rhythm (about 10 hours).** Four weekday sessions of 90 minutes on the current pattern; a Saturday block of two hours for a timed set or a mock; a Sunday hour for the log and re-solving failures; one full day off. From week 5, system design practice (item 8.1, using the framework in the System Design roadmap) and behavioural work (item 9.1) are added inside the same budget, so the pace of new problems drops slightly.

**Mocks.** The first mock is in week 5, when you have enough patterns to be tested on. From week 9, one mock a week, alternating coding, design and behavioural, with a peer or a platform (item 7.3). Record yourself when you can and watch it back once: pacing and silence are invisible from the inside.

## Example: the plan as a table

Item numbers refer to this roadmap. "Problems" is new problems that week; re-solves from the log come on top.

| Week | Patterns and items | Problems | System design | Behavioural | Weekend |
|---|---|---|---|---|---|
| 1 | Protocol and complexity (1.1 to 1.4), arrays and hashing (2.1) | 10 | none | list your eight stories by title | timed set: 2 easy, 1 medium |
| 2 | Two pointers, sliding window (2.2, 2.3) | 10 | none | none | timed set |
| 3 | Stack, binary search (2.4, 2.5) | 10 | none | none | timed set |
| 4 | Linked lists, intervals, strings (3.1, 2.6, 2.7) | 8 | none | write stories 1 and 2 in STAR | review week: re-solve every logged failure from weeks 1 to 3 |
| 5 | Trees (3.2) | 10 | read the framework; one design | story 3 | first mock (coding) |
| 6 | Trees, heaps, tries (3.2, 3.3, 3.4) | 10 | one design | story 4 | mock (coding) |
| 7 | Graphs, topological sort (4.1, 4.2) | 10 | one design | story 5 | timed set |
| 8 | Backtracking, union-find, shortest paths (5.2, 3.5, 4.3) | 8 | one design | story 6 | review week |
| 9 | Dynamic programming, one dimension (5.3) | 10 | one design | stories 7 and 8 | mock (coding and behavioural) |
| 10 | Dynamic programming, two dimensions; greedy (5.4, 5.5) | 10 | one design | rehearse all eight aloud | mock (system design) |
| 11 | Mixed timed sets; bits and maths (5.6); Java idioms (6.1, 6.2) | 12 mixed | one design | mock behavioural with a peer | two mocks |
| 12 | Taper: re-solve the mistakes log, light mixed sets, rest | 6 | review your design notes | final run-through | rest before the first interview |

That is about 115 new problems, which is all of Grind 75 with time to spare or most of NeetCode 150 (skip the hard problems on the first pass and return to them in weeks 11 and 12 if the mediums are landing). Time budget: about 10 hours in weeks 1 to 4, 12 hours in weeks 5 to 10 when design and behavioural are added, 10 in week 11, and 6 in week 12.

## Example: week 7 in detail

- Monday (90 minutes): read the graph pattern note (items 4.1 and 4.2), then Number of Islands (200) and Max Area of Island (695).
- Tuesday (90 minutes): Rotting Oranges (994) and Clone Graph (133). Log that you forgot to mark cells visited on enqueue.
- Wednesday (90 minutes): Course Schedule (207) and Course Schedule II (210).
- Thursday (90 minutes): Pacific Atlantic Water Flow (417) and Surrounded Regions (130); re-solve Monday's logged failure if any.
- Friday: off.
- Saturday (2 hours): one timed set of two random mediums from weeks 1 to 6, then one 45-minute system design (a URL shortener or a rate limiter) against the framework, written up in one page.
- Sunday (60 minutes): read the week's log entries, re-solve the two weakest problems from memory, write story 5.

## Signs you are ready

- You solve an unseen medium from your list's patterns in 25 minutes about three times out of four, with a correct complexity statement, and you can name the pattern within the first three minutes.
- Two different mock interviewers have rated you "hire" or better in consecutive weeks.
- Each of your eight stories takes two to three minutes without notes and survives two follow-up questions.
- You can run a 45-minute design on a prompt you have not practised and reach a complete, consistent high-level design with the main trade-offs stated.
- Your mistakes log shows the same category of error no more than once in the last three weeks.

If you are still reading more than 40% of solutions in a timed set, or the same bug category recurs weekly, you are not ready yet; extend the plan by two to four weeks rather than scheduling the interviews and hoping.

## Pitfalls

- Switching lists or platforms midway. The sense of progress resets and the pattern coverage becomes uneven.
- Reading solutions without re-solving. Understanding a solution and producing it under time pressure are different skills; only the second one is tested.
- Only easies, or only hards. Mediums are what interviews ask; the plan is built around them.
- Counting hours instead of problems solved cold. Four hours of reading is not progress; two problems solved without hints is.
- Postponing mocks until you feel ready. Feeling ready is the output of mocks, not the input.
- Leaving behavioural preparation to the final week. Stories need rehearsal and the follow-up questions need thought.
- No rest day. Plateaus after week 6 are almost always fatigue; the fix is rest, not more hours.
- Starting the plan a week before the interviews. Then run a triage instead: the top patterns you already know, your eight stories, one mock, and sleep.
- Not scheduling interviews deliberately. Tell recruiters your timeline, put practice-run companies first and your top choice last.

## Check yourself

1. Why are weeks 4 and 8 review weeks with fewer new problems, and what exactly do you do in them that you would not do in a normal week?
2. Your week 9 mock goes badly on a sliding-window problem you solved correctly in week 2. What does that tell you, and what changes in the plan?
3. You have eight weeks and eight hours a week instead of twelve and ten. Which rows of the table do you merge or drop, and which do you keep untouched?
4. Which two signs from the readiness list are measurable without another person, and how would you measure them this week?

## Go deeper

- [Grind 75](https://www.techinterviewhandbook.org/grind75/) · set your weeks and hours and get the ordered list; it maps directly onto the table above.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the pattern-ordered list with video solutions; follow its graph top to bottom.
- [Tech Interview Handbook: Coding interview study plan](https://www.techinterviewhandbook.org/coding-interview-study-plan/) · a 3-month plan with the same structure and the reasoning behind the weekly rhythm.
- [Pramp](https://www.pramp.com/) and [interviewing.io](https://interviewing.io/) · peer and professional mock interviews for weeks 5 to 12.

---

Part of [DSA & Interviews](../README.md) · items 7.1, 7.2, 9.5
