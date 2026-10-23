# Blocking vs non-blocking I/O: thread-per-request, event loops, and where virtual threads fit

> **In one sentence:** Blocking I/O parks a thread for every operation in flight, so concurrency is bounded by how many threads you can afford; non-blocking I/O lets one thread per core wait on thousands of sockets at once but forces you to write callbacks; virtual threads keep the blocking style and make the threads cheap, which is why they fit most services better than either extreme.

**Why it matters:** The choice between a Tomcat-style thread pool, a Netty or Node event loop, and virtual threads decides how your service behaves when a downstream dependency slows down: whether it runs out of threads, whether one blocking call stalls every request on the same core, and whether anyone can read the stack trace afterwards. Every modern web framework asks you to pick one of these models, and the trade-offs are not about speed per request.

## The idea

**Blocking** means the calling thread does nothing until the operation completes: `InputStream.read` waits for bytes, a JDBC `executeQuery` waits for the database, `Thread.sleep`, `Future.get`, `BlockingQueue.take` and lock acquisition all wait. The operating system parks the thread; it costs no CPU while parked, but it costs a thread. In **thread-per-request** servers (Tomcat's default pool of 200 threads, a `ThreadPoolExecutor`), a request owns a thread from start to finish, so the maximum number of requests in flight is the thread count, and each slow dependency holds threads hostage (item 5.1). The model's virtue is that code reads top to bottom, exceptions propagate normally, and a thread dump shows exactly where each request is.

**Non-blocking** means a read on a socket with no data returns at once, and the program asks the OS to tell it when any of many sockets becomes readable (`epoll` on Linux, `kqueue` on macOS, `java.nio.channels.Selector` in Java). An **event loop** (the reactor pattern) is one thread that waits for readiness events and dispatches each to a handler; Node.js runs one, Netty runs one per core or two. A single thread can serve ten thousand idle connections because waiting costs nothing per connection. The rule that makes it work is absolute: never block the event loop. One `Thread.sleep`, one JDBC call, one `synchronized` wait on a loop thread stalls every connection assigned to it.

**The cost of callbacks.** Without a thread to park, "what happens next" must be a function you hand over: a callback, a `CompletableFuture` chain, a reactive pipeline. Control flow is inverted, the stack trace at an error shows the event loop rather than your business logic, exceptions have to be routed by hand (`exceptionally`, `onErrorResume`), and every function that calls an asynchronous function must itself become asynchronous, all the way up. Debugging, profiling and `ThreadLocal`-based context (MDC, security context, transactions) all need special support. The gain is real only when the number of concurrent operations is far larger than the number of threads you can afford.

**Where virtual threads fit.** A virtual thread blocks in the ordinary way, but the JDK implements the blocking call so that the virtual thread is unmounted from its carrier and the carrier serves another virtual thread; underneath, the JDK uses the same non-blocking sockets and poller the event loop would (item 5.5). So the code stays blocking and readable, the threads cost kilobytes instead of megabytes, and concurrency is bounded by memory and the downstream, not by a pool. The event loop keeps its edge for extreme connection counts per core, for protocol work where you control every byte, and when you want backpressure expressed in the stream itself (item 5.7). Neither model makes CPU-bound work faster.

## Example: fetch two URLs three ways

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpResponse.BodyHandlers;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FetchTwoUrls {

    private static final HttpClient CLIENT = HttpClient.newHttpClient();
    private static final HttpRequest FIRST = HttpRequest.newBuilder(URI.create("https://example.com/")).build();
    private static final HttpRequest SECOND = HttpRequest.newBuilder(URI.create("https://example.org/")).build();

    static int blocking() throws Exception {
        HttpResponse<String> firstResponse = CLIENT.send(FIRST, BodyHandlers.ofString());
        HttpResponse<String> secondResponse = CLIENT.send(SECOND, BodyHandlers.ofString());
        return firstResponse.body().length() + secondResponse.body().length();
    }

    static int withCompletableFuture() throws Exception {
        CompletableFuture<Integer> firstLength = CLIENT.sendAsync(FIRST, BodyHandlers.ofString())
                .thenApply(response -> response.body().length());
        CompletableFuture<Integer> secondLength = CLIENT.sendAsync(SECOND, BodyHandlers.ofString())
                .thenApply(response -> response.body().length());
        return firstLength.thenCombine(secondLength, Integer::sum).get();
    }

    static int withVirtualThreads() throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> firstLength = executor.submit(() -> CLIENT.send(FIRST, BodyHandlers.ofString()).body().length());
            Future<Integer> secondLength = executor.submit(() -> CLIENT.send(SECOND, BodyHandlers.ofString()).body().length());
            return firstLength.get() + secondLength.get();
        }
    }
}
```

Timed with `System.nanoTime` around each call after one warm-up request, from a laptop with OpenJDK 25:

```text
blocking             74 ms, 1154 bytes
CompletableFuture    33 ms, 1154 bytes
virtual threads      44 ms, 1154 bytes
```

The blocking version takes the sum of the two round trips because the calling thread does them one after the other. The other two take roughly the longer of the two, because both requests are in flight at once. The difference between them is the shape of the code, not the speed: the future version expresses "both, then combine" as a chain, and any further step (store the result, log it, call a third service) becomes another `thenApply` or `thenCompose`; the virtual-thread version is the blocking code wrapped in `submit`, and a third service is one more line that calls `send`. Put a breakpoint or a thread dump in each and the virtual-thread stack says `FetchTwoUrls.lambda$withVirtualThreads`, while the future's `thenApply` runs on whichever `HttpClient` worker thread completed the response.

Scale the example to a thousand URLs and the blocking version needs a thousand platform threads (or a pool and a queue), the future version needs none but must still bound its concurrency by hand, and the virtual-thread version needs a `Semaphore` around `send` for the same reason: whatever the model, the downstream has a limit (item 5.5).

## Pitfalls

- Blocking on the event loop. A JDBC call, a `synchronized` wait, `Thread.sleep`, or `CompletableFuture.join()` inside a Netty handler or a WebFlux pipeline stalls every connection on that loop thread. Blocking work must be handed to a separate executor (`publishOn`, `subscribeOn`, `thenApplyAsync(function, executor)`).
- Heavy work in `thenApply`. Non-`Async` callbacks run on the thread that completes the future, often an I/O thread; CPU-heavy steps belong in `thenApplyAsync` with your own executor (item 5.2).
- Asynchronous without a limit. Firing ten thousand `sendAsync` calls in a loop is trivially easy and takes down the downstream; non-blocking code needs explicit concurrency limits because nothing blocks to slow the producer.
- Mixing models in one request path. A blocking repository called from a reactive controller gives you the complexity of both and the scalability of neither; pick one model per service.
- Treating non-blocking as faster. Per request it is usually a little slower (more hand-offs between threads); it wins on resource use at high concurrency, and only there.
- Missing timeouts. `HttpRequest.newBuilder(...).timeout(Duration.ofSeconds(2))`, JDBC `setQueryTimeout`, `CompletableFuture.orTimeout`: without them a slow dependency turns every model into a resource leak.

## Check yourself

1. A thread-per-request service has 200 threads and calls a payment API that normally answers in 50 ms. The API slows to 5 seconds. Compute the throughput the service can still sustain, and explain what the event-loop version of the same service would do instead.
2. Why does one blocking JDBC call on a Netty event-loop thread affect requests that never touch the database?
3. In the `CompletableFuture` version, on which thread does `response.body().length()` run, and why would a 50 ms JSON parse there be a problem?
4. What does a virtual thread do while `CLIENT.send` waits for bytes, and what resource is it still consuming?

## Go deeper

- [The C10K problem](http://www.kegel.com/c10k.html) · the 1999 essay that framed the whole debate; the I/O strategies it lists are still the ones in use.
- [Node.js: Don't Block the Event Loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop) · the clearest statement of the event loop's one rule, with the failure modes.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) · the "Motivation" section is the best short comparison of thread-per-request and asynchronous styles.
- [HttpClient Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html) · `send` versus `sendAsync`, executors, and timeouts in the JDK's own client.

---

Part of [Memory & Concurrency](../README.md) · item 5.4
