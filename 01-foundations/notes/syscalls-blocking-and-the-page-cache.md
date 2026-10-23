# System calls, blocking I/O and the page cache

> **In one sentence:** Your code cannot touch hardware; every read, write and socket operation is a system call that traps into the kernel, and for files the kernel answers from its page cache, so a successful `write` means "the kernel has your bytes", not "the disk has them", until `fsync` says otherwise.

**Why it matters:** "The log line was written, but after the crash it was gone"; a service idle at 2% CPU and yet unresponsive because every pool thread sits in a blocking call; a thread dump that says `RUNNABLE` for a thread that has not run in minutes; a write benchmark that measures memory copies and reports disk throughput.

## The idea

**User mode and kernel mode (item 2.4).** Your code runs in a restricted CPU mode that cannot issue I/O instructions, touch other processes' memory or change page tables. To do any of that, the program executes a trap instruction (`svc` on ARM64, `syscall` on x86-64) with a system call number and arguments in registers; the CPU switches to kernel mode, the kernel runs the handler, and control returns with a result. The switch costs a fraction of a microsecond; the handler's work costs anything from nothing to a disk seek. Java hides them inside `FileInputStream.read`, `SocketChannel.write` and `Thread.sleep`; `strace -f` shows them.

**File descriptors (item 2.5).** The kernel hands a process small integers for what it has opened: files, sockets, pipes, timers. `0`, `1` and `2` are stdin, stdout and stderr. Each `FileInputStream`, `Socket` or `FileChannel` wraps one; the per-process limit (`ulimit -n`) is why a leaked stream eventually fails with `Too many open files`. `ls -l /proc/<pid>/fd` lists them.

**What blocking costs.** A `read` on a pipe or socket with nothing to read does not spin. The kernel marks the thread as sleeping (`S` in `ps`), charges it no CPU and schedules something else; when data arrives, an interrupt wakes it and it is rescheduled, two context switches later. The cost is not CPU time but the thread, with its stack and kernel bookkeeping, being unavailable for anything else, which is how a pool of 200 threads blocked on a slow downstream makes a service unresponsive while idle. Non-blocking I/O (`epoll`, NIO selectors, Netty) multiplexes many connections on one thread; virtual threads (Java 21) unmount instead of parking a kernel thread.

**The page cache.** The kernel keeps file contents in otherwise unused RAM. A `read` of a cached page is a memory copy and takes microseconds; the first read of an uncached page is a disk access. A `write` copies your bytes into the page cache, marks the page *dirty* and returns. Flusher threads write dirty pages back later, on Linux after `vm.dirty_expire_centisecs` (30 seconds by default) or sooner under memory pressure. Until that writeback, a power cut loses data your program believes it saved.

**Layers of buffering, and what fsync does.** Bytes travel through your `BufferedWriter` (a user-space buffer of 8 KiB), then the `write` syscall into the page cache, then the device's own write cache, then the medium. `flush()` only empties the first buffer into the second. `fsync(fd)` (`FileChannel.force(true)`, `FileDescriptor.sync()`) asks the kernel to write the file's dirty pages and metadata and to tell the device to flush its cache, and returns only when that is done. `fdatasync` (`force(false)`) skips metadata not needed to read the data back. On macOS the JDK uses `fcntl(F_FULLFSYNC)` instead, because Apple's `fsync` does not flush the drive's cache.

What `fsync` guarantees: when it returns 0, the data and metadata of *that file* are on stable storage, provided the device honours flush requests. What it does not guarantee:

1. A new file's existence. The name lives in the directory, so after creating or renaming a file you must `fsync` the directory too, or the file can vanish after a crash with its data intact.
2. Anything about other files, or the order in which several files reach the disk.
3. Error recovery. If `fsync` fails with `EIO`, Linux may already have marked the pages clean; a retry returns success and the data is gone. PostgreSQL discovered this in 2018 and now deliberately crashes when `fsync` fails. Treat a failed `fsync` as "this file is corrupt".
4. Atomicity. A crash in the middle of a `write` can leave half a record. Databases solve this with a write-ahead log; for small files the idiom is: write a temporary file, `fsync` it, `rename` it over the target, `fsync` the directory.

## Example: one durable append, traced

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class DurableAppend {

    public static void main(String[] arguments) throws IOException {
        Path path = Path.of("orders.log");
        ByteBuffer record = ByteBuffer.wrap("order 42 paid\n".getBytes(StandardCharsets.UTF_8));
        try (FileChannel channel = FileChannel.open(path,
                StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND)) {
            while (record.hasRemaining()) {
                channel.write(record);
            }
            channel.force(true);
        }
        System.out.println("appended and fsynced " + path.toAbsolutePath());
    }
}
```

On Linux, `strace -f -e trace=openat,write,fsync,fdatasync,close -o trace.txt java DurableAppend` recorded 158 of those calls, most of them the JVM opening its own files. The four on `orders.log`:

```text
openat(AT_FDCWD, "orders.log", O_WRONLY|O_CREAT|O_APPEND, 0666) = 4
write(4, "order 42 paid\n", 14)   = 14
fsync(4)                          = 0
close(4)                          = 0
```

The open options became `O_WRONLY|O_CREAT|O_APPEND`, `write` returned after copying 14 bytes into the page cache, and `fsync` returned when the device had them. With `force(false)` the third line is `fdatasync(4)`. Without `force`, the record still appears in the file immediately, from the page cache, and becomes durable only at the next writeback.

**A blocked thread, from both sides.** A program that calls `System.in.read()` on a pipe nobody writes to, on Linux with JDK 21:

```text
$ ps -L -o tid,stat,wchan:18,comm -p 89 | head -3
    TID STAT WCHAN              COMMAND
     89 Sl   futex_do_wait      java
     90 Sl   anon_pipe_read     java
$ jstack 89 | grep -A2 '^"main"'
"main" #1 [90] prio=5 os_prio=0 cpu=32.47ms elapsed=3.23s tid=0x0000ffff8002aab0 nid=90 runnable
   java.lang.Thread.State: RUNNABLE
	at java.io.FileInputStream.readBytes(java.base@21.0.12.1/Native Method)
$ strace -f -p 89
[pid    90] read(0 <unfinished ...>
```

The kernel says thread 90 sleeps in `anon_pipe_read`; `strace` shows its unfinished `read(0`; `jstack` calls the same thread `RUNNABLE`, because the JVM reports any thread inside a native call as runnable. Hundreds of `RUNNABLE` threads in `readBytes`, `read0` or `poll` are blocked threads; `ps -L` or `strace` tells you on what.

## Pitfalls

- `flush()` is not durability. It moves bytes from your buffer to the kernel's. Only `fsync` moves them to the disk.
- Forgetting the directory `fsync` after creating or renaming a file; almost no application code does it. The rename idiom above is the usual fix.
- `fsync` on every record. Each call is a device flush: hundreds of microseconds on an SSD, around ten milliseconds on a spinning disk. Batch records and `fsync` once per batch (group commit), as databases do.
- Benchmarking the page cache. A write test without `fsync` measures `memcpy`; a read test run twice measures RAM the second time.
- Blocking calls on threads that must not block: an event-loop thread, the common `ForkJoinPool` behind parallel streams and `CompletableFuture`, a tiny fixed pool. One blocked thread stalls everything behind it.

## Check yourself

1. `write` returned 14 and the process then crashed. Is the record on disk? What if the kernel crashed instead? What if power was lost one millisecond after `fsync` returned?
2. A thread has been blocked in a read for thirty seconds. How much CPU has it used, what resource is being consumed, and what will `jstack` report?
3. You write a new file, `fsync` it, and the machine loses power. After the reboot the file is missing. Which step did you skip?
4. A tool reports that your laptop writes 2 GB/s to disk. Why can that measurement be correct and useless at the same time?

## Go deeper

- [OSTEP: Limited Direct Execution](https://pages.cs.wisc.edu/~remzi/OSTEP/cpu-mechanisms.pdf) · the trap mechanism, and how the kernel stays in control while your code runs on the bare CPU.
- [strace zine](https://jvns.ca/blog/2015/04/14/strace-zine/) · Julia Evans on reading `strace` output.
- [OSTEP: Crash Consistency](https://pages.cs.wisc.edu/~remzi/OSTEP/file-journaling.pdf) · what a file system itself does to survive a crash, and why that does not protect your data.
- [Dan Luu: Files are hard](https://danluu.com/file-consistency/) · how often real programs get `fsync` wrong, with the research behind it.
- [LWN: PostgreSQL's fsync() surprise](https://lwn.net/Articles/752063/) · how a failed `fsync` can lose data silently, and what PostgreSQL changed.

---

Part of [Foundations](../README.md) · items 2.4, 2.5
