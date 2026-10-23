# How browsers render a page

> **In one sentence:** A browser parses HTML into a DOM and CSS into a CSSOM, combines them into a render tree, computes layout, paints pixels into layers and composites the layers on the GPU; scripts can stall the parsing step, and JavaScript that changes geometry and then reads it forces the layout step to run again, which is where most "the page feels slow" complaints come from.

**Why it matters:** When you review a frontend pull request you need to know why a large JavaScript bundle delays the first paint, why a loop over table rows freezes the tab, and why animating `transform` is smooth while animating `top` is not. Core Web Vitals (item 4.6) are measurements of this pipeline, and interviewers for full-stack roles ask for it in exactly this form: "what happens between the HTML arriving and pixels appearing?"

## The idea

**1. Parse.** The HTML parser builds the DOM incrementally as bytes arrive. A preload scanner runs ahead of it and starts fetching the stylesheets, scripts and images it sees. CSS is parsed into the CSSOM. CSS is **render-blocking**: the browser will not paint until the CSSOM is complete, because painting unstyled content and then restyling it would look broken.

**2. Scripts interrupt parsing.** A classic `<script src="...">` stops the parser until the script has downloaded and run, because the script may `document.write` or query the DOM so far. A classic script also waits for the CSSOM, because it may read computed styles. So "CSS blocks scripts and scripts block parsing" is the chain that delays first render. The attributes change this:

| Script | Download | Executes | Order kept |
|---|---|---|---|
| `<script src>` | blocks the parser | immediately, parser paused | yes |
| `<script async src>` | in parallel | as soon as it arrives, parser paused | no |
| `<script defer src>` | in parallel | after parsing, before `DOMContentLoaded` | yes |
| `<script type="module">` | in parallel | deferred by default; `async` opts out | yes |

Use `defer` or modules for your application code and `async` only for independent scripts such as analytics.

**3. Style and render tree.** DOM and CSSOM are combined into a tree of boxes to display. `display: none` elements are not in it; `visibility: hidden` elements are, with their size reserved.

**4. Layout (reflow).** The browser computes the position and size of every box. Geometry is interdependent (a wider sidebar narrows the content, a longer paragraph pushes everything below it), so layout work is roughly proportional to the size of the affected subtree, and often the whole document.

**5. Paint.** Boxes become drawing commands (fill this rectangle, draw this text), rasterised into one or more layers.

**6. Composite.** The layers are positioned and blended, on a separate compositor thread and the GPU. `transform` and `opacity` changes to an element with its own layer can be handled here alone, without layout or paint, which is why they animate at 60 frames per second while `left`, `width` or `margin` do not.

**Which steps run again** depends on what changed: geometry (`width`, `font-size`, adding a node, changing text) costs layout, paint and composite; appearance only (`color`, `background`, `box-shadow`) costs paint and composite; `transform` and `opacity` cost composite only. Browsers batch style and layout work and run it once per frame, about every 16 milliseconds on a 60 Hz display, unless JavaScript forces it earlier.

**Forced synchronous layout.** Reading a geometric property (`offsetWidth`, `offsetHeight`, `getBoundingClientRect()`, `scrollTop`, some `getComputedStyle` values) after a change that invalidated layout forces the browser to run layout *now* to answer correctly. One forced layout is cheap. A loop that writes and then reads on each iteration forces one layout per iteration: **layout thrashing**.

**The critical rendering path** is the set of resources the browser must have before the first render: the HTML, every render-blocking stylesheet, and every parser-blocking script. Shorten it by keeping the initial CSS small, loading scripts with `defer`, declaring late-discovered critical resources early with `<link rel="preload">` (fonts, the hero image) and `<link rel="preconnect">` for third-party origins, and sizing images with `width`/`height` attributes so layout does not shift when they arrive.

**What makes a page slow,** in the order you will encounter it: too much JavaScript (download, then parse, compile and execute on the main thread, all before the app can respond), render-blocking CSS and fonts, resource chains (a stylesheet that imports a stylesheet that loads a font), layout thrashing in scroll or resize handlers, very large DOMs, and third-party scripts that do all of the above outside your control.

## Example: a layout-thrashing loop and its fix

A dashboard sets each card's width to half of its container, for a few hundred cards:

```javascript
function fitCards(cards) {
  for (const card of cards) {
    const containerWidth = card.parentElement.offsetWidth;   // read
    card.style.width = `${containerWidth / 2}px`;            // write
  }
}
```

Iteration 1 reads `offsetWidth` (layout is clean, so the cached value is returned) and writes a width, which invalidates layout. Iteration 2 reads `offsetWidth` again; layout is dirty, so the browser must run it synchronously to answer. Every subsequent iteration does the same. With 500 cards that is 500 layouts in one task, and the Performance panel in Chrome DevTools shows a comb of purple "Layout" blocks, each flagged "Forced reflow is a likely performance bottleneck".

The fix is to separate the reads from the writes so that layout is invalidated once:

```javascript
function fitCards(cards) {
  const containerWidths = Array.from(cards, (card) => card.parentElement.offsetWidth);   // all reads

  cards.forEach((card, index) => {
    card.style.width = `${containerWidths[index] / 2}px`;                                 // all writes
  });
}
```

Now the reads all hit clean layout and the writes dirty it once; the browser runs one layout at the next frame. The same effect without JavaScript is usually better still: `width: 50%` in CSS, or a Grid or Flexbox layout (item 5.3), lets the layout engine do the arithmetic in its own batch.

If the work must be spread over time (hundreds of measurements on scroll), do it inside `requestAnimationFrame`, which runs just before the browser's own style and layout pass, and read in one frame and write in the next.

## Pitfalls

- A classic `<script>` in `<head>` without `defer`. Nothing renders until the bundle has downloaded and run. The symptom is a blank page for as long as the script takes on a slow network.
- Reading `offsetHeight` "just to be safe" inside a resize or scroll handler that also writes styles. Each event fires many times per second, and each handler forces layout.
- Animating `top`, `left`, `width` or `margin`. Every frame runs layout and paint. Use `transform: translate()` and `opacity`, and promote the element to its own layer with `will-change: transform` only for the duration of the animation.
- Images without dimensions. Each one arrives and shifts everything below it: a layout per image, and a Cumulative Layout Shift penalty.
- `display: none` toggled many times during a loop. Each toggle removes or adds boxes to the render tree and invalidates layout; build off-screen (or in a `DocumentFragment`) and attach once.
- Measuring with a warm cache on a fast laptop. The critical rendering path only shows itself with network throttling and CPU throttling turned on in DevTools.
- Treating "the bundle is gzipped to 300 kB" as the cost. Parse and compile time scales with the uncompressed size, on the main thread, on the user's phone.

## Check yourself

1. A stylesheet and a deferred script are both still downloading. Which of them blocks the first paint, and why does the browser make that choice?
2. Explain why `fitCards` performs 500 layouts in the first version and 1 in the second, without using the word "slow".
3. Why does animating `transform` stay smooth when the main thread is busy running JavaScript, while animating `left` stutters?
4. The home page ships one 1.2 MB JavaScript bundle and the first paint takes four seconds on a mid-range phone, but only 300 ms on your laptop. List the pipeline steps that differ between the two devices, and the first two changes you would make.

## Go deeper

- [web.dev: How browsers work](https://web.dev/articles/howbrowserswork) · the long-form walk through parsing, style, layout and paint.
- [web.dev: Rendering performance](https://web.dev/articles/rendering-performance) · the pixel pipeline (JavaScript, style, layout, paint, composite) and what each property change costs.
- [web.dev: Understanding the critical path](https://web.dev/learn/performance/understanding-the-critical-path) · render-blocking and parser-blocking resources, with the script attributes.
- [web.dev: Avoid large, complex layouts and layout thrashing](https://web.dev/articles/avoid-large-complex-layouts-and-layout-thrashing) · forced synchronous layout explained with the DevTools view.
- [Paul Irish: What forces layout / reflow](https://gist.github.com/paulirish/5d52fb081b3570c81e3a) · the list of properties and methods whose reads force layout.

---

Part of [JavaScript & Frontend](../README.md) · items 4.1, 4.2
