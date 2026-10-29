# Java versions: the cadence, the LTS releases, what changed from 8 to 25, and which distribution to run

> **In one sentence:** Since Java 9 a new feature release ships every March and September, Oracle designates one every two years as long-term support (17, 21, 25), a feature arrives as a *preview* for one or more releases before it is final, and the JDK you run in production is one of several builds of the same OpenJDK source, chosen by support terms rather than features.

**Why it matters:** "We are on Java 17, can we use virtual threads?" (no, 21), "is this `switch` pattern a preview?" (not since 21), "why does the build break on JDK 23 with Lombok?" (annotation processing default), "which Docker base image?" are weekly questions. Knowing the map of releases, and that each feature's JEP names its status, saves arguing from memory. It is also the standard warm-up question in a Java interview.

## The idea

**Cadence and support.** Java 8 shipped in 2014 and Java 9 in 2017, with three years of accumulated change. Since then the schedule is fixed: a feature release every six months, each supported by Oracle until the next one, and every second year (every third year before 21) an LTS release that gets years of updates from Oracle and from the other vendors. The LTS releases are 8, 11, 17, 21 and 25. Features between LTS releases are not experimental; they are simply delivered incrementally, and the LTS release contains everything shipped since the previous one.

**Preview, incubator, experimental.** A *preview* language or API feature is complete but may change; it needs `--enable-preview` at compile and run time, and class files compiled with it run only on that exact release. An *incubator* module (`jdk.incubator.vector`) is an API in development. An *experimental* JVM feature needs `-XX:+UnlockExperimentalVMOptions`. Production code uses none of these; the JEP for each feature says which status it has in which release.

**What changed, by release.** Only the items a backend developer meets; each is final in the release listed unless marked.

| Release | Year | Language and library | JVM and tooling |
|---|---|---|---|
| 8 (LTS) | 2014 | lambdas, streams, default methods, `Optional`, `java.time`, `CompletableFuture` | Metaspace replaces PermGen |
| 9 | 2017 | modules (JPMS), `List.of`/`Map.of`, private interface methods, `jshell` | G1 default collector, compact strings, `-Xlog` unified logging, `jlink`, multi-release JARs, `invokedynamic` string concatenation |
| 10 | 2018 | `var` for locals, `List.copyOf`, `Optional.orElseThrow()` | container awareness (CPU and memory limits respected), application class-data sharing |
| 11 (LTS) | 2018 | `HttpClient`, `String.isBlank`/`lines`/`strip`/`repeat`, `Files.readString`/`writeString`, `var` in lambda parameters, single-file `java Foo.java` | Java EE and CORBA modules removed (JAXB, JAX-WS must be added as dependencies), Flight Recorder open-sourced, ZGC experimental |
| 12 to 13 | 2019 | `Collectors.teeing`, `String.indent` | Shenandoah, switch expressions and text blocks in preview |
| 14 | 2020 | switch expressions final; records and `instanceof` patterns in preview | helpful `NullPointerException` messages, JFR event streaming, CMS removed |
| 15 | 2020 | text blocks final; sealed classes in preview | ZGC and Shenandoah production-ready, Nashorn removed, hidden classes |
| 16 | 2021 | records final, `instanceof` patterns final, `Stream.toList()` | JDK internals strongly encapsulated by default, `jpackage`, Unix-domain sockets |
| 17 (LTS) | 2021 | sealed classes final, `RandomGenerator` API; pattern matching for `switch` in preview | `--illegal-access` removed (use `--add-opens`), context-specific deserialisation filters, Security Manager deprecated for removal, macOS/AArch64 port |
| 18 | 2022 | UTF-8 as the default charset, `jwebserver`, `@snippet` in Javadoc | core reflection reimplemented on method handles, finalisation deprecated for removal |
| 19 to 20 | 2022 to 2023 | virtual threads, record patterns and structured concurrency in preview or incubation | Linux/RISC-V port |
| 21 (LTS) | 2023 | virtual threads, record patterns, pattern matching for `switch`, sequenced collections; unnamed patterns, scoped values and structured concurrency in preview | generational ZGC, key encapsulation mechanism API, dynamic agent loading warns |
| 22 | 2024 | foreign function and memory API final, unnamed variables and patterns (`_`) final, multi-file source launch; stream gatherers, statements before `super()` and class-file API in preview | G1 region pinning |
| 23 | 2024 | Markdown Javadoc comments; primitive types in patterns and module import declarations in preview | generational ZGC the default ZGC mode, `javac` no longer runs classpath annotation processors unless told to, `sun.misc.Unsafe` memory access deprecated for removal |
| 24 | 2025 | stream gatherers final, class-file API final | ahead-of-time class loading and linking (the AOT cache), virtual threads no longer pin on `synchronized`, Security Manager permanently disabled, compact object headers experimental, generational Shenandoah, ML-KEM and ML-DSA, Windows 32-bit port removed |
| 25 (LTS) | 2025 | scoped values final, module import declarations final, compact source files and instance `main` final, flexible constructor bodies final; structured concurrency and primitive patterns still in preview | compact object headers final, AOT method profiling and command-line ergonomics, JFR CPU-time profiling (experimental, Linux) and method tracing, generational Shenandoah default, 32-bit x86 port removed |

**Choosing a distribution.** All of these are builds of the OpenJDK source for a given release, differing in licence, support length, platforms and bundled extras, and passing the same compatibility test kit:

- Eclipse Temurin (Adoptium): vendor-neutral, free, long update windows for LTS releases, the common default for containers.
- Amazon Corretto, Microsoft Build of OpenJDK, Azul Zulu, BellSoft Liberica, Red Hat build of OpenJDK, SapMachine: the same with a vendor behind it; pick the one your platform or support contract already covers.
- Oracle JDK: Oracle's own build under the no-fee terms for 17 and later, with free updates until one year after the next LTS, then paid.
- Oracle's OpenJDK builds at jdk.java.net: GPL, updated only for the current feature release; good for trying a new release, wrong for production.
- GraalVM: a JDK plus the Graal JIT and native image (see item 4.6).

Match the major version to the framework: Spring Boot 3 requires Java 17 or later; Spring Boot 4 and Spring Framework 7 keep Java 17 as the baseline. Run the newest LTS the framework supports, upgrade within a year of a new LTS, and keep the patch version current (there are quarterly security updates).

## Example: what an upgrade from 8 to 21 actually hits

A short checklist from real migrations, in the order the failures appear:

1. Build. `maven-compiler-plugin` `<release>21</release>`; upgrade every plugin and Lombok, Mockito, Byte Buddy, ASM-based libraries first; they read class files and fail on unknown versions.
2. Removed modules. `javax.xml.bind` (JAXB), `javax.annotation.PostConstruct`, `javax.activation`: add `jakarta.xml.bind-api` plus an implementation, `jakarta.annotation-api`. Then the `javax` to `jakarta` package rename if you move to Spring Boot 3 or Jakarta EE 9 or later at the same time.
3. Encapsulation. `InaccessibleObjectException` or `IllegalAccessError` from a library: upgrade the library; as a last resort `--add-opens java.base/java.lang=ALL-UNNAMED` (see item 3.7).
4. Charset. Code relying on the platform default charset behaves differently on Java 18 and later (UTF-8 everywhere); `-Dfile.encoding=COMPAT` restores the old behaviour while you fix it (see item 1.2).
5. GC and memory. The default collector changed from Parallel to G1 in 9; container limits are honoured since 10, so `-Xmx` set to the host's memory now gets the container killed. Switch to `-XX:MaxRAMPercentage` (see item 4.5).
6. Things that only warn now and will break later: dynamic agent loading (21), `sun.misc.Unsafe` memory access (23 and later), finalisation.

And what you gain the day it is done: records, sealed types and pattern matching for the domain model (item 1.6), virtual threads for the request path (item 5.4), `HttpClient`, text blocks for SQL and JSON in tests, helpful `NullPointerException` messages, and a JDK that still receives security updates.

## Pitfalls

- Reading "LTS" as "stable" and the others as "beta". Every release is production quality; LTS only means a longer update window. Staying on 11 because 17 "is new" cost teams years of language features.
- Enabling preview features in production. The class files stop working on the next release. Use them in experiments and in tests that are pinned to a JDK, nowhere else.
- Confusing the JDK version with the `--release` target. Compiling with JDK 25 and `--release 17` gives class files that run on 17 and cannot use anything newer; the flag also hides APIs that did not exist in 17, which `-source`/`-target` do not.
- Mixing distributions between build and run. Build on Temurin 21.0.x, run on Corretto 21.0.y is fine; build on 21, run on 17 fails with `UnsupportedClassVersionError` (class file version 65 versus 61).
- Tracking the major version but not the patch. Quarterly updates fix TLS, serialisation and GC bugs; a container image pinned to `21.0.1` for two years is unpatched.
- Expecting Java 8 behaviour from `String.format`, `Locale` defaults, or `getBytes()` on a new JDK. The charset and locale-data defaults changed (18 for the charset); test the integration layer, not only the unit tests.
- Guessing a feature's release. The JEP index is one search away, and it states the release and whether the feature was preview or final there.

## Check yourself

1. A colleague wants to use `switch` with record patterns in a service that runs on Java 17. What is the answer, and in which release did that feature become final?
2. What does `--enable-preview` imply for the class files you produce, and why is that unacceptable for a library?
3. Your container has a 2 GiB limit and the JVM is started with `-Xmx4g`. What changed in Java 10 that makes this behave differently from an early Java 8, and what flag should replace it?
4. Name three concrete things that break in a Java 8 to 21 upgrade before any application code is changed, and the fix for each.

## Go deeper

- [Java Almanac](https://javaalmanac.io/) · every release with its JEPs, plus API diffs between any two versions; the answer to "when was this added".
- [Marco Behler: A Guide to Java Versions and Features](https://www.marcobehler.com/guides/a-guide-to-java-versions-and-features) · the same story as a narrative, with the distribution question answered plainly.
- [JEP index](https://openjdk.org/jeps/0) · the primary source for each feature's status per release.
- [Inside Java](https://inside.java/) · the JDK team's own announcements, including what each release's "Road to" article covers.

---

Part of [Java](../README.md) · item 6.4
