# Garbage collection fundamentals: reachability, generations and the HotSpot collectors

> **In one sentence:** A garbage collector keeps every object reachable from the roots and reclaims the rest, the collectors differ in how they find and move the survivors (mark-sweep, compact, or copy; stopped or concurrent; whole heap or one generation at a time), and that choice is a trade between throughput, pause time and memory.

**Why it matters:** GC shows up in every Java service as latency spikes, CPU spent collecting instead of serving, and heaps that are "full" when the live data is small. Ten lines of a GC log, read correctly, tell you whether you have a leak, an undersized heap, or nothing at all; choosing the collector is a two-minute decision that is easy to get wrong for years.

## The idea

**Reachability.** An object is live if it can be reached by following references from a **GC root**: a local variable or operand on any thread's stack, a `static` field of a loaded class, a JNI reference, or a few JVM-internal structures. Everything else is garbage, however recently it was used. There is no reference counting in HotSpot, so cycles are not a problem, and nothing is freed at any particular moment; it is freed when a collection runs.

**Three ways to collect.**

1. **Mark-sweep.** Mark every reachable object, then put the unmarked gaps on free lists. Cost is proportional to the whole heap, and the heap fragments, so allocation must search for a gap.
2. **Mark-compact.** Mark, then slide the live objects together and fix every reference. No fragmentation and bump-pointer allocation afterwards, but compaction touches all live data.
3. **Copying.** Copy the live objects into an empty region (the *to-space*) and declare the old one free. Cost is proportional to live data only, dead objects cost nothing, and the result is compact; the price is reserving space to copy into.

**Generations.** The weak generational hypothesis says most objects die young: a request's temporary strings and DTOs are garbage within milliseconds, while caches and pools live as long as the process. So HotSpot splits the heap into a **young generation** (Eden plus two survivor spaces) and an **old generation**. A **minor GC** collects only the young generation by copying: survivors bounce between the survivor spaces, ageing on each collection, and are **promoted** to the old generation after `MaxTenuringThreshold` (default 15) collections or when a survivor space overflows. Because little survives, minor GCs are cheap and frequent. A **major GC** collects the old generation; a **full GC** collects the whole heap, including class unloading, and is the expensive one. A write barrier records old-to-young references in a card table or remembered set so that a minor GC need not scan the old generation.

**Stop-the-world versus concurrent.** A stop-the-world (STW) phase brings every Java thread to a safepoint and holds it there; its length is what you see as a pause. A concurrent phase runs alongside the application, which keeps mutating the object graph, so the collector needs barriers (G1 and Shenandoah use a snapshot-at-the-beginning write barrier; ZGC uses load barriers and coloured pointers) and it needs CPU and spare heap while it works. If the application allocates faster than the concurrent collector frees, the collector loses: G1 falls back to a full GC, ZGC stalls the allocating threads.

**The HotSpot collectors.**

| Collector | Flag | Young collection | Old collection | Optimised for | Choose it when |
|---|---|---|---|---|---|
| Serial | `-XX:+UseSerialGC` | STW copying, one thread | STW mark-compact, one thread | footprint | tiny heaps, one CPU, short-lived tools |
| Parallel | `-XX:+UseParallelGC` | STW copying, all cores | STW mark-compact, all cores | throughput | batch jobs where total time matters and pauses do not |
| G1 (default since JDK 9) | `-XX:+UseG1GC` | STW copying of regions | concurrent marking, then STW evacuation of the emptiest regions ("mixed" collections) | balance, with a pause target (`-XX:MaxGCPauseMillis`, default 200) | almost every service |
| ZGC | `-XX:+UseZGC` | concurrent (generational since JDK 23, JEP 474) | concurrent marking and relocation | pauses well under a millisecond | large heaps and strict latency, if you can spend CPU and memory headroom |
| Shenandoah | `-XX:+UseShenandoahGC` | concurrent | concurrent | low pauses | same goals as ZGC; not shipped in Oracle's builds |

The JVM picks Serial by itself when it does not see a "server-class machine": fewer than two CPUs or roughly less than 2 GB of memory, which includes many small containers. Rule of thumb: stay on G1 unless you can name the problem. Pauses do not matter and you want every bit of throughput: Parallel. Pauses of tens of milliseconds are unacceptable and the heap is several gigabytes: ZGC, and measure the extra CPU. One CPU and a few hundred megabytes: Serial, which also has the smallest off-heap overhead.

## Example: reading `-Xlog:gc`

Run any program with `-Xlog:gc` (always on in production; the cost is negligible). This is G1 on OpenJDK 25 with `-Xmx128m`, running a loop that churns short-lived arrays while keeping a bounded cache of about 70 MB:

```text
[0.005s][info][gc] Using G1
[0.045s][info][gc] GC(3) Pause Young (Normal) (G1 Evacuation Pause) 87M->69M(128M) 2.489ms
[0.050s][info][gc] GC(4) Pause Young (Concurrent Start) (G1 Evacuation Pause) 97M->82M(128M) 2.340ms
[0.050s][info][gc] GC(5) Concurrent Mark Cycle
[0.055s][info][gc] GC(6) Pause Young (Normal) (G1 Evacuation Pause) 104M->92M(128M) 3.620ms
[0.057s][info][gc] GC(5) Pause Remark 103M->97M(128M) 0.337ms
[0.059s][info][gc] GC(5) Pause Cleanup 101M->101M(128M) 0.010ms
[0.059s][info][gc] GC(5) Concurrent Mark Cycle 9.100ms
[0.060s][info][gc] GC(9) Pause Young (Prepare Mixed) (G1 Evacuation Pause) 115M->106M(128M) 0.530ms
[0.062s][info][gc] GC(10) Pause Young (Mixed) (G1 Evacuation Pause) (Evacuation Failure: Allocation) 119M->113M(128M) 0.511ms
```

Each line is: JVM uptime, log tags, a GC id, the kind of collection, its cause, heap occupancy before and after with the committed heap in parentheses, and the pause length. Reading the story:

- `GC(3)` is an ordinary minor GC: 87 MB in use, 69 MB after, 2.5 ms stopped. The 18 MB difference died in Eden; the rest is the cache plus whatever was promoted.
- `GC(4)` is a minor GC that also started a **concurrent cycle** (`GC(5)`) because old-generation occupancy crossed G1's threshold. Marking ran *concurrently*: `GC(6)`, a normal minor GC, is interleaved with it. `Remark` and `Cleanup` are the cycle's two short pauses.
- `GC(9)` and `GC(10)` are **mixed** collections: young regions plus the old regions marking found mostly empty. `Evacuation Failure: Allocation` means G1 ran out of free regions to copy into: this heap is too small for this workload, and a full GC is next.

The number to watch over hours is the "after" value of successive collections: flat means a stable live set, rising means a leak or a working set that outgrew the heap (item 2.5), and regular `Pause Full` lines mean G1 lost the race. `-Xlog:gc*` adds per-generation region counts, promotion and metaspace to every collection when you need the detail.

## Pitfalls

- Calling `System.gc()` to "free memory". It requests a full GC, the most expensive kind, and frees nothing that was not already garbage. `-XX:+DisableExplicitGC` exists because libraries do this.
- Sizing the heap to the machine instead of the live set. A heap that is three to four times the live set gives the young generation room to let objects die; a heap barely above the live set makes every collection promote and every promotion expensive.
- Judging a collector from one pause. Compare GC CPU time, the 99th percentile pause and allocation stalls under the same load; concurrent collectors buy pause time with throughput and memory.
- Mistaking a growing heap for a leak. Collectors defer work while there is room; occupancy that climbs until a major collection and then drops is normal. A leak is "after" values that never come back down.
- Humongous allocations in G1. Objects bigger than half a region (regions are 1 to 32 MB) go straight into the old generation and are reclaimed late; large byte arrays for uploads or serialisation are the usual culprits.
- Advice older than your JDK. G1 has been the default since JDK 9; ZGC became generational in JDK 23 and dropped its non-generational mode in JDK 24 (JEP 490), so older ZGC guidance no longer applies.

## Check yourself

1. A `static final Map<String, Config>` holds configuration for the whole process. Why does the collector never free it, and does it cost anything during a minor GC?
2. Why is a copying collector cheap for the young generation but a poor choice for an old generation that is 90 percent live?
3. In the log above, what does `97M->82M` on `GC(4)` tell you that `Pause Remark 103M->97M` does not, and why could a normal young GC run in the middle of the marking cycle?
4. A nightly batch job on a 16-core box takes 40 minutes and nobody is waiting on any single request. Which collector would you try, what would you expect to improve, and what would you check to confirm it?

## Go deeper

- [Oracle: Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/) · the official reference; the [Generations](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-collector-implementation.html) and [Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html) chapters cover this note's ground precisely.
- [JEP 439: Generational ZGC](https://openjdk.org/jeps/439) · why a concurrent collector still wants generations, with the design explained from first principles.
- [Baeldung: JVM Garbage Collectors](https://www.baeldung.com/jvm-garbage-collectors) · a quick survey of the collectors and their flags.
- [GCeasy](https://gceasy.io/) · upload a GC log and get the trend graphs this note asks you to read by eye.

---

Part of [Memory & Concurrency](../README.md) · items 2.1, 2.2, 2.3
