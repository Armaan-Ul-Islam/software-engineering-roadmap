# Promises, async/await and the event loop

> **In one sentence:** JavaScript runs your code on one thread with a loop that takes one task at a time, drains the whole microtask queue (promise reactions and `await` continuations) after each task, and only then moves on, which is why the output order of mixed `setTimeout` and Promise code is fully predictable.

**Why it matters:** "Predict the output order" is the standard JavaScript interview question, and the model behind it is what you need to debug a UI that freezes, a Node service that stops answering health checks, or a promise rejection that crashes a process at 3 a.m. For a Java developer the hard part is not the syntax but the inversion: there are no threads to block, so every slow operation must hand control back to the loop.

## The idea

Three structures do all the work:

1. **The call stack.** One stack, one thread. A function runs to completion; nothing pre-empts it. While it runs, no click handler, timer or network callback can execute.
2. **The task queue** (also "macrotask" queue). Timers (`setTimeout`, `setInterval`), I/O completions, and in the browser user events and `postMessage` each enqueue a task. The loop takes one task, runs it to completion, then (in a browser) may render, then takes the next.
3. **The microtask queue.** Promise reactions (`.then`, `.catch`, `.finally`), continuations after `await`, and `queueMicrotask` callbacks go here. After every task, and in fact after every callback, the engine drains this queue *completely*, including microtasks enqueued by microtasks. Nothing from the task queue runs until it is empty.

The timers and the network are handled outside the JavaScript thread (by the browser or by libuv in Node, see item 3.1). Only the callback runs on the loop. This is the sense in which JavaScript is single-threaded yet concurrent: many operations are in flight at once, and their completions are interleaved one callback at a time, so there are no data races on your variables, and also no way to wait for a result without giving up the thread.

**A Promise** is a one-shot container for a value that is not there yet. It is `pending`, then either `fulfilled` with a value or `rejected` with a reason, and never changes again. `.then` registers a reaction and returns a new promise, so reactions chain. If the promise is already settled when `.then` is called, the reaction is still queued as a microtask; it never runs synchronously.

**`async`/`await`** is syntax over promises. An `async` function runs synchronously until its first `await`, then returns a pending promise to its caller. `await expression` wraps the value in a promise if needed, suspends the function, and queues the continuation as a microtask once that promise settles. The caller is not blocked; it continues after the call. A `throw` inside an async function rejects the returned promise; an `await` on a rejected promise throws at that line, so `try`/`catch` works as expected.

**Combinators** for several promises:

| Combinator | Settles when | Result |
|---|---|---|
| `Promise.all` | all fulfil, or the first rejects | array of values, or that first rejection |
| `Promise.allSettled` | all settle | array of `{ status, value }` or `{ status, reason }` |
| `Promise.race` | the first settles, either way | that value or rejection |
| `Promise.any` | the first fulfils, or all reject | that value, or an `AggregateError` |

**Unhandled rejections.** A promise that rejects with no handler attached by the time the microtask queue drains fires `unhandledrejection` in the browser and, in Node 15 and later, crashes the process by default (`--unhandled-rejections=strict` is the default mode). Every promise needs an owner that either awaits it or attaches a `.catch`.

## Example: predict the output

Save as `order.mjs` and run `node order.mjs`.

```javascript
console.log("script start");

setTimeout(() => console.log("timeout 0"), 0);

Promise.resolve()
  .then(() => console.log("then 1"))
  .then(() => console.log("then 2"));

(async () => {
  console.log("async start");
  await null;
  console.log("after await");
})();

console.log("script end");
```

Output:

```text
script start
async start
script end
then 1
after await
then 2
timeout 0
```

Line by line:

1. `script start` prints synchronously.
2. `setTimeout` hands a timer to the host and returns immediately. The callback becomes a *task* once the timer fires, which is at the earliest after the current task.
3. `Promise.resolve()` is already fulfilled, so `.then(then 1)` queues a microtask straight away. The second `.then` attaches to the promise returned by the first `.then`, which is still pending, so nothing is queued for `then 2` yet.
4. The async function is called. It runs synchronously, printing `async start`, until `await null`. `null` is wrapped in a fulfilled promise and the continuation is queued as the *second* microtask. The function returns a pending promise and control comes back to the script.
5. `script end` prints. The script task is finished.
6. The microtask queue is drained: `then 1` runs first and fulfils the promise `then 2` is waiting on, which queues `then 2` at the back. `after await` was already second, so it runs next. Then `then 2`.
7. The queue is empty, so the loop takes the next task: the timer callback prints `timeout 0`.

The rule to carry away: synchronous code first, then every microtask (in order, including new ones), then one task, repeat.

## Example: the error that escapes `try`

```javascript
async function loadSettings() {
  try {
    return fetchJson("/api/settings");          // not awaited: the rejection leaves before catch can see it
  } catch (error) {
    return DEFAULT_SETTINGS;                    // never runs
  }
}
```

`return fetchJson(...)` returns the pending promise from the function. When it rejects later, this `try` block has already finished. Write `return await fetchJson(...)` inside a `try`, or let the caller handle it. The same thing happens with `promises.forEach(async ...)`: `forEach` ignores the returned promises, so errors vanish and nothing waits. Use `for...of` with `await`, or `await Promise.all(items.map(...))`.

## Pitfalls

- Blocking the loop and expecting a timer or a `fetch` callback to interrupt it. `setTimeout(callback, 0)` means "after the current task and all microtasks", not "now". A 2-second synchronous loop delays every timer by 2 seconds.
- Infinite microtasks. A `.then` that schedules another `.then` forever starves the task queue: the page never renders and timers never fire. Use `setTimeout` to yield to the loop.
- Sequential `await` in a loop when the calls are independent. Three `await fetch(...)` statements take three round trips; `await Promise.all([...])` takes one. The reverse mistake, `Promise.all` over a thousand requests, is a self-inflicted denial of service; batch with a concurrency limit.
- `Promise.all` for operations that must all complete. It rejects on the first failure while the others keep running with nobody listening. Use `allSettled` when you need every outcome.
- Forgetting that `async` makes a function return a promise. A caller that does not `await` gets a `Promise { <pending> }`, and a `return` inside `.then` in a non-async callback is not the function's return value.
- Node specifics: `process.nextTick` callbacks run before promise microtasks, and `setImmediate` runs in a later phase than I/O callbacks. Reach for `queueMicrotask` and `setTimeout` unless you know why you need the others.
- Testing with fake timers (Vitest, Jest) and forgetting that promises still need microtask flushes: `await vi.runAllTimersAsync()` style helpers exist for this reason.

## Check yourself

1. Swap `await null` for `await new Promise((resolve) => setTimeout(resolve, 0))` in the example. Where does `after await` move to, and why?
2. A handler does `const user = await loadUser(); const orders = await loadOrders();`. When is that the right shape, and when is it a bug?
3. Why does a `try`/`catch` around `return fetchJson(url)` not catch the rejection, while `return await fetchJson(url)` does?
4. A Node service logs "UnhandledPromiseRejection" and exits once a day. What are the two ways a rejection becomes unhandled, and which fix is a real fix rather than a global handler that hides the bug?

## Go deeper

- [Jake Archibald: Tasks, microtasks, queues and schedules](https://jakearchibald.com/2015/tasks-microtasks-queues-and-schedules/) · the canonical interactive walkthrough; step through the example above visually.
- [Philip Roberts: What the heck is the event loop anyway?](https://www.youtube.com/watch?v=8aGhZQkoFbQ) · 26 minutes that fix the call stack and task queue model.
- [Jake Archibald: In The Loop](https://www.youtube.com/watch?v=cCOL7MC4Pl0) · adds rendering and `requestAnimationFrame` to the picture.
- [javascript.info: Promises, async/await](https://javascript.info/async) · promises, chaining, error handling and the combinators with exercises.
- [Node.js: The Node.js Event Loop](https://nodejs.org/en/learn/asynchronous-work/event-loop-timers-and-nexttick) · the phases, `process.nextTick` and `setImmediate` on the server side.

---

Part of [JavaScript & Frontend](../README.md) · items 1.6, 1.7
