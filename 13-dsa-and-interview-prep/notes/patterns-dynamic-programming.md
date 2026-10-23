# Patterns: dynamic programming

> **In one sentence:** Dynamic programming is recursion over a problem whose answer for a state depends only on the answers for smaller states, with each state computed once; find the state, write the recurrence, memoise it, then turn it into a table and shrink the table if the recurrence only looks back a step or a row.

**Why it matters:** DP is where most preparation stalls and where the hard half of "medium" problems lives. It is also a transferable skill: edit distance is how diff tools and fuzzy matching work, knapsack-style DP is resource allocation, and LCS is behind three-way merges. The interview skill is not having memorised fifty problems; it is a procedure that takes you from an exponential brute force to O(states × transitions) in a few minutes.

## The idea

**Recognising DP.** The question asks for a minimum or maximum cost, the number of ways, the longest or shortest something, or whether a target is reachable, over a sequence of choices. The brute force is a recursion with several branches per step, so it is exponential, and when you draw its tree the same subproblem appears many times (overlapping subproblems). The optimal answer is built from optimal answers to smaller instances (optimal substructure). A greedy choice is tempting but you cannot prove it: Coin Change with coins `{1, 3, 4}` and amount 6 is the standard counterexample (greedy takes `4 + 1 + 1`, optimal is `3 + 3`).

**The procedure.**

1. **Define the state.** The smallest set of parameters that determines the answer to a subproblem: an index, two indices, an index plus a remaining capacity. If two different partial histories lead to the same parameters and the same remaining problem, the parameters are a state.
2. **Write the recurrence** by looking at the last (or first) decision: what choices exist, what smaller state each choice leads to, how to combine them (`min`, `max`, `+`, or `||`).
3. **Base cases**, including the empty case, which is usually where the table has its extra row or column.
4. **Memoise top-down.** Wrap the recursion with a cache keyed by the state (an array, with `null` or a sentinel for "not yet computed").
5. **Convert to bottom-up** by computing states in an order where every dependency is already filled, usually increasing index.
6. **Optimise space.** If state `i` depends only on `i - 1` and `i - 2`, keep two variables; if row `i` depends only on row `i - 1`, keep two rows.

**One dimension or two.** A single index or amount (Climbing Stairs, House Robber, Coin Change, Longest Increasing Subsequence, Decode Ways) gives a 1-D table. Two sequences (Longest Common Subsequence, Edit Distance), a grid (Unique Paths), or an index plus a capacity (0/1 Knapsack, Partition Equal Subset Sum) give a 2-D table, often reducible to one row.

**Complexity.** Number of states times the work per state: O(n) for Climbing Stairs and House Robber, O(amount · coins) for Coin Change, O(m · n) for LCS, O(n^2) for the simple LIS. Space is the table size before optimisation, plus recursion depth for top-down.

## Example: Climbing Stairs (70) and House Robber (198), one dimension

Climbing Stairs: the number of ways to reach step `n` is the ways to reach `n - 1` plus the ways to reach `n - 2`, because the last move was one step or two. The table only looks back twice, so two variables replace it.

```java
public final class OneDimensional {

    public int climbStairs(int stepCount) {
        int waysToReachTwoBack = 1;
        int waysToReachPrevious = 1;
        for (int step = 2; step <= stepCount; step++) {
            int waysToReachHere = waysToReachPrevious + waysToReachTwoBack;
            waysToReachTwoBack = waysToReachPrevious;
            waysToReachPrevious = waysToReachHere;
        }
        return waysToReachPrevious;
    }

    public int rob(int[] houses) {
        int bestUpToTwoBack = 0;
        int bestUpToPrevious = 0;
        for (int value : houses) {
            int bestUpToHere = Math.max(bestUpToPrevious, bestUpToTwoBack + value);
            bestUpToTwoBack = bestUpToPrevious;
            bestUpToPrevious = bestUpToHere;
        }
        return bestUpToPrevious;
    }
}
```

House Robber: for each house, either skip it (best so far) or rob it (its value plus the best up to two houses back). `rob(new int[] {2, 7, 9, 3, 1})` returns 12 (houses 2, 9 and 1). `climbStairs(5)` returns 8. Both are O(n) time and O(1) space.

## Example: Coin Change (322), top-down and then bottom-up

Fewest coins to make `amount`, or -1. State: the remaining amount. Recurrence: `fewest(remaining) = 1 + min over coins of fewest(remaining - coin)`, taking only coins that fit and sub-results that are reachable.

```java
import java.util.Arrays;

public final class CoinChange {

    public int coinChangeTopDown(int[] coins, int amount) {
        return fewestCoins(coins, amount, new Integer[amount + 1]);
    }

    private int fewestCoins(int[] coins, int remaining, Integer[] fewestByAmount) {
        if (remaining == 0) {
            return 0;
        }
        if (fewestByAmount[remaining] != null) {
            return fewestByAmount[remaining];
        }
        int best = -1;
        for (int coin : coins) {
            if (coin > remaining) {
                continue;
            }
            int fewestForRest = fewestCoins(coins, remaining - coin, fewestByAmount);
            if (fewestForRest >= 0 && (best == -1 || fewestForRest + 1 < best)) {
                best = fewestForRest + 1;
            }
        }
        fewestByAmount[remaining] = best;
        return best;
    }

    public int coinChangeBottomUp(int[] coins, int amount) {
        int unreachable = amount + 1;
        int[] fewestCoinsFor = new int[amount + 1];
        Arrays.fill(fewestCoinsFor, unreachable);
        fewestCoinsFor[0] = 0;
        for (int subAmount = 1; subAmount <= amount; subAmount++) {
            for (int coin : coins) {
                if (coin <= subAmount) {
                    fewestCoinsFor[subAmount] = Math.min(fewestCoinsFor[subAmount], fewestCoinsFor[subAmount - coin] + 1);
                }
            }
        }
        return fewestCoinsFor[amount] == unreachable ? -1 : fewestCoinsFor[amount];
    }
}
```

Both return 3 for coins `{1, 2, 5}` and amount 11, and -1 for coins `{2}` and amount 3. The conversion is mechanical: the memo array becomes the table, the recursive call becomes a table lookup, and the loop runs in the order the recursion would have filled the cache (small amounts first). The bottom-up sentinel is `amount + 1`, never `Integer.MAX_VALUE`, because the recurrence adds 1 to it and `Integer.MAX_VALUE + 1` is negative. Both versions are O(amount · coins) time; top-down also uses O(amount) stack, which is fine for the problem's limit of 10^4.

## Example: Longest Common Subsequence (1143), two dimensions

State: `(firstIndex, secondIndex)`, the LCS of the first `firstIndex` characters of one string and the first `secondIndex` of the other. If the last characters match, extend the diagonal; otherwise drop one character from either string and take the better result. Row 0 and column 0 are the empty-prefix base cases.

```java
public final class LongestCommonSubsequence {

    public int longestCommonSubsequence(String first, String second) {
        int[][] lcsLength = new int[first.length() + 1][second.length() + 1];
        for (int firstIndex = 1; firstIndex <= first.length(); firstIndex++) {
            for (int secondIndex = 1; secondIndex <= second.length(); secondIndex++) {
                if (first.charAt(firstIndex - 1) == second.charAt(secondIndex - 1)) {
                    lcsLength[firstIndex][secondIndex] = lcsLength[firstIndex - 1][secondIndex - 1] + 1;
                } else {
                    lcsLength[firstIndex][secondIndex] =
                            Math.max(lcsLength[firstIndex - 1][secondIndex], lcsLength[firstIndex][secondIndex - 1]);
                }
            }
        }
        return lcsLength[first.length()][second.length()];
    }
}
```

The table for `"abcde"` and `"ace"`:

```text
        ""  a  c  e
   ""    0  0  0  0
   a     0  1  1  1
   b     0  1  1  1
   c     0  1  2  2
   d     0  1  2  2
   e     0  1  2  3
```

The answer is the bottom-right cell, 3. Every cell depends only on the row above and the cell to its left, so two rows (or one row plus one saved diagonal value) suffice, bringing space from O(m · n) to O(min(m, n)). Edit Distance (72) is the same table with three neighbours and a `+ 1` for insert, delete and replace.

## Example: Longest Increasing Subsequence (300)

State: the length of the longest increasing subsequence that *ends at* index `end`. Every earlier index with a smaller value can precede it.

```java
import java.util.Arrays;

public final class LongestIncreasingSubsequence {

    public int lengthOfLIS(int[] numbers) {
        int[] longestEndingAt = new int[numbers.length];
        Arrays.fill(longestEndingAt, 1);
        int best = 0;
        for (int end = 0; end < numbers.length; end++) {
            for (int earlier = 0; earlier < end; earlier++) {
                if (numbers[earlier] < numbers[end]) {
                    longestEndingAt[end] = Math.max(longestEndingAt[end], longestEndingAt[earlier] + 1);
                }
            }
            best = Math.max(best, longestEndingAt[end]);
        }
        return best;
    }
}
```

`[10, 9, 2, 5, 3, 7, 101, 18]` gives 4. Note that the answer is the maximum over the table, not the last cell, because the subsequence can end anywhere. This is O(n^2); the O(n log n) version keeps an array of "smallest tail of an increasing subsequence of each length" and places each number with a binary search (item 2.5), which is the follow-up interviewers ask for.

## Pitfalls

- A state that is too small. If the answer for `(index)` secretly depends on what was chosen before, add that to the state; the symptom is a wrong answer that is impossible to fix by tweaking the recurrence.
- Filling the table in an order that reads cells not yet computed. Iterating amounts downwards in Coin Change reads zeros and returns nonsense; the bottom-up order must follow the dependencies.
- `Integer.MAX_VALUE` as "infinity" in a recurrence that adds to it. Use `amount + 1`, or check for the sentinel before adding.
- Counting problems that overflow `int`. Use `long`, or apply the modulus the problem specifies at every addition.
- A memo keyed by string concatenation of indices (`"1" + "12"` equals `"11" + "2"`). Use a 2-D array or a record.
- Returning from the recursion without writing to the memo on some path. Every `return` after the base cases must store its result first.
- Subsequence versus subarray. A subsequence skips elements (LIS, LCS); a subarray or substring is contiguous (Maximum Subarray, which is Kadane's algorithm, not LIS).
- Space-optimised knapsack in the wrong direction. 0/1 knapsack must iterate capacity downwards so each item is used at most once; unbounded knapsack (Coin Change) iterates upwards.

## Check yourself

1. Why is "the remaining amount" a sufficient state for Coin Change, while "the current index in the coins array" alone is not? What problem does the state `(index, remaining)` solve instead?
2. Convert the top-down `fewestCoins` into the bottom-up loop by hand: which line becomes the table, which becomes the lookup, and why does the loop go from 1 to `amount`?
3. In the LCS table, which cells does `lcsLength[3][2]` depend on, and what does it mean in words for `"abcde"` and `"ace"`?
4. House Robber II (213) arranges the houses in a circle. How do you reduce it to two calls of the linear `rob`, and why does that work?

## Go deeper

- [Tech Interview Handbook: Dynamic programming cheatsheet](https://www.techinterviewhandbook.org/algorithms/dynamic-programming/) · the common DP shapes and the problems to practise, grouped by state design.
- [Aditya Verma: Dynamic Programming playlist](https://www.youtube.com/playlist?list=PL_z_8CaSLPWekqhdCPmFohncHwz8TY2Go) · builds each family (knapsack, subsequence, interval) from the recursion to the table with the same procedure as above.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the 1-D DP and 2-D DP nodes, each with video solutions for the problems in this note.
- [MIT 6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/) · the dynamic programming lectures formalise "subproblems, relate, topological order, base, original, time" as a checklist.

---

Part of [DSA & Interviews](../README.md) · items 5.3, 5.4
