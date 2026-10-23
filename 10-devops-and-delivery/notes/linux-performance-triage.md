# Linux performance triage in 60 seconds

> **In one sentence:** Ten standard commands, run in a fixed order, tell you within a minute whether a slow Linux machine is short of CPU, memory, disk or network or whether the process itself is the problem, and `ss` and `lsof` extend the same discipline to sockets and file descriptors.

**Why it matters:** In production you rarely get to attach a profiler; you get a shell for five minutes on a machine where "everything is slow". The checklist, popularised by Netflix's performance team, turns those minutes into a method. Most Java incidents on Linux turn out to be one of five things: CPU saturation, memory pressure, file-descriptor exhaustion, ephemeral-port exhaustion, or the OOM killer, and every one of them shows up in these outputs.

## The idea

**The checklist.** Run each for a few seconds; the first line of `vmstat`, `iostat` and `sar` is an average since boot and should be ignored.

| Command | What it shows | What to look for |
|---|---|---|
| `uptime` | load averages over 1, 5 and 15 minutes: runnable plus uninterruptible (disk-waiting) tasks | compare with the CPU count; rising or falling tells you whether you arrived early or late |
| `dmesg -T \| tail` | recent kernel messages | OOM killer, TCP drops, disk errors, segfaults |
| `vmstat 1` | `r` runnable, `b` blocked, swap `si`/`so`, I/O `bi`/`bo`, interrupts `in`, context switches `cs`, CPU `us`/`sy`/`id`/`wa`/`st` | `r` above the CPU count is saturation; any `si`/`so` is swapping; high `sy` is kernel work; `st` is a noisy neighbour |
| `mpstat -P ALL 1` | the same per CPU | one CPU at 100 percent and the rest idle is a single-threaded bottleneck or an interrupt storm |
| `pidstat 1` | CPU per process, continuously | which process; `-t` adds threads, which map to Java thread names via `jstack` |
| `iostat -xz 1` | per device: `r/s`, `w/s`, `rkB/s`, `wkB/s`, `r_await`, `w_await`, `aqu-sz`, `%util` | `await` above 10 ms on an SSD or `%util` near 100 is a disk bottleneck |
| `free -m` | `total`, `used`, `free`, `buff/cache`, `available` | only `available` matters; `buff/cache` is reclaimable page cache |
| `sar -n DEV 1` | `rxkB/s`, `txkB/s`, `%ifutil` per interface | throughput against the link speed |
| `sar -n TCP,ETCP 1` | `active/s`, `passive/s` connections, `retrans/s` | retransmits mean a congested network or an overloaded peer |
| `top` | the cross-check | `top -H -p <pid>` lists threads with their CPU share |

**The page cache and "free" memory.** Linux uses idle RAM to cache files; `free` reports it under `buff/cache` and it is given back the moment a process needs it. A machine with 200 MB `free` and 6 GB `available` is healthy. Swapping (`si`/`so` in `vmstat`) is the real warning sign, and for a JVM it is fatal to latency.

**The OOM killer.** When the kernel cannot reclaim enough memory for a cgroup or the whole machine, it kills the process with the highest `oom_score` and writes to the kernel log: `Out of memory: Killed process 4321 (java) total-vm:... anon-rss:... file-rss:...`, or `Memory cgroup out of memory` for a container limit. `dmesg -T` or `journalctl -k` is where you look when a JVM vanished without a log line (item 3.4).

**Sockets.** `ss -s` summarises; `ss -tanp` lists every TCP socket with its owning process; `ss -ltnp` shows listeners. `Recv-Q` on a listening socket is the length of the accept queue (connections the application has not accepted yet) and `Send-Q` its maximum; on an established socket `Recv-Q` is bytes the application has not read and `Send-Q` bytes the peer has not acknowledged. `ss -tan state time-wait | wc -l` counts connections in `TIME_WAIT`.

**File descriptors.** Every socket, file and pipe is one. `ls /proc/<pid>/fd | wc -l` against `Max open files` in `/proc/<pid>/limits` shows how close a process is; `lsof -p <pid> -nP | awk '{print $5}' | sort | uniq -c | sort -rn` shows what kind they are. `java.io.IOException: Too many open files` almost always means a leak (streams or connections not closed; use try-with-resources), not a limit that is too low.

**Ephemeral ports.** An outbound connection takes a local port from `net.ipv4.ip_local_port_range`, by default 32768 to 60999, so 28,232 ports per destination address and port. A closed client-side connection sits in `TIME_WAIT` for 60 seconds, which is fixed in the kernel. Opening more than about 470 new connections per second to one upstream exhausts the range, and the JVM reports `java.net.BindException: Cannot assign requested address`. The fix is connection reuse (an HTTP client pool with keep-alive, a database pool), not kernel tuning; `net.ipv4.tcp_tw_reuse` buys a little margin for outbound connections.

## Example: a saturated Java service

`vmstat 1` on a 4-CPU host serving a Spring Boot API:

```text
procs -----------memory---------- ---swap-- -----io---- -system-- -------cpu-------
 r  b   swpd   free   buff  cache   si   so    bi    bo   in    cs us sy id wa st
14  0      0 612340  48212 2890412    0    0     0    96 9120 41230 91  7  2  0  0
15  0      0 611980  48212 2890420    0    0     0    88 9348 43877 92  6  2  0  0
13  1      0 611204  48220 2890436    0    0     0   140 9011 40102 90  8  1  1  0
```

- `r` of 13 to 15 on 4 CPUs: three to four runnable threads per CPU. This is CPU saturation, and every request is queueing for the processor.
- `us` 91, `sy` 7, `wa` 0: the time goes to user code, not the kernel and not disk. Either application code or garbage collection; `top -H -p <pid>` tells which, because GC threads have names like `GC Thread#3` and `G1 Conc#0`.
- `cs` above 40,000 per second: many threads fighting for 4 CPUs, consistent with a thread pool far larger than the CPU count.
- `free` steady, `si`/`so` zero: memory is not the problem here.

Next step: `pidstat -t -p <pid> 1` for the hottest threads, convert the thread id to hex with `printf '%x\n' <tid>`, and find it as `nid=0x...` in `jcmd <pid> Thread.print`.

`ss -tanp` on the same host, trimmed:

```text
State      Recv-Q  Send-Q  Local Address:Port    Peer Address:Port   Process
LISTEN     101     100     0.0.0.0:8080          0.0.0.0:*           users:(("java",pid=4321,fd=45))
ESTAB      0       0       10.0.3.7:8080         10.0.1.21:51012     users:(("java",pid=4321,fd=312))
ESTAB      184320  0       10.0.3.7:8080         10.0.1.22:40288     users:(("java",pid=4321,fd=318))
TIME-WAIT  0       0       10.0.3.7:47712        10.0.9.5:5432
TIME-WAIT  0       0       10.0.3.7:47716        10.0.9.5:5432
```

- The listener's accept queue is full (`Recv-Q` 101 of a `Send-Q` backlog of 100). The kernel is dropping or delaying new connections; clients see connect timeouts. The backlog is Tomcat's `server.tomcat.accept-count` (default 100), and the application is not accepting because its worker threads are all busy, which matches the `vmstat`.
- An established connection with 184,320 bytes in `Recv-Q`: the client sent a request the application has not read yet. Same cause.
- `TIME_WAIT` sockets towards `10.0.9.5:5432`: the service is opening and closing database connections instead of pooling them. `ss -tan state time-wait | wc -l` shows how many; if it grows, ephemeral ports are next.

## Pitfalls

- Reading the load average without the CPU count, or forgetting that it includes tasks blocked on disk. Load 24 on 8 CPUs with `us` at 30 percent and `b` at 16 is an I/O problem, not a CPU one.
- Panicking at a low `free`. Look at `available`; look for `si`/`so`.
- Reading `top`'s `%CPU` for a JVM without `-H`. 400 percent on a 4-CPU host is saturation, and only the thread view says which threads.
- Raising `ulimit -n` to make "too many open files" go away. The leak is still there; it just takes longer to fill the larger limit.
- Tuning `tcp_fin_timeout` for `TIME_WAIT`. It controls `FIN_WAIT_2`; the 60-second `TIME_WAIT` is not a sysctl. Reuse connections instead.
- In containers: `vmstat` and `free` show the host, not the cgroup. Read `/sys/fs/cgroup/cpu.stat` (`nr_throttled`, `throttled_usec`) and `/sys/fs/cgroup/memory.current` for the container's own view, and bring tools in with `kubectl debug` and an image such as `nicolaka/netshoot`.
- `dmesg` denied. Some distributions restrict it (`kernel.dmesg_restrict`); `journalctl -k` shows the same messages.

## Check yourself

1. `uptime` shows a load of 24 on an 8-CPU host, `vmstat` shows `us` plus `sy` at 30 percent and `b` at 16. What kind of saturation is it, and which command do you run next?
2. Explain the three abnormal numbers in the `ss` excerpt and name the Spring Boot or driver setting related to each.
3. The JVM logs `Too many open files`. Which three commands tell you whether it is a leak and of what kind of descriptor?
4. A service opens a new HTTP connection per request to one upstream and intermittently fails with `Cannot assign requested address`. Explain the failure with numbers and name the fix.

## Go deeper

- [Netflix: Linux Performance Analysis in 60,000 Milliseconds](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55) · the original checklist with an explanation of every command.
- [Brendan Gregg: Linux Performance](https://www.brendangregg.com/linuxperf.html) · the map of every tool, from the checklist to BPF.
- [Brendan Gregg: The USE Method](https://www.brendangregg.com/usemethod.html) · utilisation, saturation and errors for every resource; the method behind the checklist.
- [Linux ate my RAM](https://www.linuxatemyram.com/) · the page cache and `available`, explained for people who panic at `free`.
- [ss(8) manual page](https://man7.org/linux/man-pages/man8/ss.8.html) · the state filters and the meaning of the queue columns.
- [Julia Evans: tcpdump is amazing](https://jvns.ca/blog/2016/03/16/tcpdump-is-amazing/) · the next tool when `ss` says the problem is on the wire.

---

Part of [DevOps & Delivery](../README.md) · items 7.1, 7.2, 7.4
