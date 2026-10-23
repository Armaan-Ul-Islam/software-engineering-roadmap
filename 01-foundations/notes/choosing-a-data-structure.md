# Choosing a data structure for everyday backend code

> **In one sentence:** Nearly every collection decision in a service answers one of four questions (sequence, lookup by key, membership, or priority); the defaults are `ArrayList`, `HashMap`, `HashSet` and `PriorityQueue`, the specialised ones (`ArrayDeque`, `LinkedHashMap`, `TreeMap`, `EnumMap`) exist for specific needs, and `LinkedList` is almost never the answer.

**Why it matters:** Code reviews are full of `LinkedList` "because inserts are O(1)", `HashMap`s keyed by objects that break the `equals`/`hashCode` contract, and tests that depend on `HashMap` iteration order until a JDK upgrade reorders them.

## The idea

Four questions before typing `new`:

1. How do I access elements: by position, by key, by "is it in there", or by "give me the smallest next"?
2. Which order do I need when iterating: insertion, sorted, or none?
3. Will it be shared between threads?
4. If keyed: is the key immutable, and does it implement `equals` and `hashCode` correctly?

**Hash tables (item 4.3).** `HashMap` keeps an array of buckets and places a key at `hash & (capacity - 1)`. Colliding keys chain in a list; since Java 8 a chain of eight or more becomes a red-black tree (O(log n) lookups when the keys are `Comparable`). All of this rests on one contract: equal objects must return equal hash codes, and a key's hash must not change while it is in the map. Records and `Objects.hash` get the contract right; mutable fields in keys are how it goes wrong.

**Linked structures (item 4.4).** `LinkedList` is a chain of node objects, each holding the element plus two references, roughly 24 bytes of overhead per element. `get(index)` walks from an end, iteration is a cache miss per node, and the O(1) insert or remove only applies if you already stand at the position with a `ListIterator`. `ArrayDeque` is a circular array: O(1) amortised at both ends, no per-element allocation, and the right choice for both stacks and FIFO queues. A linked list earns its place only when you insert or remove many elements mid-traversal through its iterator, and even then `ArrayList.removeIf` covers the common case.

**Trees and heaps (item 4.5).** `TreeMap` and `TreeSet` are red-black trees: O(log n) for everything, iteration in sorted order, and navigation methods (`floorKey`, `ceilingEntry`, `subMap`) that a hash table cannot offer. The comparator must agree with `equals`, or keys that compare as 0 silently merge. `PriorityQueue` is a binary heap: O(log n) `offer` and `poll`, O(1) `peek`, and its iteration order is heap order, not sorted order.

**The rest.** `LinkedHashMap` is a `HashMap` plus a linked list through its entries, giving insertion order, or access order with the three-argument constructor, which together with `removeEldestEntry` is a small LRU cache. `EnumMap` and `EnumSet` are an array indexed by ordinal and a bit mask, the fastest choice whenever the key is an enum. `List.of`, `Set.of` and `Map.of` are immutable and reject `null`; in OpenJDK, `Set.of` and `Map.of` iterate in an order that changes from one JVM run to the next, deliberately, so that order-dependent code fails early. Shared mutable collections (`ConcurrentHashMap`, `BlockingQueue`) belong to the Memory & Concurrency domain.

**The decision table (item 4.9):**

| You need | Use | Not | Because |
|---|---|---|---|
| A sequence with index access, mostly appended to | `ArrayList` | `LinkedList` | contiguous memory, O(1) `get`, cache-friendly iteration |
| A stack or FIFO queue on one thread | `ArrayDeque` | `Stack`, `LinkedList` | O(1) at both ends without per-node objects |
| Lookup by key, order irrelevant | `HashMap` | `TreeMap` | O(1) average instead of O(log n) |
| Lookup by key with stable iteration order (JSON output, tests, audit logs) | `LinkedHashMap` | relying on `HashMap` order | insertion order is specified; `HashMap` order is not |
| Range queries, nearest key, sorted output | `TreeMap`, `TreeSet` | sorting a `HashMap` on every call | O(log n) with `floor`, `ceiling`, `subMap` |
| Membership and deduplication | `HashSet` | `List.contains` | O(1) instead of O(n) per check (item 4.1) |
| Keys are an enum | `EnumMap`, `EnumSet` | `HashMap`, `HashSet` | array by ordinal, no hashing, no boxing |
| Repeatedly take the smallest or most urgent | `PriorityQueue` | re-sorting a list after each insert | O(log n) insert and remove-min |
| A fixed set of constants | `List.of`, `Set.of`, `Map.of` | mutable collections | immutable, null-free, intent is visible |

## Example: three ways to break a hash set

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public final class HashContract {

    static final class CoordinateWithoutHashCode {
        private final int x;
        private final int y;

        CoordinateWithoutHashCode(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof CoordinateWithoutHashCode that && x == that.x && y == that.y;
        }
    }

    static final class MutableCoordinate {
        private int x;
        private int y;

        MutableCoordinate(int x, int y) {
            this.x = x;
            this.y = y;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof MutableCoordinate that && x == that.x && y == that.y;
        }

        @Override
        public int hashCode() {
            return Objects.hash(x, y);
        }
    }

    record Coordinate(int x, int y) {
    }

    public static void main(String[] arguments) {
        Set<CoordinateWithoutHashCode> withoutHashCode = new HashSet<>();
        withoutHashCode.add(new CoordinateWithoutHashCode(1, 2));
        System.out.println("equals only, contains equal key: " + withoutHashCode.contains(new CoordinateWithoutHashCode(1, 2)));

        Set<MutableCoordinate> mutableKeys = new HashSet<>();
        MutableCoordinate coordinate = new MutableCoordinate(1, 2);
        mutableKeys.add(coordinate);
        coordinate.x = 99;
        System.out.println("mutated key, contains itself:    " + mutableKeys.contains(coordinate));
        System.out.println("mutated key, remove succeeded:   " + mutableKeys.remove(coordinate));
        System.out.println("mutated key, set size:           " + mutableKeys.size());

        Set<Coordinate> records = new HashSet<>();
        records.add(new Coordinate(1, 2));
        System.out.println("record, contains equal key:      " + records.contains(new Coordinate(1, 2)));
    }
}
```

Output:

```text
equals only, contains equal key: false
mutated key, contains itself:    false
mutated key, remove succeeded:   false
mutated key, set size:           1
record, contains equal key:      true
```

The first class overrides `equals` but inherits the identity `hashCode`, so two equal coordinates land in different buckets and the set cannot find what it holds. The second class is correct until the key mutates: it now hashes to another bucket, `contains` and `remove` both fail, and the entry stays in the set forever. In a long-lived cache that is a memory leak no heap dump will explain. The record gets both methods generated from its components and is immutable, so it cannot go wrong.

## Pitfalls

- Mutable keys, including JPA entities whose `hashCode` uses a generated id that is `null` until the first flush: entries added before the flush become unreachable after it. Use immutable keys, or hash on a business key that exists from construction.
- Depending on `HashMap` or `HashSet` iteration order. It changes with capacity, with the keys and between JDK versions. Use `LinkedHashMap` or sort explicitly.
- A `TreeMap` comparator that disagrees with `equals`, for example comparing only on a `lastName` field: distinct keys with the same last name overwrite each other.
- Printing or iterating a `PriorityQueue` and expecting sorted output.
- Choosing `LinkedList` because it "implements `Queue`". `ArrayDeque` does too, and its own documentation says it is likely to be faster than `LinkedList` as a queue and than `Stack` as a stack.

## Check yourself

1. A `HashMap<Customer, Order>` where `Customer` is a JPA entity whose `hashCode` is based on its generated id. You put three new customers in the map, save them, then look them up. What happens and why?
2. You need the ten most recent events per user and to drop the oldest when an eleventh arrives. Which structure, and what does each insert cost?
3. Describe the exact access pattern under which `LinkedList` beats `ArrayList`, and name the `ArrayList` method that removes the most common reason for wanting it.
4. A test asserts on JSON generated from a `HashMap<String, Object>`. It passes locally and fails in CI with the keys in another order. Give two plausible causes and the fix.

## Go deeper

- [Java Collections Framework overview](https://dev.java/learn/api/collections-framework/) · the official tour; read the pages on choosing implementations and on hashing.
- [Object.hashCode contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#hashCode()) · the contract in the JDK's own words.
- [Algorithms, 4th ed.: Hash Tables](https://algs4.cs.princeton.edu/34hash/) · how hashing, chaining and resizing work underneath `HashMap`.
- [Algorithms, 4th ed.: Balanced Search Trees](https://algs4.cs.princeton.edu/33balanced/) and [Priority Queues](https://algs4.cs.princeton.edu/24pq/) · what `TreeMap` and `PriorityQueue` are made of.

---

Part of [Foundations](../README.md) · items 4.3, 4.4, 4.5, 4.9
