# React hooks and effects

> **In one sentence:** Hooks let a function component keep state (`useState`), hold a value without re-rendering (`useRef`), cache a computation or a function identity (`useMemo`, `useCallback`) and synchronise with something outside React (`useEffect`), and most effect bugs come from using `useEffect` for things that are not synchronisation, or from ignoring that an effect can be superseded before it finishes.

**Why it matters:** `useEffect` is where React code goes wrong in production: fetches that resolve out of order and show the wrong customer, intervals that leak after navigation, effects that run on every render because a dependency is a fresh object each time, and state that is set from a stale closure. Each has a short rule behind it. Reviewers who know the rules spot these in seconds; developers who do not spend days on them.

## The idea

**`useState` and updater functions.** `const [count, setCount] = useState(0)` declares state that survives re-renders. The `count` you read is a snapshot for this render. `setCount(count + 1)` twice in one handler sets the same value twice, because both calls read the same snapshot. `setCount((previous) => previous + 1)` queues a function that React applies to the latest state, so two calls add two. Use the updater form whenever the new value depends on the old one, and always inside asynchronous callbacks, where the closed-over snapshot may be old. Pass a function to compute expensive initial state once: `useState(() => parseSavedFilters())`.

**`useEffect(setup, dependencies)`** runs `setup` after React has committed the render to the DOM, without blocking the paint. If `setup` returns a function, that cleanup runs before the next `setup` and when the component unmounts. The dependency array controls when it re-runs: omitted means after every render; `[]` means after the first render only; `[customerId]` means after any render in which `customerId` changed (compared with `Object.is`). Every reactive value the effect reads, which is every prop, state variable and anything computed from them in the component body, must be in the array; the `react-hooks/exhaustive-deps` lint rule enforces it, and suppressing the rule is almost always a bug waiting to happen. In development, Strict Mode runs setup, cleanup, setup for every effect once, to prove that your cleanup actually undoes your setup.

**What an effect is for.** Synchronising with something React does not control: subscribing to a WebSocket, starting a timer, measuring a DOM node, integrating a non-React widget, logging a page view. Not for: computing values from props or state (compute them during render), reacting to a user event (do it in the handler), resetting state when a prop changes (use `key`, see item 6.2), or, in most applications, fetching data (use a library built for it, item 6.7). The official page "You Might Not Need an Effect" lists the cases; read it once a year.

**The race in naive fetching.** An effect that fetches on `customerId` change issues one request per change, but responses may arrive in any order, and the last one to arrive wins the state. The cleanup is the fix: either abort the request or set a flag so a superseded response is ignored.

**`useRef`** returns `{ current }` that persists across renders. Writing to it does not trigger a render, so it is for values that the UI does not display: a DOM node (`ref={inputRef}`), an interval id, the latest version of a callback, "did this already run". Do not read or write `ref.current` during render; do it in effects and handlers.

**`useMemo` and `useCallback`** cache a value or a function between renders until a dependency changes. `useCallback(fn, deps)` is `useMemo(() => fn, deps)`. They have two legitimate uses: skipping a genuinely expensive computation, and keeping an object or function identity stable so that a `memo` child or an effect dependency does not fire on every render. React may throw the cache away, so they are performance hints, never correctness tools. Default to not using them.

**Custom hooks** are functions whose name starts with `use` and that call other hooks. They share *logic*, not state: each component that calls `useDebouncedValue(search, 300)` gets its own state and effects. Extracting a hook is how you give an effect a name and a single home. The rules of hooks (call them at the top level, in the same order every render, only from components or other hooks) exist because React identifies each hook call by its position.

## Example: a fetch with a stale-response bug, then fixed

```tsx
import { useEffect, useState } from "react";

interface Customer {
  id: string;
  name: string;
}

function CustomerDetails({ customerId }: { customerId: string }) {
  const [customer, setCustomer] = useState<Customer | null>(null);

  useEffect(() => {
    fetch(`/api/customers/${customerId}`)
      .then((response) => response.json())
      .then((loadedCustomer: Customer) => setCustomer(loadedCustomer));
  }, [customerId]);

  if (customer === null) {
    return <p>Loading...</p>;
  }
  return <h1>{customer.name}</h1>;
}
```

The user clicks customer 7 (a slow request, say 2 seconds) and then customer 8 (fast, 100 ms). Customer 8 appears. Two seconds later customer 7's response arrives and `setCustomer` overwrites the state: the heading now shows customer 7 while the prop, the URL and the user all say 8. Three further defects hide in the same code: a non-2xx response is parsed as if it were a customer, a network error is an unhandled rejection, and the old customer stays on screen while the new one loads.

The corrected version aborts the superseded request in the cleanup:

```tsx
function CustomerDetails({ customerId }: { customerId: string }) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const abortController = new AbortController();
    setCustomer(null);
    setError(null);

    fetch(`/api/customers/${customerId}`, { signal: abortController.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((loadedCustomer: Customer) => setCustomer(loadedCustomer))
      .catch((caught: Error) => {
        if (caught.name !== "AbortError") {
          setError(caught);
        }
      });

    return () => abortController.abort();
  }, [customerId]);

  if (error !== null) {
    return <p role="alert">{error.message}</p>;
  }
  if (customer === null) {
    return <p>Loading...</p>;
  }
  return <h1>{customer.name}</h1>;
}
```

When `customerId` changes from 7 to 8, React runs the cleanup for the 7 effect (aborting that request) before running the setup for 8. The late response can no longer arrive; if the server does not support cancellation, the equivalent is a `let ignore = false` flag set to `true` in the cleanup and checked before every `set` call. Strict Mode's setup-cleanup-setup cycle now also behaves: the first request is aborted, the second completes.

This is thirty lines for one request with no caching, no retry and no deduplication across components. That is the argument for a data-fetching library (item 6.7), which does exactly this, plus the rest, behind one hook.

## Pitfalls

- An object or array literal, or an inline function, in the dependency array. It is a new reference every render, so the effect runs every render. Depend on the primitive fields, move the construction inside the effect, or memoise it.
- Suppressing `exhaustive-deps` to "run once". The effect then captures stale props and state forever. If something must run once per mount and never again, it is usually not an effect at all (a lazy initialiser, or application start-up code outside React).
- A `setInterval` in an effect without cleanup. Every re-mount adds another interval; the symptom is a counter that speeds up after navigating away and back. Return `() => clearInterval(id)`.
- Setting state in an effect based on other state. The chain renders two or three times and is a sign that the second value should be derived during render.
- Reading `ref.current` during render to decide what to show. Changing a ref does not re-render, so the UI will not update when the value changes. If the UI depends on it, it is state.

## Check yourself

1. Why does `setCount(count + 1)` three times produce `count + 1`, and what does that reveal about what `count` is inside a render?
2. In the fixed example, exactly when does React call `abortController.abort()` relative to the next request being sent? Why does the order matter for the race?
3. A component derives `fullName` from `firstName` and `lastName` with `useState` plus `useEffect`. How many renders does one keystroke cause, and what is the one-line replacement?
4. An effect subscribes to `window.resize` and reads `props.onResize` inside the listener. Without `onResize` in the dependency array, which version of the callback runs after the parent re-renders with a new one? Name two ways to fix it.

## Go deeper

- [react.dev: You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect) · the catalogue of effects that should be plain code, with before and after versions.
- [react.dev: Synchronizing with Effects](https://react.dev/learn/synchronizing-with-effects) · the lifecycle, cleanup, Strict Mode's double run, and the fetch race with the `ignore` flag.
- [react.dev: Removing Effect Dependencies](https://react.dev/learn/removing-effect-dependencies) · how to make the dependency array honest without disabling the linter.
- [Dan Abramov: A Complete Guide to useEffect](https://overreacted.io/a-complete-guide-to-useeffect/) · long, from 2019, still the deepest treatment of closures, snapshots and dependencies.
- [react.dev: Reusing Logic with Custom Hooks](https://react.dev/learn/reusing-logic-with-custom-hooks) · when to extract a hook and what it does and does not share.

---

Part of [JavaScript & Frontend](../README.md) · items 6.4, 6.5
