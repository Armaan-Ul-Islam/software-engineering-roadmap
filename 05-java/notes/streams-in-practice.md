# Streams in practice

> **In one sentence:** A stream pipeline does nothing until its terminal operation pulls elements through it one at a time, which is why `filter` plus `findFirst` stops early, why `sorted` and `distinct` must buffer everything, and why a parallel stream on the shared common pool only pays off for large, CPU-bound, easily split work.

**Why it matters:** Streams are the default idiom for collection processing in Java, and most bugs with them come from the evaluation model rather than the syntax: a `toMap` that works for a year and then dies on the first duplicate key, a stream reused after its terminal operation, side effects in `peek` that do not run, and a `parallelStream()` with blocking I/O inside that starves every other parallel stream and `CompletableFuture` in the JVM.

## The idea

**Laziness.** A pipeline is a source, zero or more intermediate operations (`map`, `filter`, `sorted`, each returning a new stream and doing no work), and exactly one terminal operation (`collect`, `forEach`, `findFirst`, `count`). Nothing runs until the terminal operation. Elements are then processed *vertically*: one element goes through every stage before the next element starts. **Short-circuiting** terminals (`findFirst`, `anyMatch`, `allMatch`) and intermediates (`limit`, `takeWhile`) stop pulling as soon as they can.

**Stateless versus stateful.** `map`, `filter`, `flatMap` and `mapMulti` look at one element at a time. `sorted`, `distinct`, `skip` and `limit` need state: `sorted` must see every element before it emits the first one, so `Stream.iterate(...).sorted().limit(10)` never terminates, and stateful operations are where parallel streams lose their speed-up.

**Single use.** A stream is consumed by its terminal operation; a second call throws `IllegalStateException: stream has already been operated upon or closed`.

**Side effects.** Lambdas in a pipeline should be pure. `peek` exists for debugging and the runtime may skip it: since Java 9, `List.of(1, 2, 3).stream().peek(System.out::println).count()` prints nothing because `count()` can read the size from the source.

**The collectors that matter.**

| Collector | What you get | Watch out for |
|---|---|---|
| `Stream.toList()` (Java 16) | unmodifiable list, nulls allowed | `Collectors.toList()` returns an `ArrayList` in practice but the contract does not promise mutability. |
| `groupingBy(classifier)` | `Map<K, List<T>>`, a `HashMap` | add a map factory (`TreeMap::new`) and a downstream (`counting()`, `summingInt`, `mapping`, `reducing`) when you need more than lists. |
| `toMap(key, value)` | `HashMap` | throws `IllegalStateException` on a duplicate key and `NullPointerException` on a null value. |
| `toMap(key, value, merge)` | the merge function decides what to do with duplicates | add a fourth argument (`LinkedHashMap::new`) to keep encounter order. |
| `partitioningBy(predicate)` | `Map<Boolean, List<T>>` with both keys always present | unlike `groupingBy`, an empty partition is still there. |
| `teeing(first, second, merger)` (Java 12) | two collectors over one pass, combined | the way to get a count and a sum, or a min and a max, without iterating twice. |

**When a loop is clearer.** You need the index, you want to stop early and also record why, you are updating two structures at once, the lambda bodies need checked exceptions, or the pipeline would need a comment to explain. A `for` loop is not a failure of modernity.

**Parallel streams.** `parallelStream()` splits the source with its `Spliterator` and runs the chunks on `ForkJoinPool.commonPool()`, whose parallelism is the number of available processors minus one (the calling thread also works). It helps when the source splits well (`ArrayList`, arrays, `IntStream.range`), there are many elements, each element costs real CPU time, the operations are stateless, and the result is cheap to merge (`sum`, `toList`; `groupingBy` into `HashMap`s merges badly, `groupingByConcurrent` helps). It hurts for small collections, `LinkedList` or `Stream.iterate` sources, `sorted` and `limit`, and above all for blocking work: a stream of 20 HTTP calls run in parallel occupies the common pool, which is shared with every other parallel stream and with `CompletableFuture.supplyAsync` defaults across the whole JVM. Common-pool size is a JVM-wide setting (`-Djava.util.concurrent.ForkJoinPool.common.parallelism`); running a parallel stream from inside a custom `ForkJoinPool` task makes it use that pool, but that is an implementation detail, not a documented contract. Virtual threads (see item 5.4) do not apply to parallel streams. For concurrent I/O use an executor, not `parallel()`.

## Example: totals per customer, and the `toMap` trap

```java
record Order(String customerId, BigDecimal total) {}

List<Order> orders = List.of(
    new Order("alice", new BigDecimal("10.00")),
    new Order("bob", new BigDecimal("20.00")),
    new Order("alice", new BigDecimal("5.50")));

Map<String, BigDecimal> totalsByCustomer = orders.stream()
    .collect(Collectors.groupingBy(
        Order::customerId,
        TreeMap::new,
        Collectors.reducing(BigDecimal.ZERO, Order::total, BigDecimal::add)));
System.out.println(totalsByCustomer);        // {alice=15.50, bob=20.00}

Map<String, BigDecimal> totals = orders.stream()
    .collect(Collectors.toMap(Order::customerId, Order::total));
// java.lang.IllegalStateException: Duplicate key alice (attempted merging values 10.00 and 5.50)
```

The `toMap` version is what gets written first, and it passes every test whose fixture has one order per customer. The fix is to say what a duplicate means:

```java
Map<String, BigDecimal> merged = orders.stream()
    .collect(Collectors.toMap(Order::customerId, Order::total, BigDecimal::add));
System.out.println(merged);                  // {bob=20.00, alice=15.50}
```

Two more collectors over the same data:

```java
Map<Boolean, Long> largeOrders = orders.stream()
    .collect(Collectors.partitioningBy(
        order -> order.total().compareTo(new BigDecimal("10.00")) >= 0, Collectors.counting()));
System.out.println(largeOrders);             // {false=1, true=2}

record Summary(long count, BigDecimal sum) {}

Summary summary = orders.stream().collect(Collectors.teeing(
    Collectors.counting(),
    Collectors.reducing(BigDecimal.ZERO, Order::total, BigDecimal::add),
    Summary::new));
System.out.println(summary);                 // Summary[count=3, sum=35.50]
```

## Example: watching laziness

```java
String first = Stream.of("a", "bb", "ccc", "dddd")
    .peek(word -> System.out.println("filtering " + word))
    .filter(word -> word.length() > 1)
    .map(word -> {
        System.out.println("mapping " + word);
        return word.toUpperCase();
    })
    .findFirst()
    .orElseThrow();
System.out.println(first);
```

```text
filtering a
filtering bb
mapping bb
BB
```

`ccc` and `dddd` are never touched: `findFirst` asked for one element, `bb` satisfied the filter, and the pipeline stopped.

## Pitfalls

- `toMap` without a merge function on data that can repeat. The exception message names the key, which is the only reason this is quick to diagnose.
- `toMap` with a value function that can return `null`. It throws `NullPointerException` from `HashMap.merge`; use `groupingBy` or filter first.
- Reusing a stream variable. Build the pipeline where you use it, or write a `Supplier<Stream<T>>`.
- Mutating a shared collection from `forEach` on a parallel stream (`parallel().forEach(list::add)`). Corrupts the `ArrayList`. Use `collect`.
- `sorted()` before `limit()` on a big stream expecting cheapness. The sort still buffers everything.
- Boxing. `Stream<Integer>` with `reduce(0, Integer::sum)` allocates per element; use `mapToInt(...).sum()`.
- `findFirst()` or `findAny()` on a stream whose selected element is `null` throws `NullPointerException`; filter nulls or map to `Optional`.
- Parallel streams in a web request. They help nobody: the request is already one of hundreds running in parallel, and you are now borrowing a JVM-wide pool for it.
- Streams with checked exceptions. Wrapping in `UncheckedIOException` inside every lambda is a sign the loop would be clearer.

## Check yourself

1. Why does the laziness example print `filtering bb` and `mapping bb` but nothing for `ccc`? What would change if `findFirst()` were `toList()`?
2. `toMap(Order::customerId, Order::total)` has worked in production for a year and now throws. What happened, and what are two fixes with different semantics?
3. Which of these should be parallel, and why: summing `IntStream.range(0, 50_000_000)`, `linkedList.parallelStream().sorted().limit(10)`, `ids.parallelStream().map(httpClient::fetch)`?
4. A colleague's `parallelStream()` with blocking JDBC calls slows down a `CompletableFuture.supplyAsync` chain in an unrelated module. Explain the connection.

## Go deeper

- [dev.java: The Stream API](https://dev.java/learn/api/collections-and-streams/streams/) · the official tutorial, from pipelines to custom collectors.
- [Baeldung: The Java Stream API](https://www.baeldung.com/java-8-streams) · a compact reference of every operation with examples.
- [Baeldung: When to Use a Parallel Stream](https://www.baeldung.com/java-when-to-use-parallel-stream) · splitting, merging and the common pool, with measurements.
- [java.util.stream package documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html) · the package comment defines laziness, stateful operations, side effects and the rules for parallel execution; read it once.
- [Collectors API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html) · every collector, including the exact exceptions `toMap` throws.

---

Part of [Java](../README.md) · items 2.6, 2.7
