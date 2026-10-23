# JVM flags and choosing a garbage collector for a service

> **In one sentence:** For a service in a container, size the heap as a percentage of the container's memory (`-XX:MaxRAMPercentage`), pick the collector by the pause times you need and the CPUs you have (G1 by default, ZGC for low pauses on large heaps, Parallel for throughput batch jobs), always write a GC log and a heap dump on `OutOfMemoryError`, and never set a flag you cannot explain.

**Why it matters:** The JVM's defaults were chosen for a generic machine, not for a two-CPU container with 2 GB: left alone it takes a quarter of the memory for the heap and, below two CPUs, silently picks the single-threaded Serial collector. Most "the JVM is slow" and "the pod keeps getting OOM-killed" tickets are a mismatch between container limits and JVM sizing, and the GC log is the artefact that tells you whether you have a leak, a sizing problem or an allocation problem (see item 8.5).

## The idea

**Heap sizing.** `-Xmx` sets the maximum heap in absolute terms; `-XX:MaxRAMPercentage` sets it as a percentage of the memory the JVM detects, which inside a container is the cgroup limit (container support has been on by default since JDK 10, with cgroup v2 supported since JDK 15). The default is 25 percent. `-XX:InitialRAMPercentage` (default 1.5625) or `-Xms` sets the starting size; in a container with a fixed limit, start and maximum are usually set equal so the heap does not grow and shrink under load. The heap is not the whole process: Metaspace, thread stacks (about 1 MB per platform thread), the code cache, direct `ByteBuffer`s and the collector's own data structures live outside it. A heap at 50 to 75 percent of the container limit leaves room for them; a heap at 95 percent gets the process killed by the kernel with exit code 137 and no Java stack trace. Check what the JVM decided with `java -XX:+PrintFlagsFinal -version | grep -E 'MaxHeapSize|Use.*GC '` inside the container; `-XshowSettings:system` (Linux only) prints the container limits it detected. `-XX:ActiveProcessorCount=N` overrides CPU detection, which drives GC thread counts and the common pool.

**Choosing a collector.** Each is a trade between pause time, throughput and footprint:

| Collector | Flag | Character | Pick it for |
|---|---|---|---|
| G1 | `-XX:+UseG1GC` (default with 2+ CPUs and about 2 GB+) | region-based, mostly concurrent marking, pause goal `-XX:MaxGCPauseMillis=200` | almost every service: balanced latency and throughput, heaps from 1 GB to tens of GB |
| ZGC | `-XX:+UseZGC` | fully concurrent, pauses well under a millisecond regardless of heap size; needs CPU headroom and some extra heap | latency-sensitive services with large heaps and spare cores |
| Parallel | `-XX:+UseParallelGC` | stop-the-world, all cores, highest throughput, longest pauses | batch jobs and anything where total runtime matters more than any single pause |
| Serial | `-XX:+UseSerialGC` (the default below 2 CPUs or about 1.8 GB) | one thread, smallest footprint | tiny sidecars and single-CPU containers, where there is no CPU for concurrent work anyway |

ZGC changed across releases: Java 21 added the generational mode behind `-XX:+ZGenerational`, Java 23 made it the default, and Java 24 removed the other mode, so on Java 25 `-XX:+UseZGC` alone is correct and `-XX:+ZGenerational` only prints `Ignoring option ZGenerational; support was removed in 24.0`. Java 25 also made compact object headers a product feature (`-XX:+UseCompactObjectHeaders`, JEP 519, off by default), which shrinks every object header by four bytes and noticeably reduces heap use for small-object-heavy applications.

**Diagnostics you always want on.** `-XX:+HeapDumpOnOutOfMemoryError` with `-XX:HeapDumpPath` pointing at a mounted volume (the file is about the size of the live heap). `-XX:+ExitOnOutOfMemoryError`, so that an `OutOfMemoryError` kills the process and the orchestrator restarts it instead of leaving a half-dead JVM serving errors. And unified logging for GC: `-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m`, where the four colon-separated parts are selectors, output, decorators and output options.

**Reading a GC log.** With `-Xlog:gc` every collection is one line:

```text
[2026-10-24T00:39:09.444+0600][0.018s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 18M->1M(32M) 0.366ms
```

Decorators, then the collection id, the pause type (`Young (Normal)`, `Young (Concurrent Start)`, `Young (Mixed)`, `Remark`, `Cleanup`, or `Full`), the cause, heap used before and after with the committed size in parentheses, and the pause duration. Read three things from a sequence of these: the *after* value is the live set, and if it climbs across collections under steady load you have a leak or a growing working set; `Pause Full` lines under G1 mean the concurrent cycle lost the race against allocation or the heap is too small; and frequency times duration is the fraction of time the application is paused. `-Xlog:gc*` adds the per-phase breakdown and lines such as `[gc,heap] GC(0) Eden regions: 17->0(13)` and `[gc,cpu] GC(0) User=0.00s Sys=0.00s Real=0.00s`, where high `Sys` points at paging and a `Real` much larger than `User` divided by the GC threads points at CPU starvation.

## Example: a production options line for a container

```text
java -XX:MaxRAMPercentage=75.0 -XX:InitialRAMPercentage=75.0 \
     -XX:+UseG1GC -XX:MaxGCPauseMillis=200 \
     -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps \
     -XX:+ExitOnOutOfMemoryError \
     -Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m \
     -jar app.jar
```

| Flag | Why it is there |
|---|---|
| `-XX:MaxRAMPercentage=75.0` | heap scales with the container limit; 75 percent leaves a quarter for Metaspace, stacks, code cache and direct buffers. Lower it for services with many threads or large off-heap caches. |
| `-XX:InitialRAMPercentage=75.0` | start at the final size; memory problems appear at startup rather than at peak traffic. |
| `-XX:+UseG1GC` | explicit, so a one-CPU environment does not silently switch to Serial. |
| `-XX:MaxGCPauseMillis=200` | the default, written down so the intent is visible; lower it only after reading the log. |
| `-XX:+HeapDumpOnOutOfMemoryError`, `-XX:HeapDumpPath=/dumps` | the one chance to see what filled the heap, written to a volume that survives the restart. |
| `-XX:+ExitOnOutOfMemoryError` | fail fast and let the orchestrator restart a healthy process. |
| `-Xlog:gc*:file=...` | rotated GC log, five files of 20 MB, with wall-clock time so it lines up with application logs. |

For a latency-critical service on a large heap with spare CPU, replace the G1 pair with `-XX:+UseZGC`; for a nightly batch job, with `-XX:+UseParallelGC`. When you do not control the command line, the `JAVA_TOOL_OPTIONS` environment variable carries the same flags (the JVM prints `Picked up JAVA_TOOL_OPTIONS:` at startup).

## Pitfalls

- `-Xmx` equal or close to the container limit. The kernel kills the process (exit code 137) before the JVM can throw `OutOfMemoryError`, so you get neither a heap dump nor a stack trace.
- Leaving `MaxRAMPercentage` at its default. A 2 GB container runs with a 512 MB heap.
- Not knowing the Serial fallback. A one-CPU container gets Serial unless you say otherwise, and a service with pause-time goals will notice.
- CPU shares without quotas. The JVM may see all host CPUs and start dozens of GC threads; set `-XX:ActiveProcessorCount`.
- Flags copied from old blog posts. `-XX:+UseConcMarkSweepGC` and `-XX:PermSize` no longer exist; the JVM refuses to start or warns and ignores them. Do not hide that with `-XX:+IgnoreUnrecognizedVMOptions`.
- Hand-tuning generation sizes under G1 (`-Xmn`, `-XX:NewRatio`). It disables G1's adaptive sizing; set the pause goal instead.
- Heap dumps written to the container's ephemeral filesystem. The restart deletes the evidence.
- No GC log because "it costs performance". It does not measurably, and it is the first thing you need in an incident.

## Check yourself

1. A container has a 4 GB limit and one CPU, and the JVM runs with no flags. How large is the maximum heap, and which collector runs?
2. Why is `-Xmx3800m` in a 4 GB container dangerous, and what will you see (and not see) when it goes wrong?
3. The GC log shows `Pause Young` every two seconds with `3900M->3850M(4096M)`, then a `Pause Full` lasting four seconds. What is happening, and which two different root causes should you distinguish?
4. When would you pick Parallel over G1, and ZGC over G1? Name the price of each.

## Go deeper

- [Oracle: Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/) · each collector's behaviour and tuning options; the G1 and ZGC chapters are short.
- [The java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html) · every flag, the full `-Xlog` syntax and the container options.
- [JEP 439: Generational ZGC](https://openjdk.org/jeps/439) and [JEP 519: Compact Object Headers](https://openjdk.org/jeps/519) · what changed in ZGC in Java 21 and in object layout in Java 25.
- [Java Performance, 2nd edition](https://www.oreilly.com/library/view/java-performance-2nd/9781492056102/) · chapters 5 and 6 explain the collectors and how to read their logs (paid).

---

Part of [Java](../README.md) · items 4.4, 4.5
