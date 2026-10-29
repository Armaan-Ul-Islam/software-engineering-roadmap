# Rendering strategies: CSR, SSR, SSG and React Server Components

> **In one sentence:** The question is where HTML gets produced and when: in the browser after the JavaScript arrives (client-side rendering), on a server per request (server-side rendering, followed by hydration in the browser), at build time (static generation), or, with React Server Components, on the server for components that never ship to the browser at all, mixed with client components that do; each option trades time to first content, server cost and complexity differently.

**Why it matters:** A backend developer meets this choice at the architecture meeting: "should the new frontend be a SPA on the CDN talking to our Spring API, or a Next.js app?" The answer changes where business logic runs, which process talks to the database, how authentication works and what the operations team deploys. Interviewers ask about hydration and Server Components because people who have only read the marketing get them wrong.

## The idea

**Client-side rendering (CSR).** The server sends an almost empty `index.html` plus a JavaScript bundle. The browser downloads and runs the bundle, which fetches data from the API and renders the DOM. First content appears only after HTML, JavaScript and the first API round trip have all completed in sequence. This is the Vite plus React SPA from item 7.1: trivial to host (static files on any CDN or inside Spring Boot's static resources, see item 8.1), one backend to secure, and a poor LCP on slow devices and an empty page for crawlers that do not execute JavaScript.

**Server-side rendering (SSR).** A Node server runs the React components per request, calls `renderToString` (or the streaming `renderToPipeableStream`) and sends complete HTML. The browser paints immediately, then downloads the same components as JavaScript and **hydrates**: React walks the existing DOM, attaches event handlers and takes over. Until hydration finishes, the page is visible but not interactive. SSR improves LCP and crawlability at the cost of a Node process in the request path, double execution of every component (server and client), and a new class of bug, the hydration mismatch, when the server's HTML differs from the client's first render (a timestamp, `window.innerWidth`, a `Math.random()`).

**Static site generation (SSG).** SSR at build time: every page is rendered to an HTML file once and served from a CDN. Perfect for content that changes with a deploy (documentation, marketing), useless for a per-user dashboard. Incremental variants regenerate a page in the background after it goes stale.

**React Server Components (RSC).** A different split. A **Server Component** runs only on the server (per request or at build), may be `async`, may read the database or the file system directly, and its output is sent to the client as a serialised tree, not as JavaScript; its code and its dependencies never reach the bundle. A **Client Component** (a file starting with `"use client"`) is ordinary React: shipped to the browser, hydrated, may use `useState` and event handlers. Server Components can render Client Components and pass them serialisable props; Client Components cannot import Server Components. The result is that a page's data access, markdown rendering, date formatting and heavy libraries can stay on the server while only the interactive islands ship JavaScript. RSC is a React feature, but it needs a framework with a bundler integration to use; Next.js's App Router is the mainstream implementation.

**Next.js at a glance.** A React framework that gives you file-based routing, SSR, SSG, streaming, Server Components, server actions (functions marked `"use server"` that the client can call as form actions) and an image component, with a Node (or edge) runtime that must be deployed. For a team with a Spring backend, the honest question is whether the Node layer is a backend-for-frontend you want (it can hold the session, call Spring with a service token, and render pages with data in one hop) or a second backend you did not ask for.

| Strategy | HTML produced | Needs Node at request time | Interactive after | Fits |
|---|---|---|---|---|
| CSR | in the browser | no | bundle plus API responses | internal tools, dashboards behind login |
| SSR | per request on the server | yes | hydration | public pages with per-request data |
| SSG | at build time | no | hydration | content that changes per deploy |
| RSC | server components on the server, client components hydrated | yes (or at build) | hydration of client components only | content-heavy pages with a few interactive parts |

## Example: what the server actually sends

A component rendered to a string with `react-dom/server`:

```tsx
import { renderToString } from "react-dom/server";
import { Counter } from "./Counter.tsx";

const html = renderToString(<Counter step={5} />);
console.log(html);
```

With React 19.3:

```text
<div><p>Count: <!-- -->0</p><button>Increase</button></div>
```

That is what a CSR page lacks on first paint and what an SSR page has. Note what is missing: there is no `onClick` in the HTML. The button does nothing until the client bundle loads and `hydrateRoot(container, <Counter step={5} />)` runs; the `<!-- -->` comment marks a text boundary so hydration can match "Count: " and "0" as separate text nodes. If the client rendered `Count: 1` on first render (say, from `localStorage`), React would log a hydration mismatch and, in React 18 and later, re-render that subtree on the client.

The same component as a Server Component is not possible as written, because `useState` and `onClick` require the browser. The RSC version splits it:

```tsx
// OrderSummary.tsx: a Server Component (no directive needed; this is the default in the App Router)
import { CancelButton } from "./CancelButton.tsx";

export default async function OrderSummary({ orderId }: { orderId: string }) {
  const order = await orderRepository.findById(orderId);
  return (
    <section>
      <h1>Order {order.id}</h1>
      <p>{formatCurrency(order.amount, order.currency)}</p>
      <CancelButton orderId={order.id} />
    </section>
  );
}
```

```tsx
// CancelButton.tsx: a Client Component
"use client";
import { useState } from "react";

export function CancelButton({ orderId }: { orderId: string }) {
  const [pending, setPending] = useState(false);
  return <button disabled={pending} onClick={() => { setPending(true); cancelOrder(orderId); }}>Cancel</button>;
}
```

`orderRepository` and `formatCurrency` (and whatever currency library it pulls in) exist only on the server; the browser receives the rendered `<h1>` and `<p>` plus the code for `CancelButton`. The `orderId` prop crosses the boundary because it is a string; a database connection or a function could not.

## Pitfalls

- Choosing SSR for an internal application behind a login. Nobody crawls it, users are on fast office machines, and you have added a Node tier to deploy, monitor and secure. CSR on a CDN or inside Spring Boot is simpler.
- Hydration mismatches from time, locale or viewport. Render the same thing on both sides on the first pass, then update in an effect; or mark the subtree with `suppressHydrationWarning` only when the difference is harmless.
- Treating the SSR server as stateless when it holds cookies and tokens. It is now part of your authentication perimeter and talks to Spring on the user's behalf; secure it like a backend-for-frontend (see item 8.3).
- Putting secrets in a component that turns out to be a Client Component. Anything imported into a `"use client"` file ships to the browser. Keep database access and keys in Server Components or server actions, and use the framework's lint rules that flag server-only imports.
- Assuming Server Components remove the need for an API. The browser still needs an endpoint for interactive updates, and other clients (mobile, partners) still need the Spring API. RSC moves page composition, not the API.
- Measuring only time to first byte. SSR improves first paint and can worsen time to interactive if the bundle is unchanged, because the user now sees buttons that do nothing for two seconds.
- Static generation for pages that depend on who is logged in. The build has no user; such pages must be SSR or CSR.

## Check yourself

1. Describe the sequence of network requests before a user sees content on a CSR page versus an SSR page, and name the metric from item 4.6 that each sequence most affects.
2. What is hydration, what must be true of the server HTML and the client's first render for it to succeed, and what does React do when it is not?
3. A colleague proposes moving `orderRepository.findById` into a component so "React can just read the database". Under which rendering model is that legitimate, and what must be true of the file?
4. Your product is an internal CRM with a Spring backend. Argue for CSR, then argue for Next.js with Server Components, and say which fact about the users would decide it.

## Go deeper

- [react.dev: Server Components](https://react.dev/reference/rsc/server-components) · the definition, what can cross the boundary, and the `"use client"` rule.
- [Next.js: Learn](https://nextjs.org/learn) · the official course; the App Router chapters show RSC, streaming and server actions in one application.
- [react.dev: Quick Start](https://react.dev/learn) · the page on creating a React app states React's own view on when a framework is appropriate.
- [web.dev: Web Vitals](https://web.dev/articles/vitals) · the metrics that decide whether the rendering choice mattered.

---

Part of [JavaScript & Frontend](../README.md) · item 6.10
