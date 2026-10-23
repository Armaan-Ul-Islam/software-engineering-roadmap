# A problem-solving protocol for coding interviews

> **In one sentence:** Run the same seven steps on every problem (understand, examples and edge cases, match a pattern, plan with complexity, implement, test by hand, evaluate), say what you are doing at each step, and treat hints as information rather than as failure.

**Why it matters:** Candidates who know the algorithm still fail because they start typing before they know what the input looks like, go silent for ten minutes, or never test what they wrote. Interviewers score the process as much as the result: a candidate who talks through a brute force, improves it with one hint and tests it by hand usually beats one who silently writes an optimal solution with an off-by-one error. The same protocol is also how you debug a production incident without flailing.

## The idea

A 45-minute interview has about 40 minutes of problem time. The protocol below gives each step a budget so that you notice when you are overspending.

1. **Understand (2 to 3 minutes).** Restate the problem in your own words and ask about what the statement leaves open: input size, value ranges, duplicates, whether the input is sorted, what to return when there is no answer, whether the input fits in memory. The size tells you the complexity you need: 10^5 elements means O(n log n) or better, 20 elements means exponential is fine.
2. **Examples and edge cases (2 to 3 minutes).** Write one normal example and two or three edge cases, with the expected output for each, before thinking about an algorithm. This is what you will test against later, so decide the answers now while you are not yet attached to a solution.
3. **Match a pattern (2 to 3 minutes).** Name the brute force first, then look for the cue words: sorted or pairs (two pointers, item 2.2), contiguous or substring (sliding window, item 2.3), "k largest" (heap, item 3.3), "number of ways" or "minimum cost" over choices (dynamic programming, items 5.3 and 5.4), "all combinations" (backtracking, item 5.2), grid or dependencies (graph, items 4.1 and 4.2).
4. **Plan with complexity (3 to 5 minutes).** State the approach in two or three sentences and its time and space complexity, then ask for agreement before coding. If the interviewer hesitates, that is a hint; take it now rather than after fifteen minutes of typing.
5. **Implement (15 to 20 minutes).** Write the code top-down, with full names, narrating intent ("I keep the index of each value I have seen so I can look up a complement in constant time"), not syntax ("now I create a hash map"). If you need a helper, write its signature and move on; fill it in after the main flow works.
6. **Test by hand (5 minutes).** Trace the normal example through the code line by line, tracking every variable on paper, then the edge cases. Reading the code and nodding is not testing.
7. **Evaluate (2 minutes).** State the final complexity, what you would improve with more time, and any assumption you made.

**Thinking aloud.** Narrate decisions, not keystrokes. Say what you are about to try and why, say when you reject an idea and why, and when you need to think, say "let me think about the shrinking condition for a moment" so silence is understood. If you are stuck, say what you are stuck on; a precise question gets a precise hint.

**Using hints.** A hint is the interviewer buying your time back. Acknowledge it, restate it in your own words to confirm you understood, connect it to your plan ("so if I sort first, the pairs become adjacent, which means two pointers"), and move on. Arguing with a hint, or ignoring it and continuing on the old path, is the most expensive mistake in the room.

**The edge-case checklist.** Run through it at step 2 and again at step 6:

| Category | Cases to write down |
|---|---|
| Size | empty input, one element, two elements, the maximum size in the constraints |
| Values | all equal, duplicates, negatives and zero, the minimum and maximum allowed value |
| Order | already sorted, reverse sorted, rotated |
| Answer | no valid answer, multiple valid answers, the answer is the whole input |
| Arithmetic | sums or products that overflow `int`, division by zero, `k` larger than `n` |
| Structure | `null` nodes, a tree that is a single path, a cycle in a linked structure, a disconnected graph |

## Example: the protocol applied to Two Sum (LeetCode 1)

Given an array of integers and a target, return the indices of the two numbers that add up to the target. Exactly one answer exists and you may not use the same element twice. What you say is in quotation marks.

**Understand.** "So I return two indices, not the values, and the same index cannot be used twice. Can the array contain negatives and duplicates? How large can it be? Are the values bounded?" The constraints say up to 10^4 elements, values between -10^9 and 10^9. "That rules out an O(n^2) solution being necessary, and the difference of two values fits in an `int`, so I do not need `long`."

**Examples and edge cases.** `[2, 7, 11, 15]` with target 9 gives `[0, 1]`. `[3, 3]` with target 6 gives `[0, 1]` and tests that a value is not paired with itself. `[-1, -2, -3, -4, -5]` with target -8 gives `[2, 4]` and tests negatives. Two elements is the smallest valid input.

**Match a pattern.** "Brute force is every pair, O(n^2). The question for each element is whether its complement, target minus the element, has appeared before. That is a lookup, so a hash map from value to index gives O(1) per element."

**Plan with complexity.** "One pass. For each element, compute the complement, check the map, and if it is there return the stored index and the current one; otherwise store the current value with its index. O(n) time, O(n) space. Shall I go ahead?"

**Implement.**

```java
import java.util.HashMap;
import java.util.Map;

public final class TwoSum {

    public int[] twoSum(int[] numbers, int target) {
        Map<Integer, Integer> indexByValue = new HashMap<>();
        for (int index = 0; index < numbers.length; index++) {
            int complement = target - numbers[index];
            Integer complementIndex = indexByValue.get(complement);
            if (complementIndex != null) {
                return new int[] {complementIndex, index};
            }
            indexByValue.put(numbers[index], index);
        }
        throw new IllegalArgumentException("no two numbers add up to " + target);
    }
}
```

"I check the map before inserting the current element, so an element can never match itself. The exception is for the case the problem says cannot happen; I would rather fail loudly than return a bogus pair."

**Test by hand.** `[2, 7, 11, 15]`, target 9: index 0, complement 7, not in the map, store 2 at 0. Index 1, complement 2, found at 0, return `[0, 1]`. Then `[3, 3]`, target 6: index 0, complement 3, the map is empty, store 3 at 0. Index 1, complement 3, found at 0, return `[0, 1]`. "If I had inserted before checking, index 0 would have matched itself here."

**Evaluate.** "O(n) time, O(n) extra space. If the array were sorted I could use two pointers in O(1) space, but sorting would lose the indices unless I sorted index pairs, which costs O(n log n). The hash map is the right trade here."

The whole exchange takes about fifteen minutes, which leaves time for the follow-up most interviewers have ready (three numbers summing to a target, or the sorted variant).

## Pitfalls

- Coding in the first minute. The symptom is a correct solution to a problem that was not asked (values returned instead of indices, a count instead of a list).
- Silence. Ten quiet minutes read as being lost even when you are not. Narrate the decision you are weighing.
- Treating a hint as a verdict. Interviewers give hints to everyone; what they score is how fast you integrate one.
- "Testing" by re-reading. Only a trace with actual values on paper finds the off-by-one, the unhandled `null`, and the self-match.
- Running out of time with no working code. If the optimal approach is not coming, write the brute force cleanly, say its complexity, and improve it from there; a working O(n^2) with a stated plan for O(n) scores far better than an empty editor.

## Check yourself

1. In the Two Sum solution, what breaks if you move the `put` above the `get`, and which edge case from the checklist catches it?
2. The interviewer says "what if the array were sorted?" halfway through your hash-map implementation. What do you say in the next thirty seconds?
3. You have fifteen minutes left and no idea how to get below O(n^2). What do you do with the time?
4. Which three clarifying questions would you ask for "find the longest substring with at most k distinct characters" and why does each one change the solution?

## Go deeper

- [Tech Interview Handbook: Coding interview cheatsheet](https://www.techinterviewhandbook.org/coding-interview-cheatsheet/) · the before, during and after checklist that this protocol condenses.
- [Tech Interview Handbook: Coding interview techniques](https://www.techinterviewhandbook.org/coding-interview-techniques/) · how to attack a problem you have not seen, with worked cues for each pattern.
- [Cracking the Coding Interview](https://www.crackingthecodinginterview.com/) · paid; the "BUD" optimisation walkthrough (bottlenecks, unnecessary work, duplicated work) complements step 3.

---

Part of [DSA & Interviews](../README.md) · items 1.1, 1.3, 1.4
