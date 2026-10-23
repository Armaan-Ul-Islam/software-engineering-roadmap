# JVM class loading and JIT compilation

> **In one sentence:** Class files are loaded on first use through a parent-first chain of class loaders and run in the interpreter until they are hot, when C1 and then C2 compile them with inlining and speculative optimisations that the JVM can undo (deoptimise); the loading side explains `ClassNotFoundException` versus `NoClassDefFoundError` and classpath conflicts, the compilation side explains warm-up and why a `System.nanoTime` loop is not a benchmark.

**Why it matters:** Two incident types come straight from this material: "works on my machine, `NoSuchMethodError` in production" (two versions of a class on the classpath) and "the first minute after a deploy is slow and p99 spikes afterwards" (warm-up and deoptimisation). It also stops you from trusting a timing loop that measured the interpreter, or nothing at all.

## The idea

**Class files and lazy loading.** `javac` turns each type into a `.class` file of constant pool, fields, bytecode and attributes. The JVM loads a class when it is first referenced (a `new`, a static access, `Class.forName`), then **links** it (verification, static field preparation, lazy resolution of symbolic references) and **initialises** it (static initialisers run exactly once, on first active use).

**Class loaders and delegation.** Three built-in loaders form a chain: the bootstrap loader (`java.base`; shows up as `null` from `getClassLoader()`), the platform loader (`java.sql`, `java.net.http` and other modules outside the core) and the application loader (your `-cp` or module path). Each loader asks its parent first and searches its own locations only if the parent fails. So nothing on the classpath can replace `java.lang.String`, and when two jars contain the same class, the first one on the classpath wins, silently. A class's identity is the pair (loader, name), so the same class loaded by two loaders (Tomcat gives each web application its own) is two types, which is where `ClassCastException: com.acme.Foo cannot be cast to com.acme.Foo` comes from.

**The three errors.** `ClassNotFoundException` is checked and thrown when a loader is asked for a class *by name* and cannot find it (`Class.forName`, JDBC driver names, reflective configuration). `NoClassDefFoundError` is an `Error`: your bytecode references a class that existed at compile time but cannot be loaded now (jar missing, wrong scope), or its static initialiser failed earlier. In the second case the message is `Could not initialize class X`, and the real cause was an `ExceptionInInitializerError` logged once, possibly hours before. `NoSuchMethodError` and `NoSuchFieldError` mean the class was found but in a different version from the one you compiled against (see item 6.2).

**Interpreter, C1, C2.** HotSpot interprets bytecode while counting invocations and loop back-edges. With tiered compilation (the default), a warm method is compiled by **C1** (tier 3, fast, instrumented to profile types and branches) and, once hot, by **C2** (tier 4, slow, optimised using that profile). Compilation runs on background threads; a running loop can be swapped into compiled code mid-flight (on-stack replacement, OSR).

**Inlining and speculation.** Inlining is the optimisation that enables the others: small methods (up to 35 bytecodes, `MaxInlineSize`) are inlined everywhere, hot ones up to 325 bytecodes (`FreqInlineSize`). Once inlined, escape analysis can remove allocations, constants fold, dead code disappears and loops unroll. Virtual calls are inlined when the profile shows one or two receiver types, guarded by a type check; a site that has seen three or more stays a real virtual call. When a guard fails, a new subclass is loaded, or a branch that "never" happened happens, the JVM **deoptimises**: it discards the compiled code (`made not entrant`), falls back to the interpreter, re-profiles and recompiles. This is the latency spike after a deployment or when a rare code path is first exercised.

**Warm-up.** A freshly started service runs interpreted code while the compiler threads compete for CPU, so ramp traffic up after a deploy. Class data sharing and the AOT cache (see item 4.6) shorten the class-loading part; Java 25's AOT method profiling (JEP 515) lets C2 start from a saved profile.

**Why naive benchmarks lie.** A `System.nanoTime` loop measures the interpreter and the compiler at work (no warm-up), measures nothing when the result is unused (dead-code elimination), measures a constant when the inputs are known at compile time (constant folding), and feeds the JIT a profile with one implementation type where production has five. JMH addresses each: forked JVMs, warm-up iterations, `Blackhole` to consume results, `@State` objects to hide inputs, and statistics with error bounds.

## Example: diagnosing a classpath conflict

An application compiled against `greeting-lib-2.0.0.jar` runs with `greeting-lib-1.0.0.jar` earlier on the classpath:

```text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String com.example.greeting.Greeter.greet(java.lang.String)'
	at com.example.app.Main.main(Main.java:7)
```

The class was found (otherwise it would be `NoClassDefFoundError`), so a different version is being loaded. Ask the JVM where it came from:

```text
$ java -Xlog:class+load -cp app:greeting-lib-1.0.0.jar:greeting-lib-2.0.0.jar com.example.app.Main | grep Greeter
[0.056s][info][class,load] com.example.greeting.Greeter source: file:/work/greeting-lib-1.0.0.jar
```

From code or a debugger, `Greeter.class.getProtectionDomain().getCodeSource().getLocation()` gives the same answer. The fix is in the build, not the JVM (see item 6.2).

The initialisation trap, in one program:

```java
static final class Config {
    static final String REGION = load();          // throws IllegalStateException
}

Class.forName("com.example.DoesNotExist");      // 1: ClassNotFoundException: com.example.DoesNotExist
Config.REGION;                                   // 2: ExceptionInInitializerError caused by IllegalStateException: ...
Config.REGION;                                   // 3: NoClassDefFoundError: Could not initialize class Boot$Config
```

Only the first failing access shows the real cause; every later one says `Could not initialize class`.

## Example: watching the JIT, then measuring properly

```text
$ java -XX:+PrintCompilation Hot | grep Hot::
   17    9       3       Hot::checksum (38 bytes)
   18   10 %     4       Hot::checksum @ 10 (38 bytes)
   20   11       4       Hot::checksum (38 bytes)
   22    9       3       Hot::checksum (38 bytes)   made not entrant: not used
  114   14 %     4       Hot::main @ 28 (57 bytes)   made not entrant: uncommon trap
```

Columns: milliseconds since start, compile id, attributes (`%` is an OSR compilation, `s` synchronized, `!` has exception handlers), tier, method and bytecode size. `checksum` went through tier 3, was OSR-compiled at tier 4 mid-loop, then got a normal tier 4 version and the tier 3 one was retired; `main` was later deoptimised through an uncommon trap (JDK 25 output).

A JMH benchmark of the same method (annotation processing must be on; with `javac` 23 and later Maven needs `annotationProcessorPaths` pointing at `jmh-generator-annprocess`, or `META-INF/BenchmarkList` is never generated):

```java
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@State(Scope.Thread)
@Fork(1)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 1)
public class ChecksumBenchmark {

    private int[] values;

    @Setup
    public void setUp() {
        values = IntStream.range(0, 64).toArray();
    }

    @Benchmark
    public int checksum() {
        int sum = 0;
        for (int value : values) {
            sum = 31 * sum + value;
        }
        return sum;
    }
}
```

```text
Benchmark                   Mode  Cnt   Score   Error  Units
ChecksumBenchmark.checksum  avgt    5  45.081 ± 3.828  ns/op
```

Returning `sum` keeps the loop alive: JMH feeds return values into a `Blackhole`. Make `values` a `static final` constant instead of `@State` data and C2 may fold the whole method into a number.

## Pitfalls

- Shading or copying classes into "utility" jars. Two copies of one class are the classic source of `NoSuchMethodError`; `-Xlog:class+load` finds the winner in seconds.
- Catching `NoClassDefFoundError` and continuing. The class is permanently unusable in that loader; find the `ExceptionInInitializerError` in the log instead.
- Benchmarking with `System.nanoTime` in a `main` method. Use JMH, and heed its own warning: the numbers are data, not insight, until you know why they are what they are.
- `-Xint` or `-XX:TieredStopAtLevel=1` in production to "stabilise" latency. They remove C2; fix the deoptimisation cause instead.

## Check yourself

1. A library call fails with `NoClassDefFoundError: Could not initialize class com.acme.Settings` at 14:00. Where in the logs is the real cause, and what does it look like?
2. The same `com.acme.Plugin` class appears on the classpath twice, in different versions. Which one does the application loader use, and how do you prove it without reading the pom?
3. Why can a method that was compiled by C2 suddenly run slowly again after a plugin is loaded at runtime?
4. A colleague's timing loop shows that `computeChecksum` takes 0.3 nanoseconds. Name two JIT optimisations that could produce that number and the JMH features that defeat them.

## Go deeper

- [JVM Internals](https://blog.jamesdbloom.com/JVMInternals.html) · class files, loading, linking and initialisation on one page, with diagrams.
- [Baeldung: Class Loaders in Java](https://www.baeldung.com/java-classloaders) · the hierarchy, delegation and how to write a custom loader.
- [Shipilёv: JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/) · short, measured posts on inlining, OSR, deoptimisation and other JIT behaviour.
- [JMH](https://github.com/openjdk/jmh) and the [JMH samples](https://github.com/openjdk/jmh/tree/master/jmh-samples/src/main/java/org/openjdk/jmh/samples) · each sample demonstrates one way a benchmark goes wrong.
- [JVM Specification, chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html) · the exact rules.

---

Part of [Java](../README.md) · items 4.1, 4.3
