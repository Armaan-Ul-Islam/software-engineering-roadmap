# Patterns: two pointers and sliding window

> **In one sentence:** When the brute force is "every pair" or "every subarray", two indices that each only move forward (towards each other from the ends, or as the start and end of a window) cut O(n^2) to O(n), provided you can argue that the candidates each move skips can never be better.

**Why it matters:** These two patterns cover a large share of the array and string problems in NeetCode 150 and Grind 75, and they are the first thing an interviewer expects you to try when the input is sorted or the statement says "contiguous" or "substring". They are also the patterns people get almost right: the loop is short, and the bugs are in when to shrink the window and where to record the answer.

## The idea

**Recognising the pattern.**

| Cue in the statement | Pattern |
|---|---|
| sorted array, or you may sort; "pair with sum", "closest pair", "remove duplicates in place" | two pointers, opposite directions or same direction |
| palindrome, "container", "trapping water", partition around a value | two pointers, opposite directions |
| "contiguous subarray", "substring", "window of size k" | fixed-size sliding window |
| "longest/shortest substring such that", "at most k distinct", "contains all characters of" | variable-size sliding window with a frequency map |

**Opposite-direction pointers.** Start at both ends and move the pointer whose side cannot improve the answer. The proof obligation is a monotone argument: in a sorted array, if `values[leftIndex] + values[rightIndex] < target`, then every pair `(leftIndex, anything to the left of rightIndex)` is also too small, so `leftIndex` can be abandoned.

```java
int leftIndex = 0;
int rightIndex = values.length - 1;
while (leftIndex < rightIndex) {
    int sum = values[leftIndex] + values[rightIndex];
    if (sum == target) {
        return new int[] {leftIndex, rightIndex};
    }
    if (sum < target) {
        leftIndex++;
    } else {
        rightIndex--;
    }
}
```

**Same-direction pointers** (a reader and a writer) compact an array in place: the reader visits every element, the writer marks where the next kept element goes. Remove Duplicates from Sorted Array (26) and Move Zeroes (283) are this shape.

**Sliding window.** The window is `[windowStart, windowEnd]`. The end advances one step per iteration, adding an element to some window state (a sum, a count array, a map of frequencies). When the state says the window is invalid, the start advances until it is valid again. Both indices move at most `n` times, so the total is O(n) despite the inner `while`.

```java
int windowStart = 0;
for (int windowEnd = 0; windowEnd < input.length(); windowEnd++) {
    add(input.charAt(windowEnd));
    while (windowIsInvalid()) {
        remove(input.charAt(windowStart));
        windowStart++;
    }
    best = Math.max(best, windowEnd - windowStart + 1);
}
```

Two variants of the same template: for a **longest valid window**, record the length after shrinking (above); for a **shortest valid window**, the loop is `while (windowIsValid())`, you record inside it, then shrink. A **fixed window** of size `k` has no `while`: once `windowEnd >= k - 1`, record, then remove `input[windowEnd - k + 1]`.

The window works only when validity is monotone: if a window is invalid, every larger window containing it must also be invalid (or the mirror statement for "valid"). "Sum of a subarray equals k" with negative numbers breaks that, because adding an element can make the sum go down; use prefix sums instead (item 2.1).

**When a frequency map joins the window.** As soon as validity is about characters (distinct count, "contains all of"), keep counts per character and one or two integers derived from them (`distinctInWindow`, `distinctSatisfied`) so the validity check is O(1) instead of a scan of the map.

**Complexity.** Every solution in this note is O(n) time. Two pointers use O(1) extra space; windows use O(k) for the alphabet or the number of distinct keys.

## Example: Two Sum II and Container With Most Water (opposite directions)

Two Sum II (167) is the template above on a sorted array with 1-based indices in the answer: return `new int[] {leftIndex + 1, rightIndex + 1}`.

Container With Most Water (11) uses the same loop with a different reason to move: the area is `width * min(leftHeight, rightHeight)`, so moving the taller side can only shrink the width without raising the limiting height. Always move the shorter side.

```java
public int maxArea(int[] heights) {
    int leftIndex = 0;
    int rightIndex = heights.length - 1;
    int best = 0;
    while (leftIndex < rightIndex) {
        int area = (rightIndex - leftIndex) * Math.min(heights[leftIndex], heights[rightIndex]);
        best = Math.max(best, area);
        if (heights[leftIndex] < heights[rightIndex]) {
            leftIndex++;
        } else {
            rightIndex--;
        }
    }
    return best;
}
```

For `[1, 8, 6, 2, 5, 4, 8, 3, 7]` the loop computes the areas 8, 49, 18, 40, 16, 15, 4 and 6, and returns 49.

## Example: Longest Substring Without Repeating Characters (3)

Longest valid window; the window is invalid when the character just added is already inside it.

```java
import java.util.HashSet;
import java.util.Set;

public final class LongestSubstringWithoutRepeating {

    public int lengthOfLongestSubstring(String input) {
        Set<Character> inWindow = new HashSet<>();
        int best = 0;
        int windowStart = 0;
        for (int windowEnd = 0; windowEnd < input.length(); windowEnd++) {
            char added = input.charAt(windowEnd);
            while (inWindow.contains(added)) {
                inWindow.remove(input.charAt(windowStart));
                windowStart++;
            }
            inWindow.add(added);
            best = Math.max(best, windowEnd - windowStart + 1);
        }
        return best;
    }
}
```

`"abcabcbb"` gives 3, `"bbbbb"` gives 1, `"pwwkew"` gives 3, `""` gives 0. A faster variant stores the last index of each character in an `int[128]` and jumps `windowStart` straight past the previous occurrence instead of shrinking one step at a time; same complexity, fewer operations.

## Example: Minimum Window Substring (76)

Shortest valid window with a frequency map. The window is valid when every character of the pattern is present at least as often as required. Rather than comparing two maps on every step, keep `distinctSatisfied`, the number of distinct pattern characters whose required count the window currently meets.

```java
import java.util.HashMap;
import java.util.Map;

public final class MinimumWindowSubstring {

    public String minWindow(String source, String pattern) {
        if (pattern.isEmpty() || source.length() < pattern.length()) {
            return "";
        }
        Map<Character, Integer> required = new HashMap<>();
        for (char character : pattern.toCharArray()) {
            required.merge(character, 1, Integer::sum);
        }
        Map<Character, Integer> windowCounts = new HashMap<>();
        int distinctRequired = required.size();
        int distinctSatisfied = 0;
        int bestStart = 0;
        int bestLength = Integer.MAX_VALUE;
        int windowStart = 0;
        for (int windowEnd = 0; windowEnd < source.length(); windowEnd++) {
            char added = source.charAt(windowEnd);
            if (required.containsKey(added)) {
                int count = windowCounts.merge(added, 1, Integer::sum);
                if (count == required.get(added)) {
                    distinctSatisfied++;
                }
            }
            while (distinctSatisfied == distinctRequired) {
                if (windowEnd - windowStart + 1 < bestLength) {
                    bestLength = windowEnd - windowStart + 1;
                    bestStart = windowStart;
                }
                char removed = source.charAt(windowStart);
                if (required.containsKey(removed)) {
                    int count = windowCounts.merge(removed, -1, Integer::sum);
                    if (count < required.get(removed)) {
                        distinctSatisfied--;
                    }
                }
                windowStart++;
            }
        }
        return bestLength == Integer.MAX_VALUE ? "" : source.substring(bestStart, bestStart + bestLength);
    }
}
```

`minWindow("ADOBECODEBANC", "ABC")` returns `"BANC"`; `minWindow("a", "aa")` returns `""`. Note that `count` is an `int`, so `count == required.get(added)` unboxes and compares values. Comparing two `Integer` objects from the maps with `==` would work for counts up to 127 and silently fail above (item 6.2).

## Pitfalls

- Using a window where validity is not monotone (subarray sums with negative numbers). The symptom is a wrong answer on a hand-made example with a negative in the middle, and the fix is prefix sums or a different pattern.
- Shrinking with `if` instead of `while`. One step of shrinking is not always enough to restore validity.
- Recording the answer at the wrong point: after shrinking for "longest", inside the valid loop for "shortest". Swapping them gives off-by-one lengths that pass the easy examples.
- Window length is `windowEnd - windowStart + 1`. Forgetting the `+ 1` is the most common bug in this family.
- Updating the state when adding but not when removing (or the reverse). The `distinctSatisfied` counter must be decremented at exactly the moment a count drops below the requirement, not below zero.
- Comparing boxed `Integer` counts with `==`.
- Moving the wrong pointer in Container With Most Water (moving the taller side) or moving both when equal; with equal heights either side is fine, but move only one.

## Check yourself

1. In the minimum-window code, why is `distinctSatisfied` incremented only when `count == required.get(added)` and not when `count >= required.get(added)`?
2. Given "longest subarray with sum at most k" over non-negative integers, write the window's invalid condition and the point where you record the answer. What changes if the array may contain negatives?
3. Why is moving the shorter line in Container With Most Water safe? State the claim that justifies skipping all the pairs you never evaluate.
4. Both indices only move forward, yet the sliding-window code has a `while` inside a `for`. How many times can the body of the `while` run over the whole execution, and why?

## Go deeper

- [LeetCode Patterns (Sean Prashad)](https://seanprashad.com/leetcode-patterns/) · problems grouped by pattern; filter by "Two Pointers" and "Sliding Window" for a progression.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Two Pointers and Sliding Window nodes, each with a video walkthrough of the problems in this note.
- [Tech Interview Handbook: Array cheatsheet](https://www.techinterviewhandbook.org/algorithms/array/) · the cues and corner cases for array problems, including these two patterns.

---

Part of [DSA & Interviews](../README.md) · items 2.2, 2.3
