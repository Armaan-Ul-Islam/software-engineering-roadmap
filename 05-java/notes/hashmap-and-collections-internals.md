# HashMap and collections internals

> **In one sentence:** `HashMap` turns `hashCode()` into a bucket index, chains collisions in a list that becomes a red-black tree when it grows long, and doubles its table once it is three quarters full; `ArrayList` grows by half for amortised O(1) appends; and nearly every job people reach for `LinkedList` to do is done faster by `ArrayList` or `ArrayDeque`.

**Why it matters:** Collections chosen by habit cost performance and sometimes correctness: a test that depends on `HashMap` iteration order passes until the map resizes, a `PriorityQueue` iterated as if it were sorted produces garbage, and `list.contains` inside a loop quietly turns an import into an O(n²) job. Interviewers ask how `HashMap` works because the answer exercises hashing, `equals`/`hashCode` (see item 1.3) and amortised analysis in one go.

## The idea

**HashMap (OpenJDK 8 and later).** The map holds an array of buckets whose length is always a power of two, 16 by default. For a key it computes `hash = h ^ (h >>> 16)` where `h` is `key.hashCode()`, folding the high bits into the low bits, and picks the bucket `(table.length - 1) & hash`. Without the fold, keys whose hash codes differ only in the high bits would share a bucket, because the mask only looks at the low bits. Colliding entries form a linked list; `get` walks it comparing the stored hash first and then `equals`. When a ninth entry is added to a bucket that already holds eight, and the table has at least 64 slots, the list becomes a red-black tree, so lookups in that bucket are O(log n) instead of O(n), which also defuses hash-flooding attacks. If the table is smaller than 64, the map resizes instead; a tree turns back into a list when a resize leaves it with six or fewer entries. The **load factor** (0.75) sets the resize threshold: when `size` exceeds `capacity × 0.75`, the table doubles and every entry is redistributed, each bucket splitting into "same index" and "index plus old capacity". A resize is O(n) but rare, so inserts are amortised O(1). One `null` key is allowed. Iteration order is unspecified and changes after a resize.

**LinkedHashMap** threads a doubly linked list through the entries: insertion order by default, or access order when constructed with `accessOrder = true`, in which case `get` and `put` move the entry to the tail. The protected hook `removeEldestEntry` runs after every insertion; return `true` and the head entry is evicted. That is a complete LRU cache.

**TreeMap** is a red-black tree ordered by a `Comparator` or natural order: O(log n) for everything, sorted iteration, and navigation (`floorKey`, `ceilingEntry`, `headMap`, `subMap`). It uses only `compareTo`, never `equals` or `hashCode`, so a comparator that returns 0 for two distinct keys merges them. **EnumMap** is an array indexed by `ordinal()`, the fastest map for enum keys.

**ArrayList** keeps its elements in an `Object[]`. The first `add` allocates room for 10; when full, the array grows to 1.5 times its size (`oldCapacity + (oldCapacity >> 1)`) and the elements are copied. Each element is copied a bounded number of times in total, so n appends cost O(n) and each append is amortised O(1). `get` and `set` are O(1); inserting or removing in the middle is O(n) but uses `System.arraycopy`, a fast memory move; `remove(Object)` and `contains` are O(n).

**LinkedList** is a doubly linked list. Every element needs a node object (header plus three references), the nodes are scattered in memory, and `get(index)` walks from the nearer end. Even for queues and stacks, where it is O(1), it loses to `ArrayDeque` through allocation and cache misses. Its one real advantage is O(1) removal through a `ListIterator` while iterating; its author, Joshua Bloch, has said publicly that he never uses it.

**ArrayDeque** is a circular array that doubles when full: amortised O(1) at both ends, no index access, no `null` elements. Use it for stacks (instead of the synchronised legacy `Stack`) and for queues (instead of `LinkedList`).

**PriorityQueue** is a binary min-heap in an array: `offer` and `poll` are O(log n), `peek` is O(1), `remove(Object)` and `contains` are O(n). Iterating it yields heap order, not sorted order, and ties between equal priorities are not stable.

| Operation | ArrayList | LinkedList | ArrayDeque | HashMap | TreeMap | PriorityQueue |
|---|---|---|---|---|---|---|
| get / put by index or key | O(1) | O(n) | no index | O(1) expected, O(log n) in a treeified bucket | O(log n) | no |
| add at end / offer | O(1) amortised | O(1) | O(1) amortised | | | O(log n) |
| add or remove at front | O(n) | O(1) | O(1) amortised | | | |
| remove in the middle | O(n) | O(1) via iterator, O(n) to reach it | no | | | O(n) by object |
| contains(value) | O(n) | O(n) | O(n) | containsKey O(1) | O(log n) | O(n) |
| smallest element | | | | | O(log n) firstKey | O(1) peek |
| iteration order | index | index | deque order | unspecified | sorted | heap, not sorted |

## Example: an LRU cache in ten lines

```java
import java.util.LinkedHashMap;
import java.util.Map;

final class LruCache<K, V> extends LinkedHashMap<K, V> {

    private final int maximumEntries;

    LruCache(int maximumEntries) {
        super(16, 0.75f, true);
        this.maximumEntries = maximumEntries;
    }

    @Override
    protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
        return size() > maximumEntries;
    }
}
```

```java
LruCache<String, Integer> cache = new LruCache<>(3);
cache.put("a", 1);
cache.put("b", 2);
cache.put("c", 3);
cache.get("a");              // "a" is now the most recently used
cache.put("d", 4);           // size would be 4, so the eldest ("b") is evicted
System.out.println(cache);   // {c=3, a=1, d=4}
```

The third constructor argument switches on access order; without it you have a FIFO cache. The class is not thread-safe; for a cache shared between request threads use a library such as Caffeine.

## Example: `PriorityQueue` is not sorted

```java
PriorityQueue<Integer> queue = new PriorityQueue<>(List.of(5, 1, 4, 2, 3));
System.out.println(queue);                       // [1, 2, 4, 5, 3]  heap order
StringBuilder polled = new StringBuilder();
while (!queue.isEmpty()) {
    polled.append(queue.poll()).append(' ');
}
System.out.println(polled);                      // 1 2 3 4 5  only poll gives sorted order
```

## Pitfalls

- Mutable keys. Changing a field that feeds `hashCode` after the key is in the map leaves it in the wrong bucket; `get` returns `null` and the entry can never be removed by key.
- A `hashCode` that returns a constant or a handful of values. Everything lands in one bucket. If the keys are `Comparable`, treeification keeps lookups at O(log n); otherwise the tree has to fall back to scanning and you are at O(n).
- Depending on `HashMap` or `HashSet` iteration order. It changes when the table resizes and between JDK versions. Use `LinkedHashMap`, `TreeMap`, or sort.
- `new HashMap<>(100)` to hold 100 entries. The argument is the table size, so the map resizes at 75 entries. Use `HashMap.newHashMap(expectedSize)` (Java 19), which accounts for the load factor.
- `list.remove(1)` on a `List<Integer>`. That is `remove(int index)`, not `remove(Object)`; write `list.remove(Integer.valueOf(1))`.
- Removing inside a for-each loop. The next `iterator.next()` throws `ConcurrentModificationException` (see item 2.5). Use `removeIf` or `Iterator.remove`.
- `list.contains` in a loop over another list. O(n × m); put one side in a `HashSet` first.

## Check yourself

1. Why does `HashMap` XOR the upper 16 bits of the hash code into the lower 16 bits before masking with `table.length - 1`?
2. A bucket has nine colliding entries but the table has 32 slots. Does the map treeify that bucket? What does it do instead, and why is that usually enough?
3. Appending n elements to an `ArrayList` triggers about log₁.₅(n) resizes, each copying the whole array. Why is the total still O(n)?
4. You need a FIFO work queue drained by one thread, and a "next deadline" structure for a scheduler. Which collection for each, and why not `LinkedList` for either?

## Go deeper

- [Baeldung: Java HashMap Under the Hood](https://www.baeldung.com/java-hashmap-advanced) · walks through `hash()`, `putVal` and `resize` in the OpenJDK source.
- [Baeldung: A Guide to Java HashMap](https://www.baeldung.com/java-hashmap) · the API and the `equals`/`hashCode` requirements for keys.
- [Baeldung: ArrayList vs. LinkedList](https://www.baeldung.com/java-arraylist-linkedlist) · the complexity comparison, with the memory overhead of linked nodes.
- [dev.java: The Collections Framework](https://dev.java/learn/api/collections-framework/) · the official tour of every interface and implementation, including when to choose which.
- [HashMap API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html) and [LinkedHashMap API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html) · the class comments document load factor, capacity and the `removeEldestEntry` contract.

---

Part of [Java](../README.md) · items 2.2, 2.3
