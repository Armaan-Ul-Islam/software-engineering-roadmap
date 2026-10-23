# Memory & Concurrency

> How programs use memory and do many things at once: stack and heap, caches, garbage collection, memory models, threads, locks, lock-free techniques, thread pools, async I/O and virtual threads. Language-neutral ideas, Java examples.

**Prerequisites:** [Foundations](../01-foundations/README.md)

**Done when you can:**

- Draw the stack and heap for a running method and explain what the garbage collector can and cannot reclaim.
- Explain happens-before and spot a visibility bug in a code review before it reaches production.
- Reproduce, then fix, a race condition, a deadlock and a thread-pool starvation.
- Size a thread pool from measured latency and target throughput, and say when virtual threads or non-blocking I/O are the better tool.
- Read a GC log or a heap dump well enough to tell a leak from a badly sized heap.

## Roadmap

### 1. Memory: the mental model

- [ ] 1.1 Stack frames, heap objects, references vs values; what lives where in Java (primitives, objects, arrays, strings, statics) · [Baeldung: Stack Memory and Heap Space in Java](https://www.baeldung.com/java-stack-heap)
- [ ] 1.2 Object layout and cost: headers, alignment, compressed references, the real size of an `Integer` or an empty `ArrayList` · [JOL: Java Object Layout](https://github.com/openjdk/jol) · [Shipilёv: JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/)
- [ ] 1.3 Allocation: bump-pointer allocation and TLABs; why allocating is cheap and why allocation rate still matters · [JVM Anatomy Quark #4: TLAB allocation](https://shipilev.net/jvm/anatomy-quarks/4-tlab-allocation/)
- [ ] 1.4 Escape analysis and scalar replacement: when the JIT removes your allocation entirely · [JVM Anatomy Quark #18: Scalar replacement](https://shipilev.net/jvm/anatomy-quarks/18-scalar-replacement/)
- [ ] 1.5 Memory hierarchy for programmers: cache lines, prefetching, false sharing, data-oriented layouts · [Mechanical Sympathy](https://mechanical-sympathy.blogspot.com/) · [What Every Programmer Should Know About Memory](https://people.freebsd.org/~lstewart/articles/cpumemory.pdf)
- [ ] 1.6 Manual memory management for contrast: malloc/free, ownership, RAII, use-after-free; how Rust's borrow checker frames the same problem · [The Rust Book: Ownership](https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html)

### 2. Garbage collection

- [ ] 2.1 Reachability and GC roots; mark-sweep, mark-compact, copying collection; stop-the-world pauses · [Oracle: Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/) · [Baeldung: JVM Garbage Collectors](https://www.baeldung.com/jvm-garbage-collectors)
- [ ] 2.2 Generational collection: the weak generational hypothesis, young and old generations, minor vs major vs full GC · [Oracle: Generations](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-collector-implementation.html)
- [ ] 2.3 The HotSpot collectors: Serial, Parallel, G1, ZGC, Shenandoah; throughput vs pause time; how to choose · [Oracle: Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html) · [JEP 439: Generational ZGC](https://openjdk.org/jeps/439)
- [ ] 2.4 Heap sizing and GC logs: `-Xmx`, `-XX:MaxRAMPercentage`, `-Xlog:gc*`, allocation rate, promotion, GC overhead · [GCeasy](https://gceasy.io/) · [java command: -Xlog](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [ ] 2.5 Memory leaks in a garbage-collected language: unbounded caches, static collections, listeners, `ThreadLocal`s, classloader leaks; finding them with heap dumps · [Eclipse Memory Analyzer](https://eclipse.dev/mat/) · [Baeldung: Understanding Memory Leaks in Java](https://www.baeldung.com/java-memory-leaks)
- [ ] 2.6 Reference types: strong, soft, weak, phantom; `WeakHashMap`; `Cleaner` instead of finalizers · [Baeldung: Soft, Weak and Phantom References](https://www.baeldung.com/java-weak-reference)
- [ ] 2.7 Off-heap and native memory: direct buffers, Metaspace, thread stacks, code cache; why RSS exceeds `-Xmx` · [Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)

### 3. Memory models and visibility

- [ ] 3.1 Why a memory model exists: compiler and CPU reordering, store buffers, caches, and what sequential consistency would cost · [Preshing: Weak vs. Strong Memory Models](https://preshing.com/20120930/weak-vs-strong-memory-models/) · [Preshing: Memory Ordering at Compile Time](https://preshing.com/20120625/memory-ordering-at-compile-time/)
- [ ] 3.2 The Java Memory Model: program order, synchronisation actions, happens-before; what a data race is · [JSR-133 FAQ](https://www.cs.umd.edu/~pugh/java/memoryModel/jsr-133-faq.html) · [Shipilёv: Java Memory Model Pragmatics](https://shipilev.net/blog/2014/jmm-pragmatics/) · [JLS 17.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4)
- [ ] 3.3 `volatile`: visibility and ordering without atomicity; the double-checked locking story · [Jenkov: Java volatile](https://jenkov.com/tutorials/java-concurrency/volatile.html) · [Baeldung: Double-Checked Locking with Singleton](https://www.baeldung.com/java-singleton-double-checked-locking)
- [ ] 3.4 Safe publication, `final` fields, and immutability as a concurrency tool · [Shipilёv: Safe Publication and Safe Initialization](https://shipilev.net/blog/2014/safe-public-construction/)
- [ ] 3.5 Acquire/release semantics and `VarHandle` access modes, for when `volatile` is too strong · [Preshing: Acquire and Release Semantics](https://preshing.com/20120913/acquire-and-release-semantics/) · [Doug Lea: Using JDK 9 Memory Order Modes](https://gee.cs.oswego.edu/dl/html/j9mm.html)

### 4. Threads and shared state

- [ ] 4.1 Platform threads: what they cost (stack, context switch), how many you can have, how the scheduler treats them · [Jenkov: Java Concurrency Tutorial](https://jenkov.com/tutorials/java-concurrency/index.html)
- [ ] 4.2 Race conditions: check-then-act, read-modify-write, compound actions; "atomic" is per operation, not per line · [Java Concurrency in Practice, ch. 2](https://jcip.net/)
- [ ] 4.3 Mutual exclusion: `synchronized`, intrinsic locks and reentrancy, `ReentrantLock`, `ReadWriteLock`, `StampedLock`, fairness · [Jenkov: Java synchronized](https://jenkov.com/tutorials/java-concurrency/synchronized.html) · [Baeldung: Guide to java.util.concurrent.Locks](https://www.baeldung.com/java-concurrent-locks)
- [ ] 4.4 Coordination: `wait`/`notify`, `Condition`, `CountDownLatch`, `CyclicBarrier`, `Semaphore`, `Phaser` · [Oracle: Guarded Blocks](https://docs.oracle.com/javase/tutorial/essential/concurrency/guardmeth.html) · [Baeldung: CountDownLatch](https://www.baeldung.com/java-countdown-latch)
- [ ] 4.5 Deadlock, livelock, starvation: the four conditions, lock ordering, `tryLock` with timeouts, reading a thread dump · [Baeldung: Deadlock and Livelock](https://www.baeldung.com/java-deadlock-livelock) · [Java Concurrency in Practice, ch. 10](https://jcip.net/)
- [ ] 4.6 Atomics and CAS: `AtomicInteger`, `compareAndSet`, the ABA problem, `LongAdder`, when atomics beat locks · [Jenkov: Compare and Swap](https://jenkov.com/tutorials/java-concurrency/compare-and-swap.html) · [Baeldung: Atomic Variables](https://www.baeldung.com/java-atomic-variables)
- [ ] 4.7 Concurrent collections: `ConcurrentHashMap` (and its `compute` pitfalls), `CopyOnWriteArrayList`, `BlockingQueue`s, `ConcurrentLinkedQueue` · [Baeldung: Guide to ConcurrentMap](https://www.baeldung.com/java-concurrent-map)
- [ ] 4.8 Thread confinement, `ThreadLocal`, `ScopedValue`, and designing shared mutable state away · [JEP 506: Scoped Values](https://openjdk.org/jeps/506)
- [ ] 4.9 Lock-free and wait-free structures at a glance; what the LMAX Disruptor taught the industry · [LMAX Disruptor](https://lmax-exchange.github.io/disruptor/)

### 5. Structuring concurrent work

- [ ] 5.1 Executors and thread pools: core/max size, queue type, rejection policy, shutdown; sizing for CPU-bound vs I/O-bound work with Little's law · [Jenkov: ExecutorService](https://jenkov.com/tutorials/java-util-concurrent/executorservice.html) · [Baeldung: Thread Pools in Java](https://www.baeldung.com/thread-pool-java-and-guava)
- [ ] 5.2 Futures and promises: `Future`, `CompletableFuture` composition, exception handling, timeouts, and which pool runs your callbacks · [Baeldung: Guide to CompletableFuture](https://www.baeldung.com/java-completablefuture)
- [ ] 5.3 Fork/join and parallel streams: work stealing, the shared common pool trap, when parallel streams are slower · [Oracle: Fork/Join](https://docs.oracle.com/javase/tutorial/essential/concurrency/forkjoin.html) · [Baeldung: Guide to the Fork/Join Framework](https://www.baeldung.com/java-fork-join)
- [ ] 5.4 Blocking vs non-blocking I/O: thread-per-request, event loops and reactors, and the cost of callbacks · [The C10K problem](http://www.kegel.com/c10k.html) · [Node.js: Don't Block the Event Loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop)
- [ ] 5.5 Virtual threads (Java 21+): how they are scheduled, pinning, when they help and when they do not · [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · [Oracle: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [ ] 5.6 Structured concurrency: scopes, cancellation and error propagation as a tree of tasks · [JEP 505: Structured Concurrency](https://openjdk.org/jeps/505)
- [ ] 5.7 Reactive streams and backpressure: Project Reactor at a glance; when reactive is worth its complexity · [Reactive Streams](https://www.reactive-streams.org/) · [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/)
- [ ] 5.8 Other models for comparison: actors (Akka, Erlang), CSP (Go channels), async/await (JavaScript, C#, Kotlin coroutines) · [Go by Example: Channels](https://gobyexample.com/channels) · [Kotlin: Coroutines basics](https://kotlinlang.org/docs/coroutines-basics.html)

### 6. Correctness and performance in practice

- [ ] 6.1 Designing for concurrency: immutability, confinement, message passing, idempotent operations, minimising shared state · [Java Concurrency in Practice, ch. 3-4](https://jcip.net/)
- [ ] 6.2 Testing concurrent code: latches in tests, stress tests, `jcstress` for memory-model bugs · [jcstress](https://github.com/openjdk/jcstress)
- [ ] 6.3 Diagnosing: thread dumps (`jcmd <pid> Thread.print`), lock contention and allocation profiling with JFR and async-profiler · [async-profiler](https://github.com/async-profiler/async-profiler) · [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)
- [ ] 6.4 Amdahl's law and why adding threads stops helping; contention and coherence costs · [Amdahl's law](https://en.wikipedia.org/wiki/Amdahl%27s_law)
- [ ] 6.5 Latency vs throughput, queueing basics and Little's law for capacity planning · [Little's law](https://en.wikipedia.org/wiki/Little%27s_law)

## Resources

### Start here

- [Java Concurrency in Practice](https://jcip.net/) · Goetz et al. Written for Java 5, still the definitive text on the concepts; read with the Java 21+ API in mind (paid).
- [Jakob Jenkov: Java Concurrency Tutorial](https://jenkov.com/tutorials/java-concurrency/index.html) · free, clear, and complete coverage of the concurrency utilities.
- [Aleksey Shipilёv: JMM Pragmatics](https://shipilev.net/blog/2014/jmm-pragmatics/) · the memory model explained by the person who maintains the tooling around it. Pair with his [JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/).
- [OSTEP: Concurrency](https://pages.cs.wisc.edu/~remzi/OSTEP/) · the OS-level foundations: threads, locks, condition variables, deadlock.
- [Oracle Java Tutorials: Concurrency](https://docs.oracle.com/javase/tutorial/essential/concurrency/) · short and official; good for a first pass.

### Books

- [Java Performance, 2nd ed.](https://www.oreilly.com/library/view/java-performance-2nd/9781492056102/) · Scott Oaks. GC tuning, JIT, and the tooling, in practice (paid).
- [The Art of Multiprocessor Programming](https://www.oreilly.com/library/view/the-art-of/9780124159501/) · Herlihy and Shavit. The theory behind locks, CAS and lock-free structures (paid).
- [Is Parallel Programming Hard, And, If So, What Can You Do About It?](https://mirrors.edge.kernel.org/pub/linux/kernel/people/paulmck/perfbook/perfbook.html) · Paul McKenney's free book from the Linux kernel world.

### Courses and videos

- [Inside Java](https://inside.java/) · articles and podcasts from the JDK team; follow the virtual threads and GC tags.
- [Java YouTube channel](https://www.youtube.com/@java) · "JEP Café" and "Road to Java 21/25" episodes on virtual threads, structured concurrency and scoped values.
- [Preshing on Programming](https://preshing.com/) · the clearest writing on memory ordering, lock-free programming and CPU behaviour.

### References

- [JLS chapter 17: Threads and Locks](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html) · the formal memory model.
- [java.util.concurrent package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html) · read the package docs, they are excellent.
- [Doug Lea's home page](https://gee.cs.oswego.edu/dl/) · the JSR-133 cookbook and memory order modes paper.
- [Oracle GC Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/) · the official reference for every collector and flag.
