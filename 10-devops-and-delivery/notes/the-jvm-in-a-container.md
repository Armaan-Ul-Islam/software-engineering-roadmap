# The JVM in a container: heap, CPUs and OOMKilled

> **In one sentence:** A container-aware JVM derives its heap size, garbage collector and thread counts from the cgroup limits it sees, but the heap is only part of what the process uses, so the memory limit has to cover heap plus Metaspace, thread stacks, code cache and direct buffers, or the kernel kills the container with exit code 137 and no stack trace.

**Why it matters:** The most common JVM incident on Kubernetes is a Pod that restarts with `OOMKilled` while the application log shows nothing wrong, usually because `-Xmx` was set close to the container limit. The second most common is a service that takes minutes to start and shows latency spikes because a CPU limit of one core quietly switched it to the Serial collector and throttled JIT compilation. Both are settings, not bugs, and both come up in interviews as "my container has 1 GiB, why is it killed with a 768 MiB heap".

## The idea

**What the JVM sees.** Since JDK 10 (and 8u191) HotSpot reads the cgroup limits of its container (`-XX:+UseContainerSupport`, on by default on Linux): the memory limit becomes "physical memory" and the CPU quota becomes the processor count. Without a limit, it sees the whole node.

**Heap defaults.** The maximum heap is `MaxRAMPercentage` of that memory, default 25, so a 1 GiB limit gives a 256 MiB heap and a 4 GiB limit a 1 GiB heap. (For very small containers, under roughly 250 MiB, the JVM switches to `MinRAMPercentage`, default 50.) The initial heap is `InitialRAMPercentage`, default 1.5625 percent, 16 MiB for 1 GiB. Set the percentage deliberately: `-XX:MaxRAMPercentage=50.0` follows the limit when someone changes it, `-Xmx512m` does not.

**Why RSS is larger than the heap.** The cgroup counts the process's resident memory, which includes:

| Region | What is in it | How to bound it |
|---|---|---|
| Java heap | your objects | `-XX:MaxRAMPercentage` or `-Xmx` |
| Metaspace | class metadata; grows with every class loaded, and a Spring application loads tens of thousands | `-XX:MaxMetaspaceSize` |
| Code cache | JIT-compiled code; 240 MiB reserved by default, committed as it fills | `-XX:ReservedCodeCacheSize` |
| Thread stacks | one per thread; 1 MiB reserved on x86_64 and 2 MiB on aarch64 (`-Xss`), committed only as touched | fewer threads, or `-Xss512k` |
| Direct buffers | `ByteBuffer.allocateDirect` from Tomcat, Netty, JDBC and Kafka clients; the default limit equals the maximum heap | `-XX:MaxDirectMemorySize` |
| GC bookkeeping | card tables, G1 remembered sets | proportional to heap |
| Native | glibc malloc arenas, zip inflaters, JNI libraries, the CDS archive, symbol tables | `MALLOC_ARENA_MAX=2` |

A process with a 512 MiB heap commonly sits between 800 MiB and 1 GiB of RSS. `-Xmx` equal to the limit guarantees an OOM kill under load.

**CPUs.** With a CPU quota (`limits.cpu` in Kubernetes) `Runtime.availableProcessors()` returns the quota rounded up: `500m` gives 1, `1500m` gives 2. CPU shares (`requests.cpu`) are ignored by JDK 19 and later, including the backports in the 17 and 11 update releases. That count sizes the common `ForkJoinPool`, the GC worker threads (`ParallelGCThreads` equals the CPU count up to 8, then grows by five eighths of each extra CPU) and the JIT compiler threads. Most important: HotSpot only chooses G1 on a "server class machine" with at least 2 CPUs and about 1.75 GiB of memory; a one-CPU container gets the Serial collector unless you pass `-XX:+UseG1GC`. `-XX:ActiveProcessorCount=2` overrides the detected count, which matters when there is no CPU limit and the JVM would otherwise size its pools for a 64-core node. Why a CPU limit throttles the JVM is covered in item 4.5.

**OOMKilled versus OutOfMemoryError.**

| | `OOMKilled` | `java.lang.OutOfMemoryError` |
|---|---|---|
| Who kills | the kernel's cgroup OOM killer | the JVM itself |
| Why | the RSS of the whole container exceeded the limit | one JVM region is full: `Java heap space`, `Metaspace`, `Direct buffer memory`, `unable to create native thread` |
| Evidence | exit code 137 (128 + SIGKILL), `Reason: OOMKilled` in `kubectl describe`, `Memory cgroup out of memory` in `dmesg`, nothing in the application log | a stack trace in the log, a heap dump if `-XX:+HeapDumpOnOutOfMemoryError` |
| Fix | lower the heap or the non-heap budget, or raise the limit | fix the leak, or raise that region's limit |

Add `-XX:+ExitOnOutOfMemoryError` so a JVM that hits `OutOfMemoryError` exits and gets restarted instead of limping on with dead threads, and point `-XX:HeapDumpPath` at a volume, because a dump written into the container filesystem disappears with the restart.

**How to verify.** `java -XX:+PrintFlagsFinal -version` prints every flag's effective value with its origin (`ergonomic` means the JVM chose it). `-Xlog:os+container=trace` shows what the container detection found. `jcmd <pid> VM.native_memory summary`, for a JVM started with `-XX:NativeMemoryTracking=summary`, breaks committed memory down into Java Heap, Class, Thread, Code, GC, Internal, Symbol and the rest; it is the only honest way to size the non-heap budget. `jcmd` ships with the JDK, not the JRE, so measure with the JDK variant of your image.

## Example: a memory budget for a 1 GiB container

What the JVM decides on its own (Temurin 21.0.12, aarch64 host):

```text
$ docker run --rm --memory=1g --cpus=1 eclipse-temurin:21-jre-jammy \
    java -XX:+PrintFlagsFinal -version | grep -E ' (MaxHeapSize|ReservedCodeCacheSize|ThreadStackSize|UseG1GC|UseSerialGC) '
   size_t MaxHeapSize              = 268435456     {product} {ergonomic}
    uintx ReservedCodeCacheSize    = 251658240     {pd product} {ergonomic}
     intx ThreadStackSize          = 2040          {pd product} {default}
     bool UseG1GC                  = false         {product} {default}
     bool UseSerialGC              = true          {product} {ergonomic}

$ docker run --rm --memory=1g --cpus=1 eclipse-temurin:21-jre-jammy java -Xlog:os+container=trace -version 2>&1 | grep -E 'Quota|Period|active_processor_count|Memory Limit' | head -5
[0.002s][trace][os,container] CPU Quota is: 100000
[0.002s][trace][os,container] CPU Period is: 100000
[0.002s][trace][os,container] CPU Quota count based on quota/period: 1
[0.002s][trace][os,container] OSContainer::active_processor_count: 1
[0.002s][trace][os,container] Memory Limit is: 1073741824
```

A 256 MiB heap, a Serial collector and 2 MiB thread stacks, all by ergonomics. With `--memory=2g --cpus=2` the same image reports `MaxHeapSize = 536870912`, `UseG1GC = true` and `ParallelGCThreads = 2`.

The budget for a Spring Boot service with about 250 threads:

| Region | Budget | Setting |
|---|---|---|
| Heap | 512 MiB | `-XX:MaxRAMPercentage=50.0` |
| Metaspace | 128 MiB | `-XX:MaxMetaspaceSize=128m`, after measuring with `jcmd <pid> VM.metaspace` |
| Code cache | 64 MiB committed | leave the 240 MiB reservation; only committed pages count |
| Thread stacks | 96 MiB | 200 Tomcat workers plus pools, GC and JIT threads; committed stacks stay far below the reserved size |
| Direct buffers | 48 MiB | `-XX:MaxDirectMemorySize=48m` |
| GC, JVM internals, native allocations | 96 MiB | `MALLOC_ARENA_MAX=2` |
| Headroom for page cache and spikes | 80 MiB | |
| Total | 1024 MiB | |

As a Kubernetes container environment:

```yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: >-
      -XX:MaxRAMPercentage=50.0 -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=48m
      -XX:+UseG1GC -XX:+ExitOnOutOfMemoryError
      -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/dumps
  - name: MALLOC_ARENA_MAX
    value: "2"
```

The JVM confirms it at start-up with `Picked up JAVA_TOOL_OPTIONS: ...` on stderr. Then run a load test with `-XX:NativeMemoryTracking=summary`, compare the committed total from `jcmd <pid> VM.native_memory summary` with `kubectl top pod`, and adjust. The rule of thumb that comes out of such measurements is a heap of 50 to 75 percent of the limit, towards the low end for applications with many threads or many classes.

## Pitfalls

- `-Xmx` equal to the limit, or `MaxRAMPercentage=90`. The heap alone fits; the process does not. Symptom: `OOMKilled` under load with a quiet log.
- No memory limit at all. The JVM sizes its heap from the node's memory, and a Pod that was fine on a small node becomes a memory hog on a large one. Always set `limits.memory` for a JVM.
- Raising `-Xmx` to fix `OOMKilled`. It makes the kill more likely. Lower the heap or raise the container limit.
- `limits.cpu: 1` on a service that needs G1. The collector changes silently, and parallel streams and the common pool run with parallelism 1. Check with `PrintFlagsFinal`.
- Heap dumps on the container filesystem. The restart deletes the evidence. Mount a volume for `HeapDumpPath`.
- Reading `kubectl top pod` as "JVM memory". It reports the working set, which includes page cache for files the container wrote; the OOM killer counts the same cgroup usage, so the number is relevant, but it is not heap.
- `OutOfMemoryError: unable to create native thread`. This is not a heap problem; it is thread stacks, the cgroup `pids` limit or `ulimit -u`. Count threads with `jcmd <pid> Thread.print`.

## Check yourself

1. A container has `limits.memory: 2Gi` and no JVM flags. What is the maximum heap, and which regions compete for the other 1.5 GiB?
2. The Pod restarts with exit code 137 and an empty error log. Which three things do you check, in which order, and what distinguishes this from an `OutOfMemoryError`?
3. Why does `limits.cpu: 1` change the garbage collector, and which single command shows what the JVM chose?
4. With `-Xmx1g` in a 1 GiB container, name three allocations that push RSS past the limit before the heap is even full.

## Go deeper

- [The java command reference (JDK 21)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html) · the authoritative description of `MaxRAMPercentage`, `ActiveProcessorCount`, `NativeMemoryTracking` and every other flag used here.
- [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview) · a practical guide to heap sizing, GC choice and CPU limits for JVM containers.
- [Kubernetes: Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) · what requests and limits mean to the kernel on the other side of the cgroup.

---

Part of [DevOps & Delivery](../README.md) · item 3.4
