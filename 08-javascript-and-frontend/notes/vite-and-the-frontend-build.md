# Vite and the frontend build

> **In one sentence:** In development Vite serves your source files as native ES modules and swaps changed modules into the running page, while for production it bundles, tree-shakes, splits and fingerprints everything with Rollup; environment variables, the API proxy and source maps are where the two modes differ in ways that bite.

**Why it matters:** Backend developers meet the frontend build when it breaks: the API works in `vite dev` and 404s in production (the proxy was dev-only), a secret ends up in the bundle (`VITE_` means public), a 2 MB `index.js` loads on every page (no code splitting), or a stack trace in the error tracker points at line 1 of a minified file (no source maps). Each is a one-paragraph concept once the two modes are clear.

## The idea

**Development: no bundle.** `vite` starts a dev server that serves `index.html` and, when the browser requests `/src/main.tsx`, transforms that single file on demand (TypeScript and JSX are stripped by esbuild, which does not type-check) and returns it as an ES module. The browser follows the `import` graph and requests each module separately. Startup time is independent of application size because nothing is bundled up front. Third-party packages are the exception: Vite pre-bundles each dependency once with esbuild (converting CommonJS to ESM and collapsing packages with hundreds of internal files into one request) and caches the result in `node_modules/.vite`.

**Hot module replacement (HMR).** When a file changes, Vite pushes the new module over a WebSocket and the page replaces it in place without a reload. With `@vitejs/plugin-react`, React Fast Refresh re-renders the edited component while keeping its state, as long as the file exports only components.

**Production: one optimised graph.** `vite build` hands the same module graph to Rollup (Vite is moving to Rolldown, a Rust port with the same plugin interface; check which your version uses) and writes `dist/`: an `index.html` plus `assets/` files whose names contain a content hash, so that they can be cached forever and change their URL when their content changes (item 8.5). Along the way:

1. **Tree shaking** removes exports nothing imports. It depends on ESM's static structure, so CommonJS dependencies shake poorly, and a module with side effects at the top level cannot be dropped; the `sideEffects` field in a package's `package.json` tells the bundler which files are safe.
2. **Code splitting** turns every dynamic `import()` into a separate chunk loaded on demand, and shared dependencies into chunks of their own. `React.lazy` plus `Suspense` is the React-side idiom for route-level splitting. `build.rollupOptions.output.manualChunks` controls grouping when the defaults produce too many or too few files.
3. **Minification** with esbuild, and CSS extraction into hashed `.css` files.
4. **Source maps** map minified output back to source for error trackers and DevTools. `build.sourcemap: true` publishes them next to the bundle; `"hidden"` emits them without the reference comment so that you can upload them to Sentry or similar without serving them to users. Development always has them.
5. **Browser targets.** `build.target` sets the syntax level the output may use; the default is a modern baseline (in Vite 7, the Baseline Widely Available set of browsers). Vite does not read a `browserslist` configuration itself (tools like Autoprefixer do), and it adds no polyfills: supporting old browsers means `@vitejs/plugin-legacy`, which emits a second, transpiled bundle with polyfills.

**Environment variables.** Vite loads `.env`, `.env.local`, `.env.[mode]` and `.env.[mode].local` (`mode` is `development` for `vite` and `production` for `vite build`, or whatever `--mode staging` says). Only variables prefixed with `VITE_` are exposed to the browser code, as `import.meta.env.VITE_NAME`, and they are **replaced at build time** as string literals. Two consequences: anything `VITE_` is public and shipped to every user, so never put a secret there; and a value baked in at build time cannot change per deployment without rebuilding, which is why runtime configuration usually comes from an endpoint or an injected `window.__CONFIG__` instead (item 8.5). The built-ins `import.meta.env.MODE`, `DEV`, `PROD` and `BASE_URL` are always available.

**The proxy exists only in development.** `server.proxy` makes the dev server forward `/api` to your Spring Boot process so that the browser sees one origin (see item 8.2). `vite build` produces static files; nothing proxies anything in production. Same-origin serving or a reverse proxy has to be arranged there separately.

**Type-checking is a separate step.** Because esbuild strips types without checking them, a project compiles with type errors. The standard script is `"build": "tsc -b && vite build"`, and CI should run `tsc` even when it does not build.

## Example: a minimal configuration for a React app talking to a Spring API

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: "hidden",
  },
});
```

```bash
# .env.development
VITE_API_BASE_URL=/api

# .env.production
VITE_API_BASE_URL=https://api.example.com
```

```typescript
// src/vite-env.d.ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

```typescript
// src/api/baseUrl.ts
export const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;
```

In development, requests go to `/api/...` on the Vite origin and are proxied to Spring. In production, the literal `"https://api.example.com"` is written into the bundle, and the API must allow that origin with CORS, or you serve the frontend from the same origin and keep `/api`.

Route-level code splitting:

```tsx
import { lazy, Suspense } from "react";

const ReportsPage = lazy(() => import("./pages/ReportsPage"));

export function App() {
  return (
    <Suspense fallback={<p>Loading...</p>}>
      <ReportsPage />
    </Suspense>
  );
}
```

`vite build` now emits `assets/ReportsPage-[hash].js`, requested only when the component first renders. Run `vite build` and read the summary it prints: a chunk over about 500 kB triggers Vite's size warning and is the first candidate for splitting. `vite preview` serves `dist/` locally so that you can test the production build, proxy-free, before deploying.

## Pitfalls

- A secret in a `VITE_` variable. It is in the bundle, readable by anyone who opens DevTools. Secrets stay on the server; the frontend gets them indirectly through your API.
- The API works in development and fails after deployment. The proxy was doing the routing. Configure the reverse proxy or CORS for production, and test with `vite preview` behind the same setup.
- Type errors in production code. `vite build` succeeded because esbuild does not type-check; `tsc -b` was not in the script or CI.
- Importing a whole library for one function (`import _ from "lodash"` instead of `lodash-es` or a named import from an ESM build). CommonJS and side-effectful modules defeat tree shaking; check the bundle with a visualiser plugin before blaming the bundler.
- Caching `index.html` as aggressively as the hashed assets. Users keep an old `index.html` that references assets that no longer exist. Hashed files are immutable; `index.html` is not.
- Relying on `process.env` in browser code. That is Node's object; Vite exposes `import.meta.env`. Some libraries expect `process.env.NODE_ENV`, which Vite replaces, but your own code should not.
- Shipping source maps to users when they contain proprietary source. `"hidden"` gives the error tracker what it needs without serving them.

## Check yourself

1. Why does Vite's dev server start in a fraction of a second on a large application, and what work has it postponed to the moment you open a page?
2. A colleague sets `VITE_DATABASE_PASSWORD` to let the frontend "talk directly to the database". Explain precisely what happens to that value at `vite build`, and what the design should be instead.
3. The same build must run in staging and production with different API hosts. Give two ways to do that, and say which one requires a rebuild.
4. The error tracker shows `index-D3f8a1.js:1:48213` with no useful trace. What configuration is missing, and why would you not simply publish the source maps alongside the bundle?

## Go deeper

- [Vite Guide](https://vite.dev/guide/) · start with "Getting Started" and "Features"; the whole guide is short.
- [Vite: Why Vite](https://vite.dev/guide/why) · the dev-server-without-bundling idea and the dependency pre-bundling explained by its authors.
- [Vite: Env Variables and Modes](https://vite.dev/guide/env-and-mode) · the `VITE_` prefix, `.env` file precedence and the `ImportMetaEnv` typing.
- [Vite: Building for Production](https://vite.dev/guide/build) · targets, chunking strategy, source maps and the `base` path.
- [Vite: server.proxy](https://vite.dev/config/server-options.html#server-proxy) · every proxy option, including path rewriting and WebSocket forwarding.

---

Part of [JavaScript & Frontend](../README.md) · items 7.1, 7.2
