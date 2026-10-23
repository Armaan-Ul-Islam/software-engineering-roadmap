# Big-O in practice: growth, amortised cost and the constants it hides

> **In one sentence:** Big-O describes how time or memory grows as the input grows, ignoring constant factors and lower-order terms, which makes it the right tool for spotting the loop that will not survive production data and the wrong tool for choosing between two operations that are both O(1).

**Why it matters:** The accidental O(n²) is the most common performance bug in backend code: `contains` on a list inside a loop, string concatenation in a loop, one query per row. It passes every test with twenty rows and takes the service down with a hundred thousand. Interviewers expect you to state the cost of `ArrayList.add`, `HashMap.get` and `LinkedList.get` without pausing, and to know why "O(1)" can still be slow.

## The idea

**Definition, informally.** `f(n)` is O(g(n)) if, for large enough n, `f(n)` is at most some constant times `g(n)`. The constant and anything that grows more slowly are dropped: 3n² + 100n is O(n²). The classes you meet daily, with the shape of code that produces them:

| Class | Where it comes from | n = 1,000 | n = 1,000,000 |
|---|---|---|---|
| O(1) | array index, hash lookup, push and pop | 1 | 1 |
| O(log n) | binary search, balanced tree, heap insert | 10 | 20 |
| O(n) | one pass over the data | 1,000 | 1,000,000 |
| O(n log n) | a good sort | 10,000 | 20,000,000 |
| O(n²) | a loop inside a loop over the same data | 1,000,000 | 10¹² |

Going from a thousand inputs to a million multiplies O(n log n) work by about 2,000 and O(n²) work by a million.

**Time and space.** Space counts the extra memory an algorithm needs beyond its input: merge sort needs O(n) scratch space, an in-place quicksort O(log n) for its recursion. In Java the hidden factor is memory per element: an `int[]` costs 4 bytes per value, a `List<Integer>` costs a 4-byte reference plus a 16-byte `Integer` object somewhere else on the heap.

**Best, average, worst.** `HashMap.get` is O(1) on average and O(n) in the worst case, when every key lands in the same bucket, which an attacker can arrange with crafted keys (hash flooding). Since Java 8 a bucket with eight or more entries becomes a red-black tree once the table has 64 buckets, so with `Comparable` keys the worst case is O(log n). `Arrays.sort` on objects uses TimSort, which is O(n log n) in the worst case and stable.

**Amortised cost.** `ArrayList.add` is O(1) *amortised*: most calls store into a free slot, but when the backing array is full it allocates a new one 1.5 times larger and copies everything, an O(n) call. Spread over n adds the copies total fewer than 3n element moves, so the average is constant, but the individual spike is real. `HashMap` does the same when it passes 75% of capacity. If you know n, pre-size: `new ArrayList<>(n)`, or `HashMap.newHashMap(n)` on Java 19 and later.

**The constants that matter.** Big-O compares growth, not speed. It hides cache locality (an array scan touches 16 ints per cache line, a linked list one node per line, see item 1.2), boxing and allocation, the cost of hashing a key (hashing a 10 KB string is O(its length) every time, though `String` caches its own hash), and anything that leaves the process. One SQL round trip costs about a millisecond, so a loop that issues n queries is O(n) in Big-O terms and catastrophic in practice. For small n, tens of elements, a linear scan over an array routinely beats a hash lookup.

**Java collections, what to know cold:**

| Operation | ArrayList | LinkedList | ArrayDeque | HashMap, HashSet | TreeMap, TreeSet | PriorityQueue |
|---|---|---|---|---|---|---|
| get by index | O(1) | O(n) | | | | |
| add at end | O(1) amortised | O(1) | O(1) amortised | | | |
| add or remove at front | O(n) | O(1) | O(1) amortised | | | |
| remove from the middle | O(n) | O(n) to find, O(1) to unlink | | | | |
| contains a value | O(n) | O(n) | O(n) | O(1) average | O(log n) | O(n) |
| get, put, remove by key | | | | O(1) average | O(log n) | |
| smallest element | O(n) | O(n) | | | O(log n) | O(1) peek, O(log n) poll |
| iterate everything | O(n), cache-friendly | O(n), pointer chasing | O(n) | O(capacity + n), no order | O(n), sorted | O(n), heap order |

## Example: the accidental quadratic

Deduplicating by checking `contains` on the result list is O(n²): every `contains` scans the whole list built so far. A `HashSet` does the same job in O(n).

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;

public final class ContainsInLoop {

    public static void main(String[] arguments) {
        for (int size : new int[] {20_000, 40_000, 80_000}) {
            int[] input = new Random(42).ints(size, 0, size / 2).toArray();
            long listNanos = time(() -> distinctWithList(input));
            long setNanos = time(() -> distinctWithSet(input));
            System.out.printf("n=%,6d  ArrayList.contains %5d ms   HashSet.add %3d ms%n",
                    size, listNanos / 1_000_000, setNanos / 1_000_000);
        }
    }

    static int distinctWithList(int[] input) {
        List<Integer> distinct = new ArrayList<>();
        for (int value : input) {
            if (!distinct.contains(value)) {
                distinct.add(value);
            }
        }
        return distinct.size();
    }

    static int distinctWithSet(int[] input) {
        Set<Integer> distinct = new HashSet<>();
        for (int value : input) {
            distinct.add(value);
        }
        return distinct.size();
    }

    static long time(Runnable work) {
        long start = System.nanoTime();
        work.run();
        return System.nanoTime() - start;
    }
}
```

Output on an Apple Silicon laptop with JDK 25:

```text
n=20,000  ArrayList.contains    56 ms   HashSet.add   2 ms
n=40,000  ArrayList.contains   210 ms   HashSet.add   3 ms
n=80,000  ArrayList.contains   771 ms   HashSet.add   2 ms
```

Doubling n multiplies the list version by almost four, which is what n² predicts; the set version is flat at this scale. Extrapolating the curve, a million inputs would take the list version about two minutes and the set version well under a second. The same shape hides in `list.indexOf`, `list.remove(Object)`, `String +=` in a loop (each `+=` copies the whole string so far), and one database query per row.

## Pitfalls

- `contains`, `indexOf` or `remove(Object)` on a `List` inside a loop. Build a `HashSet` first, or use `stream().distinct()`.
- `LinkedList.get(index)` in an index-based `for` loop: each call walks from the head, so the loop is O(n²).
- Building strings with `+=` in a loop. Use `StringBuilder`, `String.join` or `Collectors.joining`.
- Trusting O(1) for `HashMap` with a bad `hashCode`: a constant, or a hash of one low-cardinality field, turns the map into a list. See item 4.3.
- Ignoring the amortised spike. A resize copy of a huge `ArrayList` or `HashMap` on a request thread is a latency outlier. Pre-size when n is known.
- Benchmarking with `System.nanoTime` and one run. Timings like the ones above show an order-of-magnitude shape; for anything finer use JMH.

## Check yourself

1. `for (Order order : orders) { if (!seen.contains(order.id())) { seen.add(order.id()); } }`. What is the complexity when `seen` is an `ArrayList`, and when it is a `HashSet`? What must be true of the type of `order.id()` for the second answer to hold?
2. Why is `ArrayList.add` described as O(1) amortised rather than O(1), and in what kind of system does the difference matter?
3. A `HashMap<String, Customer>` has a million keys that are 10 KB strings differing only in the last character. What does a `get` with a freshly built key cost, and why does "O(1)" not warn you?
4. Algorithm A is O(n) at 50 µs per element; algorithm B is O(n log n) at 1 µs per element. For which n is A faster?

## Go deeper

- [Big-O Cheat Sheet](https://www.bigocheatsheet.com/) · the complexity table for the standard data structures and sorts, to check yourself against.
- [MIT 6.006, lecture 1](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/) · asymptotic notation done properly, in one lecture.
- [Java Collections Framework overview](https://dev.java/learn/api/collections-framework/) · the official tour of the collections, including which implementation to pick and why.
- [JMH](https://github.com/openjdk/jmh) · the benchmark harness that handles warm-up, dead-code elimination and statistics; its samples directory is a course in measurement mistakes.

---

Part of [Foundations](../README.md) · item 4.1
