# Patterns: backtracking

> **In one sentence:** Backtracking is depth-first search over partial solutions: at each step choose an option, recurse to explore what follows, then undo the choice; pruning (abandoning a partial solution as soon as it cannot succeed) and a rule for skipping duplicate choices are what make it fast enough.

**Why it matters:** Any "generate all", "find every combination" or "is there an assignment such that" question is backtracking: subsets, permutations, Sudoku, N-Queens, Word Search, and at work the combinatorial test matrix or the constraint solver you write once a decade. It is also the raw form that dynamic programming refines, so understanding the recursion tree here makes DP (items 5.3 and 5.4) much easier.

## The idea

**Recognising the pattern.** "All possible", "generate", "return all combinations/permutations/subsets", "place/assign so that no two ...", "does a path exist using each cell at most once", together with small limits (n up to about 10 for subsets and permutations, 15 to 20 for pruned searches). When the output itself is exponential in size, there is no polynomial algorithm to look for; the question is how cleanly you enumerate.

**The template.** Three lines per level: choose, explore, unchoose.

```java
private void backtrack(List<Integer> partial, List<List<Integer>> results) {
    if (isComplete(partial)) {
        results.add(new ArrayList<>(partial));
        return;
    }
    for (int candidate : candidatesFor(partial)) {
        if (!canStillSucceed(partial, candidate)) {
            continue;
        }
        partial.add(candidate);
        backtrack(partial, results);
        partial.remove(partial.size() - 1);
    }
}
```

The `partial` list is shared across the whole search and mutated in place, which is why it is copied when recorded and why every `add` must be paired with a `remove`.

**The choices that distinguish the problems.**

- **Order matters or not.** Subsets and combinations pass a `start` index and only look forward, so `{1, 2}` and `{2, 1}` are generated once. Permutations consider every unused element at every level and track them with a `boolean[] used`.
- **Reuse allowed or not.** Recurse with `index` to allow the same element again (Combination Sum), with `index + 1` to forbid it (Subsets, Combination Sum II).
- **Duplicates in the input.** Sort first, then skip a candidate equal to the previous one at the same level: `if (index > start && candidates[index] == candidates[index - 1]) continue;` for subsets and combinations, `if (index > 0 && numbers[index] == numbers[index - 1] && !used[index - 1]) continue;` for permutations.
- **Pruning.** With sorted candidates, `break` as soon as a candidate exceeds the remaining target; in a grid, fail fast on a mismatched letter before recursing.
- **Grids.** Mark the cell in place (overwrite with a sentinel), recurse, restore it. No separate visited structure needed.

**Complexity.** Subsets: O(n · 2^n) (2^n subsets, each copied in O(n)). Permutations: O(n · n!). Combination Sum: exponential in `target / smallestCandidate`, bounded by pruning. Word Search: O(rows · columns · 3^L) for a word of length L, since each step has at most three new directions.

## Example: Subsets (78) and Permutations (46)

```java
import java.util.ArrayList;
import java.util.List;

public final class SubsetsAndPermutations {

    public List<List<Integer>> subsets(int[] numbers) {
        List<List<Integer>> results = new ArrayList<>();
        collectSubsets(numbers, 0, new ArrayList<>(), results);
        return results;
    }

    private void collectSubsets(int[] numbers, int start, List<Integer> partial, List<List<Integer>> results) {
        results.add(new ArrayList<>(partial));
        for (int index = start; index < numbers.length; index++) {
            partial.add(numbers[index]);
            collectSubsets(numbers, index + 1, partial, results);
            partial.remove(partial.size() - 1);
        }
    }

    public List<List<Integer>> permute(int[] numbers) {
        List<List<Integer>> results = new ArrayList<>();
        collectPermutations(numbers, new boolean[numbers.length], new ArrayList<>(), results);
        return results;
    }

    private void collectPermutations(int[] numbers, boolean[] used, List<Integer> partial, List<List<Integer>> results) {
        if (partial.size() == numbers.length) {
            results.add(new ArrayList<>(partial));
            return;
        }
        for (int index = 0; index < numbers.length; index++) {
            if (used[index]) {
                continue;
            }
            used[index] = true;
            partial.add(numbers[index]);
            collectPermutations(numbers, used, partial, results);
            partial.remove(partial.size() - 1);
            used[index] = false;
        }
    }
}
```

`subsets(new int[] {1, 2, 3})` produces `[], [1], [1, 2], [1, 2, 3], [1, 3], [2], [2, 3], [3]`, in the order the search visits them: every partial list is a valid subset, so it is recorded on entry rather than at a leaf. `permute(new int[] {1, 2, 3})` produces the six orderings starting with `[1, 2, 3]`. Note the two undo lines in `collectPermutations`; forgetting `used[index] = false` makes every later branch see the element as taken.

## Example: Combination Sum (39), reuse and pruning

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class CombinationSum {

    public List<List<Integer>> combinationSum(int[] candidates, int target) {
        Arrays.sort(candidates);
        List<List<Integer>> results = new ArrayList<>();
        collect(candidates, 0, target, new ArrayList<>(), results);
        return results;
    }

    private void collect(int[] candidates, int start, int remaining, List<Integer> partial, List<List<Integer>> results) {
        if (remaining == 0) {
            results.add(new ArrayList<>(partial));
            return;
        }
        for (int index = start; index < candidates.length; index++) {
            if (candidates[index] > remaining) {
                break;
            }
            partial.add(candidates[index]);
            collect(candidates, index, remaining - candidates[index], partial, results);
            partial.remove(partial.size() - 1);
        }
    }
}
```

`combinationSum(new int[] {2, 3, 6, 7}, 7)` returns `[[2, 2, 3], [7]]`. The recursive call passes `index`, not `index + 1`, so a candidate may be reused; the `start` index still prevents `[2, 3, 2]` from appearing as a second copy of `[2, 2, 3]`. Sorting makes the `break` valid: once one candidate exceeds `remaining`, all later ones do too.

## Example: Word Search (79), backtracking on a grid

```java
public final class WordSearch {

    public boolean exist(char[][] board, String word) {
        for (int row = 0; row < board.length; row++) {
            for (int column = 0; column < board[0].length; column++) {
                if (search(board, word, 0, row, column)) {
                    return true;
                }
            }
        }
        return false;
    }

    private boolean search(char[][] board, String word, int position, int row, int column) {
        if (position == word.length()) {
            return true;
        }
        if (row < 0 || row >= board.length || column < 0 || column >= board[0].length
                || board[row][column] != word.charAt(position)) {
            return false;
        }
        char letter = board[row][column];
        board[row][column] = '#';
        boolean found = search(board, word, position + 1, row + 1, column)
                || search(board, word, position + 1, row - 1, column)
                || search(board, word, position + 1, row, column + 1)
                || search(board, word, position + 1, row, column - 1);
        board[row][column] = letter;
        return found;
    }
}
```

On the board `ABCE / SFCS / ADEE`, `"ABCCED"` and `"SEE"` are found and `"ABCB"` is not, because the second B would need to reuse the first. The `'#'` marker is the "choose", the restore is the "unchoose", and the short-circuit `||` is the pruning: the first successful direction stops the search. The board must be restored even on success if the caller will search for more words; the code above does so because the restore runs before `return found`.

## Pitfalls

- Recording `partial` itself instead of a copy. Every entry in `results` is then the same list, which is empty by the end. `new ArrayList<>(partial)` every time.
- `partial.remove(value)` with an `Integer` argument. `List<Integer>.remove(int)` removes by position and `remove(Object)` by value; `partial.remove(partial.size() - 1)` is unambiguous, `partial.remove(numbers[index])` is a bug waiting for a value that happens to be a valid index.
- Forgetting one of the undo steps (`used[index] = false`, restoring the grid cell). The symptom is missing results after the first complete branch.
- Skipping duplicates without sorting. The skip condition compares neighbours and only works on sorted input.
- Using a `start` index for permutations, or `used[]` for subsets. The first loses orderings; the second generates each subset in every order.
- `index + 1` where reuse is allowed, or `index` where it is not. Test with the smallest input that distinguishes them (`{2}`, target 4).
- Forgetting the empty and single-element cases: `subsets` of an empty array is `[[]]`, `permute` of one element is `[[x]]`.

## Check yourself

1. Why does `collectSubsets` record a result on entry while `collectPermutations` records only when the partial list is full? What would change if you swapped them?
2. Subsets II (90) has duplicates in the input. Write the one skip condition you add, and explain why `index > start` is part of it rather than `index > 0`.
3. In Word Search, what goes wrong if you restore the cell only in the failure branch? Give a two-word test that exposes it.
4. Permutations II (47) can skip duplicates with `!used[index - 1]` or with `used[index - 1]`. Both produce the right set; which prunes more, and why?

## Go deeper

- [NeetCode roadmap](https://neetcode.io/roadmap) · the Backtracking node has every problem in this note plus N-Queens and Palindrome Partitioning, with video solutions.
- [Tech Interview Handbook: Recursion cheatsheet](https://www.techinterviewhandbook.org/algorithms/recursion/) · the recursion techniques and corner cases that backtracking builds on.
- [LeetCode Patterns (Sean Prashad)](https://seanprashad.com/leetcode-patterns/) · filter by "Backtracking" for a graded problem list.

---

Part of [DSA & Interviews](../README.md) · item 5.2
