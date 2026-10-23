# Processes, threads and virtual memory: what RSS really measures

> **In one sentence:** A process is an address space plus the resources attached to it, threads share that address space, every address a program uses is virtual and translated page by page, and the memory a process has reserved, committed and actually touched are three different numbers, of which only the last is RSS.

**Why it matters:** Containers get OOM-killed although `-Xmx` was "set correctly"; capacity plans are made from the wrong `ps` column; a thread-per-request server falls over at a few thousand connections; and "process versus thread" opens half of all systems interviews.

## The idea

**Processes and threads (item 2.1).** A process owns an address space (code, data, heap, stacks, mapped files, shared libraries), its open file descriptors, credentials and a PID; the kernel tracks it in a process control block (`task_struct` on Linux). A thread is a schedulable unit inside a process: its own registers, program counter, stack and scheduling state, everything else shared. Sharing makes threads cheap to create and dangerous to program. Java platform threads map one-to-one onto kernel threads; virtual threads (Java 21) are scheduled by the JVM onto a small pool of carrier threads and are invisible to the kernel individually.

**Context switches.** When the kernel moves a CPU from one thread to another it saves the registers, switches stacks and, for a different process, switches page tables, then restores. The direct cost is on the order of a microsecond or a few. The indirect cost is usually larger: the new thread finds the caches and the TLB full of someone else's data. Switching between threads of one process is cheaper than between processes because the address space, and with it most of the TLB, stays. With too many runnable threads the machine spends its time switching rather than working (item 2.2).

**Virtual memory (item 2.3).** Every process sees its own private, contiguous address space; the hardware translates each virtual address to a physical one through page tables, in units of pages (4 KiB on most Linux systems, 16 KiB on Apple Silicon, 2 MiB with huge pages). The TLB caches recent translations; a miss costs a walk through the page tables, several memory accesses. Touching a page with no valid translation raises a *page fault*. A *minor* fault is served from memory: the first touch of a freshly allocated page (the kernel zero-fills a frame and maps it), or a file page already in the page cache. A *major* fault needs the disk: swap, or a file not yet cached. Every new heap page a JVM touches is a minor fault, which is what `-XX:+AlwaysPreTouch` moves from the first requests to startup.

**Reserved, committed, resident.** A program can *reserve* a range of addresses with no memory behind them (the JVM reserves the whole `-Xmx` at startup, plus a gigabyte for compressed class pointers, plus about 240 MB for the code cache), *commit* parts of it so they may be used, and finally *touch* pages so that physical frames are assigned. `VSZ` (`VIRT` in `top`, `VmSize` in `/proc/<pid>/status`) counts everything mapped, reserved included, and says almost nothing. `RSS` (`RES`, `VmRSS`) counts pages currently in physical memory: anonymous memory (heap, stacks, `malloc`) plus file-backed pages such as shared libraries, which several processes may share, so summing RSS across processes over-counts; `PSS` in `/proc/<pid>/smaps_rollup` divides shared pages fairly. Pages written out to swap are in neither.

**Why a JVM's RSS exceeds -Xmx.** The heap is one consumer among many: class metadata (Metaspace), the JIT code cache, garbage collector data structures (G1's remembered sets and card tables), thread stacks (1 MiB reserved per platform thread, only the touched part resident), NIO direct buffers, the JVM's own `malloc` use, native libraries, and the shared libraries in the file-backed part of RSS. Native Memory Tracking itemises everything the JVM allocates: start with `-XX:NativeMemoryTracking=summary` and read it with `jcmd <pid> VM.native_memory summary`. In a container, size the heap as a share of the limit with `-XX:MaxRAMPercentage` and leave room for the rest.

## Example: one JVM, four different sizes

A program that allocates 64 MiB of byte arrays and sleeps, started with `java -Xmx256m -XX:NativeMemoryTracking=summary MemoryDemo` in a Linux container with JDK 21:

```text
$ ps -o pid,rss,vsz,nlwp,stat,cmd -p 363
    PID   RSS    VSZ NLWP STAT CMD
    363 154780 3287224 22 Sl   java -Xmx256m -XX:NativeMemoryTracking=summary MemoryDemo
$ grep -E '^(VmSize|VmRSS|RssAnon|RssFile|VmSwap|Threads)' /proc/363/status
VmSize:  3287224 kB
VmRSS:    154780 kB
RssAnon:  134736 kB
RssFile:   20044 kB
VmSwap:        0 kB
Threads:  22
$ ps -o min_flt,maj_flt -p 363
 MINFL  MAJFL
 21627      0
```

`ps` sizes are in KiB: 3.1 GiB virtual, 151 MiB resident, 22 threads (`NLWP`), state `S` for sleeping with `l` for multi-threaded. Of the resident memory, 132 MiB is anonymous (heap and JVM structures) and 20 MiB is file-backed (the JDK's shared libraries and `modules` file). 21,627 minor faults and no major ones: every page was zero-filled on first touch, nothing came from disk. The same program on macOS reported a `VSZ` of 468 GiB, which shows how little that column means.

```text
$ jcmd 363 VM.native_memory summary
Total: reserved=1747704KB, committed=230716KB
-                 Java Heap (reserved=262144KB, committed=148480KB)
-                     Class (reserved=1048672KB, committed=224KB)
-                    Thread (reserved=44943KB, committed=967KB)
                            (threads #22)
                            (stack: reserved=44880KB, committed=904KB, peak=904KB)
-                      Code (reserved=247740KB, committed=7600KB)
-                        GC (reserved=58980KB, committed=56764KB)
```

Abridged. Four numbers for one process: 3.1 GiB virtual, 1.7 GiB reserved by the JVM, 225 MiB committed, 151 MiB resident. The 256 MiB heap is reserved in full, committed to 145 MiB so far, and resident only where the arrays and the collector have touched it. Note the 55 MiB of GC structures sized for the maximum heap, and 22 thread stacks of which 904 KiB are resident out of 44 MiB reserved. Let this process churn through its heap for a day and the resident size settles near the committed total plus the file-backed pages, here roughly 350 MiB for a 256 MiB `-Xmx`. Size the container for that number, not for `-Xmx`.

## Pitfalls

- Reading `VSZ` or `VIRT` as memory use. It is address space. Look at `RSS`, and at `PSS` when summing over processes.
- `-Xmx` equal to the container limit. The non-heap parts push RSS over the limit, the kernel's OOM killer sends `SIGKILL`, the exit code is 137, and there is no `OutOfMemoryError` and no heap dump because the JVM never knew. Leave 25 to 50 percent headroom, or use `MaxRAMPercentage`.
- Memory that is not on the heap: direct `ByteBuffer`s, Metaspace growth from class-loader leaks on redeploy, native libraries, `malloc` fragmentation in glibc. Heap dumps show nothing; NMT, `pmap -x` and `/proc/<pid>/smaps` do.
- One platform thread per connection. The 1 MiB stack is reserved, not resident, but each thread is a kernel object to schedule and a set of caches to pollute; tens of thousands of them is where virtual threads, or an event loop, earn their keep.
- Swap on a JVM or database host. A major fault inside a garbage collection pause turns milliseconds into seconds. Most teams disable swap on such hosts and accept the OOM kill instead.
- Confusing committed with resident. Committed memory costs nothing until touched; `-XX:+AlwaysPreTouch` pays that cost at startup instead of during the first requests.

## Check yourself

1. A JVM with `-Xmx2g` shows an RSS of 2.6 GB after a day. Name four places the extra 600 MB can live and the one command that tells you which.
2. Why is switching between two threads of one process cheaper than switching between two processes? Which state is skipped, and which cost is not?
3. Your container limit is 1 GiB and `-Xmx` is `1g`. What kills the process, what exit code do you see, and why is there no heap dump?
4. Explain the difference between a minor and a major page fault, and why `-XX:+AlwaysPreTouch` makes startup slower but the first minutes of serving faster.

## Go deeper

- [OSTEP: Processes](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-intro.pdf) and [OSTEP: Threads](https://pages.cs.wisc.edu/~remzi/OSTEP/threads-intro.pdf) · the abstractions, the process control block and why threads exist, in two short chapters.
- [OSTEP: Address Translation](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-mechanism.pdf) and [OSTEP: Paging](https://pages.cs.wisc.edu/~remzi/OSTEP/vm-paging.pdf) · pages, page tables and the TLB, with the arithmetic worked out.
- [JVM Anatomy Quark #12: Native Memory Tracking](https://shipilev.net/jvm/anatomy-quarks/12-native-memory-tracking/) · how to read NMT output and what each category is.
- [proc(5)](https://man7.org/linux/man-pages/man5/proc.5.html) · the meaning of every field in `/proc/<pid>/status`, `statm` and `smaps`.

---

Part of [Foundations](../README.md) · items 2.1, 2.3
