# `CompletableFuture` in depth: composition, exceptions, timeouts and threads

> **In one sentence:** A `CompletableFuture` is a slot that will eventually hold a value or an exception, with methods that attach the next step to run when it fills; that step runs on whichever thread completed the previous stage unless you use an `Async` variant, exceptions travel down the chain wrapped in `CompletionException`, timeouts complete the future but never stop the work, and on Java 21 most chains can be replaced by plain blocking code on a virtual thread.

**Why it matters:** `CompletableFuture` is how Java HTTP clients, database drivers and frameworks hand back asynchronous results, so you will read and write these chains whether you like the style or not. The bugs are specific and repeat: a `thenApply` that parses a 5 MB response on an I/O thread, a `thenApply` that should have been `thenCompose` and yields a `CompletableFuture<CompletableFuture<T>>`, an `exceptionally` that never matches because the exception arrived wrapped, and a timeout that fired while the request it abandoned kept running.

## The idea

**Creating and completing.** `supplyAsync(supplier)` runs the supplier on `ForkJoinPool.commonPool()` and returns a future for its result; `supplyAsync(supplier, executor)` uses your pool, which is what production code should do. `runAsync` is the same without a result. `completedFuture(value)` and `failedFuture(exception)` (Java 9) build already-complete futures. `new CompletableFuture<>()` is an empty slot that something else fills later with `complete(value)` or `completeExceptionally(exception)`: the promise side, used to bridge callback APIs. A future completes once; both methods return `true` only for the call that actually did it.

**Composition.** Three methods cover almost everything:

| Method | Function shape | Use when |
|---|---|---|
| `thenApply(function)` | `T -> U` | transforming a value synchronously (parse, map, extract) |
| `thenCompose(function)` | `T -> CompletionStage<U>` | the next step is itself asynchronous (a second call that needs the first result) |
| `thenCombine(other, function)` | `(T, V) -> U` | two independent futures whose results are both needed |

`thenApply` with a function that returns a future gives you a future of a future; `thenCompose` flattens it (it is `flatMap`). `thenAccept` and `thenRun` are the void forms. For more than two futures, `allOf(futures...)` returns a `CompletableFuture<Void>` that completes when all of them have; read the values afterwards with `join()` on each, which cannot block because they are already complete. `anyOf` completes with the first outcome, value or exception.

**Exceptions.** When a stage fails, every dependent stage is skipped and completed exceptionally. Three methods see the failure: `exceptionally(function)` runs only on failure and replaces the exception with a value; `handle((value, exception) -> ...)` runs in both cases and returns a new value; `whenComplete((value, exception) -> ...)` observes both cases and passes the original outcome through unchanged, which is what you want for logging and metrics. The wrapping rule: the throwable these methods receive is the raw exception only when `completeExceptionally` was called on that very future. When it was thrown inside a supplier or function, or arrived from an upstream stage, it is a `CompletionException` whose `getCause()` is the real one. So `exceptionally(exception -> exception instanceof TimeoutException ? fallback : ...)` quietly never matches; test the cause. At the end of the chain `join()` throws the unchecked `CompletionException`, while `get()` unwraps it and throws `ExecutionException` with the original exception as cause.

**Timeouts (Java 9).** `orTimeout(duration, unit)` completes the future exceptionally with a `TimeoutException` if it is still pending when time runs out; `completeOnTimeout(value, duration, unit)` completes it with a fallback value instead. Both are driven by one JDK-wide daemon thread (`CompletableFutureDelayScheduler` on JDK 9 to 24, `ForkJoinPool.commonPool-delayScheduler` on JDK 25). Neither cancels nor interrupts the work that was meant to produce the value; the supplier runs to the end on its own thread. A timeout on a future is a promise to the caller, not a limit on the resource.

**Which thread runs a stage.** A non-`Async` dependent stage (`thenApply`, `thenCompose`, `exceptionally`, ...) runs on the thread that completes the previous stage if that stage is still pending when you attach it, and on your own thread if it had already completed. So the same callback may run on an HTTP client's I/O thread, on the timeout thread above, or on the caller, and nothing in the code tells you which. The `Async` variants (`thenApplyAsync` and friends) hand the function to an executor: the common pool by default, sized at `availableProcessors - 1` and shared with parallel streams (item 5.3), or the executor you pass. Rule: keep non-`Async` stages trivial, and give anything that blocks or computes its own executor.

**Cancellation.** `cancel(mayInterruptIfRunning)` completes the future with `CancellationException` and ignores its argument: nothing is interrupted, because the future does not know which thread is working for it. Dependents complete with a `CompletionException` wrapping the `CancellationException`, and the upstream work carries on. To stop the work, cancel at the source: the HTTP request, the JDBC statement, or a flag the supplier checks.

**When virtual threads make the chain unnecessary.** The chain exists so that no platform thread sits blocked on I/O. A virtual thread blocks for almost nothing (item 5.5), so "call three services, combine, with a timeout" becomes three `Future.get(timeout, unit)` calls on a virtual-thread executor, or a `StructuredTaskScope` (item 5.6), in straight-line code with stack traces, exceptions and a debugger that work. Keep `CompletableFuture` where a library hands you one, where you must offer a callback-style API, or on JDKs before 21.

## Example: fan-out to three services with per-call timeouts

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

public class ProductPageFanOut {

    record ProductPage(String productId, String price, int stock, List<String> reviews) {
    }

    private static final ExecutorService SERVICE_CALLS =
            Executors.newFixedThreadPool(4, Thread.ofPlatform().name("service-call-", 0).factory());

    public static void main(String[] arguments) throws InterruptedException {
        System.out.println("1: " + loadPage("sku-1", Duration.ofMillis(50), false).join());
        System.out.println("2: " + loadPage("sku-2", Duration.ofMillis(500), false).join());
        try {
            loadPage("sku-3", Duration.ofMillis(50), true).join();
        } catch (CompletionException exception) {
            System.out.println("3: join threw " + exception.getClass().getSimpleName()
                    + " caused by " + exception.getCause());
        }
        SERVICE_CALLS.shutdown();
        SERVICE_CALLS.awaitTermination(2, TimeUnit.SECONDS);
    }

    static CompletableFuture<ProductPage> loadPage(String sku, Duration reviewsLatency, boolean inventoryDown) {
        return call("catalogue", Duration.ofMillis(20), () -> "product-" + sku.substring(4))
                .thenCompose(productId -> fanOut(productId, reviewsLatency, inventoryDown));
    }

    static CompletableFuture<ProductPage> fanOut(String productId, Duration reviewsLatency, boolean inventoryDown) {
        CompletableFuture<String> price = call("pricing", Duration.ofMillis(50), () -> "99.00")
                .orTimeout(200, TimeUnit.MILLISECONDS);
        CompletableFuture<Integer> stock = call("inventory", Duration.ofMillis(50), () -> {
                    if (inventoryDown) {
                        throw new IllegalStateException("inventory unavailable");
                    }
                    return 7;
                })
                .orTimeout(200, TimeUnit.MILLISECONDS);
        CompletableFuture<List<String>> reviews = call("reviews", reviewsLatency, () -> List.of("great", "fine"))
                .completeOnTimeout(List.of(), 200, TimeUnit.MILLISECONDS);
        return CompletableFuture.allOf(price, stock, reviews)
                .thenApply(nothing -> {
                    System.out.println("   assembling on " + Thread.currentThread().getName());
                    return new ProductPage(productId, price.join(), stock.join(), reviews.join());
                });
    }

    static <T> CompletableFuture<T> call(String service, Duration latency, Supplier<T> response) {
        return CompletableFuture.supplyAsync(() -> {
            sleep(latency);
            T result = response.get();
            System.out.println("   " + service + " answered on " + Thread.currentThread().getName());
            return result;
        }, SERVICE_CALLS);
    }

    static void sleep(Duration duration) {
        try {
            Thread.sleep(duration);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        }
    }
}
```

On OpenJDK 25:

```text
   catalogue answered on service-call-0
   pricing answered on service-call-1
   reviews answered on service-call-3
   inventory answered on service-call-2
   assembling on service-call-2
1: ProductPage[productId=product-1, price=99.00, stock=7, reviews=[great, fine]]
   catalogue answered on service-call-0
   pricing answered on service-call-1
   inventory answered on service-call-3
   assembling on ForkJoinPool.commonPool-delayScheduler
2: ProductPage[productId=product-2, price=99.00, stock=7, reviews=[]]
   catalogue answered on service-call-0
   pricing answered on service-call-1
   reviews answered on service-call-0
3: join threw CompletionException caused by java.lang.IllegalStateException: inventory unavailable
   reviews answered on service-call-2
```

The catalogue lookup feeds the fan-out through `thenCompose` because the fan-out is itself asynchronous. In run 1 the three calls overlap on three pool threads and the page is assembled on `service-call-2`, the thread that completed the last prerequisite. In run 2 the reviews call takes 500 ms, `completeOnTimeout` supplies an empty list after 200 ms, and the last prerequisite was therefore completed by the JDK's timeout thread, so the assembly runs there; anything slow in that `thenApply` would delay every other timeout in the JVM. The final line is run 2's abandoned reviews call finishing 300 ms after its page was returned: the timeout freed the caller and nothing else. In run 3 the inventory supplier throws, `allOf` completes exceptionally, the assembly is skipped, and `join` delivers the original exception wrapped in a `CompletionException`.

## Pitfalls

- `thenApply` where `thenCompose` was meant. The code compiles, the type is `CompletableFuture<CompletableFuture<T>>`, and the outer future completes before the inner call has even started.
- Heavy work in a non-`Async` stage. It runs on whichever thread completes the previous stage: an HTTP client's selector thread, the timeout thread, or a pool you do not own. Use `thenApplyAsync(function, executor)` for anything that parses, computes or blocks.
- Blocking calls on the common pool. `supplyAsync(supplier)` without an executor shares `availableProcessors - 1` threads with every parallel stream in the JVM; a few blocking calls stall all of them (item 5.3).
- Matching exceptions without unwrapping. `exception instanceof TimeoutException` is false in a dependent stage; check `exception.getCause()` or unwrap `CompletionException` first.
- `join()` inside a stage. It blocks the completing thread, and inside a bounded pool it can wait for a task that cannot start because the pool is full: a deadlock (item 5.1).
- Nobody consumes the future. A failed future with no `join`, `get`, `handle` or `whenComplete` fails in silence; attach at least a `whenComplete` that logs.
- Trusting `orTimeout` to protect a resource. It frees the caller, not the connection, thread or downstream call; put the real limit on the client (`HttpRequest.timeout`, JDBC `setQueryTimeout`).

## Check yourself

1. `fetchUser(id).thenApply(user -> fetchOrders(user))`, where `fetchOrders` returns a `CompletableFuture<List<Order>>`. What is the type of the result, when does it complete, and which one-word change fixes it?
2. A `thenApply` after `HttpClient.sendAsync` parses a large JSON body. On which thread does it run, what else in the process is affected while it runs, and how do you move it?
3. `future.orTimeout(2, TimeUnit.SECONDS)` fires. What is the supplier's thread doing now, and what does `exceptionally(exception -> exception instanceof TimeoutException)` evaluate to in the next stage? Why?
4. Rewrite the fan-out example for virtual threads in words: what replaces `allOf`, how is the per-call timeout expressed, and what does a thread dump show that it could not show before?

## Go deeper

- [Baeldung: Guide to CompletableFuture](https://www.baeldung.com/java-completablefuture) · every method family with a short example; good for a first pass.
- [CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html) · the class comment states the threading and exception-wrapping rules this note is built on; read it once in full.
- [CompletionStage Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html) · the naming scheme (`then`, `Async`, `Either`, `Both`) explained systematically.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · the "Motivation" section is the best short argument for when the asynchronous style is no longer worth it.

---

Part of [Memory & Concurrency](../README.md) · item 5.2
