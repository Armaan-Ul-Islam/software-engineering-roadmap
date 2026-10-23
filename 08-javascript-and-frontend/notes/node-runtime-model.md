# The Node.js runtime model: one loop, a thread pool, and what blocks it

> **In one sentence:** Node runs all of your JavaScript on a single thread driven by libuv's event loop, hands network I/O to the operating system and file system, DNS and some crypto work to a small thread pool, and therefore stays responsive exactly as long as no single callback keeps that one thread busy.

**Why it matters:** In a Spring service, a slow handler costs you one thread out of a few hundred. In Node, it costs you the only thread: every concurrent request, timer and health check waits until it returns. That one difference explains most Node production incidents ("the service is up but answers nothing"), most of the Node vs JVM debate, and why `*Sync` APIs and synchronous crypto are banned in request handlers.

## The idea

**Two engines.** V8 parses, compiles (with a JIT) and runs JavaScript, and owns the heap and garbage collector. libuv provides everything the language does not: the event loop, timers, non-blocking sockets on top of `epoll`/`kqueue`/IOCP, and a **thread pool** (four threads by default, `UV_THREADPOOL_SIZE` raises it up to 1024) for operations the operating system offers no asynchronous interface for.

**Where work runs.**

| Work | Runs on |
|---|---|
| Your JavaScript, every callback, every `await` continuation | the one event loop thread |
| TCP/HTTP sockets, pipes | the OS, non-blocking; the loop is only told when data is ready |
| `fs.*` (asynchronous forms), `dns.lookup`, `zlib`, `crypto.pbkdf2`/`scrypt`/`randomBytes` (asynchronous forms) | the libuv thread pool |
| `worker_threads` | separate V8 isolates with their own loops, communicating by message passing |
| Child processes, `cluster` workers | separate OS processes |

**The loop** cycles through phases: timers, pending I/O callbacks, poll (wait for I/O and run its callbacks), check (`setImmediate`), close callbacks. Between every callback it drains `process.nextTick` and the promise microtask queue (see item 1.7). The useful simplification: the loop takes one ready callback, runs it to completion, repeats.

**What blocks it.** Anything synchronous and long: `JSON.parse` or `JSON.stringify` of a multi-megabyte payload, `pbkdf2Sync`/`scryptSync`, `readFileSync` or `execSync` in a handler, a regular expression with catastrophic backtracking applied to user input (`/^(\w+\s?)*$/` on a long string with no match), sorting or aggregating a large array, rendering a huge template. None of these is a bug in a script; all of them are a bug in a server, because the loop cannot accept, parse or answer anything else meanwhile.

**Escape hatches, in order of preference.**

1. Use the asynchronous API. `pbkdf2` instead of `pbkdf2Sync` moves the work to the thread pool and frees the loop.
2. Do less on the loop: stream large bodies instead of buffering, paginate, cap input sizes, reject pathological regexes (or use RE2-style engines).
3. `worker_threads` for CPU-heavy JavaScript. Each worker is a separate isolate; you pass messages (structured clone) or share memory through `SharedArrayBuffer`. Pools of workers exist as libraries.
4. `cluster` or a process manager to run one process per core behind one port. This scales throughput; it does not help a single slow request, and processes share nothing.

Measure event loop delay with `perf_hooks.monitorEventLoopDelay()`; most APM agents report it as "event loop lag", and it is the first graph to look at when latency spikes without CPU saturation.

**Node vs the JVM for a backend service, honestly.**

| | Node | JVM (Spring Boot) |
|---|---|---|
| Concurrency model | one loop per process, async everywhere | thread per request; virtual threads in Java 21 give the same scalability with blocking code |
| I/O-heavy workloads | excellent; little memory per connection | excellent; more memory per thread unless virtual |
| CPU-heavy workloads | needs workers or more processes; one slow task stalls everything | parallel across cores in one process; a slow task costs one thread |
| Startup and footprint | fast start, small heap; good for serverless and CLIs | slower start, larger heap; GraalVM native images narrow the gap |
| Typing and refactoring | optional (TypeScript), erased at runtime | static, checked, mature tooling |
| Ecosystem | enormous, fast-moving, uneven quality; same language as the browser | deep, stable, enterprise libraries; slower to change |
| Operations | `--inspect`, heap snapshots, `--cpu-prof`; fewer production diagnostics | thread dumps, JFR, heap dumps, decades of GC tuning knowledge |

Node fits I/O-bound services, backends-for-frontends, server-side rendering, real-time connections and tooling, and teams who want one language across the stack. The JVM fits CPU-heavy or long-running transactional systems, large codebases, and organisations that already run it well. Neither is faster "in general"; the question is where your CPU time goes and how your team debugs at 3 a.m.

## Example: a handler that blocks the loop, and the fix

```javascript
// server.mjs
import { createServer } from "node:http";
import { pbkdf2Sync } from "node:crypto";

const server = createServer((request, response) => {
  if (request.url === "/hash") {
    const derivedKey = pbkdf2Sync("password", "salt", 1_000_000, 64, "sha512");
    response.end(derivedKey.toString("hex"));
    return;
  }
  response.end("ok");
});

server.listen(3000);
```

Run it, start the slow request, and send a cheap one while the hashing is in progress:

```bash
curl -s -o /dev/null -w "/hash %{time_total}s\n" localhost:3000/hash &
sleep 0.1
curl -s -o /dev/null -w "/     %{time_total}s\n" localhost:3000/
wait
```

Measured on the laptop used to write this note, `/hash` took about 290 ms and `/`, sent 100 ms later, took about 190 ms. The cheap request did no work at all; it waited for the hashing to finish because the handler held the only thread, and a health check or any other user would have waited the same way. If a million iterations finishes quickly on your machine, raise the count until `/hash` takes a noticeable fraction of a second and send the second request inside that window.

The fix is the asynchronous API, which runs on the thread pool:

```javascript
// server.mjs
import { createServer } from "node:http";
import { pbkdf2 } from "node:crypto";
import { promisify } from "node:util";

const deriveKey = promisify(pbkdf2);

const server = createServer(async (request, response) => {
  if (request.url === "/hash") {
    try {
      const derivedKey = await deriveKey("password", "salt", 1_000_000, 64, "sha512");
      response.end(derivedKey.toString("hex"));
    } catch (error) {
      response.statusCode = 500;
      response.end("hashing failed");
    }
    return;
  }
  response.end("ok");
});

server.listen(3000);
```

Repeating the measurement against this version, `/` answered in about 1 ms while `/hash` was still running and still took about 290 ms. The hashing takes exactly as long; the difference is that the loop is free to serve everyone else in the meantime. Four concurrent `/hash` requests still saturate the default pool, so a fifth one queues: size the pool, or rate-limit the expensive endpoint.

For CPU work that is pure JavaScript (parsing, aggregation, image processing), there is no asynchronous API to switch to; move it to a `worker_threads` worker and keep what comes back small. The result is copied to the main thread with structured clone, so posting a 50 MB parsed object back costs the main thread almost as much as parsing it there.

## Pitfalls

- `*Sync` calls that were fine at startup, copied into a handler. `readFileSync` of a config file before `listen()` is correct; the same call per request serialises your service.
- Trusting CPU graphs. A blocked loop shows as one core at 100% while the others idle, and as timeouts everywhere. Watch event loop delay, not CPU.
- Health checks that pass while the loop is blocked. If the check is served by the same process, it stalls too, and the orchestrator restarts the pod mid-request. Put a timeout on the probe that reflects your real latency budget.
- Thread pool starvation. Four parallel `fs` reads or `pbkdf2` calls fill the pool; the fifth waits even though the loop is idle. `dns.lookup` is in the same pool, so slow DNS can stall unrelated file reads.
- Unhandled errors in async handlers. A rejected promise in `createServer(async ...)` is not sent to the client; it crashes the process under Node's default policy. Wrap handlers or use a framework that does (item 3.4).

## Check yourself

1. A Spring developer argues that Node "cannot handle concurrency because it has one thread". What is wrong with the claim for I/O-bound work, and what is right about it for CPU-bound work?
2. Your service shows p99 latency of 3 seconds on every endpoint during a nightly report job that runs in the same process. CPU is at 25% on a 4-core box. Explain the numbers and name two fixes.
3. Why does `await pbkdf2(...)` free the event loop while `await` on a plain synchronous function does not? Where does the work actually run in each case?
4. For which of these would you pick Node over the JVM, and why: a PDF rendering service, a WebSocket presence service for 100k connections, a nightly batch that recomputes risk scores, a BFF that aggregates five REST calls per page?

## Go deeper

- [Node.js: The Node.js Event Loop](https://nodejs.org/en/learn/asynchronous-work/event-loop-timers-and-nexttick) · the phases, with `setImmediate` and `process.nextTick` explained.
- [Node.js: Don't Block the Event Loop (or the Worker Pool)](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop) · the official guide behind this note, including the ReDoS and JSON examples.
- [Node.js: Worker threads](https://nodejs.org/api/worker_threads.html) · the API reference, with the note on when workers help and when they do not.
- [Node.js: Cluster](https://nodejs.org/api/cluster.html) · one process per core behind one port, and how connections are distributed.
- [Node.js Design Patterns](https://www.nodejsdesignpatterns.com/) · the book-length treatment of the reactor pattern, streams and scaling (paid).

---

Part of [JavaScript & Frontend](../README.md) · items 3.1, 3.8
