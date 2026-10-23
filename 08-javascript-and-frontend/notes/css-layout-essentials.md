# CSS layout essentials

> **In one sentence:** Every element is a box whose size follows the box model, every property value is decided by the cascade (origin, layers, specificity, source order) and inheritance, and nearly every layout you will need is either one-dimensional (Flexbox: a row or a column of things) or two-dimensional (Grid: rows *and* columns), made responsive with a few media or container queries.

**Why it matters:** Backend developers avoid CSS because it feels arbitrary: a width that is not the width you set, a rule that "does not apply", a sidebar that overflows on a narrow screen. None of it is arbitrary. The box model, the cascade and the two layout systems are about a dozen concepts, and with them you can lay out an admin page, review frontend CSS for real problems, and stop reaching for `!important`.

## The idea

**The box model.** Each box has content, padding, border and margin, from the inside out. With the default `box-sizing: content-box`, `width: 200px` is the content width and padding and border are added outside it, so a `200px` input with `1rem` padding is wider than `200px`. Almost every project starts with the reset that makes `width` mean what people expect:

```css
*, *::before, *::after { box-sizing: border-box; }
```

Vertical margins between blocks in normal flow *collapse*: two `1rem` margins between siblings become one `1rem` gap, not two. Flexbox and Grid items do not collapse margins, which is one reason layout feels more predictable inside them.

**The cascade** decides which declaration wins when several target one element, in this order:

1. Origin and importance: author styles beat the browser's defaults; `!important` reverses the order, which is why it is so hard to override later.
2. Cascade layers: `@layer base, components, overrides;` lets you declare that anything in a later layer beats anything in an earlier one regardless of specificity. Unlayered styles beat all layers.
3. Specificity, counted as three numbers (ids, classes/attributes/pseudo-classes, elements/pseudo-elements) compared left to right. `#main .card p` is (1, 1, 1) and beats `.sidebar .card .title p` at (0, 3, 1). Inline `style` attributes beat any selector. `:where(...)` has zero specificity, which makes it ideal for defaults you intend to override.
4. Source order: the last declaration wins among equals.

**Inheritance.** Text properties (`color`, `font-*`, `line-height`, `text-align`) inherit from the parent; box properties (`margin`, `padding`, `border`, `width`, `background`) do not. Custom properties (`--brand: #0b5fff;` read with `var(--brand)`) inherit, can be redefined on any subtree, and are how themes and design tokens are implemented.

**Units.** Use `rem` for sizes that should scale with the user's font settings, `%` and `fr` for shares of available space, `vw`/`vh`/`dvh` for viewport-relative sizes, and `clamp(min, preferred, max)` for fluid values without a media query.

**Flexbox: one dimension.** `display: flex` on a container lays its children out along the main axis (`flex-direction: row` by default). `justify-content` distributes items along that axis, `align-items` along the cross axis, `gap` spaces them. Each item's `flex: <grow> <shrink> <basis>` says how it shares free space; `flex: 1` means "take an equal share of what is left". `margin-left: auto` on one item pushes it, and everything after it, to the end. Flex items refuse to shrink below their content size by default (`min-width: auto`), which is the cause of most "the long text overflowed my toolbar" bugs; `min-width: 0` fixes it.

**Grid: two dimensions.** `display: grid` with `grid-template-columns` and `grid-template-rows` defines tracks; `grid-template-areas` names regions so that children are placed with `grid-area: sidebar` instead of line numbers. `repeat(auto-fill, minmax(16rem, 1fr))` produces as many columns as fit, which makes a card grid responsive without any media query. `1fr` is really `minmax(auto, 1fr)`, so a track can grow with its content; `minmax(0, 1fr)` is the Grid version of `min-width: 0`.

**Responsive basics.** Start from the narrow layout and add complexity as space allows. `@media (width >= 48rem)` (range syntax, supported in current browsers) switches layouts by viewport width. Container queries switch by the size of the *component's container*: `container-type: inline-size` on the wrapper, then `@container (width >= 30rem)` inside, so a card lays itself out the same way whether it is in a sidebar or a main column. `prefers-color-scheme` and `prefers-reduced-motion` are media queries too.

**The properties that solve most layout problems:** `box-sizing: border-box`, `display: flex` with `gap`, `justify-content`, `align-items`, `flex: 1`, `min-width: 0`, `display: grid` with `grid-template-columns`, `grid-template-areas`, `minmax()`, `max-width` with `margin-inline: auto` for centred content, `position: sticky` for headers, `overflow: auto` for scrollable panes, `aspect-ratio` and `object-fit: cover` for images.

## Example: an application shell in Grid, a toolbar in Flexbox

```html
<body class="app">
  <header class="app-header">
    <div class="toolbar">
      <strong>Orders</strong>
      <input class="toolbar-search" type="search" placeholder="Search orders">
      <div class="toolbar-actions">
        <button>New order</button>
        <button>Account</button>
      </div>
    </div>
  </header>
  <nav class="app-sidebar">Navigation</nav>
  <main class="app-content">Content</main>
</body>
```

```css
*, *::before, *::after { box-sizing: border-box; }
body { margin: 0; font: 1rem/1.5 system-ui, sans-serif; }

.app {
  display: grid;
  grid-template-columns: 16rem minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr);
  grid-template-areas:
    "header  header"
    "sidebar content";
  min-height: 100dvh;
}

.app-header  { grid-area: header; border-bottom: 1px solid #ddd; }
.app-sidebar { grid-area: sidebar; overflow-y: auto; border-right: 1px solid #ddd; padding: 1rem; }
.app-content { grid-area: content; overflow: auto; padding: 1.5rem; }

@media (width < 48rem) {
  .app {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas:
      "header"
      "content";
  }
  .app-sidebar { display: none; }
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1rem;
}

.toolbar-search  { flex: 0 1 24rem; min-width: 0; }
.toolbar-actions { margin-left: auto; display: flex; gap: 0.5rem; }
```

Reading it:

1. The shell is a two-column, two-row grid filling the viewport (`min-height: 100dvh`). The header spans both columns by appearing twice in its row of `grid-template-areas`; the sidebar and the content each take one cell. `minmax(0, 1fr)` on the content column and row lets wide tables inside `.app-content` scroll instead of stretching the page.
2. Below `48rem` the grid becomes one column and the sidebar is removed from the layout (a real application would turn it into a drawer).
3. The toolbar is a flex row. The search field has a preferred width of `24rem`, may shrink (`1`) but never grows (`0`), and `min-width: 0` lets it shrink below its intrinsic width on a narrow screen instead of pushing the buttons off the edge.
4. `margin-left: auto` on the actions group absorbs all remaining free space, pushing the buttons to the right without a spacer element. The group is itself a small flex container so its buttons get a `gap`.

Paste both blocks into an HTML file and resize the window: that is the whole feedback loop CSS needs.

## Pitfalls

- Fighting specificity with `!important`. The next person needs `!important` too, and the file becomes unmaintainable. Lower specificity instead: single classes, `:where()` for defaults, and layers for the few cases that need ordering.
- Setting `width: 100%` on something with padding under `content-box`. It overflows its parent by the padding. Use the `border-box` reset.
- A flex item with long unbreakable text that overflows the row. Add `min-width: 0` (or `overflow: hidden`) to the item.
- A `1fr` grid column that grows past the viewport because a child is wide. Use `minmax(0, 1fr)`.
- Centring with magic margins or absolute positioning. `display: grid; place-items: center;` on the parent centres a child in both axes; `margin-inline: auto` with a `max-width` centres a block horizontally.

## Check yourself

1. Two rules target the same `<p>`: `.article .intro` and `#page p`. Which wins and why? How would you change the second rule so that it stays useful as a default but loses to any class-based rule?
2. Why does the search field shrink gracefully on a narrow screen while a plain `<input>` without `min-width: 0` would overflow? Which default is responsible?
3. Rewrite the application shell so that the sidebar is on the right. Which single declaration changes?
4. A card component looks right on the dashboard and wrong in a narrow sidebar, even though both are on a wide screen. Why does a media query not help, and what does?

## Go deeper

- [web.dev: Learn CSS](https://web.dev/learn/css) · the complete course; the box model, cascade, specificity, Flexbox and Grid modules cover this note.
- [Josh Comeau: An Interactive Guide to Flexbox](https://www.joshwcomeau.com/css/interactive-guide-to-flexbox/) · the mental model of free space, growing and shrinking, with live controls.
- [Josh Comeau: An Interactive Guide to CSS Grid](https://www.joshwcomeau.com/css/interactive-guide-to-grid/) · tracks, `fr`, `minmax`, areas and `auto-fill`, interactively.
- [CSS-Tricks: A Complete Guide to Flexbox](https://css-tricks.com/snippets/css/a-guide-to-flexbox/) and [A Complete Guide to CSS Grid](https://css-tricks.com/snippets/css/complete-guide-grid/) · the reference charts to keep open while writing layout code.
- [Flexbox Froggy](https://flexboxfroggy.com/) and [Grid Garden](https://cssgridgarden.com/) · twenty minutes each, and the properties stick.

---

Part of [JavaScript & Frontend](../README.md) · items 5.2, 5.3
