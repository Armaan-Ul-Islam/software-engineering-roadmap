# JavaScript & Frontend

> What a backend developer needs from the other side: the JavaScript language and its runtime model, TypeScript, Node.js, how browsers work, enough HTML and CSS to be useful, React fundamentals, and wiring a frontend to a Spring API without fighting CORS and authentication.

**Prerequisites:** [Web & HTTP](../02-web-and-http/README.md), [Foundations](../01-foundations/README.md)

**Done when you can:**

- Explain the event loop, microtasks and macrotasks, and predict the output order of a snippet mixing Promises and `setTimeout`.
- Read and write modern JavaScript and TypeScript fluently: modules, closures, async/await, generics, narrowing.
- Build and debug a small Node.js service, and say precisely when Node is and is not a good fit compared with the JVM.
- Explain how a browser turns HTML, CSS and JavaScript into pixels, and what makes a page slow.
- Build a React app with hooks and data fetching that talks to a Spring Boot API, with CORS and authentication done correctly.
- Review a frontend pull request for what matters: state handling, effects, keys, accessibility basics, bundle size.

## Roadmap

### 1. The JavaScript language

- [ ] 1.1 Values and types: primitives vs objects, dynamic typing, coercion, `==` vs `===`, truthiness, `NaN`, `typeof` quirks · [javascript.info: Data types](https://javascript.info/types) · [MDN: JavaScript data types and data structures](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Data_structures)
- [ ] 1.2 Variables and scope: `let`/`const`/`var`, block scope, hoisting, the temporal dead zone, closures · [javascript.info: Variable scope, closure](https://javascript.info/closure) · [You Don't Know JS Yet: Scope & Closures](https://github.com/getify/You-Dont-Know-JS/blob/2nd-ed/scope-closures/README.md)
- [ ] 1.3 Functions and `this`: call-site binding, arrow functions, `call`/`apply`/`bind`, methods vs functions · [javascript.info: Object methods, "this"](https://javascript.info/object-methods)
- [ ] 1.4 Objects, prototypes and classes: the prototype chain, `class` as syntax over prototypes, getters and setters, private fields · [javascript.info: Prototypes, inheritance](https://javascript.info/prototypes) · [MDN: Inheritance and the prototype chain](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Inheritance_and_the_prototype_chain)
- [ ] 1.5 Arrays and immutability: `map`/`filter`/`reduce`, spread and rest, destructuring, optional chaining, `structuredClone` · [javascript.info: Array methods](https://javascript.info/array-methods)
- [ ] 1.6 Asynchrony: callbacks, Promises, `async`/`await`, error handling, `Promise.all`/`allSettled`/`race`/`any`, unhandled rejections · [javascript.info: Promises, async/await](https://javascript.info/async)
- [ ] 1.7 The event loop: call stack, task queue, microtask queue, rendering steps; the same model in Node with its phases · [Philip Roberts: What the heck is the event loop anyway?](https://www.youtube.com/watch?v=8aGhZQkoFbQ) · [Jake Archibald: Tasks, microtasks, queues and schedules](https://jakearchibald.com/2015/tasks-microtasks-queues-and-schedules/) · [Jake Archibald: In The Loop](https://www.youtube.com/watch?v=cCOL7MC4Pl0)
- [ ] 1.8 Modules: ES modules vs CommonJS, named and default exports, dynamic `import()`, the dual-package problem · [javascript.info: Modules](https://javascript.info/modules) · [Node.js: ECMAScript modules](https://nodejs.org/api/esm.html)
- [ ] 1.9 Iterators, generators, `Symbol`, `Map`/`Set`/`WeakMap`, `Proxy` at a glance · [javascript.info: Generators, advanced iteration](https://javascript.info/generators-iterators)
- [ ] 1.10 Errors: `Error` subclasses, `cause`, stack traces across async boundaries · [MDN: Error](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Error)
- [ ] 1.11 Dates, numbers and strings: `Intl`, the coming `Temporal` API, floating point, Unicode and string length surprises · [MDN: Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl) · [TC39: Temporal](https://tc39.es/proposal-temporal/docs/)

### 2. TypeScript essentials

- [ ] 2.1 Why TypeScript: structural typing, inference, `strict` mode, and what the compiler cannot check at runtime · [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) · [Total TypeScript Essentials](https://www.totaltypescript.com/books/total-typescript-essentials)
- [ ] 2.2 Types vs interfaces, unions and discriminated unions, narrowing, literal types, `unknown` vs `any`, `never` · [Handbook: Narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html)
- [ ] 2.3 Generics, utility types (`Partial`, `Pick`, `Record`, `ReturnType`), mapped and conditional types at a glance · [Handbook: Generics](https://www.typescriptlang.org/docs/handbook/2/generics.html) · [Handbook: Utility Types](https://www.typescriptlang.org/docs/handbook/utility-types.html)
- [ ] 2.4 Validating at the boundary: schema libraries (Zod, Valibot), types generated from OpenAPI, sharing DTO shapes with the backend · [Zod](https://zod.dev/) · [openapi-typescript](https://openapi-ts.dev/)
- [ ] 2.5 The `tsconfig` settings that matter: `strict`, `target`, `module`, `moduleResolution`, `noUncheckedIndexedAccess`; `tsc` for checking, a bundler for building · [TSConfig Reference](https://www.typescriptlang.org/tsconfig/)

### 3. Node.js

- [ ] 3.1 The runtime model: V8, libuv, one event loop thread, non-blocking I/O, the thread pool; CPU work vs I/O work · [Node.js: The Node.js Event Loop](https://nodejs.org/en/learn/asynchronous-work/event-loop-timers-and-nexttick) · [Node.js: Don't Block the Event Loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop)
- [ ] 3.2 npm and `package.json`: scripts, dependencies vs devDependencies, semver ranges, lockfiles, `npx`, workspaces; pnpm and Yarn · [npm docs: package.json](https://docs.npmjs.com/cli/v10/configuring-npm/package-json) · [Semantic Versioning](https://semver.org/)
- [ ] 3.3 Core modules: `fs`, `path`, `http`, `events`, `stream`, `crypto`, `worker_threads`, `child_process`; streams and backpressure · [Node.js API documentation](https://nodejs.org/api/) · [Node.js: Stream](https://nodejs.org/api/stream.html)
- [ ] 3.4 Building an HTTP API: Express or Fastify, middleware, routing, validation, error handling, graceful shutdown · [Express](https://expressjs.com/) · [Fastify](https://fastify.dev/)
- [ ] 3.5 Configuration, structured logging (pino), environment variables, process managers, Docker images for Node · [pino](https://getpino.io/) · [Docker: Node.js language-specific guide](https://docs.docker.com/guides/nodejs/)
- [ ] 3.6 Testing: Vitest or Jest, the built-in `node:test` runner, HTTP tests with supertest · [Vitest](https://vitest.dev/) · [Node.js: Test runner](https://nodejs.org/api/test.html)
- [ ] 3.7 Debugging and profiling: `--inspect`, Chrome DevTools, CPU profiles, finding memory leaks in long-running processes · [Node.js: Debugging](https://nodejs.org/en/learn/getting-started/debugging)
- [ ] 3.8 Node vs the JVM for a service: concurrency model, I/O vs CPU throughput, ecosystem, operational maturity · [Node.js Design Patterns](https://www.nodejsdesignpatterns.com/)
- [ ] 3.9 The wider runtime landscape: Deno, Bun, edge runtimes; what they change and what they do not · [Bun](https://bun.sh/) · [Deno](https://deno.com/)

### 4. The browser platform

- [ ] 4.1 How browsers render: parsing, DOM and CSSOM, render tree, layout, paint, compositing; reflow vs repaint · [web.dev: How browsers work](https://web.dev/articles/howbrowserswork) · [web.dev: Rendering performance](https://web.dev/articles/rendering-performance)
- [ ] 4.2 The critical rendering path; script loading with `defer`, `async` and modules; resource hints · [web.dev: Understanding the critical path](https://web.dev/learn/performance/understanding-the-critical-path)
- [ ] 4.3 The DOM and events: selection and mutation, propagation (capture, target, bubble), delegation, passive listeners · [javascript.info: Introduction to browser events](https://javascript.info/introduction-browser-events) · [javascript.info: Bubbling and capturing](https://javascript.info/bubbling-and-capturing)
- [ ] 4.4 Network from the browser: `fetch`, `AbortController`, streaming responses, `FormData`, cookies vs `Authorization` headers, CORS in practice · [MDN: Using the Fetch API](https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch)
- [ ] 4.5 Storage: cookies, `localStorage`/`sessionStorage`, IndexedDB, the Cache API; what to store where · [MDN: Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API)
- [ ] 4.6 Web performance: Core Web Vitals (LCP, INP, CLS), bundle size, code splitting, lazy loading, image optimisation · [web.dev: Web Vitals](https://web.dev/articles/vitals) · [web.dev: Learn Performance](https://web.dev/learn/performance)
- [ ] 4.7 Security in the browser: XSS, CSP, CSRF, clickjacking, and the frontend side of authentication (details in Security) · [OWASP: Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [ ] 4.8 DevTools fluency: Elements, Console, Network, Performance, Application · [Chrome DevTools documentation](https://developer.chrome.com/docs/devtools)
- [ ] 4.9 Accessibility basics: semantic HTML, keyboard navigation, labels, ARIA only when needed, colour contrast · [web.dev: Learn Accessibility](https://web.dev/learn/accessibility) · [MDN: Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility)

### 5. HTML and CSS for backend developers

- [ ] 5.1 Semantic HTML, forms and built-in validation, document structure · [web.dev: Learn HTML](https://web.dev/learn/html) · [MDN: HTML](https://developer.mozilla.org/en-US/docs/Web/HTML)
- [ ] 5.2 CSS fundamentals: the cascade, specificity, inheritance, the box model, units, custom properties · [web.dev: Learn CSS](https://web.dev/learn/css) · [MDN: CSS](https://developer.mozilla.org/en-US/docs/Web/CSS)
- [ ] 5.3 Layout: Flexbox and Grid; responsive design with media and container queries · [Josh Comeau: An Interactive Guide to Flexbox](https://www.joshwcomeau.com/css/interactive-guide-to-flexbox/) · [Josh Comeau: An Interactive Guide to CSS Grid](https://www.joshwcomeau.com/css/interactive-guide-to-grid/) · [Flexbox Froggy](https://flexboxfroggy.com/) · [Grid Garden](https://cssgridgarden.com/)
- [ ] 5.4 Styling approaches: plain CSS and CSS Modules, Tailwind, CSS-in-JS; component libraries; design tokens · [Tailwind CSS](https://tailwindcss.com/docs)

### 6. React

- [ ] 6.1 The mental model: UI as a function of state, components and JSX, props vs state, one-way data flow · [react.dev: Quick Start](https://react.dev/learn) · [react.dev: Thinking in React](https://react.dev/learn/thinking-in-react)
- [ ] 6.2 Rendering: render vs commit, reconciliation and keys, what triggers a re-render, `memo`, and when optimisation is premature · [Mark Erikson: A (Mostly) Complete Guide to React Rendering Behavior](https://blog.isquaredsoftware.com/2020/05/blogged-answers-a-mostly-complete-guide-to-react-rendering-behavior/) · [react.dev: Render and Commit](https://react.dev/learn/render-and-commit)
- [ ] 6.3 State: `useState`, `useReducer`, lifting state up, deriving instead of duplicating, immutable updates · [react.dev: Managing State](https://react.dev/learn/managing-state)
- [ ] 6.4 Effects: `useEffect` semantics, dependencies, cleanup, and the "you might not need an effect" rule · [react.dev: You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect) · [Dan Abramov: A Complete Guide to useEffect](https://overreacted.io/a-complete-guide-to-useeffect/)
- [ ] 6.5 Other hooks and patterns: `useRef`, `useMemo`/`useCallback`, `useContext`, custom hooks, composition · [react.dev: Reusing Logic with Custom Hooks](https://react.dev/learn/reusing-logic-with-custom-hooks)
- [ ] 6.6 Forms: controlled vs uncontrolled inputs, validation, React Hook Form · [React Hook Form](https://react-hook-form.com/)
- [ ] 6.7 Data fetching and server state: TanStack Query (caching, invalidation, mutations), loading and error states, optimistic updates · [TanStack Query](https://tanstack.com/query/latest) · [TkDodo: Practical React Query](https://tkdodo.eu/blog/practical-react-query)
- [ ] 6.8 Routing and application structure: React Router, code splitting, feature folders · [React Router](https://reactrouter.com/)
- [ ] 6.9 Client state management: the limits of Context, Zustand, Redux Toolkit; choosing by scale · [Zustand](https://zustand.docs.pmnd.rs/) · [Redux Toolkit](https://redux-toolkit.js.org/) · [Redux Style Guide](https://redux.js.org/style-guide/)
- [ ] 6.10 Rendering strategies and frameworks: CSR vs SSR vs SSG, React Server Components, Next.js at a glance · [react.dev: Server Components](https://react.dev/reference/rsc/server-components) · [Next.js: Learn](https://nextjs.org/learn)
- [ ] 6.11 Testing React: React Testing Library with Vitest, Playwright for end-to-end · [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/) · [Playwright](https://playwright.dev/)

### 7. Tooling and the build

- [ ] 7.1 Vite: dev server, hot module replacement, proxying API calls to a backend, environment variables, production builds · [Vite Guide](https://vite.dev/guide/)
- [ ] 7.2 What bundlers and transpilers do: the ESM graph, tree shaking, code splitting, source maps, polyfills and browserslist · [Vite: Why Vite](https://vite.dev/guide/why)
- [ ] 7.3 Linting and formatting: ESLint flat config, Prettier or Biome; type-checking in CI · [ESLint](https://eslint.org/docs/latest/) · [Biome](https://biomejs.dev/)

### 8. Frontend meets Spring backend

- [ ] 8.1 Serving options: same origin (static resources from Spring Boot) vs separate hosting behind a reverse proxy or CDN · [Spring Boot: Static Content](https://docs.spring.io/spring-boot/reference/web/servlet.html#web.servlet.spring-mvc.static-content)
- [ ] 8.2 CORS between a Vite dev server and Spring, and in production; the proxy alternative · [Vite: server.proxy](https://vite.dev/config/server-options.html#server-proxy) · [Spring: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [ ] 8.3 Authentication from a SPA: session cookie with CSRF token vs OAuth2 Authorization Code with PKCE (ideally through a BFF); where tokens live · [Spring Security: CSRF with JavaScript SPAs](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html#csrf-integration-javascript-spa) · [IETF: OAuth 2.0 for Browser-Based Apps](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps)
- [ ] 8.4 Contracts: OpenAPI-generated TypeScript clients, handling Problem Details errors, pagination and dates over JSON · [openapi-typescript](https://openapi-ts.dev/) · [RFC 9457: Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html)
- [ ] 8.5 Deploying a frontend: build artifacts, cache headers for fingerprinted files, environment-specific configuration, SPA fallback routing · [web.dev: HTTP cache](https://web.dev/articles/http-cache)

## Resources

### Start here

- [javascript.info: The Modern JavaScript Tutorial](https://javascript.info/) · the best free, complete and current JavaScript course; part 1 covers section 1.
- [react.dev: Learn React](https://react.dev/learn) · the official tutorial, rewritten around hooks; read it in order.
- [Node.js: Learn](https://nodejs.org/en/learn) · the official guides, especially the asynchronous work section.
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) · short enough to read end to end.
- [Full Stack Open](https://fullstackopen.com/en/) · University of Helsinki's free course: React, Node, TypeScript, testing and more, with exercises.

### Books

- [Eloquent JavaScript](https://eloquentjavascript.net/) · Marijn Haverbeke; free online, thoughtful and precise.
- [You Don't Know JS Yet](https://github.com/getify/You-Dont-Know-JS) · Kyle Simpson; free on GitHub, the deep dive into scope, closures and `this`.
- [JavaScript: The Definitive Guide, 7th edition](https://www.oreilly.com/library/view/javascript-the-definitive/9781491952016/) · David Flanagan; the reference (paid).
- [Effective TypeScript](https://effectivetypescript.com/) · Dan Vanderkam; 83 specific ways to improve your TypeScript (paid).
- [Node.js Design Patterns](https://www.nodejsdesignpatterns.com/) · Casciaro and Mammino (paid).

### Courses and videos

- [Philip Roberts: What the heck is the event loop anyway?](https://www.youtube.com/watch?v=8aGhZQkoFbQ) · 26 minutes that fix the mental model for good.
- [Jake Archibald: In The Loop](https://www.youtube.com/watch?v=cCOL7MC4Pl0) · the browser event loop including rendering.
- [web.dev: Learn](https://web.dev/learn) · Google's free courses on HTML, CSS, performance, accessibility and more.
- [Frontend Masters](https://frontendmasters.com/) · high-quality workshops (paid).
- [Fireship](https://www.youtube.com/@Fireship) · fast, accurate overviews of tools and concepts.

### References

- [MDN Web Docs](https://developer.mozilla.org/) · the reference for JavaScript, HTML, CSS and web APIs.
- [Can I use](https://caniuse.com/) · browser support tables.
- [TkDodo's blog](https://tkdodo.eu/blog/) · the best writing on React Query and React patterns.
- [Josh Comeau](https://www.joshwcomeau.com/) · interactive explanations of CSS and React.
- [Lydia Hallie: JavaScript Visualized](https://www.lydiahallie.com/blog) · animated explanations of the event loop, promises and more.
- [roadmap.sh: JavaScript](https://roadmap.sh/javascript), [TypeScript](https://roadmap.sh/typescript), [Node.js](https://roadmap.sh/nodejs), [React](https://roadmap.sh/react), [Frontend](https://roadmap.sh/frontend) · visual overviews.
