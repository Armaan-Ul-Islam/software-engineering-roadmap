# Java

> The language, the standard library and the JVM as used in modern backend work: from `equals`/`hashCode` to generics, streams, records and sealed types; through class loading, JIT and GC; to the tooling that finds what is slow or leaking. Targets Java 21 and 25.

**Prerequisites:** [Foundations](../01-foundations/README.md), [Memory & Concurrency](../03-memory-and-concurrency/README.md)

**Done when you can:**

- Explain what happens to your code from `javac` to JIT-compiled machine code, and show it with the JDK's own tools.
- Write idiomatic modern Java: records, sealed types, pattern matching, streams, `Optional` as a return type, immutability by default.
- Explain generics (invariance, wildcards, erasure) and collection internals (`HashMap`, `ArrayList`) well enough to predict behaviour and performance.
- Use the concurrency API, including virtual threads, correctly for a server workload.
- Diagnose a production JVM with a thread dump, a heap dump, a GC log, a JFR recording and a flame graph.
- Set up, read and fix a Maven build, including dependency conflicts and BOMs.

## Roadmap

### 1. Language core

- [ ] 1.1 Types and values: primitives vs wrappers, autoboxing and the `Integer` cache, overflow, `char` and Unicode · [dev.java: Numbers and Strings](https://dev.java/learn/numbers-strings/)
- [ ] 1.2 Strings: immutability, the string pool, `StringBuilder`, formatting, text blocks, encodings · [dev.java: Strings](https://dev.java/learn/numbers-strings/strings/)
- [ ] 1.3 `equals`, `hashCode`, `compareTo`, `toString`: the contracts, and what breaks when they are violated · [notes](notes/equals-hashcode-and-value-semantics.md) · [Baeldung: equals() and hashCode() contracts](https://www.baeldung.com/java-equals-hashcode-contracts)
- [ ] 1.4 Classes and interfaces: default/static/private interface methods, abstract classes, nested and inner classes, enums with behaviour · [dev.java: Classes and Objects](https://dev.java/learn/classes-objects/)
- [ ] 1.5 Immutability and value-based design: records, `final`, defensive copies, builders · [notes](notes/equals-hashcode-and-value-semantics.md) · [dev.java: Using Record to Model Immutable Data](https://dev.java/learn/records/)
- [ ] 1.6 Sealed types, pattern matching for `instanceof` and `switch`, record patterns: modelling a domain as algebraic data types · [notes](notes/records-sealed-types-and-pattern-matching.md) · [dev.java: Pattern Matching](https://dev.java/learn/language/fp/pattern-matching/) · [JEP 441: Pattern Matching for switch](https://openjdk.org/jeps/441)
- [ ] 1.7 Generics: invariance, bounded types, wildcards and PECS, type erasure and its consequences · [notes](notes/generics-wildcards-and-erasure.md) · [Baeldung: The Basics of Java Generics](https://www.baeldung.com/java-generics) · [Angelika Langer: Java Generics FAQ](http://www.angelikalanger.com/GenericsFAQ/JavaGenericsFAQ.html)
- [ ] 1.8 Exceptions: checked vs unchecked, try-with-resources, suppressed exceptions, exception translation and design · [notes](notes/exceptions-done-right.md) · [dev.java: Exceptions](https://dev.java/learn/exceptions/)
- [ ] 1.9 Lambdas, functional interfaces, method references, effectively final and captured variables · [dev.java: Lambda Expressions](https://dev.java/learn/lambdas/)
- [ ] 1.10 `Optional` done right: as a return type only; `map`, `flatMap`, `orElseThrow`; never `isPresent`/`get` · [notes](notes/optional-done-right.md) · [Baeldung: Guide to Java Optional](https://www.baeldung.com/java-optional) · [Brian Goetz on the intent of Optional](https://stackoverflow.com/a/26328555)
- [ ] 1.11 Modern idioms worth adopting: `var`, switch expressions, unnamed variables, enhanced `instanceof`, sequenced collections · [Java Almanac](https://javaalmanac.io/)
- [ ] 1.12 Nullness: `Objects.requireNonNull`, nullability annotations, JSpecify and what Spring 7 adopted · [JSpecify](https://jspecify.dev/)

### 2. Collections and streams

- [ ] 2.1 The Collections Framework map: `List`, `Set`, `Map`, `Queue`, `Deque`, their implementations, and a choice table · [dev.java: The Collections Framework](https://dev.java/learn/api/collections-framework/)
- [ ] 2.2 `HashMap` internals: hashing, buckets, treeification, resize and load factor; `LinkedHashMap`, `TreeMap`, `EnumMap` · [notes](notes/hashmap-and-collections-internals.md) · [Baeldung: A Guide to Java HashMap](https://www.baeldung.com/java-hashmap) · [Baeldung: Java HashMap Under the Hood](https://www.baeldung.com/java-hashmap-advanced)
- [ ] 2.3 `ArrayList` vs `LinkedList` vs `ArrayDeque`; `PriorityQueue`; growth strategies and amortised cost · [notes](notes/hashmap-and-collections-internals.md) · [Baeldung: ArrayList vs. LinkedList](https://www.baeldung.com/java-arraylist-linkedlist)
- [ ] 2.4 Immutable collections (`List.of`, `copyOf`), unmodifiable views, `Collections` utilities, defensive copying · [dev.java: Immutable Collections](https://dev.java/learn/api/collections-framework/immutable-collections/)
- [ ] 2.5 Iteration: fail-fast iterators and `ConcurrentModificationException`; `Comparator` composition; sequenced collections · [JEP 431: Sequenced Collections](https://openjdk.org/jeps/431)
- [ ] 2.6 Streams: pipelines, laziness, short-circuiting, stateful operations, collectors (`groupingBy`, `toMap`, `teeing`), the `toMap` duplicate-key trap · [notes](notes/streams-in-practice.md) · [dev.java: The Stream API](https://dev.java/learn/api/collections-and-streams/streams/) · [Baeldung: The Java Stream API](https://www.baeldung.com/java-8-streams)
- [ ] 2.7 Parallel streams: when they help, when they hurt, and the shared common pool problem · [notes](notes/streams-in-practice.md) · [Baeldung: When to Use a Parallel Stream](https://www.baeldung.com/java-when-to-use-parallel-stream)
- [ ] 2.8 Stream gatherers (Java 24+): custom intermediate operations · [JEP 485: Stream Gatherers](https://openjdk.org/jeps/485)

### 3. The standard library you should know

- [ ] 3.1 `java.time`: `Instant`, `LocalDateTime`, `ZonedDateTime`, `Duration` vs `Period`, formatting, and the pitfalls (server zones, DST) · [notes](notes/java-time-essentials.md) · [Baeldung: Introduction to the Java Date/Time API](https://www.baeldung.com/java-8-date-time-intro)
- [ ] 3.2 I/O and NIO: `Path` and `Files`, streams and readers, charsets, buffering, memory-mapped files · [dev.java: Java I/O](https://dev.java/learn/java-io/)
- [ ] 3.3 Math and money: `BigDecimal` scale and rounding, random numbers (`SecureRandom`, `RandomGenerator`) · [Baeldung: BigDecimal and BigInteger](https://www.baeldung.com/java-bigdecimal-biginteger)
- [ ] 3.4 Reflection, annotations and annotation processing: how Spring, Jackson and Lombok work under the hood · [Baeldung: Guide to Java Reflection](https://www.baeldung.com/java-reflection) · [Baeldung: Java Annotation Processing](https://www.baeldung.com/java-annotation-processing-builder)
- [ ] 3.5 Serialisation: why Java serialisation is dangerous; Jackson for JSON (records, polymorphism, dates, visibility) · [Baeldung: Jackson JSON Tutorial](https://www.baeldung.com/jackson)
- [ ] 3.6 `java.net.http.HttpClient`, `ProcessBuilder`, logging with SLF4J and Logback · [Baeldung: Java HttpClient](https://www.baeldung.com/java-9-http-client) · [SLF4J manual](https://www.slf4j.org/manual.html)
- [ ] 3.7 The module system at a glance: what JPMS is for, when you meet it (`jlink`, `--add-opens`) · [dev.java: Modules](https://dev.java/learn/modules/)

### 4. The JVM

- [ ] 4.1 From bytecode to classes: class files, the class loader hierarchy and delegation, `ClassNotFoundException` vs `NoClassDefFoundError` · [notes](notes/jvm-class-loading-and-jit.md) · [JVM Internals](https://blog.jamesdbloom.com/JVMInternals.html) · [Baeldung: Class Loaders in Java](https://www.baeldung.com/java-classloaders)
- [ ] 4.2 Runtime data areas: heap, Metaspace, thread stacks, code cache; the kinds of `OutOfMemoryError` and `StackOverflowError` · [JVM Specification, ch. 2](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html)
- [ ] 4.3 JIT compilation: interpreter, C1/C2 tiers, inlining, deoptimisation, warm-up; why naive micro-benchmarks lie · [notes](notes/jvm-class-loading-and-jit.md) · [Shipilёv: JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/) · [JMH](https://github.com/openjdk/jmh)
- [ ] 4.4 Garbage collectors in practice: G1 (default), ZGC, Parallel; choosing and tuning for a service (concepts in Memory & Concurrency) · [notes](notes/jvm-flags-and-gc-choice.md) · [Oracle: Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/21/gctuning/)
- [ ] 4.5 JVM flags that matter: heap sizing, `-XX:MaxRAMPercentage`, GC selection, `-XX:+HeapDumpOnOutOfMemoryError`, `-Xlog`, container support · [notes](notes/jvm-flags-and-gc-choice.md) · [The java command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [ ] 4.6 Startup and footprint: class data sharing, the AOT cache (Java 24+), GraalVM native image at a glance · [JEP 483: Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483) · [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/)

### 5. Concurrency in Java (the API)

- [ ] 5.1 `Thread`, `Runnable`/`Callable`, `ExecutorService`, `ScheduledExecutorService`, orderly shutdown · [Jenkov: ExecutorService](https://jenkov.com/tutorials/java-util-concurrent/executorservice.html)
- [ ] 5.2 `CompletableFuture` in depth: async methods, composition, `allOf`/`anyOf`, exception handling, timeouts, custom executors · [Baeldung: Guide to CompletableFuture](https://www.baeldung.com/java-completablefuture)
- [ ] 5.3 The `java.util.concurrent` toolbox: locks, atomics, latches, `ConcurrentHashMap`, `BlockingQueue` · [java.util.concurrent package summary](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)
- [ ] 5.4 Virtual threads in practice: `newVirtualThreadPerTaskExecutor`, pinning and `synchronized` (fixed in Java 24), `ThreadLocal` costs, observability · [notes](notes/virtual-threads-in-practice.md) · [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · [JEP 491: Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491)
- [ ] 5.5 Structured concurrency and scoped values · [JEP 505: Structured Concurrency](https://openjdk.org/jeps/505) · [JEP 506: Scoped Values](https://openjdk.org/jeps/506)

### 6. Build, dependencies and project hygiene

- [ ] 6.1 Maven: lifecycle and phases, `pom.xml`, scopes, plugins, multi-module builds; `mvn clean install` explained · [notes](notes/maven-essentials.md) · [Marco Behler: mvn clean install, a short guide to Maven](https://www.marcobehler.com/guides/mvn-clean-install-a-short-guide-to-maven) · [Maven: Getting Started](https://maven.apache.org/guides/getting-started/)
- [ ] 6.2 Dependency management: transitive dependencies, nearest-wins mediation, BOMs, `dependency:tree`, exclusions, the enforcer plugin · [notes](notes/maven-essentials.md) · [Maven: Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [ ] 6.3 Gradle at a glance: Kotlin DSL, tasks, version catalogs; when teams choose it · [Gradle User Manual](https://docs.gradle.org/current/userguide/userguide.html)
- [ ] 6.4 Java versions: the six-month cadence, LTS releases (17, 21, 25), what changed between them, choosing a distribution · [Java Almanac](https://javaalmanac.io/) · [Marco Behler: A Guide to Java Versions and Features](https://www.marcobehler.com/guides/a-guide-to-java-versions-and-features)
- [ ] 6.5 Static analysis and formatting: Error Prone, SpotBugs, Checkstyle, Spotless; `-Xlint:all` and `-Werror` · [Error Prone](https://errorprone.info/) · [SpotBugs](https://spotbugs.github.io/)
- [ ] 6.6 Packaging and running: executable JARs, `jlink` runtimes, container images (details in DevOps & Delivery) · [Spring Boot: Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html)

### 7. Testing

- [ ] 7.1 JUnit 5: lifecycle, assertions, parameterised and nested tests, extensions · [notes](notes/testing-with-junit5-mockito-and-testcontainers.md) · [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [ ] 7.2 AssertJ fluent assertions and custom assertions · [AssertJ documentation](https://assertj.github.io/doc/)
- [ ] 7.3 Mockito: stubs vs mocks vs spies, argument captors, `verify`, and when mocking is a design smell · [notes](notes/testing-with-junit5-mockito-and-testcontainers.md) · [Mockito](https://site.mockito.org/) · [Baeldung: Mockito Series](https://www.baeldung.com/mockito-series)
- [ ] 7.4 Testcontainers for databases, brokers and anything with a Docker image · [notes](notes/testing-with-junit5-mockito-and-testcontainers.md) · [Testcontainers for Java](https://java.testcontainers.org/)
- [ ] 7.5 Property-based testing (jqwik), mutation testing (PIT), coverage (JaCoCo) and what coverage does not tell you · [jqwik](https://jqwik.net/) · [PIT](https://pitest.org/) · [JaCoCo](https://www.jacoco.org/jacoco/)
- [ ] 7.6 Micro-benchmarks with JMH, and why a `System.nanoTime` loop is wrong · [JMH samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples)

### 8. Troubleshooting a running JVM

- [ ] 8.1 Thread dumps: `jcmd <pid> Thread.print`, thread states, finding deadlocks and hot loops · [notes](notes/jvm-troubleshooting-workflow.md) · [Oracle: Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/)
- [ ] 8.2 Heap dumps and leak hunting: `jcmd <pid> GC.heap_dump`, the dominator tree in Eclipse MAT, `HeapDumpOnOutOfMemoryError` · [notes](notes/jvm-troubleshooting-workflow.md) · [Eclipse Memory Analyzer](https://eclipse.dev/mat/)
- [ ] 8.3 JDK Flight Recorder and Mission Control: always-on profiling of allocation, locks, GC and I/O · [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html) · [Oracle: Flight Recorder API guide](https://docs.oracle.com/en/java/javase/21/jfapi/)
- [ ] 8.4 async-profiler and flame graphs: CPU, allocation, lock and wall-clock profiles · [async-profiler](https://github.com/async-profiler/async-profiler) · [Brendan Gregg: Flame Graphs](https://www.brendangregg.com/flamegraphs.html)
- [ ] 8.5 A workflow for the three classic incidents: high CPU, memory growth, stuck requests · [notes](notes/jvm-troubleshooting-workflow.md) · [Oracle: Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/)
- [ ] 8.6 Exposing JVM metrics: JMX, Micrometer, and what to alert on (details in Spring and DevOps & Delivery) · [Micrometer](https://micrometer.io/)

### 9. Idiomatic Java and code quality

- [ ] 9.1 Effective Java, item by item: object creation, common methods, classes and interfaces, generics, enums, lambdas, methods, exceptions, concurrency, serialisation · [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/)
- [ ] 9.2 Readable Java: small classes, intention-revealing names, explicit imports, immutable by default, no clever code · [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html)
- [ ] 9.3 Design patterns as they appear in the JDK and Spring: Builder, Factory, Strategy, Decorator, Template Method, Observer · [Java Design Patterns](https://java-design-patterns.com/)
- [ ] 9.4 Lombok: what it generates, where it bites (`equals` on entities, builders on inheritance), and when records replace it · [Project Lombok features](https://projectlombok.org/features/)

## Resources

### Start here

- [dev.java: Learn Java](https://dev.java/learn/) · the official tutorials, rewritten for modern Java by the JDK team. Start here for sections 1 to 3.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · Joshua Bloch. The book that turns a Java programmer into a Java engineer (paid).
- [Baeldung: Java tutorials](https://www.baeldung.com/java-tutorial) · the broadest collection of focused, runnable examples; verify version-specific details.
- [Marco Behler's guides](https://www.marcobehler.com/guides) · long-form, opinionated guides on Java versions, Maven, JDBC and more.
- [Java Almanac](https://javaalmanac.io/) · every feature by Java version, with API diffs.

### Books

- [Java Concurrency in Practice](https://jcip.net/) · still the reference for the concurrency concepts (paid).
- [Modern Java in Action](https://www.manning.com/books/modern-java-in-action) · lambdas, streams and functional-style Java (paid).
- [Java Performance, 2nd edition](https://www.oreilly.com/library/view/java-performance-2nd/9781492056102/) · Scott Oaks. JIT, GC, memory and the tools (paid).
- [The Well-Grounded Java Developer, 2nd edition](https://www.manning.com/books/the-well-grounded-java-developer-second-edition) · the JVM, bytecode, class loading and modern features (paid).
- [Core Java](https://horstmann.com/corejava/) · Cay Horstmann. The thorough reference when you need the full story (paid).

### Courses and videos

- [Java on YouTube](https://www.youtube.com/@java) · the official channel: JEP Café, Inside Java Newscast, and the "Road to" series for each release.
- [Inside Java](https://inside.java/) · news, articles and podcasts from the JDK team.
- [nipafx](https://nipafx.dev/) · Nicolai Parlog's articles and talks on modern Java features.
- [Marco Codes](https://www.youtube.com/@MarcoCodes) · Marco Behler's practical videos.
- [Jakob Jenkov: Java tutorials](https://jenkov.com/tutorials/java/index.html) · clear coverage of the core language and concurrency.

### References

- [Java Language Specification](https://docs.oracle.com/javase/specs/) and [JDK 21 API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/) · the primary sources.
- [JEP index](https://openjdk.org/jeps/0) · read the JEP for any feature you use; they are well written.
- [roadmap.sh: Java](https://roadmap.sh/java) · visual overview.
- [GeeksforGeeks: Java](https://www.geeksforgeeks.org/java/) · broad coverage with many examples; cross-check against dev.java.
- [Baeldung: Java interview questions](https://www.baeldung.com/java-interview-questions) · a checklist of what people get asked.
- [Awesome Java](https://github.com/akullpp/awesome-java) · the curated library landscape.
