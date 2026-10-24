# Virtual threads in Spring Boot

> **In one sentence:** `spring.threads.virtual.enabled=true` makes Tomcat, `@Async`, `@Scheduled` and the message listener containers run each task on a cheap virtual thread instead of a pooled platform thread, which removes the thread pool as a concurrency limit and changes nothing else: the database pool, the downstream connection pools and the CPU still bound the work, and the way you observe threads has to change with it.

**Why it matters:** The pitch is "reactive throughput without rewriting to reactive", and it is true for services that spend their time waiting on I/O. The disappointment comes when a team flips the switch, measures the same latency under load, and concludes that virtual threads do not work; the thread cap was never the bottleneck, the ten-connection pool was. Knowing exactly what the property switches, what it leaves alone, and how pinning used to bite is what makes the feature usable in production.

## The idea

**What a virtual thread is.** A virtual thread (JEP 444, final in Java 21) is a `java.lang.Thread` that the JDK schedules onto a small pool of carrier platform threads, a `ForkJoinPool` with one carrier per core by default. When it blocks on I/O, a lock or `sleep`, it unmounts and the carrier runs another virtual thread; the blocked stack lives on the heap. Creating one costs kilobytes rather than a megabyte of stack, so a million can exist, and blocking code stays blocking code. There is no speed-up for CPU-bound work, and a virtual thread is not faster than a platform thread; it is cheaper to have waiting.

**What the property switches.** With `spring.threads.virtual.enabled=true` on Java 21 or later (Boot 3.2 and later):

- Tomcat and Jetty execute requests on virtual threads (named `tomcat-handler-N` for Tomcat) instead of the `http-nio-8080-exec-N` pool, so `server.tomcat.threads.max` no longer applies.
- Boot's `applicationTaskExecutor` becomes a `SimpleAsyncTaskExecutor` that starts a virtual thread per task, so `@Async` methods and Spring MVC's asynchronous request handling are no longer bounded by `spring.task.execution.pool.*`.
- The `TaskScheduler` becomes a `SimpleAsyncTaskScheduler`, so each `@Scheduled` run gets its own virtual thread and the single-thread default of item 1.6 stops mattering.
- Spring for Apache Kafka and Spring AMQP listener containers run their consumer threads as virtual threads.

**What it does not change.** A HikariCP pool of ten still allows ten concurrent statements; the eleventh request parks in `getConnection`, cheaply, but it parks, and under load you see `Connection is not available` after `connection-timeout` instead of requests queuing in Tomcat. The HTTP client pool still caps outbound calls per host and in total. A `ThreadPoolTaskExecutor` you defined yourself keeps its platform threads and its size. `ThreadLocal`s work, but each of a hundred thousand virtual threads has its own copy, so a large per-thread cache becomes a memory problem. `synchronized`, `ReentrantLock` and the memory model are unchanged, and JDBC still blocks; it just blocks a virtual thread.

**Pinning.** On JDK 21 to 23, a virtual thread that blocks while inside a `synchronized` block or method, or inside a native call, cannot unmount: it pins its carrier. A JDBC driver with `synchronized` around its socket reads pins one carrier per in-flight query, and with as many pinned carriers as cores, every other virtual thread stops being scheduled. Detect it with `-Djdk.tracePinnedThreads=full`, which prints the stack of each pinning thread, or with the JFR event `jdk.VirtualThreadPinned`. Libraries moved to `ReentrantLock` to avoid it (the PostgreSQL driver from 42.6 onwards, for example), and JDK 24 (JEP 491) removes the limitation for `synchronized` and `Object.wait()` altogether, leaving only native frames. On Java 21 the practical rule is: upgrade the drivers, then check once under load.

**Observability.** Virtual threads are not in `jstack` or `jcmd <pid> Thread.print`; use `jcmd <pid> Thread.dump_to_file -format=json <file>`, which lists them with their stacks. `jvm.threads.live` and the other `ThreadMXBean` metrics count platform threads only, so a flat thread count under heavy load is expected, not reassuring. JFR has `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd` (off by default; there are too many) and `jdk.VirtualThreadPinned` (on, with a 20 ms threshold). MDC, security context and tracing context propagate as before, through `ThreadLocal`, because a request still runs start to finish on one thread.

**Tomcat settings that still matter.** `server.tomcat.max-connections` (8192) caps open connections and `server.tomcat.accept-count` (100) the backlog beyond that; `server.tomcat.connection-timeout` and `server.tomcat.keep-alive-timeout` decide how long idle connections are kept; `server.max-http-request-header-size` and `server.tomcat.max-http-form-post-size` bound what a request may send. With the thread cap gone, `max-connections` becomes the effective ceiling on in-flight requests, forty times the old 200, and something else must provide the back-pressure the thread pool used to provide by accident: a bulkhead in front of each scarce resource (item 8.4), or a short `connection-timeout` on the pool so that overload fails fast.

## Example: the properties, and a thread dump before and after

```properties
spring.threads.virtual.enabled=true
server.tomcat.max-connections=8192
server.tomcat.accept-count=100
server.tomcat.connection-timeout=20s
server.tomcat.keep-alive-timeout=60s
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=2000
```

The scenario: an endpoint that runs one 40 ms query, hit with 2,000 concurrent requests on an eight-core machine.

**Before**, on platform threads, `jcmd <pid> Thread.print` shows 200 `http-nio-8080-exec-N` threads. Ten are `RUNNABLE` in a socket read inside the PostgreSQL driver; 190 are `TIMED_WAITING` in `HikariPool.getConnection`, with `ConcurrentBag.borrow` on the stack. The other 1,800 requests wait in Tomcat's connection backlog and are not visible as threads at all. `hikaricp.connections.pending` reads 190, `jvm.threads.live` about 230, and p99 latency is measured in seconds.

**After**, `jcmd <pid> Thread.dump_to_file -format=json /tmp/threads.json` lists about 2,000 virtual threads named `tomcat-handler-N`. Ten are mounted and running the query; the rest are parked in `LockSupport.park` under `HikariPool.getConnection`, now as virtual threads rather than queued connections. The carriers, `ForkJoinPool-1-worker-N`, number eight and are mostly idle. `jvm.threads.live` reads about 30, `hikaricp.connections.pending` about 1,990, and p99 latency is the same seconds as before: the database was the bottleneck all along, and the change made the queue visible and cheap, not shorter.

What the same dump shows virtual threads did buy: the 200-thread ceiling is gone, so requests that do not need the database (a cached read, a call to a fast downstream service) are served at once instead of waiting behind the database-bound ones; the 2,000 waiting requests cost a few megabytes of heap instead of 2,000 thread stacks; and if the work were outbound HTTP calls against a 200-connection client pool, the service would now run 200 concurrent calls per instance without a thread pool to size. To make the database case faster, the next move is `hikaricp.connections.usage` (item 4.1), not more threads.

## Pitfalls

- Expecting lower latency on a database-bound service. The pool is the limit; raise it only as far as the database can serve, and measure.
- Keeping `connection-timeout` at the default 30 seconds. Thousands of virtual threads now wait half a minute each before failing; two seconds and a clear 503 is kinder to users and to the database.
- A `synchronized` block around blocking I/O in your own code on JDK 21 to 23. It pins; switch to `ReentrantLock` or move to JDK 24.
- Old JDBC drivers and connection pools. Check their release notes for virtual-thread support and run `-Djdk.tracePinnedThreads=full` once under load.
- Pooling virtual threads. A fixed pool of virtual threads reintroduces the cap the feature removed; use `Executors.newVirtualThreadPerTaskExecutor()` or let Boot do it.
- Caching heavy objects in `ThreadLocal`s. One copy per pooled thread becomes one copy per request.
- Reading `jvm.threads.live` and `jstack` as if nothing had changed. Both ignore virtual threads; update the dashboards and the dump command.
- Removing every limit. Without the Tomcat pool, concurrency is bounded by `max-connections`; put an explicit bulkhead in front of each scarce resource.

## Check yourself

1. A colleague enables virtual threads and reports identical p99 latency under load. Which metric tells you whether the thread pool was ever the bottleneck, and what was?
2. Why does a `synchronized` block around a socket read matter on JDK 21 but not on JDK 24, and how would you find such a block in production?
3. After the switch, `jvm.threads.live` shows 30 while the service handles 5,000 concurrent requests. Explain, and name the command that shows the real picture.
4. With `server.tomcat.threads.max` no longer in effect, what limits the number of in-flight requests now, and what should provide back-pressure instead?

## Go deeper

- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · the feature as specified, including the scheduling model and the pinning caveats.
- [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491) · what JDK 24 changed and what still pins.
- [Oracle: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) · the Java 21 developer guide, with the thread-dump and JFR instructions.
- [Spring blog: Embracing Virtual Threads](https://spring.io/blog/2022/10/11/embracing-virtual-threads) · the Spring team's analysis of what virtual threads change for Spring applications.
- [Spring Boot 3.2 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes) · the list of components that `spring.threads.virtual.enabled` switches.
- [Spring Boot: Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html) · the Tomcat properties that still apply.

---

Part of [Spring](../README.md) · item 3.7
