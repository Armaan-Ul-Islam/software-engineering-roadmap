# `ThreadLocal` and `ScopedValue`: per-thread context without passing parameters

> **In one sentence:** A `ThreadLocal` gives every thread its own copy of a variable, which is how request ids, logging context and security principals travel through code that never declares them; on pooled threads it leaks into the next request unless you `remove()` it, it costs a lookup per `get` and a copy per child thread, and it fits virtual threads badly, which is why Java 25's `ScopedValue` binds a value for the duration of one call, immutably, and shares it with the subtasks forked inside that call.

**Why it matters:** The classic incident is user B's log lines carrying user A's request id, or user A's authenticated principal, because a pooled thread kept its `ThreadLocal` from the previous request. The classic redeploy incident is Tomcat warning that a web application created a `ThreadLocal` and failed to remove it, while the old classloader stays in Metaspace (item 2.5). With virtual threads, a per-thread cache multiplied by a million threads is a memory problem by design. Interviewers ask about `ThreadLocal` because it tests whether you know what "the thread" means inside a thread pool.

## The idea

**What it is for.** `ThreadLocal<T>` has `get()`, `set(value)`, `remove()` and `withInitial(supplier)`. Each `Thread` owns a small map from `ThreadLocal` instance to value, and `get()` reads the current thread's entry. That makes it *implicit context*: a request id, tenant or locale available at any depth of the call stack without a parameter on every method. Logging MDC (`MDC.put("requestId", id)` in SLF4J and Logback) is a `ThreadLocal` holding a map; Spring's `RequestContextHolder` and `SecurityContextHolder` are `ThreadLocal`s; Spring's transaction manager binds the current JDBC connection to the thread the same way. The older use, a per-thread cache of a non-thread-safe object such as `SimpleDateFormat`, has mostly been replaced by immutable classes such as `DateTimeFormatter`.

**What it costs.** Every `get()` is a hash lookup in the current thread's map: cheap, not free, so read it once into a local variable in hot code. Memory is one value per thread that has touched the variable. The map keys the `ThreadLocal` weakly but holds the value strongly, so when the `ThreadLocal` object itself becomes unreachable the value lingers as a stale entry until that thread's map happens to clean it up.

**Leaks, and `remove()`.** Pooled threads (Tomcat's request threads, any `ExecutorService`) live as long as the process. A value that is `set` and never removed therefore survives the request: the next request on that thread sees it (a correctness bug, and a security bug when the value is a principal), and everything it references stays reachable (a memory leak). On redeploy inside a servlet container, a value whose class belongs to the web application pins that application's classloader, and Tomcat logs "created a ThreadLocal with key of type [...] but failed to remove it when the web application was stopped". The rule: whoever calls `set` on a thread it does not own must call `remove()` in a `finally` on the same thread, at the boundary where the request enters and leaves (a servlet filter, an interceptor, a `ThreadPoolExecutor.afterExecute`).

**Inheritance.** `InheritableThreadLocal` copies the parent's value into a child thread *when the child is created*. That does nothing for a pool, whose threads were created at start-up, so a request's context does not follow a task into an executor; frameworks fix this with a decorator that captures the context at submit time and restores it inside the worker (Spring's `TaskDecorator`, Micrometer's context-propagation library). Virtual threads inherit inheritable thread-locals by default; `Thread.ofVirtual().inheritInheritableThreadLocals(false)` switches it off.

**Why it fits virtual threads poorly.** JEP 506 names three problems: *unconstrained mutability* (any code can `set` at any time, so data flows in any direction), *unbounded lifetime* (there is no scope; cleanup is a manual `remove`), and *expensive inheritance* (every child thread copies every inheritable value). Virtual threads make all three worse: there are a million of them, they are never pooled so a per-thread cache is filled once and thrown away, and they are created constantly so inheritance copies constantly (item 5.5).

**`ScopedValue`** (JEP 506, final in Java 25; a preview API in Java 21 to 24 behind `--enable-preview`):

```java
private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

ScopedValue.where(REQUEST_ID, "req-7f3a").run(() -> handle(request));
```

Inside `run` (or `call`, when a result is needed), `REQUEST_ID.get()` returns `"req-7f3a"` on this thread at any call depth. When `run` returns, the binding is gone: nothing to `remove`, nothing to leak, and no code inside can change it; a nested `where` for the same key shadows it for the nested scope only, and the outer value is restored afterwards. `get()` on an unbound value throws `NoSuchElementException`, so code that may run outside a scope uses `isBound()` or `orElse(fallback)`. Subtasks forked with `StructuredTaskScope` inside the scope see the same binding without copying (item 5.6): the value is shared for the lifetime of the scope rather than duplicated per thread, which is the inheritance model that survives a million threads. What `ScopedValue` is not: a mutable per-thread cache, or a value set in one place and read much later on the same thread outside any call tree. Those stay `ThreadLocal`, with `remove()`.

## Example: a request id that leaks across pooled requests

One pooled thread handles two requests. The first carries a request id header, the second (an internal health probe) does not.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class RequestIdLeak {

    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] arguments) throws InterruptedException {
        ExecutorService requestThreads = Executors.newFixedThreadPool(1, Thread.ofPlatform().name("http-", 1).factory());
        requestThreads.submit(() -> handle("GET /orders/42", "req-7f3a"));
        requestThreads.submit(() -> handle("GET /health", null));
        requestThreads.shutdown();
        requestThreads.awaitTermination(1, TimeUnit.SECONDS);
    }

    static void handle(String request, String incomingRequestId) {
        if (incomingRequestId != null) {
            REQUEST_ID.set(incomingRequestId);
        }
        log(request + " handled");
    }

    static void log(String message) {
        System.out.printf("[%s] [request=%s] %s%n", Thread.currentThread().getName(), REQUEST_ID.get(), message);
    }
}
```

```text
[http-1] [request=req-7f3a] GET /orders/42 handled
[http-1] [request=req-7f3a] GET /health handled
```

The health probe is logged under the previous request's id. In a real service the second line is a different customer, and whoever greps the logs for `req-7f3a` later will read the wrong request's story. The `ThreadLocal` fix is the `finally`:

```java
static void handle(String request, String incomingRequestId) {
    try {
        if (incomingRequestId != null) {
            REQUEST_ID.set(incomingRequestId);
        }
        log(request + " handled");
    } finally {
        REQUEST_ID.remove();
    }
}
```

That works, and it relies on every entry point remembering to do it.

## Example: the same request id as a `ScopedValue` (Java 25)

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class RequestIdScoped {

    private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

    public static void main(String[] arguments) throws InterruptedException {
        ExecutorService requestThreads = Executors.newFixedThreadPool(1, Thread.ofPlatform().name("http-", 1).factory());
        requestThreads.submit(() -> handle("GET /orders/42", "req-7f3a"));
        requestThreads.submit(() -> handle("GET /health", null));
        requestThreads.submit(() -> log("after both requests"));
        requestThreads.shutdown();
        requestThreads.awaitTermination(1, TimeUnit.SECONDS);
    }

    static void handle(String request, String incomingRequestId) {
        if (incomingRequestId == null) {
            log(request + " handled");
            return;
        }
        ScopedValue.where(REQUEST_ID, incomingRequestId).run(() -> log(request + " handled"));
    }

    static void log(String message) {
        System.out.printf("[%s] [request=%s] %s%n", Thread.currentThread().getName(), REQUEST_ID.orElse("none"), message);
    }
}
```

Compiled and run on OpenJDK 25 with no flags (on JDK 21 to 24, add `--enable-preview`):

```text
[http-1] [request=req-7f3a] GET /orders/42 handled
[http-1] [request=none] GET /health handled
[http-1] [request=none] after both requests
```

The binding exists exactly while `run` executes, on the same pooled thread, and there is no cleanup to forget. The one real restriction is visible in the shape of the code: everything that should see the id must be called from inside `run`, which is also what makes the value's lifetime obvious to a reader.

## Pitfalls

- A `set` without a `remove`. The symptom is a log line or a principal from a previous request appearing on an unrelated one, only in production, only on pooled threads.
- `remove()` on a different thread. The value belongs to the thread that set it; removing from an asynchronous callback clears the callback thread's copy and leaves the original.
- Reading a `ThreadLocal` inside a task submitted to another pool. The worker thread has its own empty copy, so the value is `null` and the code "works" until something dereferences it. Capture the value before submitting, or use a task decorator that propagates it.
- `withInitial` creating a resource per thread. A `ThreadLocal<Connection>` on a 200-thread pool is 200 connections that are never closed.
- Heavy per-thread caches on virtual threads. The cache is filled once per request and discarded with the thread; pass the object as a parameter or share a thread-safe instance (item 5.5).
- `ScopedValue.get()` outside its scope. The binding follows `StructuredTaskScope` forks, not tasks handed to a shared `ExecutorService`; those see an unbound value and `get()` throws `NoSuchElementException`.
- Expecting to mutate a `ScopedValue`. A nested `where` shadows for its own scope only; code that needs to publish a changed value upwards needs a different design, usually a return value.

## Check yourself

1. A filter calls `CURRENT_USER.set(user)` and a controller later submits work to a fixed thread pool that calls `CURRENT_USER.get()`. What does the worker see, and what are two ways to make it see the right user?
2. Why does `InheritableThreadLocal` not solve the previous question, and what would its cost be on virtual threads if it did?
3. A `ThreadLocal<SimpleDateFormat>` cache is fine on a 200-thread Tomcat. What changes when the application moves to virtual threads, and what replaces it?
4. In the `ScopedValue` example, what does `REQUEST_ID.get()` return inside a `StructuredTaskScope` subtask forked from `handle`? And inside a task that `handle` submits to a shared `ExecutorService`?

## Go deeper

- [JEP 506: Scoped Values](https://openjdk.org/jeps/506) · the motivation section is the clearest account of what is wrong with thread-locals; then the API.
- [ThreadLocal Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html) · `get`, `set`, `remove`, `withInitial` and the inheritance semantics.
- [Oracle: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html) · includes the guidance on thread-local variables with virtual threads.
- [Logback: Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html) · how MDC rides on thread-locals and what that means for thread pools and child threads.
- [Micrometer Context Propagation](https://github.com/micrometer-metrics/context-propagation) · the library that captures `ThreadLocal` context at submit time and restores it in executors and reactive pipelines.

---

Part of [Memory & Concurrency](../README.md) · item 4.8
