# JDK Flight Recorder and async-profiler in practice

> **In one sentence:** JFR is the always-on recorder built into the JVM (CPU samples, allocation, locks, GC, file and socket I/O, your own events) that you read with `jfr view` or JDK Mission Control; async-profiler is the external sampler you reach for when you need the exact answer to "where does the CPU or allocation go", with native and kernel frames, drawn as a flame graph.

**Why it matters:** The difference between "the service is slow" and "26% of CPU is string concatenation in `renderLine`, and the lock in `count` is contended two million times a second" is one recording and ten minutes of reading. Both tools are cheap enough to run on production, and the thread-dump workflow (item 8.5) hands over to them the moment the question is "what is this thread doing over time" rather than "what is it doing now".

## The idea

**JFR** records typed events into thread-local buffers, writes them to a file, and costs little enough to run continuously. Two built-in configurations: `default` (method samples every 20 ms, allocation samples throttled to 150 per second, lock waits over 20 ms) and `profile` (10 ms, 300 per second, 10 ms). Start it three ways:

```bash
java -XX:StartFlightRecording=duration=60s,filename=rec.jfr,settings=profile -jar app.jar
jcmd <pid> JFR.start duration=60s filename=/tmp/rec.jfr settings=profile
java -XX:StartFlightRecording=disk=true,maxage=24h,maxsize=1g,dumponexit=true,filename=/dumps/ -jar app.jar
```

The third form is the production setting: a rolling recording kept on disk, so after an incident `jcmd <pid> JFR.dump filename=/tmp/incident.jfr` gives you the last hours without having been there. Individual events can be tuned in the same option (`jdk.JavaMonitorEnter#threshold=0ms`), and `jfr configure` writes a custom `.jfc`.

Reading a recording: `jfr summary` lists event counts, `jfr print --events <name>` dumps events as text, and `jfr view <view>` (JDK 21 and later) prints the views Mission Control would show: `hot-methods`, `allocation-by-site`, `allocation-by-class`, `contention-by-site`, `gc-pauses`, `file-reads-by-path`, `socket-reads-by-host`, `exception-by-site`, `pinned-threads` and about eighty more (`jfr view` with no arguments lists them). JDK Mission Control is the GUI for the same file, with the automated analysis page as a starting point.

What JFR's method sampling sees: Java frames of threads running Java code, plus a separate sample for threads in native methods. It does not see kernel time, JIT compiler threads or GC threads as stacks, so "the process uses 100% CPU but the hot methods add up to 40%" means the rest is in the JVM itself; `jfr view gc-cpu-time` and `thread-cpu-load` show where. JDK 25 added experimental CPU-time sampling on Linux (JEP 509) that attributes samples by CPU time consumed rather than wall-clock intervals.

**Custom events** are the underrated half of JFR. Subclass `jdk.jfr.Event`, add fields, call `begin()`, `commit()`; the event carries its duration, thread and stack trace, and appears next to GC pauses and socket reads on the same timeline. Spring Boot's `startup` events and the JDK's own virtual-thread pinning event (`jdk.VirtualThreadPinned`, see item 5.4) are this mechanism.

**async-profiler** attaches to a running JVM (`asprof`) or loads as an agent, samples with the operating system's timers or `perf_events` on Linux, and walks stacks with `AsyncGetCallTrace`, so it is not biased towards safepoints and includes native and kernel frames. Modes: `-e cpu` (CPU time), `-e wall` (wall-clock, for threads that wait), `-e alloc` (allocation, sampled at TLAB boundaries so it is cheap), `-e lock` (contended monitors and `java.util.concurrent` locks), plus any hardware or kernel event on Linux (`-e cache-misses`, `-e page-faults`). Output formats: an interactive HTML flame graph (default), `collapsed` for other tools, `flat` and `tree` for text, and `jfr` for Mission Control. `jfrconv` goes the other way and draws a flame graph from a JFR file. Add `-XX:+UnlockDiagnosticVMOptions -XX:+DebugNonSafepoints` to the JVM so inlined frames are attributed to the right line.

**Reading a flame graph.** The x-axis is sorted alphabetically, not by time; width is the share of samples; each box is a frame and the boxes above it are its callees. Look for wide plateaus at the top (leaf methods consuming CPU themselves) and wide towers (a call path worth optimising as a whole). A flame graph of `-e wall` shows where threads wait; of `-e alloc`, which paths allocate the most bytes.

## Example: one program, three views

A program with four threads doing string concatenation in a loop and counting under one `synchronized` lock, recorded with the `profile` configuration and the lock threshold lowered:

```bash
java -XX:StartFlightRecording=duration=20s,filename=hot.jfr,settings=profile,jdk.JavaMonitorEnter#threshold=0ms HotService
jfr view hot-methods hot.jfr
jfr view allocation-by-site hot.jfr
jfr view contention-by-site hot.jfr
```

```text
                              Java Methods that Execute the Most

Method                                                                        Samples Percent
----------------------------------------------------------------------------- ------- -------
jdk.internal.util.DecimalDigits.uncheckedGetCharsLatin1(int, int, byte[])       1,139  29.42%
HotService.renderLine(int)                                                      1,020  26.34%
HotService.count(String)                                                          528  13.64%
java.lang.StringLatin1.hashCode(byte[])                                           495  12.78%
java.lang.String$$StringConcat.0x000001fe01045c00.concat(Object, int, int)        359   9.27%

                                      Allocation by Site

Method                                                                     Allocation Pressure
-------------------------------------------------------------------------- -------------------
jdk.internal.misc.Unsafe.allocateUninitializedArray(Class, int)                         82.55%
java.lang.String$$StringConcat.0x000001fe01045c00.concat(Object, int, int)              16.16%

                                                   Contention by Site

StackTrace                                                                                Count        Avg.        Max.
------------------------------------------------------------------------------------- --------- ----------- -----------
HotService.count(String)                                                              2,674,646  0.00353 ms     56.9 ms
```

The hot-methods view says the CPU goes to formatting integers into strings and concatenating (`renderLine` builds a line with `+=` twenty times). Allocation says the same thing from the other side: nearly everything allocated is the `byte[]` behind those strings. Contention says the lock in `count` was contended 2.7 million times in twenty seconds, with one wait of 57 ms. With the default threshold of 10 ms that view would have shown a single entry, which is why lowering the threshold for a short recording is worth it.

The same process under async-profiler, which also shows what JFR cannot:

```bash
asprof -d 4 -e cpu -o flat,traces=0 <pid>
asprof -d 30 -e cpu -f cpu.html <pid>
asprof -d 30 -e alloc -f alloc.html <pid>
asprof -d 30 -e lock -f lock.html <pid>
```

```text
--- Execution profile ---
Total samples       : 1539

          ns  percent  samples  top
  ----------  -------  -------  ---
  2340000000   15.20%      234  ObjectMonitor::try_spin
  2250000000   14.62%      225  __psynch_cvwait
  1560000000   10.14%      156  mach_absolute_time
  1390000000    9.03%      139  jdk.internal.util.DecimalDigits.uncheckedGetCharsLatin1
  1380000000    8.97%      138  HotService.renderLine
  1040000000    6.76%      104  java.lang.String$$StringConcat.0x000000e001041800.concat
```

Thirty percent of CPU is `ObjectMonitor::try_spin` and `__psynch_cvwait`: threads spinning and then parking on the contended monitor, inside the JVM and the kernel. JFR's Java-only sampling attributed none of that; it showed `count` at 13% because that is the Java frame the threads were in. Both are true; async-profiler's picture is the one that says "the lock costs as much CPU as the work".

A custom event, so that the same recording also says which orders were slow:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;

@Name("shop.Checkout")
@Label("Checkout")
@Category("Shop")
class CheckoutEvent extends Event {
    @Label("Order id")
    String orderId;
    @Label("Line count")
    int lineCount;
}

static void checkout(String orderId, int lineCount) {
    CheckoutEvent event = new CheckoutEvent();
    event.begin();
    doTheWork(orderId, lineCount);
    event.orderId = orderId;
    event.lineCount = lineCount;
    event.commit();
}
```

`jfr print --events shop.Checkout rec.jfr` then prints each checkout with its `duration`, thread and stack trace, and `jfr view shop.Checkout rec.jfr` tabulates them. Events that take no time cost almost nothing; a threshold can be set per event to record only slow ones.

## Pitfalls

- Recording without a disk and without `maxsize`. In-memory recordings keep a fixed window; a long `duration` with `disk=false` silently drops the beginning. For continuous recording use `disk=true,maxage=...,maxsize=...`.
- Reading only `hot-methods`. The Java-frame view misses GC, JIT, lock spinning and kernel time. If the percentages do not add up to the CPU you see in `top`, use `gc-cpu-time`, `thread-cpu-load`, or async-profiler.
- Default lock and I/O thresholds. `jdk.JavaMonitorEnter` at 10 ms and `jdk.FileRead` at 1 ms hide the death-by-a-thousand-cuts case. Lower them for a targeted recording; do not lower them for a rolling production recording, where volume matters.
- Profiling the wrong thing. CPU profiles of a service that is waiting on a database show nothing; use `-e wall` (or JFR's `socket-reads-by-host` and `latencies-by-type` views) when latency is the problem and CPU is idle.
- Inlining confusion. Without `-XX:+DebugNonSafepoints` the JIT attributes samples to the caller of an inlined method; a hot line in the flame graph is then one or two frames off.
- Containers. `asprof` must run as the JVM's user inside the same PID namespace, and on Linux `perf_events` needs `kernel.perf_event_paranoid` low enough or a fallback timer mode (`-e ctimer` or `-e itimer`); the error message names the fix. JFR has no such requirement, which is a reason to keep it on.
- Trusting a short profile of a cold JVM. The first seconds are interpreter and C1 code; profile after warm-up, or you optimise code that the C2 compiler would have inlined away (see item 4.3).
- Allocation profiling expectations. Both tools sample allocations (TLAB-based), so counts are estimates and tiny objects in a hot loop can be under-represented; the ranking is reliable, the absolute bytes are not.

## Check yourself

1. A JFR `hot-methods` view accounts for 40% of the process's CPU. Name three places the other 60% can be and the view or tool that shows each.
2. Why does `contention-by-site` show nothing for a lock that is acquired a million times a second, and what one change to the recording makes it visible?
3. The service's p99 latency is 2 s but CPU is at 10%. Which async-profiler event do you use, and what shape do you expect in the flame graph?
4. What does a custom JFR event give you that a log line with a duration does not?

## Go deeper

- [Oracle: Flight Recorder API guide](https://docs.oracle.com/en/java/javase/21/jfapi/) · custom events, streaming with `RecordingStream`, and the configuration model.
- [The jfr command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) · every subcommand including `view` and `configure`.
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html) · the GUI; start with the Automated Analysis page, then Method Profiling, Memory and Lock Instances.
- [async-profiler](https://github.com/async-profiler/async-profiler) · the README is the manual: modes, output formats, agent options and the container section.
- [Brendan Gregg: Flame Graphs](https://www.brendangregg.com/flamegraphs.html) · how to read them, from the person who invented them.
- [JEP 509: JFR CPU-Time Profiling (Experimental)](https://openjdk.org/jeps/509) · why wall-clock sampling misattributes CPU and what the Linux CPU-time sampler changes.

---

Part of [Java](../README.md) · items 8.3, 8.4
