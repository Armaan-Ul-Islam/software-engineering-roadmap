# Finding memory leaks in a garbage-collected language

> **In one sentence:** A Java memory leak is an object that is still reachable but will never be used again, the GC log shows it as post-collection occupancy that only ever rises, a heap dump opened in Eclipse MAT shows who holds it, and when the process grows while the heap does not, the growth is somewhere the heap dump cannot see.

**Why it matters:** Leaks are the slowest-burning production incident: the service is healthy for days, then pauses lengthen, then it dies with `OutOfMemoryError` at the worst hour, restarts, and the cycle begins again. Knowing the five shapes a Java leak takes, and the fifteen-minute diagnostic path from GC log to dominator tree, is the difference between fixing the cause and scheduling a nightly restart.

## The idea

The collector frees what is unreachable (item 2.1). It cannot know that the entry you put in a map two hours ago will never be read again. So a leak in Java is always a *reference you forgot you were keeping*, and almost always one of these shapes:

1. **A static or long-lived collection that only grows.** A registry, a list of "recent" events, a `static Map` used as a cache without eviction.
2. **An unbounded cache.** A `HashMap` or `ConcurrentHashMap` keyed by something with unbounded cardinality (request id, user id, SQL text with inlined parameters). Caffeine or Guava caches with a maximum size and expiry exist for this reason.
3. **Listeners and callbacks that are registered and never removed.** Each one usually holds its enclosing object alive, and the enclosing object holds everything it references.
4. **`ThreadLocal` values on pooled threads.** Request threads in Tomcat or a thread pool live for the life of the process, so a value that is `set` and never `remove`d lives as long. On redeploy inside a servlet container, the value also pins the old web application's classloader.
5. **Classloader leaks.** Anything from a JDK or container class that references an application class (a registered JDBC driver, a running thread, a `ThreadLocal`, a static cache in a shared library) keeps the whole classloader and every class it loaded in Metaspace after redeploy.

**What a leak looks like in a GC log.** Read the "after" occupancy of successive collections (item 2.3). With a stable live set it saws between two values. With a leak it climbs: minor GCs reclaim less each time, concurrent cycles start and achieve nothing, full GCs appear and run back to back, and finally `java.lang.OutOfMemoryError: Java heap space`. A growing working set (more users, bigger caches by design) looks the same from the log alone; the heap dump tells them apart.

**When the heap is fine but the process is not.** Resident set size (RSS, what the OS and your container limit see) is the heap plus everything the JVM allocates natively: **Metaspace** (class metadata; grows with classloader leaks and class-generating frameworks), **thread stacks** (reserved per thread, committed as touched), **direct `ByteBuffer`s** (Netty, NIO, many drivers; capped by `-XX:MaxDirectMemorySize`, freed only when the owning object is collected), the JIT **code cache**, the collector's own structures, and malloc calls from native libraries. A heap dump shows none of this; Native Memory Tracking shows everything the JVM itself allocates.

## Example: a deliberate leak and the diagnostic path

```java
import java.util.HashMap;
import java.util.Map;

public class LeakyCache {

    private static final Map<String, byte[]> RESPONSE_CACHE = new HashMap<>();

    public static void main(String[] arguments) throws InterruptedException {
        long requestNumber = 0;
        while (true) {
            handleRequest("request-" + requestNumber++);
            Thread.sleep(1);
        }
    }

    private static void handleRequest(String requestId) {
        byte[] response = new byte[64 * 1024];
        RESPONSE_CACHE.put(requestId, response);
    }
}
```

The key has unbounded cardinality and nothing ever evicts. Run it with `java -Xlog:gc -Xmx256m -XX:NativeMemoryTracking=summary LeakyCache` (OpenJDK 25, G1):

```text
[1.018s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 48M->47M(256M) 6.542ms
[2.598s][info][gc] GC(1) Pause Young (Normal) (G1 Evacuation Pause) 117M->117M(256M) 16.204ms
[3.535s][info][gc] GC(2) Pause Young (Normal) (G1 Evacuation Pause) 159M->159M(256M) 5.679ms
[4.173s][info][gc] GC(3) Pause Young (Concurrent Start) (G1 Evacuation Pause) 189M->189M(256M) 2.238ms
[4.898s][info][gc] GC(6) Pause Young (Mixed) (G1 Evacuation Pause) 223M->223M(256M) 1.561ms
[5.552s][info][gc] GC(11) Pause Full (G1 Compaction Pause) 255M->238M(256M) 14.912ms
[5.606s][info][gc] GC(14) Pause Full (G1 Compaction Pause) 240M->240M(256M) 5.565ms
[5.612s][info][gc] GC(15) Pause Full (G1 Compaction Pause) 240M->240M(256M) 5.995ms
```

Every collection reclaims nothing (`117M->117M`), the concurrent cycle and the mixed collection change nothing, and the full GCs at the end free 0 MB. That is the signature. Then, in order:

1. **Cheapest look: the class histogram.** `jcmd <pid> GC.class_histogram | head` lists classes by shallow size:

   ```
    num     #instances         #bytes  class name (module)
   -------------------------------------------------------
      1:         25514       70431656  [B (java.base@25.0.1)
      2:          2289        1040816  [Ljdk.internal.vm.FillerElement; (java.base@25.0.1)
      3:         16935         406440  java.lang.String (java.base@25.0.1)
      4:          9516         304512  java.util.HashMap$Node (java.base@25.0.1)
   ```

   Byte arrays dominate. That says *what* is leaking, not *who* holds it; byte arrays are rarely the answer by themselves.

2. **Take a heap dump.** `jcmd <pid> GC.heap_dump /tmp/leak.hprof` prints `Heap dump file created [77083561 bytes in 0.077 secs]`. It dumps only live objects (it runs a full GC first; `-all` includes unreachable ones), pauses the JVM while writing, and produces a file about the size of the live heap; `-gz=1` compresses it. For the incident you did not watch live, start the JVM with `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps` and the dump is taken for you.

3. **Open it in Eclipse MAT.** Run the *Leak Suspects* report, then open the **Dominator Tree**. A dominates B when every path from the roots to B passes through A, so A's **retained size** is exactly what collecting A would free. Sorted by retained size, the top entry here is one `java.util.HashMap` retaining almost the whole heap, held by the static field `LeakyCache.RESPONSE_CACHE`; *Path to GC Roots, exclude weak and soft references* shows the chain that keeps it alive. In a real service the top entry is the same kind of thing: one collection, one field, one owner, and the fix is an eviction policy or a `remove` call.

4. **If the heap looks fine, read native memory.** With `-XX:NativeMemoryTracking=summary` on, `jcmd <pid> VM.native_memory summary` prints, for this process:

   ```
   Total: reserved=1760770KB, committed=335266KB
   -                 Java Heap (reserved=270336KB, committed=249856KB)
   -                     Class (reserved=1048649KB, committed=201KB)
                               (classes #741)
   -                    Thread (reserved=47170KB, committed=578KB)
                               (threads #23)
   -                      Code (reserved=249707KB, committed=7707KB)
   -                        GC (reserved=58907KB, committed=58683KB)
   ```

   335 MB committed for a 250 MB heap: 58 MB of it is G1's bookkeeping. `jcmd <pid> VM.native_memory baseline` now and `summary.diff` an hour later shows which category grew; `Class` growing means a classloader leak, `Thread` means leaked threads, `Internal` or `Other` often means direct buffers. NMT costs a few percent of CPU, which is acceptable for a diagnosis window.

## Pitfalls

- Dumping the heap of the only instance at peak traffic. The pause is seconds and the file is as large as the heap; dump a replica, or one instance after it has been drained.
- Reading the histogram and stopping. `byte[]`, `char[]`, `String` and `HashMap$Node` top every histogram; only the dominator tree says who owns them.
- Opening a 20 GB dump in MAT with default settings. Raise `-Xmx` in `MemoryAnalyzer.ini` to roughly the dump size, or MAT itself runs out of memory.
- Treating `OutOfMemoryError` as always a leak. A heap that is simply too small for the working set produces the same error; the difference is whether the dominator tree shows one surprising owner or many expected ones.
- Reaching for `WeakHashMap` or soft references instead of a bounded cache. Weak keys vanish when nothing else references the key, which is rarely the lifetime you wanted; soft references hand your eviction policy to the collector (item 2.6).
- Trusting the heap when the container keeps killing the process. An OOM kill from the kernel is about RSS, not heap. Count threads (`jcmd <pid> Thread.print | grep -c '^"'`), check direct memory (`jcmd <pid> VM.native_memory`), and remember that most collectors return memory to the OS slowly or not at all.

## Check yourself

1. A `static final List<Listener> LISTENERS` gains one anonymous inner class per request and nothing removes them. Which shape is this, what does the dominator tree show, and what two fixes are available?
2. Why does `GC.class_histogram` showing 70 MB of `byte[]` not tell you where the leak is, and what view does?
3. A service runs at a steady 1.2 GB heap but its RSS grows 100 MB a day until the container is killed. Name three places the growth can be and the command that distinguishes them.
4. What is the difference between an object's shallow size and its retained size, and why does MAT's Dominator Tree sort by the latter?

## Go deeper

- [Eclipse Memory Analyzer](https://eclipse.dev/mat/) · the tool; its documentation explains the Dominator Tree and the Leak Suspects report.
- [Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html) · the official guide to the categories in the `VM.native_memory` output and to `baseline` and `diff`.
- [Baeldung: Understanding Memory Leaks in Java](https://www.baeldung.com/java-memory-leaks) · the common shapes with code for each.
- [Oracle: Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/) · for the GC-log reading that comes before any dump.

---

Part of [Memory & Concurrency](../README.md) · items 2.5, 2.7
