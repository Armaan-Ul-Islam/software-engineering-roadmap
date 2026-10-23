# Patterns: binary search without off-by-one errors

> **In one sentence:** Binary search finds the boundary in any sequence that is false, false, ..., true, true for some predicate; if you always search the half-open range `[low, high)` for the first `true` and keep the invariant "everything before `low` is false, everything from `high` on is true", one template handles exact matches, first and last occurrences, rotated arrays and "the smallest feasible answer".

**Why it matters:** Binary search is short and notoriously easy to get wrong: Jon Bentley found that most professional programmers could not write a correct one, and the `(low + high) / 2` overflow bug sat in `java.util.Arrays.binarySearch` for years before Joshua Bloch fixed it in 2006. In interviews, the plain version is a warm-up; the version that matters is binary search on the answer space, which turns many "minimise the maximum" and "smallest speed/capacity such that" problems into a feasibility check plus a loop.

## The idea

**Recognising the pattern.** A sorted (or rotated sorted) array; a required O(log n); "find the first/last position of"; "minimum x such that condition(x) holds" or "maximum x such that"; any question where you can write a yes/no check that is monotone in the thing you are looking for (if speed 5 is enough, speed 6 is enough).

**The template.** Search for the first index in `[low, high)` where a predicate is true. `high` is exclusive, and returning `high` means "no index satisfied it".

```java
import java.util.function.IntPredicate;

public final class BinarySearchTemplate {

    static int firstIndexWhere(int low, int high, IntPredicate predicate) {
        while (low < high) {
            int middle = low + (high - low) / 2;
            if (predicate.test(middle)) {
                high = middle;
            } else {
                low = middle + 1;
            }
        }
        return low;
    }
}
```

Why it cannot go wrong: the invariant "all indices below `low` are false, all indices at or above `high` are true" holds at the start (both ranges are empty) and after every step (`middle` is tested and moved into the correct side). The range shrinks every iteration because `middle < high`, so `high = middle` shrinks it, and `low = middle + 1` shrinks it. When `low == high` the invariant says that index is the first `true`. There is no `low <= high`, no `high = middle - 1`, and no special return for "not found".

**Derive, do not memorise.** Every variant is a choice of range and predicate:

| Question | Range | Predicate at `index` | Answer |
|---|---|---|---|
| exact match in a sorted array | `[0, n)` | `values[index] >= target` | first `true`, if it exists and equals `target` |
| first occurrence | `[0, n)` | `values[index] >= target` | same, that index |
| last occurrence | `[0, n)` | `values[index] > target` | first `true` minus one, if that holds `target` |
| pivot of a rotated array | `[0, n)` | `values[index] <= values[n - 1]` | first `true` is the minimum |
| smallest feasible answer | `[lowestCandidate, highestCandidate)` | `feasible(index)` | first `true`, with `high` chosen so it is known to be feasible |

**Complexity.** O(log(high - low)) predicate evaluations. For search on the answer space, multiply by the cost of the feasibility check, typically O(n), giving O(n log range).

## Example: Binary Search (704) and Search in Rotated Sorted Array (33)

```java
public final class SortedSearches {

    public int search(int[] numbers, int target) {
        int index = BinarySearchTemplate.firstIndexWhere(0, numbers.length, candidate -> numbers[candidate] >= target);
        return index < numbers.length && numbers[index] == target ? index : -1;
    }

    public int searchRotated(int[] numbers, int target) {
        int length = numbers.length;
        int last = numbers[length - 1];
        int pivot = BinarySearchTemplate.firstIndexWhere(0, length, index -> numbers[index] <= last);
        int low;
        int high;
        if (target <= last) {
            low = pivot;
            high = length;
        } else {
            low = 0;
            high = pivot;
        }
        int found = BinarySearchTemplate.firstIndexWhere(low, high, index -> numbers[index] >= target);
        return found < high && numbers[found] == target ? found : -1;
    }
}
```

For `[4, 5, 6, 7, 0, 1, 2]` the predicate `numbers[index] <= 2` reads `false, false, false, false, true, true, true`, so the pivot is index 4, the position of the minimum. A target of 0 is at most 2, so it lives in `[4, 7)` and is found at index 4; a target of 5 is larger than 2, so it lives in `[0, 4)` and is found at index 1; a target of 3 searches `[0, 4)`, lands on index 0 (the first value that is at least 3), sees 4 there and returns -1. An unrotated array has pivot 0 and the second search covers everything. The problem guarantees distinct values; with duplicates the pivot predicate is not monotone (`[2, 2, 2, 0, 2]`) and the worst case degrades to O(n).

## Example: Koko Eating Bananas (875), search on the answer

Koko must eat all `piles` within `hours`, eating at most `speed` bananas per hour from one pile. Find the minimum integer speed. The array is not sorted and there is nothing to index; what is monotone is feasibility: if a speed works, every greater speed works.

```java
public final class KokoEatingBananas {

    public int minEatingSpeed(int[] piles, int hours) {
        int maxPile = 0;
        for (int pile : piles) {
            maxPile = Math.max(maxPile, pile);
        }
        return BinarySearchTemplate.firstIndexWhere(1, maxPile, speed -> hoursNeeded(piles, speed) <= hours);
    }

    private static long hoursNeeded(int[] piles, int speed) {
        long total = 0;
        for (int pile : piles) {
            total += (pile - 1) / speed + 1;
        }
        return total;
    }
}
```

`minEatingSpeed(new int[] {3, 6, 7, 11}, 8)` returns 4 and `minEatingSpeed(new int[] {30, 11, 23, 4, 20}, 5)` returns 30. The range is `[1, maxPile)`: a speed of `maxPile` always finishes in `piles.length` hours, which the constraints guarantee is at most `hours`, so the exclusive upper bound is itself a valid fallback answer and the template returns it when nothing smaller works. Two small details keep the arithmetic honest: `hoursNeeded` accumulates in a `long` because 10^4 piles of 10^9 bananas at speed 1 exceed `int`, and the ceiling is written as `(pile - 1) / speed + 1` because `(pile + speed - 1) / speed` can overflow when both are near 10^9.

The same shape solves Capacity To Ship Packages Within D Days (1011), Split Array Largest Sum (410) and Minimum Number of Days to Make m Bouquets (1482): write `feasible(candidate)`, prove it monotone in one sentence, pick bounds that are definitely infeasible-or-answer and definitely feasible, and call the template.

## Pitfalls

- Mixing conventions. `while (low <= high)` with `high = middle` loops forever; `while (low < high)` with `high = middle - 1` skips the answer. Pick the half-open template and keep it.
- `(low + high) / 2`. Overflows when both are above about 1.07·10^9. Write `low + (high - low) / 2` or `(low + high) >>> 1`.
- Returning from the middle of the loop when `values[middle] == target` and forgetting the path for "not found", or returning the wrong occurrence when duplicates exist. The template separates finding the boundary from checking what is there.
- A predicate that is not monotone. Binary search on an unsorted array, or on a feasibility check that can go true, false, true, returns an arbitrary index with no error. Say the monotonicity argument out loud before you write the loop.
- Answer-space bounds that exclude the answer. `low` must be a possible answer (speed 1, not 0, since dividing by zero) and `high` must be exclusive-and-feasible or one past the largest candidate.
- Using `Arrays.binarySearch` for first or last occurrence. Its documentation says that with duplicates there is no guarantee which one is found, and its negative return encodes the insertion point as `-(insertionPoint) - 1`, which people forget to decode.
- Forgetting that the loop variable in the lambda must be effectively final. Capture the array and the target, which never change, not a counter you are updating.

## Check yourself

1. Write the predicate and the post-processing for "last index of `target`" using the template. What do you return when `target` is smaller than every element?
2. In the Koko solution, what would go wrong if the range were `[0, maxPile)`? And if it were `[1, maxPile + 1)` with `firstIndexWhere` as written?
3. For `[2, 2, 2, 0, 2]`, show that the pivot predicate `values[index] <= values[n - 1]` is not monotone. What does that do to the search?
4. Minimum Number of Days to Make m Bouquets asks for the earliest day on which `m` bouquets of `k` adjacent flowers can be made. What is the candidate range, what is the predicate, and why is it monotone?

## Go deeper

- [Tech Interview Handbook: Sorting and searching cheatsheet](https://www.techinterviewhandbook.org/algorithms/sorting-searching/) · the corner cases and the list of binary-search problems worth doing.
- [Arrays (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html) · the `binarySearch` contract, including the duplicate caveat and the insertion-point encoding.
- [NeetCode roadmap](https://neetcode.io/roadmap) · the Binary Search node, with Koko Eating Bananas and the other answer-space problems.

---

Part of [DSA & Interviews](../README.md) · item 2.5
