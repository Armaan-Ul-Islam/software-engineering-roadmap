# Mock interviews and deliberate practice

> **In one sentence:** Solving problems is not practice unless each attempt is timeboxed, the mistake is named and logged, the problem is re-solved from memory on a schedule, and the whole performance (not just the code) is periodically tested under interview conditions with another person watching.

**Why it matters:** Most candidates who "did 300 problems" and still failed practised the wrong thing: they solved problems once, with no timer, reading the solution when stuck and never returning. Interviews test retrieval under time pressure while talking, which is a different skill from recognising a solution when you read it. Deliberate practice builds exactly that skill; mock interviews are its measuring instrument.

## The idea

**Deliberate practice has four parts.** Each is missing from the way most people grind.

1. **A timebox with a decision at the end.** Twenty-five minutes for a medium, forty for a hard. When the timer ends, you do one of two things: finish if you are coding a plan you believe in, or stop and study the solution. Never "just ten more minutes" indefinitely; the interview will not give you ten more minutes either.
2. **Studying a solution properly.** Read it until you can explain *why* it works and *what cue* in the problem statement points to it. Close it. Write it from scratch the same day. Then write one sentence in the log: the cue and the idea ("sorted plus 'pair that sums to' means two pointers from both ends"). Reading a solution and nodding is zero practice.
3. **Spaced repetition on the problem, not the pattern.** Re-solve a failed or hint-assisted problem from memory after one day, after one week and after one month. A problem that survives all three re-solves is done. A problem that fails any of them resets the schedule. This is the same spacing that makes flashcards work, applied to problems; it is cheap because re-solving a known problem takes ten minutes.
4. **A mistakes log with categories.** Every failure gets a category: did not recognise the pattern, wrong pattern, correct idea but a bug, correct code but wrong complexity, ran out of time while explaining, misread the problem. After two weeks the log shows your real weakness, which is almost never "I do not know enough algorithms". Review days are spent on the log, not on new problems (item 7.2 covers how review days fit the week).

**Mock interviews test what the log cannot see.** Thinking aloud while coding, asking clarifying questions, handling a hint without collapsing, pacing (two minutes of silence feels like ten to the interviewer), and recovering from a bug under observation. None of this is exercised when you solve alone. Sources of mocks, in order of realism:

- **A peer who is also preparing.** Alternate roles weekly; interviewing someone else teaches you what interviewers look for. Free, and the feedback improves as you both learn to give it.
- **A peer platform** such as Pramp, which pairs you with another candidate and provides the problem and a rubric.
- **A professional platform** such as interviewing.io, where the interviewer is an engineer at a hiring company; paid, but the feedback is closest to the real thing. Save these for the last four weeks.
- **A real interview at a company you do not mind losing.** Schedule one or two practice-run companies before your top choice.

**Record yourself and watch it back once.** Record the screen and audio of a mock (with the peer's consent) and watch it at 1.5x speed within a day. Pacing, filler words, silences, and the moment you stopped listening to the hint are invisible from the inside and obvious on the recording. One viewing per mock is enough; the point is to note two things to change, not to agonise.

**What to practise in the final two weeks.** Fewer new problems, more mixed timed sets, the log, and mocks. Stop learning new patterns a week before the first interview; from then on, practice is retrieval only.

## Example: a mistakes log and a mock rubric

The log is a plain text or spreadsheet file with five columns. The *cue* column is the one that does the teaching: it is what you will recognise next time.

| Date | Problem | Category | Cue to remember | Re-solve on |
|---|---|---|---|---|
| 02-03 | Longest Substring Without Repeating Characters | did not recognise the pattern | "longest substring with a constraint" means a variable sliding window with a last-seen map | 02-04, 02-10, 03-03 |
| 02-03 | Course Schedule | bug | forgot to loop over every node; started from node 0 only | 02-04, 02-10, 03-03 |
| 02-05 | Kth Largest Element | wrong complexity | sorted the array, O(n log n); the interviewer wanted the heap of size k or quickselect | 02-06, 02-12, 03-05 |
| 02-07 | Merge Intervals | ran out of time | spent 12 minutes deciding whether touching intervals overlap; ask that question first | 02-08, 02-14, 03-07 |
| 02-12 | Course Schedule (re-solve) | passed | | 03-03 |

After two weeks, count the categories. Three "did not recognise the pattern" entries for sliding window means a day on that pattern's template and five problems in a row; three "ran out of time" entries means the problem is pacing, which only mocks fix.

The mock rubric your peer fills in during the interview, scored 1 to 4, each with one sentence of evidence:

| Dimension | What a 4 looks like |
|---|---|
| Understanding | asked two or three clarifying questions, restated the problem with a small example, named the edge cases |
| Approach | named the pattern, said the complexity of the brute force, then the target, before writing code |
| Code | compiled in the head; full-word names; no long silences; tested by hand on the example |
| Communication | kept talking; said "I am thinking about X" during pauses; took the hint and used it |
| Debugging | found the bug by tracing, not by random edits |

Two consecutive mocks with every dimension at 3 or above from different interviewers is a readiness signal; the full list of signs is in [the 12-week study plan](a-12-week-study-plan.md).

A weekly loop that fits in the plan from item 7.2:

```text
Mon-Thu   90 min: 2 new problems on the current pattern, timeboxed; log every failure
Fri       off
Sat       120 min: timed set of 2 random mediums from past weeks, then (from week 5) one mock
Sun       60 min: re-solves due today from the log; watch the mock recording once; note 2 changes
```

## Pitfalls

- Solving without a timer. The feeling of "I could have done it with more time" is exactly what the interview removes; untimed solves do not transfer.
- Reading the solution at minute five. Struggle is where the pattern recognition forms; stay with it until the timebox ends.
- Logging "wrong answer" with no category or cue. The log must be reviewable; a list of problem names teaches nothing.
- Re-solving by re-reading. Re-solve means a blank editor and no notes; if you cannot start, that is data, and the schedule resets.
- Counting problems instead of cold solves. "I did 150" is not a readiness measure; "I solved 7 of the last 10 unseen mediums in 25 minutes" is.
- Postponing mocks until you feel ready. The first mock is always bad; schedule it in week 5 regardless (item 7.2), because feeling ready is what mocks produce, not what they require.
- Mocks with no rubric. "That went okay" is not feedback; ask the peer to score the five dimensions with evidence.
- Recording and never watching, or watching three times. Once, within a day, two notes.
- Practising only the coding round. Design and behavioural rounds need mocks too; alternate them from week 9.
- Grinding through fatigue. Plateaus after six weeks are usually tiredness; a rest day beats a longer session.

## Check yourself

1. Your log for the last two weeks shows six entries in "bug" and none in "did not recognise the pattern". What does that tell you, and what should next week's sessions look like?
2. Why does re-solving a problem after one day, one week and one month beat solving three new problems of the same pattern? When would the three new problems be the better choice?
3. You have one peer and no budget. Design a weekly mock arrangement that gives both of you interviewer practice as well as candidate practice, and say what the rubric should contain.
4. In a mock you went silent for three minutes and the interviewer gave a hint you did not use. Which rubric dimension dropped, and what concrete habit do you practise in the next two solo sessions to fix it?

## Go deeper

- [NeetCode roadmap](https://neetcode.io/roadmap) · the pattern-ordered list to draw timeboxed problems from, with a video solution to study once the timebox ends.
- [Pramp](https://www.pramp.com/) · free peer-to-peer mocks with a provided problem and rubric.
- [interviewing.io](https://interviewing.io/) · paid mocks with engineers from hiring companies; the recordings of past mocks on the site show what good and bad performances look like.
- [Tech Interview Handbook: Coding interview cheatsheet](https://www.techinterviewhandbook.org/coding-interview-cheatsheet/) · the behaviours the mock rubric above is checking, listed before, during and after the interview.

---

Part of [DSA & Interviews](../README.md) · items 1.5, 7.3
