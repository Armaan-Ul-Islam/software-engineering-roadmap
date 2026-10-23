# How a program runs: the CPU, the memory hierarchy and the JIT

> **In one sentence:** A CPU only ever fetches, decodes and executes instructions against a few dozen registers, so the time your code takes is set by how far away its data is (register, cache, RAM, disk) and by how well the JIT compiler turned your bytecode into tight machine code.

**Why it matters:** Two loops with identical Big-O can differ tenfold because one walks memory in order and the other jumps around. The memory hierarchy explains why `ArrayList` beats `LinkedList`, why object-heavy designs are slow whatever the algorithm, and why a Java service is slow for its first minute. Interviewers ask "what happens when you run this" to find out whether you have a model or a guess.

## The idea

**The cycle.** A core repeats one loop billions of times a second: fetch the instruction at the program counter, decode it, execute it (arithmetic on registers, a load or store, or a branch), repeat. Registers are the only place arithmetic happens; everything else is traffic to and from them. Modern cores pipeline many instructions and predict branches; a mispredicted branch throws away on the order of 10 to 20 cycles of work, so an unpredictable `if` in a hot loop is expensive and a predictable one nearly free.

**The hierarchy.** Approximate figures for a current server or laptop:

| Level | Typical size | Approximate latency |
|---|---|---|
| L1 cache | 32 to 128 KiB per core | about 1 ns |
| L2 cache | 256 KiB to 2 MiB per core | 3 to 5 ns |
| L3 cache | tens of MiB, shared | 10 to 20 ns |
| RAM | tens to hundreds of GiB | 80 to 100 ns |
| NVMe SSD, random read | TiB | tens of µs |
| Network round trip inside a datacentre | | about 500 µs |
| Spinning disk seek | | about 10 ms |

The ratios are what to remember: a RAM access costs roughly 100 L1 hits, an SSD read roughly 100 RAM accesses, a network round trip roughly 10 SSD reads.

**Cache lines and locality.** Data moves between RAM and the caches in fixed blocks called cache lines, 64 bytes on x86-64 and most ARM chips (128 on Apple Silicon). Reading one `int` pulls in its 15 neighbours for free. The hardware prefetcher notices sequential access and fetches the next lines before you ask for them. Code that touches memory in order (spatial locality) or touches the same data repeatedly (temporal locality) runs out of cache; code that follows pointers to scattered objects pays the RAM latency on every hop. The TLB, a small cache of address translations, adds its own misses when you stride across many pages (item 2.3).

**From source to machine code.** A C compiler produces machine code ahead of time and a linker glues object files into an executable; Java splits the work. `javac` compiles source to bytecode, a compact stack-machine instruction set stored in `.class` files. At run time the JVM loads classes lazily, verifies and links them, and starts executing bytecode in an interpreter. It counts invocations and loop iterations; a method that gets warm is compiled by the C1 compiler, and a hot one by C2, which uses the profile gathered so far to inline calls, remove bounds checks, unroll loops and specialise for the types actually seen. If an assumption later breaks (a new subclass shows up), the JVM deoptimises back to the interpreter and recompiles. This is why Java needs warm-up and why the first timing of anything is meaningless; `-XX:+PrintCompilation` shows what has been compiled and when.

## Example: sum a 2D array two ways

Both loops perform exactly 16,777,216 additions. Only the order differs.

```java
import java.util.function.LongSupplier;

public final class ArrayTraversal {

    private static final int ROWS = 4_096;
    private static final int COLUMNS = 4_096;

    public static void main(String[] arguments) {
        int[][] matrix = new int[ROWS][COLUMNS];
        for (int row = 0; row < ROWS; row++) {
            for (int column = 0; column < COLUMNS; column++) {
                matrix[row][column] = row ^ column;
            }
        }
        for (int round = 1; round <= 3; round++) {
            time("row-major   ", () -> sumRowMajor(matrix));
            time("column-major", () -> sumColumnMajor(matrix));
        }
    }

    static long sumRowMajor(int[][] matrix) {
        long sum = 0;
        for (int row = 0; row < ROWS; row++) {
            for (int column = 0; column < COLUMNS; column++) {
                sum += matrix[row][column];
            }
        }
        return sum;
    }

    static long sumColumnMajor(int[][] matrix) {
        long sum = 0;
        for (int column = 0; column < COLUMNS; column++) {
            for (int row = 0; row < ROWS; row++) {
                sum += matrix[row][column];
            }
        }
        return sum;
    }

    static void time(String label, LongSupplier work) {
        long start = System.nanoTime();
        long result = work.getAsLong();
        long elapsedMillis = (System.nanoTime() - start) / 1_000_000;
        System.out.printf("%s %4d ms (sum %d)%n", label, elapsedMillis, result);
    }
}
```

Run it with `java ArrayTraversal.java`. On an Apple Silicon laptop with JDK 25:

```text
row-major      10 ms (sum 34351349760)
column-major   63 ms (sum 34351349760)
row-major       7 ms (sum 34351349760)
column-major   62 ms (sum 34351349760)
row-major       6 ms (sum 34351349760)
column-major   63 ms (sum 34351349760)
```

Your numbers will differ; the ratio, here about 9x, is the point. The array is 64 MiB, far bigger than any cache, so both loops stream it from RAM. The difference is how much of each fetched line gets used. A Java `int[4096][4096]` is 4,096 separate `int[4096]` arrays of 16 KiB each. The row-major loop reads 16 consecutive ints per 64-byte line and the prefetcher keeps the next lines coming: one RAM access serves 16 additions. The column-major loop reads one int and jumps 16 KiB into the next row's array: a new cache line every time, usually a new page too (so the TLB misses as well), and by the time the loop returns for the next column the line has been evicted from L1. One RAM access serves one addition.

Two smaller things show too: the first round is slower because the loop started in the interpreter and was compiled while running, and the sum is printed because the JIT may delete a result nobody reads, together with the loop that computed it.

## Pitfalls

- Reasoning about speed from Big-O alone. Iterating a `LinkedList` and an `ArrayList` are both O(n); one chases a pointer into a cold cache line per element, the other streams through a contiguous array with the prefetcher's help.
- Measuring once, cold. The first run includes class loading, interpretation and compilation; use warm-up rounds or JMH, and consume the result.
- Object-heavy layouts. A `List<Point>` is an array of references to objects scattered across the heap; primitive arrays, or parallel arrays, keep the data contiguous.
- Unpredictable branches in hot loops. The famous "why is processing a sorted array faster" question is exactly this; sorting first, or replacing the branch with arithmetic, fixes it.
- Two threads writing different fields that share a cache line (false sharing): each write invalidates the other core's copy. The fix is padding or separate objects; the Memory & Concurrency domain has the details.

## Check yourself

1. Both loops execute the same instructions the same number of times. Explain, in terms of cache lines and pages, where the extra 55 ms goes.
2. A `LinkedList<Integer>` and an `int[]` each hold one million numbers. Estimate the number of RAM accesses needed to sum each, and say what dominates.
3. Why is the first `row-major` round slower, and what information does the C2 compiler have at that point that `javac` never had?
4. You replace `int[4096][4096]` with one `int[4096 * 4096]` indexed as `row * 4096 + column`. What changes for the row-major loop, for the column-major loop, and for memory use?

## Go deeper

- [Interactive latency numbers](https://colin-scott.github.io/personal_website/research/interactive_latency.html) · the hierarchy as numbers, with a slider for the year; memorise the ratios.
- [What Every Programmer Should Know About Memory](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf) · sections 3 and 6 cover caches and what programmers can do about them.
- [CS:APP](https://csapp.cs.cmu.edu/) · chapters 4 to 7: processor architecture, optimisation, the memory hierarchy, linking.
- [JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/) · Aleksey Shipilёv's short, measured notes on what HotSpot really does, including JIT behaviour and object layout.

---

Part of [Foundations](../README.md) · items 1.1, 1.2, 1.3
