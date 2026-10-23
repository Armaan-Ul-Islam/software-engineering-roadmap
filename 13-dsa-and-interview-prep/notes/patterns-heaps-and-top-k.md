# Patterns: heaps, top-k and k-way merge

> **In one sentence:** A heap gives you the smallest (or largest) element of a changing set in O(log n) per insert or removal, which is exactly what "the k largest", "merge k sorted streams", "the running median" and "the next task by priority" need; in Java it is `PriorityQueue`, a min-heap by default, with a `Comparator` for anything else.

**Why it matters:** Top-k and k-way merge are everyday backend work (merging sorted pages from several shards, the ten most frequent errors in a log, the next job to run), and the interview versions test two things: whether you know that a min-heap of size `k` finds the `k` largest, and whether you can write a comparator without a bug. Find Median from Data Stream is the standard two-heap problem and reappears in design interviews as "percentiles over a stream".

## The idea

**Recognising the pattern.** "k largest", "k smallest", "k most frequent", "k closest"; "merge k sorted"; "median of a stream", "running"; "schedule by priority", "earliest deadline"; "repeatedly take the two smallest and combine them". Also any Dijkstra-style algorithm (item 4.3).

**Move 1: a min-heap of size k for the k largest.** Offer every element; whenever the heap exceeds `k` elements, poll, which removes the smallest. After the pass, the heap holds the `k` largest and its root is the kth largest. O(n log k) time and O(k) space, against O(n log n) for sorting. Mirror it (a max-heap) for the `k` smallest. When `k` is close to `n`, sorting is simpler; when you only need the kth element once, quickselect is O(n) on average (item 5.1).

**Move 2: k-way merge.** Put the head of each sorted list in a heap keyed by value. Repeatedly poll the smallest, append it to the output and offer its successor. O(N log k) for `N` total elements across `k` lists.

**Move 3: two heaps for the median.** A max-heap `lowerHalf` and a min-heap `upperHalf`, kept so that every element of `lowerHalf` is at most every element of `upperHalf`, and `lowerHalf` has the same size or one more. The median is the top of `lowerHalf`, or the mean of the two tops. Each insert is O(log n); each median read is O(1).

**Move 4: `PriorityQueue` and comparators.**

```java
PriorityQueue<Integer> smallestFirst = new PriorityQueue<>();
PriorityQueue<Integer> largestFirst = new PriorityQueue<>(Comparator.reverseOrder());
PriorityQueue<int[]> byDistanceThenIndex = new PriorityQueue<>(
        Comparator.comparingInt((int[] pair) -> pair[0]).thenComparingInt(pair -> pair[1]));
PriorityQueue<Map.Entry<String, Integer>> byCount = new PriorityQueue<>(Map.Entry.comparingByValue());
```

`offer` and `poll` are O(log n); `peek` is O(1); `remove(Object)` and `contains` are O(n); building a heap from a collection with the constructor is O(n). Iterating a `PriorityQueue`, or printing it, does not give sorted order.

## Example: Kth Largest Element in an Array (215) and Top K Frequent Elements (347)

```java
import java.util.HashMap;
import java.util.Map;
import java.util.PriorityQueue;

public final class TopK {

    public int findKthLargest(int[] numbers, int rank) {
        PriorityQueue<Integer> largestSoFar = new PriorityQueue<>();
        for (int number : numbers) {
            largestSoFar.offer(number);
            if (largestSoFar.size() > rank) {
                largestSoFar.poll();
            }
        }
        return largestSoFar.peek();
    }

    public int[] topKFrequent(int[] numbers, int resultSize) {
        Map<Integer, Integer> countByNumber = new HashMap<>();
        for (int number : numbers) {
            countByNumber.merge(number, 1, Integer::sum);
        }
        PriorityQueue<Map.Entry<Integer, Integer>> leastFrequentOnTop =
                new PriorityQueue<>(Map.Entry.comparingByValue());
        for (Map.Entry<Integer, Integer> entry : countByNumber.entrySet()) {
            leastFrequentOnTop.offer(entry);
            if (leastFrequentOnTop.size() > resultSize) {
                leastFrequentOnTop.poll();
            }
        }
        int[] result = new int[resultSize];
        for (int position = 0; position < resultSize; position++) {
            result[position] = leastFrequentOnTop.poll().getKey();
        }
        return result;
    }
}
```

`findKthLargest(new int[] {3, 2, 1, 5, 6, 4}, 2)` returns 5. `topKFrequent(new int[] {1, 1, 1, 2, 2, 3}, 2)` returns `{2, 1}` (least frequent first, because the heap is polled; reverse it if the order matters). Top K Frequent has an O(n) alternative, bucket sort by count, which is worth mentioning as the follow-up.

## Example: Find Median from Data Stream (295)

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public final class MedianFinder {

    private final PriorityQueue<Integer> lowerHalf = new PriorityQueue<>(Comparator.reverseOrder());
    private final PriorityQueue<Integer> upperHalf = new PriorityQueue<>();

    public void addNum(int number) {
        lowerHalf.offer(number);
        upperHalf.offer(lowerHalf.poll());
        if (upperHalf.size() > lowerHalf.size()) {
            lowerHalf.offer(upperHalf.poll());
        }
    }

    public double findMedian() {
        if (lowerHalf.size() > upperHalf.size()) {
            return lowerHalf.peek();
        }
        return (lowerHalf.peek() + upperHalf.peek()) / 2.0;
    }
}
```

Adding 1, 2, 3: after 1 the halves are `{1}` and `{}`, median 1.0; after 2 they are `{1}` and `{2}`, median 1.5; after 3 they are `{1, 2}` and `{3}`, median 2.0. The two-step insert (push to `lowerHalf`, move its maximum to `upperHalf`) is what keeps the ordering invariant without comparing against both tops; the size check then restores the balance. Each `addNum` is three heap operations, O(log n).

## Example: Merge k Sorted Lists (23)

Uses the `ListNode` with a `value` field from item 3.1.

```java
import java.util.Comparator;
import java.util.PriorityQueue;

public final class MergeKSortedLists {

    public ListNode mergeKLists(ListNode[] lists) {
        PriorityQueue<ListNode> smallestHeadFirst = new PriorityQueue<>(Comparator.comparingInt(node -> node.value));
        for (ListNode head : lists) {
            if (head != null) {
                smallestHeadFirst.offer(head);
            }
        }
        ListNode dummyHead = new ListNode(0);
        ListNode tail = dummyHead;
        while (!smallestHeadFirst.isEmpty()) {
            ListNode smallest = smallestHeadFirst.poll();
            tail.next = smallest;
            tail = smallest;
            if (smallest.next != null) {
                smallestHeadFirst.offer(smallest.next);
            }
        }
        return dummyHead.next;
    }
}
```

Merging `1 -> 4 -> 5`, `1 -> 3 -> 4` and `2 -> 6` gives `1 -> 1 -> 2 -> 3 -> 4 -> 4 -> 5 -> 6`. The heap never holds more than `k` nodes, so this is O(N log k) time and O(k) space. The alternative, merging lists pairwise in a divide-and-conquer tree, has the same complexity and reuses Merge Two Sorted Lists (21).

## Pitfalls

- A max-heap of all `n` elements for top-k. It works, but it is O(n log n) time and O(n) space, and it tells the interviewer you did not see the size-`k` trick.
- Off-by-one in the size check. Poll when `size() > k` after offering; polling when `size() >= k` keeps `k - 1` elements.
- Comparators by subtraction. `(first, second) -> first - second` overflows for values of opposite sign near the `int` limits and silently misorders. Use `Integer.compare` or `Comparator.comparingInt`.
- Expecting `toString` or iteration to be sorted. The heap is an array in heap order; only `poll` produces sorted output.
- `remove(Object)` to "update the priority" of an element. It is O(n). Push a new entry and skip stale ones when they are polled, which is the standard Dijkstra idiom.
- Mutating an object after it is in the heap. The heap order is no longer valid and `poll` returns the wrong element with no error.
- Integer division in the median: `(a + b) / 2` truncates; divide by `2.0`.
- `null` elements. `PriorityQueue` rejects them; filter empty lists before offering heads.
- `Collections.reverseOrder()` on a `PriorityQueue<int[]>` or other non-`Comparable` type throws `ClassCastException` at the first `offer`, not at construction. Give arrays and records an explicit comparator.

## Check yourself

1. Why does a min-heap of size `k` end up holding the `k` largest elements? State the invariant that holds after each iteration.
2. In `MedianFinder`, why is the element moved from `lowerHalf` to `upperHalf` on every insert, even when it clearly belongs in `lowerHalf`? What would break if you offered directly to the half that "looks right"?
3. What are the time and space complexities of `mergeKLists` in terms of `N` (total nodes) and `k` (lists), and why is the heap never larger than `k`?
4. Top K Frequent Elements can be solved in O(n) without a heap. How, and when would you still choose the heap?

## Go deeper

- [Tech Interview Handbook: Heap cheatsheet](https://www.techinterviewhandbook.org/algorithms/heap/) · when a heap applies, the top-k trick and the problems to practise.
- [PriorityQueue (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html) · the complexity of each operation and the note that iteration order is unspecified.
- [VisuAlgo: Binary Heap](https://visualgo.net/en/heap) · watch sift-up and sift-down until the O(log n) is obvious.

---

Part of [DSA & Interviews](../README.md) · item 3.3
