# A troubleshooting workflow for the three classic JVM incidents

> **In one sentence:** Before restarting a sick JVM, capture evidence with `jcmd` (three thread dumps for stuck requests or high CPU, the GC log plus a class histogram or heap dump for memory growth, a JFR recording or async-profiler flame graph for CPU), then read it for a handful of known patterns: `BLOCKED` chains pointing at one lock holder, pool threads parked waiting for a connection, `RUNNABLE` threads stuck in the same frames, and a post-collection heap floor that keeps rising.

**Why it matters:** Incidents happen when nobody is fresh, and the first instinct is to restart, which destroys the only evidence. A fixed sequence of commands you can type from memory gets the data in two minutes and makes root cause possible later. It is also the most common senior interview scenario: "the service is slow, what do you do first?"

## The idea

**One tool: `jcmd`.** `jcmd` with no arguments lists Java processes; `jcmd <pid> help` lists the commands the JVM supports. The ones you need:

| Command | What it gives you | Cost |
|---|---|---|
| `jcmd <pid> Thread.print -l` | a thread dump with lock ownership | milliseconds, safe to repeat |
| `jcmd <pid> GC.heap_info` | heap size, used and committed per generation | none |
| `jcmd <pid> GC.class_histogram` | live instances and bytes per class | a full GC pause |
| `jcmd <pid> GC.heap_dump -gz=1 /dumps/heap.hprof` | an hprof file for Eclipse MAT | a stop-the-world pause of seconds to minutes, disk space about the live heap |
| `jcmd <pid> JFR.start duration=120s filename=/tmp/rec.jfr settings=profile` | CPU, allocation, lock and I/O events for JDK Mission Control | low, designed for production |
| `jcmd <pid> VM.flags`, `VM.command_line`, `VM.native_memory summary` | how the JVM was started; native memory if `-XX:NativeMemoryTracking=summary` is on | none |
| `jcmd <pid> Thread.dump_to_file -format=json /tmp/threads.json` | a dump that includes virtual threads (Java 21); `Thread.print` does not | milliseconds |

Around it: `top -H -p <pid>` for per-thread CPU, the GC log you should already be writing (`-Xlog:gc*`, see item 4.5), async-profiler (`asprof -d 30 -e cpu -f /tmp/cpu.html <pid>`; `-e alloc`, `-e lock`, `-e wall` for the other profiles) and Eclipse MAT for heap dumps. In a container, run `jcmd` inside the container as the same user as the JVM, which means the image needs a JDK, not a JRE.

**Thread states.** `RUNNABLE` means the thread is running or in native code, including blocking socket reads, so a `RUNNABLE` thread in `SocketDispatcher.read0` is waiting on the network, not burning CPU. `BLOCKED` is waiting to enter a `synchronized` block; the dump says `waiting to lock <id>` and somewhere another thread says `locked <id>`. `WAITING` and `TIMED_WAITING` are `park`, `wait`, `join`, `sleep`; `parking to wait for <id> (a ...ConditionObject)` under `HikariPool.getConnection` means the connection pool is empty.

**Leak or badly sized heap?** Look at heap usage *after* each collection in the GC log. A sawtooth with a stable floor is healthy. A floor that rises over hours under steady load is a leak (or a working set that genuinely grows; the histogram tells you which). A stable floor close to the maximum, with collections every few seconds and long pauses, is an undersized heap: raise `-Xmx` or shrink the working set. Frequent young collections with a low floor are a high allocation rate, which is a profiling job (`-e alloc`, or JFR's allocation events), not a sizing job.

## Example: stuck requests, the commands in order

Symptoms: latency and the request queue climb, CPU is low, nothing in the logs.

```text
$ jcmd                                              # find the pid
$ jcmd 96326 Thread.print -l > dump1.txt; sleep 10
$ jcmd 96326 Thread.print -l > dump2.txt; sleep 10
$ jcmd 96326 Thread.print -l > dump3.txt
$ grep 'java.lang.Thread.State' dump1.txt | sort | uniq -c
```

Three dumps ten seconds apart separate "stuck" from "slow but moving": a thread in the same frames in all three is stuck. Then read the request threads. These are real excerpts (JDK 25; the layout is the same on 21):

```text
"http-worker-1" #25 [27907] prio=5 os_prio=31 cpu=0.23ms elapsed=3.22s tid=0x... nid=27907 waiting on condition
   java.lang.Thread.State: TIMED_WAITING (sleeping)
	at java.lang.Thread.sleep(java.base@25.0.1/Thread.java:601)
	at Stuck.lambda$main$0(Stuck.java:13)
	- locked <0x00000070184185b0> (a java.lang.Object)

"http-worker-2" #26 [32771] prio=5 os_prio=31 cpu=0.07ms elapsed=3.11s tid=0x... nid=32771 waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
	at Stuck.lambda$main$1(Stuck.java:18)
	- waiting to lock <0x00000070184185b0> (a java.lang.Object)

"http-worker-3" #27 [43267] prio=5 os_prio=31 cpu=0.21ms elapsed=3.11s tid=0x... nid=43267 waiting on condition
   java.lang.Thread.State: WAITING (parking)
	at jdk.internal.misc.Unsafe.park(java.base@25.0.1/Native Method)
	- parking to wait for  <0x0000007018418888> (a java.util.concurrent.Semaphore$NonfairSync)
	at java.util.concurrent.Semaphore.acquireUninterruptibly(java.base@25.0.1/Semaphore.java:341)
```

Reading it: `http-worker-2` is `BLOCKED` on `<0x00000070184185b0>`; grep for `locked <0x00000070184185b0>` and you find `http-worker-1`, which holds the lock while sleeping (in production: while waiting on a remote call). Fifty threads in that state and one holder is the whole incident. `http-worker-3` is parked on a `Semaphore`, the shape of every connection-pool exhaustion: the next question is who holds the permits, usually threads that are `RUNNABLE` in a socket read against a slow database. Check `pg_stat_activity` on that side.

The dump ends with a deadlock section when there is one, and names everything you need:

```text
Found one Java-level deadlock:
=============================
"batch-1":
  waiting to lock monitor 0x0000007a00caa760 (object 0x0000007018418730, a java.util.concurrent.Semaphore),
  which is held by "batch-2"
"batch-2":
  waiting to lock monitor 0x0000007a00caa680 (object 0x00000070184185c0, a java.lang.Object),
  which is held by "batch-1"
```

If the stuck threads are all `RUNNABLE` in your own code, you have the high-CPU case instead: `top -H -p <pid>`, convert the hot thread id to match `nid=` (hex in older JDKs, `printf '%x\n' <tid>`), and look at that thread's frames across the three dumps. If the hot threads are `GC Thread#n` or `G1 Conc#n`, it is the memory case: open the GC log.

## Example: memory growth, the commands in order

```text
$ grep 'Pause' /logs/gc.log | tail -20                # heap after each pause: is the floor rising?
$ jcmd <pid> GC.class_histogram | head -15            # repeat after 10 minutes, compare counts
$ jcmd <pid> GC.heap_dump -gz=1 /dumps/heap.hprof     # or wait for -XX:+HeapDumpOnOutOfMemoryError
```

```text
 num     #instances         #bytes  class name (module)
-------------------------------------------------------
   1:          8530         384144  [B (java.base@25.0.1)
   2:          1708         225936  java.lang.Class (java.base@25.0.1)
   3:          8452         202848  java.lang.String (java.base@25.0.1)
```

`byte[]` and `String` at the top only tell you to find who holds them. In MAT, run Leak Suspects, then sort the dominator tree by retained heap and ask for the path to GC roots (excluding weak and soft references) of the top entry. The usual culprits: an unbounded `HashMap` used as a cache, a static collection, listeners never removed, `ThreadLocal`s in pooled threads.

## Pitfalls

- Restarting first. One thread dump takes a second; take it before the restart and attach it to the incident.
- A single thread dump. Without a second one you cannot tell a stuck thread from a busy one.
- Reading `RUNNABLE` as "using CPU". Socket reads are `RUNNABLE`. Correlate with `top -H`.
- Heap dumps on a serving instance under load. The pause can last minutes and the file can fill the disk; dump a drained instance, or rely on `-XX:+HeapDumpOnOutOfMemoryError` with `-XX:HeapDumpPath` on a volume with space.
- Diagnosing memory from `GC.heap_info` or `top` alone. RSS includes Metaspace, thread stacks, code cache and native buffers; a JVM can grow without a heap leak (then `VM.native_memory` is the tool).

## Check yourself

1. Why three thread dumps ten seconds apart rather than one?
2. A thread is `RUNNABLE` in `sun.nio.ch.SocketDispatcher.read0` in all three dumps. Is it the cause of your high CPU? What is it doing?
3. Heap after full collections reads 600, 650, 700 and 750 MB over four hours under steady load, with `-Xmx1g`. Leak or undersized heap, and what is your next command?
4. The class histogram shows 40 million `byte[]` instances. Is that the leak? How do you find what is holding them?

## Go deeper

- [Oracle: Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/) · the official chapters on thread dumps, heap dumps and memory leaks, with the exact output formats.
- [jcmd manual page](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) · every `jcmd` command and option.
- [Eclipse Memory Analyzer](https://eclipse.dev/mat/) · the tool for heap dumps; learn the dominator tree and "path to GC roots".
- [async-profiler](https://github.com/async-profiler/async-profiler) and [Brendan Gregg: Flame Graphs](https://www.brendangregg.com/flamegraphs.html) · how to profile CPU, allocation and locks in production, and how to read the result.
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html) · for reading JFR recordings: method profiling, allocation and lock contention views.

---

Part of [Java](../README.md) · items 8.1, 8.2, 8.5
