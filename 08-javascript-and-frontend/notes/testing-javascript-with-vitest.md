# Testing JavaScript with Vitest

> **In one sentence:** Vitest runs your tests through the same Vite pipeline that builds your code, so TypeScript, JSX and ES modules need no extra configuration; you test pure functions directly, HTTP handlers through the app object without opening a port, and React components through Testing Library by what the user sees and does, while Playwright drives a real browser for the few flows that must work end to end.

**Why it matters:** The JavaScript test ecosystem has three runners with nearly the same API (Jest, Vitest, `node:test`), two mocking styles that look alike and behave differently, and a strong convention in React testing (query by role, not by CSS class) that reviewers enforce. Knowing which layer a test belongs to, and which tool fits that layer, is the difference between a suite that catches regressions in a second and one that nobody runs.

## The idea

**Runners.** Jest is the incumbent; it ships its own transformer and module system, which is why TypeScript, ESM and JSX in Jest each need configuration. Vitest reuses Vite's transform, so a project that builds with Vite tests with zero configuration, and the API is deliberately Jest-compatible (`describe`, `it`, `expect`, `vi` in place of `jest`). Node's built-in `node:test` runner (`node --test`) needs no dependency at all and is a good fit for a small service with plain JavaScript; it lacks the ecosystem (component testing, coverage UI, watch mode polish). For a new project the pragmatic default is Vitest for anything with a build step and `node:test` for small scripts.

**Three layers, three techniques.**

| Layer | What you test | Tool |
|---|---|---|
| Pure logic | functions in, values out | `expect`, `vi.fn()` for collaborators |
| HTTP boundary | routes, validation, status codes, error bodies | Fastify's `app.inject()`, or `supertest` for any Node server |
| UI | what a user sees and can do | Testing Library (`render`, `screen`, `userEvent`) under jsdom |
| Whole system | login, checkout, the three flows that pay the bills | Playwright against a running app |

**Mocking.** `vi.fn()` creates a function that records calls and returns what you tell it (`mockResolvedValue`). `vi.spyOn(object, "method")` wraps an existing method. `vi.mock("./module")` replaces a whole module for the test file and is hoisted above the imports, which surprises people; prefer passing collaborators as parameters so you can hand in a `vi.fn()` without module mocking at all. Fake timers (`vi.useFakeTimers()`) control `setTimeout` and `Date`, and `await vi.runAllTimersAsync()` also flushes the promise callbacks that real timers would have triggered (see item 1.7).

**Testing Library's rule.** Query the DOM the way a user or a screen reader would: `getByRole("button", { name: "Increase" })`, `getByLabelText("Email")`, `getByText`. `getBy` throws when nothing matches, `queryBy` returns `null` (for asserting absence), `findBy` waits for an element to appear. Interact with `userEvent`, which fires the same sequence of events a real click or keystroke does. A test that reaches for `container.querySelector(".btn-primary")` is coupled to styling and will not catch a button that is unreachable by keyboard.

**Playwright.** It launches Chromium, Firefox or WebKit, runs a script against a real page, and auto-waits for elements and navigations. Each end-to-end test costs seconds, so keep a handful for the critical paths and put everything else in the layers above.

## Example: one suite, three layers

The Fastify app under test is the orders API from item 3.4; it exports `buildApp()` without calling `listen`.

```javascript
// src/price.js
export function totalWithDiscount(lines, discountPercent) {
  if (discountPercent < 0 || discountPercent > 100) {
    throw new RangeError(`discount out of range: ${discountPercent}`);
  }
  const subtotal = lines.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0);
  return Math.round(subtotal * (100 - discountPercent)) / 100;
}

export async function fetchExchangeRate(client, currency) {
  const response = await client.get(`/rates/${currency}`);
  return response.rate;
}
```

```javascript
// src/price.test.js
import { describe, expect, it, vi } from "vitest";
import { fetchExchangeRate, totalWithDiscount } from "./price.js";

describe("totalWithDiscount", () => {
  it("applies the discount to the subtotal", () => {
    const lines = [{ unitPrice: 10, quantity: 2 }, { unitPrice: 5.5, quantity: 1 }];
    expect(totalWithDiscount(lines, 10)).toBe(22.95);
  });

  it("rejects an impossible discount", () => {
    expect(() => totalWithDiscount([], 120)).toThrow(RangeError);
  });
});

describe("fetchExchangeRate", () => {
  it("asks the client for the currency and unwraps the rate", async () => {
    const client = { get: vi.fn().mockResolvedValue({ rate: 11.4 }) };
    await expect(fetchExchangeRate(client, "NOK")).resolves.toBe(11.4);
    expect(client.get).toHaveBeenCalledWith("/rates/NOK");
  });
});
```

```javascript
// src/orders.test.js
import { afterAll, beforeAll, expect, it } from "vitest";
import { buildApp } from "../server.mjs";

const app = buildApp();
beforeAll(() => app.ready());
afterAll(() => app.close());

it("creates an order and reads it back", async () => {
  const created = await app.inject({ method: "POST", url: "/api/orders", payload: { customerId: "c-1", amount: 42.5 } });
  expect(created.statusCode).toBe(201);
  expect(created.json()).toEqual({ id: "1", customerId: "c-1", amount: 42.5 });
});

it("rejects an invalid body before the handler runs", async () => {
  const response = await app.inject({ method: "POST", url: "/api/orders", payload: { customerId: "", amount: -1 } });
  expect(response.statusCode).toBe(400);
  expect(response.json().detail).toMatch(/customerId/);
});
```

`inject` builds a request and runs it through the whole Fastify pipeline (hooks, validation, handler, serialisation) in memory. For Express or a raw `http.Server`, `supertest` does the same by binding an ephemeral port: `await request(app.server).get("/api/orders/99").expect(404)`.

```jsx
// src/Counter.test.jsx
// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { Counter } from "./Counter.jsx";

it("increases by the step when the button is clicked", async () => {
  const user = userEvent.setup();
  render(<Counter step={5} />);

  await user.click(screen.getByRole("button", { name: "Increase" }));

  expect(screen.getByText("Count: 5")).toBeInTheDocument();
});
```

`toBeInTheDocument` comes from `@testing-library/jest-dom`, imported once in a setup file (`import "@testing-library/jest-dom/vitest"`), which is listed under `test.setupFiles` in `vitest.config.js`. The `@vitest-environment jsdom` comment switches that one file to a DOM environment; a frontend project sets `environment: "jsdom"` globally instead.

```bash
npx vitest run --reporter=verbose
```

```text
 RUN  v5.0.5 /Users/armaan/lab
 ✓ src/price.test.js > totalWithDiscount > applies the discount to the subtotal 1ms
 ✓ src/price.test.js > totalWithDiscount > rejects an impossible discount 0ms
 ✓ src/price.test.js > fetchExchangeRate > asks the client for the currency and unwraps the rate 1ms
 ✓ src/orders.test.js > creates an order and reads it back 7ms
 ✓ src/orders.test.js > rejects an invalid body before the handler runs 1ms
 ✓ src/Counter.test.jsx > increases by the step when the button is clicked 58ms
 Test Files  3 passed (3)
      Tests  6 passed (6)
   Duration  431ms
```

When an assertion fails the diff is the thing to read, not the stack trace:

```text
 FAIL  src/price.test.js > totalWithDiscount > applies the discount to the subtotal
AssertionError: expected 22.95 to be 22.94 // Object.is equality

- Expected
+ Received

- 22.94
+ 22.95
```

`vitest` without `run` starts watch mode, which reruns only the files affected by a change; that is the mode to develop in.

## Pitfalls

- `toBe` on objects. `toBe` is `Object.is`, so two equal objects fail. Use `toEqual` (ignores `undefined` properties) or `toStrictEqual`.
- Forgetting `await` on an async assertion. `expect(promise).resolves.toBe(1)` without `await` passes before the promise settles and the failure is reported, if at all, against a later test. Lint rule `@vitest/eslint-plugin` catches it.
- `vi.mock` placed after imports and expected to run in order. It is hoisted; variables declared in the file are not visible inside its factory unless created with `vi.hoisted`.
- Shared module state between tests. Vitest isolates test files, not tests within a file: the `orders` map in the example persists across the two `it` blocks (which is why the second test does not assert on `id`). Reset state in `beforeEach` or build a fresh app per test.
- Asserting on implementation details in React tests: component state, a child's props, a CSS class. Rewrite the assertion as something a user could observe.
- `getByText` for a button with an icon and a label. `getByRole("button", { name })` matches the accessible name and also proves the element is a real button, not a clickable `div` (see item 4.9).
- Real network calls in unit tests. They are slow and flaky; inject the client or intercept with MSW at the fetch layer.
- Treating Playwright as the first line of defence. Hundreds of browser tests take an hour and fail for reasons unrelated to the change; keep them few and test behaviour in the cheaper layers.

## Check yourself

1. Why can `app.inject()` exercise schema validation and the error handler without a port, and what does `supertest` do differently?
2. A test using `vi.useFakeTimers()` advances time with `vi.advanceTimersByTime(1000)` but the `await`ed result never arrives. What is missing?
3. A reviewer rejects `screen.getByTestId("submit")` in favour of `getByRole("button", { name: "Submit" })`. What extra property does the second query verify?
4. Where would you put a test for "an expired session redirects to the login page", and why does the answer depend on where the redirect logic lives?

## Go deeper

- [Vitest](https://vitest.dev/) · the guide; Mocking and Test Environment are the chapters that answer most questions.
- [Node.js: Test runner](https://nodejs.org/api/test.html) · the zero-dependency alternative for small services.
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) · the guiding principles and the query priority list.
- [Playwright](https://playwright.dev/) · Getting Started and the Best Practices page on what deserves an end-to-end test.
- [Fastify](https://fastify.dev/) · the Testing guide, which documents `inject`.

---

Part of [JavaScript & Frontend](../README.md) · items 3.6, 6.11
