# Complexity analysis, fast

> **In one sentence:** You can read the time and space complexity of most interview code off its shape (sequential loops add, nested loops multiply, a halving loop is logarithmic, recursion is a tree whose nodes you count), and the few cases that need more thought (the master theorem, amortised cost, recursion depth) each fit in one table.

**Why it matters:** Every coding interview ends with "what is the complexity?", and the same estimate is how you decide, before writing a line, whether your plan can handle the input size in the constraints. At work it is how you explain why a page takes eight seconds: two lists of 10,000 items in a nested loop is 10^8 comparisons, and `list.contains` inside a loop is the same thing wearing a disguise.

## The idea

**Count what grows.** Fix the input size `n` and count how many times the innermost operation runs as a function of `n`. Constants and lower-order terms go; `3n^2 + 20n` is O(n^2). Different inputs get different letters: a loop over `n` orders inside a loop over `m` customers is O(n·m), not O(n^2).

**Shapes you can read at a glance:**

| Shape | Complexity | Typical code |
|---|---|---|
| One loop over `n` | O(n) | a scan, a sliding window, one pass with a hash map |
| Two loops one after the other | O(n + m), so O(n) if both are over `n` | build a frequency map, then scan it |
| Nested loops over the same input | O(n^2) | every pair; the inner loop starting at `index + 1` still gives n(n-1)/2 |
| Loop that halves the remaining range | O(log n) | binary search, walking up a balanced tree |
| Loop over `n` with an O(log n) body | O(n log n) | sorting, `n` heap operations, `n` binary searches, `n` `TreeMap` lookups |
| Loop over `n` with a loop over `k` | O(n·k) | checking each of `n` words against `k` patterns |

**Recursion is a tree.** Draw the call tree: branching factor `b`, depth `d`, work per call `w`. The total is roughly `w` times the number of nodes, and the number of nodes is dominated by the last level, about `b^d`. Two branches per element over `n` elements (subsets) is 2^n; choosing one of the remaining elements each time (permutations) is n!; `n` branches that each remove one element is also n!. Memoisation changes the count from "nodes in the tree" to "distinct states times work per state", which is the whole trick of dynamic programming (items 5.3 and 5.4).

**The master theorem, when the recursion divides the input.** For `T(n) = a·T(n/b) + O(n^d)`, compare `a` with `b^d`:

| Case | Result | Example |
|---|---|---|
| `a < b^d` | O(n^d) | one recursive call on half the input plus linear work: `a = 1, b = 2, d = 1`, O(n) |
| `a = b^d` | O(n^d log n) | merge sort: `a = 2, b = 2, d = 1`, O(n log n); binary search: `a = 1, b = 2, d = 0`, O(log n) |
| `a > b^d` | O(n^(log_b a)) | two calls on half the input with constant work: `a = 2, b = 2, d = 0`, O(n); Karatsuba multiplication: `a = 3, b = 2, d = 1`, O(n^1.585) |

**Amortised cost.** Some operations are occasionally expensive but cheap on average over any sequence. `ArrayList.add` copies the whole backing array when it is full, but the capacity grows by half each time (10, 15, 22, 33, ...), so the total copying over `n` adds is O(n) and each add is O(1) amortised. `HashMap` resizes the same way. A monotonic stack (item 2.4) has a nested `while` loop, yet each element is pushed once and popped at most once, so the whole algorithm is O(n). Sliding windows are O(n) for the same reason: the start index only moves forward. Say "amortised" when you claim it; an interviewer who asks "what about the worst single operation?" is checking that you know the difference.

**Space.** Count what you allocate plus the recursion depth, because every frame on the call stack is memory. A recursive DFS over a linked list of 10^5 nodes is O(n) space even though it allocates nothing. On this machine (JDK 25, Apple Silicon, default 2 MB thread stack) a method with two `int` parameters threw `StackOverflowError` at a depth of about 37,000 once JIT-compiled and about 17,600 when run with `-Xint`; the default differs by platform and `-Xss` changes it, but the lesson stands: recursion deeper than a few tens of thousands of frames needs an explicit stack or an iterative rewrite.

**Java collections you will use in interviews:**

| Operation | Complexity | Note |
|---|---|---|
| `ArrayList` `get`, `set`, `add` at the end | O(1), add amortised | `add(index, ...)` and `remove(index)` are O(n) because they shift |
| `ArrayList` `contains`, `indexOf`, `remove(Object)` | O(n) | the usual hidden quadratic when called inside a loop |
| `LinkedList` `addFirst`, `addLast`, `removeFirst` | O(1) | `get(index)` is O(n); use `ArrayDeque` instead |
| `ArrayDeque` `push`, `pop`, `peek`, `offer`, `poll` | O(1) amortised | the stack and queue of choice |
| `HashMap`, `HashSet` `get`, `put`, `contains`, `remove` | O(1) average | a bucket that grows past eight entries becomes a red-black tree since Java 8, so a bad `hashCode` degrades to O(log n) for `Comparable` keys rather than O(n) |
| `TreeMap`, `TreeSet` `get`, `put`, `floorKey`, `ceilingKey`, `firstKey` | O(log n) | red-black tree; the answer to "sorted plus fast lookup" |
| `PriorityQueue` `offer`, `poll` | O(log n) | `peek` is O(1); `remove(Object)` and `contains` are O(n); building one from a collection with the constructor is O(n) |
| `Arrays.sort(int[])` | O(n log n) | dual-pivot quicksort, not stable (irrelevant for primitives) |
| `Arrays.sort(Object[])`, `List.sort`, `Collections.sort` | O(n log n) | TimSort, stable |
| `String.charAt`, `length` | O(1) | |
| `String` `substring`, `equals`, `hashCode` (first call), `+` | O(length) | `substring` copies since Java 7u6; `+=` in a loop is O(n^2) |
| `StringBuilder.append` | O(1) amortised | `insert(0, ...)` is O(n) |

## Example: three functions, three readings

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public final class ComplexityExamples {

    static boolean hasDuplicateByPairs(int[] numbers) {
        for (int leftIndex = 0; leftIndex < numbers.length; leftIndex++) {
            for (int rightIndex = leftIndex + 1; rightIndex < numbers.length; rightIndex++) {
                if (numbers[leftIndex] == numbers[rightIndex]) {
                    return true;
                }
            }
        }
        return false;
    }

    static boolean hasDuplicateBySorting(int[] numbers) {
        int[] sorted = numbers.clone();
        Arrays.sort(sorted);
        for (int index = 1; index < sorted.length; index++) {
            if (sorted[index] == sorted[index - 1]) {
                return true;
            }
        }
        return false;
    }

    static boolean hasDuplicateByHashing(int[] numbers) {
        Set<Integer> seen = new HashSet<>();
        for (int number : numbers) {
            if (!seen.add(number)) {
                return true;
            }
        }
        return false;
    }

    static int countSubsetsWithSum(int[] numbers, int index, int remaining) {
        if (index == numbers.length) {
            return remaining == 0 ? 1 : 0;
        }
        return countSubsetsWithSum(numbers, index + 1, remaining)
                + countSubsetsWithSum(numbers, index + 1, remaining - numbers[index]);
    }
}
```

- `hasDuplicateByPairs`: the inner loop runs n-1, n-2, ..., 0 times, which sums to n(n-1)/2. O(n^2) time, O(1) space. The early `return` improves the best case, not the worst case, and complexity is about the worst case unless you say otherwise.
- `hasDuplicateBySorting`: O(n) to clone, O(n log n) to sort, O(n) to scan; the largest term wins. O(n log n) time, O(n) space for the copy (O(1) if you may sort in place).
- `hasDuplicateByHashing`: one loop, O(1) average per `add`. O(n) time, O(n) space. This is the standard trade: a factor of log n or n in time bought with O(n) memory.
- `countSubsetsWithSum`: two calls per level, `n` levels, so 2^n leaves and about 2^(n+1) calls, each doing constant work. O(2^n) time, O(n) space for the recursion depth. Memoised on the pair (index, remaining) it becomes O(n · S) where S is the number of distinct remaining values, which is the subset-sum DP.

Spot check with the constraints: for `n = 10^5`, the pair version does about 5·10^9 comparisons (seconds to minutes), the sorting version about 1.7·10^6 (milliseconds), the hashing version 10^5. For `n = 20`, the subset recursion makes about 2·10^6 calls, fine; for `n = 40` it makes 2·10^12, not fine, and that is the signal to memoise.

## Pitfalls

- Multiplying loops that are not nested. Two consecutive O(n) loops are O(n), not O(n^2); a loop over `n` inside a loop over `m` is O(n·m), not O(n^2).
- Forgetting the sort. "Sort, then one pass" is O(n log n), and the pass is not what dominates.
- Hidden linear work inside a loop: `list.contains`, `list.remove(index)`, `list.indexOf`, `linkedList.get(index)`, `string.substring`, `string + string`, `priorityQueue.remove(object)`. Each one turns an O(n) loop into O(n^2).
- Calling recursion "O(1) space". The call stack counts, and on a degenerate tree or a long path it is O(n).
- Promising O(1) for `HashMap` with keys whose `hashCode` collides: all `int[]` keys hash by identity (so lookups never match structurally), and a `hashCode` that only uses one low-cardinality field puts everything in a few buckets.
- Confusing amortised with worst case. `ArrayList.add` is O(1) amortised but a single add can copy the whole array; a latency-sensitive loop may need to pre-size the list (`new ArrayList<>(expectedSize)`).

## Check yourself

1. A function sorts an array of `n` intervals, then for each interval does a binary search over the sorted array. What is the total complexity, and which step dominates?
2. `T(n) = 2T(n/2) + O(n)` and `T(n) = 2T(n/2) + O(1)` differ only in the per-call work. What are the two results, and which classic algorithm is each?
3. Why is a monotonic stack algorithm O(n) even though it contains a `while` loop nested inside a `for` loop? What word do you use when you claim it?
4. You replace `ArrayList<Integer>` with `LinkedList<Integer>` because the code does many `remove(index)` calls. Does the complexity improve? What does the loop that produces the indices usually look like?

## Go deeper

- [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) · the complexity of every structure and algorithm on one page; use it to verify the collection table above.
- [MIT 6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/) · the first lectures derive asymptotic notation, recurrences and amortisation properly.
- [Algorithms, 4th edition: 1.4 Analysis of Algorithms](https://algs4.cs.princeton.edu/14analysis/) · Sedgewick and Wayne measure real Java programs and show the doubling method for checking an estimate empirically.
- [ArrayList (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayList.html) · the class documentation states which operations are constant time and which are amortised.

---

Part of [DSA & Interviews](../README.md) · item 1.2
