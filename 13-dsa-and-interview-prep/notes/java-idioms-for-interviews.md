# Java idioms and pitfalls for coding interviews

> **In one sentence:** A small set of standard-library idioms (`ArrayDeque`, `PriorityQueue` with a comparator, `Map.merge` and `computeIfAbsent`, records for pairs, `Arrays.fill`, char arithmetic, `StringBuilder`) covers almost every interview problem, and a short list of language pitfalls (`Integer` equality, overflow, sort stability, mutable keys, `substring` cost, streams in hot loops) causes almost every "passes the example, fails the hidden tests".

**Why it matters:** The interview clock punishes fumbling with the library: looking up whether `Stack` iterates top-first, or spending five minutes on why `==` on map values works for 100 and fails for 1000. Knowing these cold frees your attention for the actual problem. Several of the pitfalls (the `Integer` cache, overflow, mutable keys) are also real production bugs that code review catches only when the reviewer knows them.

## The idea

**Idioms, with the shape you type.**

1. **`ArrayDeque` over `Stack` and `LinkedList`.** `push`, `pop`, `peek` for a stack; `offer`, `poll`, `peek` for a queue. `Stack` is synchronised, extends `Vector`, and iterates bottom to top. `ArrayDeque` rejects `null` and its `peek`/`poll` return `null` when empty while `pop`/`remove` throw.
2. **`PriorityQueue` with a comparator.** `new PriorityQueue<>()` is a min-heap by natural order; `Comparator.reverseOrder()` makes a max-heap; `Comparator.comparingInt(...)` and `thenComparingInt(...)` build keyed comparators; `Map.Entry.comparingByValue()` orders entries. Compare with `Integer.compare`, never with subtraction.
3. **`Map.merge` for counting, `computeIfAbsent` for grouping.** `counts.merge(key, 1, Integer::sum)` increments; a merge function that returns `null` removes the key, which makes "decrement and drop at zero" one line. `graph.computeIfAbsent(node, ignored -> new ArrayList<>()).add(neighbour)` builds an adjacency list without an `if`.
4. **Records for pairs and states.** `record Cell(int row, int column) {}` gets `equals`, `hashCode` and `toString`, so it works in a `HashSet` or as a map key; a record can be declared inside a method.
5. **`Arrays` helpers.** `Arrays.fill(table, -1)` for sentinels; `Arrays.sort(intervals, Comparator.comparingInt(interval -> interval[0]))` for sorting pairs; `Arrays.copyOfRange`; `Arrays.toString` and `Arrays.deepToString` for debugging; `Collections.nCopies(size, value)` for a pre-filled immutable list.
6. **Char arithmetic.** `letter - 'a'` is the index into an `int[26]`; `(char) ('a' + offset)` goes back; `digit - '0'` converts a digit character; `Character.isLetterOrDigit`, `Character.toLowerCase`.
7. **`StringBuilder`.** `append` in loops, `reverse()`, `setLength(length - 1)` to pop a character, `deleteCharAt`. Building a string with `+=` in a loop is O(n^2).

**Pitfalls, with the symptom.**

1. **`Integer` equality.** `==` on two `Integer` objects compares references. Boxing caches -128 to 127 (JLS 5.1.7 guarantees that range; HotSpot can enlarge it with `-XX:AutoBoxCacheMax`), so `map.get(a) == map.get(b)` is true for small counts and false for large ones. Use `equals` or unbox to `int`.
2. **Overflow.** `int` holds about ±2.1·10^9. A sum of 10^5 values up to 10^9, `(low + high) / 2`, `a * b` for two values near 10^5, and `Math.abs(Integer.MIN_VALUE)` (which stays negative) all overflow silently. Use `long`, or `Math.addExact` and `Math.multiplyExact` when you want an exception.
3. **Sort stability and primitives.** `Arrays.sort(Object[])` and `List.sort` are stable (TimSort); `Arrays.sort(int[])` is a dual-pivot quicksort, not stable, which is irrelevant for primitives but means you cannot pass a comparator. To sort `int[]` by a custom key, box to `Integer[]` or sort indices.
4. **Mutable keys and array keys.** A `List` used as a key and then modified is lost in the wrong bucket. `int[]` and other arrays hash by identity, so `Set<int[]>` never recognises an equal array. Use records, `List.of`, or encode `row * columns + column`.
5. **`substring` and `+` cost.** Since Java 7u6 `substring` copies its characters, so `substring` or `+=` inside a loop is O(n^2). Work with indices and a `StringBuilder`.
6. **Streams in hot loops.** `IntStream.range(...).boxed().collect(...)` inside an O(n^2) loop allocates and boxes on every iteration and is hard to debug under time pressure. Use streams for a final transformation of a small result, loops for the algorithm.
7. **`List.remove(int)` versus `remove(Object)`.** `list.remove(index)` removes by position; `list.remove(Integer.valueOf(value))` removes by value. With a `List<Integer>` the compiler picks by the static type of the argument, which surprises people who pass an `int` and expected a value removal.

## Example: the idioms in one file

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;

public final class Idioms {

    record Cell(int row, int column) {}

    public static void main(String[] arguments) {
        Deque<Integer> stack = new ArrayDeque<>();
        stack.push(1);
        stack.push(2);
        System.out.println(stack.peek() + " " + stack);                 // 2 [2, 1]

        PriorityQueue<int[]> byDistance = new PriorityQueue<>(
                Comparator.comparingInt((int[] pair) -> pair[0]).thenComparingInt(pair -> pair[1]));
        byDistance.offer(new int[] {5, 1});
        byDistance.offer(new int[] {2, 9});
        byDistance.offer(new int[] {2, 3});
        System.out.println(Arrays.toString(byDistance.poll()));         // [2, 3]

        Map<Character, Integer> counts = new HashMap<>();
        for (char letter : "banana".toCharArray()) {
            counts.merge(letter, 1, Integer::sum);
        }
        counts.merge('b', -1, (oldCount, delta) -> oldCount + delta == 0 ? null : oldCount + delta);
        System.out.println(counts);                                      // {a=3, n=2}

        Map<Integer, List<Integer>> neighbours = new HashMap<>();
        neighbours.computeIfAbsent(1, ignored -> new ArrayList<>()).add(2);
        neighbours.computeIfAbsent(1, ignored -> new ArrayList<>()).add(3);
        System.out.println(neighbours);                                  // {1=[2, 3]}

        Set<Cell> visited = new HashSet<>();
        visited.add(new Cell(0, 1));
        System.out.println(visited.contains(new Cell(0, 1)));            // true

        int[] cache = new int[5];
        Arrays.fill(cache, -1);
        int[][] intervals = {{5, 6}, {1, 3}, {2, 4}};
        Arrays.sort(intervals, Comparator.comparingInt(interval -> interval[0]));
        System.out.println(Arrays.toString(cache) + " " + Arrays.deepToString(intervals));
        // [-1, -1, -1, -1, -1] [[1, 3], [2, 4], [5, 6]]

        int[] letterCounts = new int[26];
        letterCounts['e' - 'a']++;
        StringBuilder builder = new StringBuilder("abc");
        builder.setLength(builder.length() - 1);
        System.out.println(letterCounts[4] + " " + (char) ('a' + 4) + " " + builder.reverse());   // 1 e ba
    }
}
```

## Example: the pitfalls, observed

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class Pitfalls {

    public static void main(String[] arguments) {
        Integer small = 127;
        Integer sameSmall = 127;
        Integer large = 1000;
        Integer sameLarge = 1000;
        System.out.println((small == sameSmall) + " " + (large == sameLarge) + " " + large.equals(sameLarge));
        // true false true

        int big = 2_000_000_000;
        System.out.println((big + big) + " " + ((long) big + big) + " " + Math.abs(Integer.MIN_VALUE));
        // -294967296 4000000000 -2147483648

        Set<int[]> cells = new HashSet<>();
        cells.add(new int[] {0, 1});
        System.out.println(cells.contains(new int[] {0, 1}));           // false

        List<Integer> values = new ArrayList<>(List.of(10, 20, 30));
        values.remove(1);
        values.remove(Integer.valueOf(30));
        System.out.println(values);                                      // [10]
    }
}
```

Run both files with `java Idioms.java` and `java Pitfalls.java`; the comments show the output.

## Pitfalls

- Mixing `push` with `poll`. `push` adds at the front and `poll` removes from the front, so the "queue" is a stack. Pair `push`/`pop` or `offer`/`poll`, never across.
- Comparators that subtract. `first - second` is fine for small non-negative counts and wrong for `Integer.MIN_VALUE` and large opposite-sign values; `Integer.compare` costs nothing more.
- `Comparator.reverseOrder()` on a `PriorityQueue` of arrays or records. It needs `Comparable` elements and fails with `ClassCastException` at the first `offer`.
- `Character` and `Integer` boxing in `switch` or `==`. `'a' == someCharacterObject` unboxes and is fine; `characterObjectA == characterObjectB` is a reference comparison that happens to work for ASCII (also cached) and fails elsewhere.
- `Arrays.asList(intArray)` producing a `List<int[]>` with one element, not a `List<Integer>`.
- `List.of` and `Map.of` are immutable and reject `null`; wrap in `new ArrayList<>(...)` when you need to mutate.

## Check yourself

1. `Map<String, Integer> counts` holds `{"a": 1000, "b": 1000}`. What does `counts.get("a") == counts.get("b")` return, and why does the same code print `true` after changing both counts to 100?
2. You need the midpoint of `low = 2_000_000_000` and `high = 2_100_000_000`. Which expressions are wrong, which are right, and why is `>>> 1` acceptable where `/ 2` is not?
3. Why can a `HashSet<int[]>` never serve as a visited set for grid cells, and what are two correct replacements?
4. Where in an interview solution would you accept a stream, and where would you refuse one? Give one example of each.

## Go deeper

- [Baeldung: Guide to the Java ArrayDeque](https://www.baeldung.com/java-array-deque) · how the deque works as a stack and a queue and why it replaces `Stack`.
- [JLS 5.1.7: Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7) · the exact guarantee about which boxed values are cached.
- [Map (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html) · the contracts of `merge`, `computeIfAbsent`, `getOrDefault` and `putIfAbsent`, including what a `null` result does.
- [PriorityQueue (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PriorityQueue.html) · operation costs and the unspecified iteration order.

---

Part of [DSA & Interviews](../README.md) · items 6.1, 6.2
