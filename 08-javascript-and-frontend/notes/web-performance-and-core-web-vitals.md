# Web performance and Core Web Vitals

> **In one sentence:** Core Web Vitals measure three things a user feels (how long until the main content is visible, LCP; how long the page takes to react to an interaction, INP; how much the layout jumps around while loading, CLS), and almost every fix is one of four moves: send less JavaScript, send it later, give the browser sizes up front, and keep long tasks off the main thread.

**Why it matters:** A backend developer tends to measure the API (p99 latency, 40 ms) and conclude the page is fast. The user waits 4 seconds because the page ships 1.8 MB of JavaScript that must download, parse and run before the first `fetch` is even sent. Google uses the Core Web Vitals as a ranking signal and reports them per URL in Search Console, so they are also the numbers product owners will quote at you. Knowing what each one measures tells you which layer to fix.

## The idea

**The three metrics**, with the thresholds Google publishes for the 75th percentile of page loads:

| Metric | Measures | Good | Poor | Typical cause |
|---|---|---|---|---|
| LCP, Largest Contentful Paint | time until the largest image or text block in the viewport is rendered | at most 2.5 s | over 4 s | slow server, render-blocking CSS and JavaScript, a hero image discovered late |
| INP, Interaction to Next Paint | the worst (roughly) latency from a click, tap or key press to the next frame, across the whole visit | at most 200 ms | over 500 ms | long tasks on the main thread, heavy re-renders, synchronous layout in handlers |
| CLS, Cumulative Layout Shift | how much visible content moves without the user causing it | at most 0.1 | over 0.25 | images and embeds without dimensions, fonts swapping, content injected above the fold |

INP replaced First Input Delay in 2024; FID measured only the delay before the handler started, INP measures until the screen updates. The metrics are collected from real users (field data, via the `web-vitals` library or Chrome's reporting) and in the lab (Lighthouse, DevTools). Lab numbers are reproducible; field numbers are the ones that count.

**Where the time goes for LCP.** Time to first byte from your server, then the HTML must be parsed far enough to discover the resources, then render-blocking CSS and synchronous scripts must arrive, then the largest element's image must be requested, downloaded and decoded. Each step is a fix: cache or stream HTML; put the hero image in the HTML (not behind JavaScript or a CSS background) with `fetchpriority="high"` and a `<link rel="preload">`; `defer` scripts; inline the small amount of CSS needed above the fold (see item 4.2).

**Bundle size and code splitting.** JavaScript is the most expensive byte: it is downloaded, parsed, compiled and executed, all before it is useful. The bundler already tree-shakes unused exports (see item 7.2). The next lever is splitting: a dynamic `import()` produces a separate chunk that is downloaded only when that code path runs. Routes are the natural boundary (`React.lazy(() => import("./pages/ReportsPage"))`), then heavy widgets (a chart library, a rich text editor, a PDF viewer). Measure before and after with the bundler's analyser; a frontend that ships one 1.2 MB chunk to every visitor is the usual starting point.

**Lazy loading.** `<img loading="lazy">` defers images below the fold until they are near the viewport; never use it on the LCP image, which should load as early as possible. `IntersectionObserver` does the same for anything else. For JavaScript, "lazy" means the dynamic import above.

**Image optimisation.** Images are most of the bytes on most pages. Serve modern formats (`AVIF`, `WebP`) with `<picture>` fallbacks, serve the size that will be displayed with `srcset` and `sizes`, and always set `width` and `height` attributes (or CSS `aspect-ratio`) so the browser reserves space before the image arrives, which is the single biggest CLS fix. Resize on upload or through an image CDN; a 4000 pixel photo displayed at 400 pixels is wasted bandwidth and decode time.

**INP and long tasks.** The main thread does everything: JavaScript, style, layout, paint. A task over 50 ms blocks input; a 300 ms re-render of a large table after a keystroke is the typical INP failure. Fixes: do less work per interaction (virtualise long lists, debounce input that triggers filtering, memoise expensive derived data), yield to the browser between chunks of work (`scheduler.yield()` where available, otherwise `setTimeout(0)` between batches), move pure computation to a Web Worker, and avoid reading layout (`offsetHeight`, `getBoundingClientRect`) right after writing it (see item 4.1).

## Example: finding and fixing the three metrics on one page

A product page built with Vite and React ships one bundle. Lighthouse reports LCP 4.8 s, INP 420 ms, CLS 0.32. The fixes, in the order they pay off:

1. CLS 0.32 to 0.02. The product image had no dimensions and the font swapped late.

```html
<img src="/images/chair-800.webp"
     srcset="/images/chair-400.webp 400w, /images/chair-800.webp 800w, /images/chair-1600.webp 1600w"
     sizes="(max-width: 600px) 100vw, 600px"
     width="800" height="600"
     alt="Oak dining chair"
     fetchpriority="high">
<link rel="preload" as="font" href="/fonts/inter-latin.woff2" type="font/woff2" crossorigin>
```

The `width` and `height` give the browser the aspect ratio, so space is reserved before the bytes arrive. Preloading the font and declaring it with `font-display: swap` (or `optional` for a non-essential face) removes the swap-induced shift.

2. LCP 4.8 s to 1.9 s. The image was requested only after React rendered it. The same `<img>` with `fetchpriority="high"` placed in the server-rendered HTML (or at least not behind a `loading="lazy"` attribute) is discovered by the preload scanner. The 1.2 MB bundle is split by route:

```jsx
import { lazy, Suspense } from "react";

const ReviewsPanel = lazy(() => import("./ReviewsPanel.jsx"));
const SizeGuideDialog = lazy(() => import("./SizeGuideDialog.jsx"));

export function ProductPage({ product }) {
  return (
    <>
      <ProductHero product={product} />
      <Suspense fallback={<p>Loading reviews...</p>}>
        <ReviewsPanel productId={product.id} />
      </Suspense>
    </>
  );
}
```

Vite emits `ReviewsPanel-[hash].js` and `SizeGuideDialog-[hash].js` as separate chunks; the main bundle no longer carries the markdown renderer the reviews use.

3. INP 420 ms to 120 ms. Typing in the "filter reviews" box re-rendered 2,000 review rows on every keystroke. Deferring the expensive part with `useDeferredValue` keeps the input responsive while the list catches up, and rendering only the rows in view (a virtualised list) caps the work regardless of count:

```jsx
import { useDeferredValue, useState } from "react";

export function ReviewFilter({ reviews }) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const visible = reviews.filter((review) => review.text.includes(deferredQuery));
  return (
    <>
      <input value={query} onChange={(event) => setQuery(event.target.value)} />
      <ReviewList reviews={visible} />
    </>
  );
}
```

The input updates on every keystroke; the filtered list is rendered with the deferred value at lower priority, so a fast typist never waits for the previous filter to finish painting.

To measure in the field, the `web-vitals` library reports each metric with an attribution object naming the element or the script responsible, which is usually enough to know which of the moves above to make.

## Pitfalls

- Optimising lab numbers only. Lighthouse on a developer laptop over fibre says 1.1 s; users on a mid-range Android phone over 4G see 5 s. Throttle CPU and network in DevTools, and read field data.
- `loading="lazy"` on the hero image. It delays the one image LCP depends on. Lazy-load below the fold only.
- A spinner that counts as the LCP element, then is replaced. The metric is final when the largest element stops changing; a late-arriving hero after a placeholder means a late LCP.
- Shipping a date library, an icon set or a charting library in the main bundle for a feature on one page. Dynamic `import()` at the feature boundary.
- Fixing CLS by making everything `position: absolute`. Give elements their sizes (`width`/`height`, `aspect-ratio`, `min-height` for ad slots) instead.
- `useMemo` everywhere as an INP fix. It does not help when the expensive part is the DOM update itself; virtualise or defer instead (see item 6.2).
- Measuring the API and declaring victory. A 40 ms response behind a 1.2 MB bundle still gives a 4 s LCP. Profile the page, not only the server.
- Third-party scripts (analytics, chat widgets, A/B testing) added by tags. They are often the largest long tasks; load them after the page is interactive and audit them with the Performance panel.

## Check yourself

1. A page has an excellent LCP but a poor INP. Which kinds of work are the likely culprits, and which DevTools panel shows them?
2. Why does setting `width` and `height` on an `<img>` reduce CLS even though CSS later scales the image to `width: 100%`?
3. Your bundle analyser shows a 600 KB PDF library in the main chunk, used by a "download invoice" button. What is the change, and what does the user see while the chunk loads?
4. Explain why the LCP of a client-rendered React page is usually worse than the same page server-rendered, in terms of the sequence of requests the browser must make.

## Go deeper

- [web.dev: Web Vitals](https://web.dev/articles/vitals) · the metric definitions and thresholds, with links to each metric's optimisation guide.
- [web.dev: Learn Performance](https://web.dev/learn/performance) · a course covering the critical path, images, fonts and JavaScript, in roughly the order this note follows.
- [web.dev: Understanding the critical path](https://web.dev/learn/performance/understanding-the-critical-path) · why render-blocking resources delay LCP.
- [web.dev: Rendering performance](https://web.dev/articles/rendering-performance) · the main-thread pipeline that INP measures.
- [Chrome DevTools documentation](https://developer.chrome.com/docs/devtools) · the Performance panel is where long tasks and layout shifts are found.

---

Part of [JavaScript & Frontend](../README.md) · item 4.6
