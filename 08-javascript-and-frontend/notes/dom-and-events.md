# The DOM and events: selection, mutation, propagation and delegation

> **In one sentence:** The DOM is a live tree of nodes you select with `querySelector` and change with properties and methods, and every event dispatched on a node travels down from `document` to the target (capture), fires on the target, then travels back up (bubble), which is what lets one listener on a parent handle clicks for thousands of children and what makes `stopPropagation` and `passive` listeners matter.

**Why it matters:** React, Vue and every other framework are layers over these two APIs, and when something goes wrong (a click that fires twice, a scroll that stutters, a handler that stops working after a list re-renders) the explanation is in the DOM and event model, not in the framework. Reviewers also expect a backend developer to spot the common mistakes: an `innerHTML` built from user input, a listener attached per row, a `scroll` handler that blocks scrolling.

## The idea

**Selection.** `document.querySelector(selector)` returns the first element matching a CSS selector, `querySelectorAll` returns a static `NodeList` of all of them. Both work on any element, not only `document`, so you can scope a search. `element.closest(selector)` walks up from the element to the nearest ancestor (including itself) that matches, which is the building block of delegation. The older `getElementsByClassName` family returns live collections that change as the DOM changes; treat them as a source of surprise.

**Mutation.** Text goes through `textContent` (safe, escapes nothing because it inserts no markup). Markup goes through `innerHTML` (parses the string as HTML, so any user-controlled part is a cross-site scripting hole, see item 4.7) or, better, through `document.createElement` plus `append`, or `insertAdjacentHTML` for trusted templates. Attributes have two faces: the attribute in the markup (`getAttribute("value")`, the initial value) and the property on the object (`input.value`, the current value). `data-*` attributes surface as `element.dataset.orderId` for `data-order-id`. Class changes go through `classList.add/remove/toggle`. Every write that changes geometry invalidates layout; batch writes and keep reads separate (see item 4.1).

**Propagation.** When an event is dispatched on a target, the browser builds the path from `window` down to the target and runs three phases:

```text
window -> document -> html -> body -> ul -> li -> button     capture phase (listeners registered with { capture: true })
                                                 button      target phase (both kinds, in registration order)
button -> li -> ul -> body -> html -> document -> window     bubble phase (default listeners)
```

Most events bubble (`click`, `input`, `keydown`, `submit`). A few do not (`focus`, `blur`, `scroll` on elements, `load`); they have bubbling siblings (`focusin`, `focusout`) or you listen in the capture phase. `event.target` is the element the event happened on; `event.currentTarget` is the element whose listener is running. `event.stopPropagation()` ends the walk after the current element's listeners; `stopImmediatePropagation` also skips the remaining listeners on that element. `event.preventDefault()` cancels the browser's default action (following a link, submitting a form, scrolling) and is independent of propagation.

**Delegation.** Because events bubble, one listener on a container sees every click inside it. The listener asks `event.target.closest(".cancel")` which child was meant. This replaces one listener per row with one per list, survives rows being added and removed, and is how React implements its own event system (one set of native listeners on the root). The cost is that any descendant listener calling `stopPropagation` silently breaks the parent's delegate.

**Passive listeners.** For `touchstart`, `touchmove` and `wheel`, the browser must wait for your listener to finish before it can scroll, because the listener might call `preventDefault()`. Registering with `{ passive: true }` promises you will not, so scrolling starts immediately on the compositor thread. Chrome and other engines already treat `touchstart`, `touchmove` and `wheel` listeners on `window`, `document` and `body` as passive by default; set it explicitly everywhere else, and never call `preventDefault` from a passive listener (it is ignored and logs a console warning).

**Other listener options.** `{ once: true }` removes the listener after its first call. `{ signal }` from an `AbortController` removes any number of listeners with one `abort()`, which is the cleanest cleanup in a component's unmount. Adding the same function reference twice to the same element and event is a no-op; adding two different arrow functions is two listeners, which is why `removeEventListener` with a fresh arrow function never removes anything.

## Example: propagation order and delegation, observed

This runs in Node under jsdom so the output can be shown; in a browser the same code goes in a `<script type="module">` with the markup on the page.

```javascript
// dom-events.mjs
import { JSDOM } from "jsdom";

const dom = new JSDOM(`
  <ul id="orders">
    <li data-order-id="1">Order 1 <button class="cancel">Cancel</button></li>
    <li data-order-id="2">Order 2 <button class="cancel">Cancel</button></li>
  </ul>
`);
const { document } = dom.window;

const list = document.querySelector("#orders");
const firstButton = document.querySelector('li[data-order-id="1"] .cancel');

for (const [element, name] of [[document, "document"], [list, "ul"], [firstButton, "button"]]) {
  element.addEventListener("click", () => console.log(`capture  ${name}`), { capture: true });
  element.addEventListener("click", () => console.log(`bubble   ${name}`));
}

list.addEventListener("click", (event) => {
  const button = event.target.closest(".cancel");
  if (!button || !list.contains(button)) {
    return;
  }
  const orderId = button.closest("li").dataset.orderId;
  console.log(`delegated: cancel order ${orderId}`);
});

firstButton.click();

console.log("--- second button, listener count unchanged");
document.querySelector('li[data-order-id="2"] .cancel').click();

console.log("--- stopPropagation on the button");
firstButton.addEventListener("click", (event) => event.stopPropagation());
firstButton.click();
```

```text
capture  document
capture  ul
capture  button
bubble   button
bubble   ul
delegated: cancel order 1
bubble   document
--- second button, listener count unchanged
capture  document
capture  ul
bubble   ul
delegated: cancel order 2
bubble   document
--- stopPropagation on the button
capture  document
capture  ul
capture  button
bubble   button
```

Reading the output: capture listeners run top-down, then the target's listeners in registration order (capture first, as the current DOM standard specifies), then bubble listeners bottom-up. The delegate on `ul` handled the second button with no listener on that button at all. After `stopPropagation` on the button, the `ul` and `document` bubble listeners never ran, and neither did the delegate: the cancel action silently stopped working.

The `list.contains(button)` guard matters when the list can contain nested lists or when `closest` could escape the container; it is cheap insurance.

## Pitfalls

- `innerHTML = "<li>" + userName + "</li>"`. Any `<script>` or `onerror=` in `userName` runs. Use `textContent`, or create elements and set properties.
- One listener per row. A thousand rows means a thousand closures that must be removed when rows are removed, or they leak. Delegate to the container.
- `stopPropagation` as a reflex. It breaks delegation, analytics listeners and React's own event handling for everything above. Prefer checking `event.target` in the parent, or `preventDefault` if the goal was to stop a default action.
- `removeEventListener(type, () => ...)`. A new arrow function is a different reference; nothing is removed. Keep the reference, use `{ once: true }`, or pass an `AbortSignal`.
- A `scroll` or `touchmove` listener that does layout reads. It runs on every frame during a scroll and the page stutters. Mark it `passive`, throttle with `requestAnimationFrame`, or use `IntersectionObserver` for "is it visible" questions.
- Listening on a node that gets replaced. A framework re-render, or `innerHTML` on a parent, creates new nodes; listeners on the old ones are gone with them. Delegation on a stable ancestor avoids this.
- Expecting `focus` or `blur` to reach a parent. They do not bubble; use `focusin`/`focusout` or capture.
- Reading `event.currentTarget` after an `await` inside the listener. It is reset to `null` once dispatch finishes, so capture what you need synchronously before the first `await`.

## Check yourself

1. A listener on `document` logs every click for analytics. Clicks on one specific button never appear. What is the most likely cause, and how would you confirm it in DevTools?
2. Why can React attach its event listeners to the root container once and still deliver `onClick` to the right component, and what native concept makes that work?
3. A mobile page scrolls with visible stutter whenever the user's finger moves. What listener option would you check first, and what does it promise the browser?
4. You need to remove six listeners from three elements when a dialog closes. Show two ways that avoid keeping six function references around.

## Go deeper

- [javascript.info: Introduction to browser events](https://javascript.info/introduction-browser-events) · the basics with live examples.
- [javascript.info: Bubbling and capturing](https://javascript.info/bubbling-and-capturing) · the three phases with diagrams, and the `stopPropagation` discussion.
- [MDN: EventTarget.addEventListener](https://developer.mozilla.org/en-US/docs/Web/API/EventTarget/addEventListener) · the options (`capture`, `once`, `passive`, `signal`) and the rule about duplicate listeners.
- [MDN: Event.target](https://developer.mozilla.org/en-US/docs/Web/API/Event/target) · versus `currentTarget`, with the delegation example.
- [web.dev: Rendering performance](https://web.dev/articles/rendering-performance) · what a scroll listener costs and why passive listeners exist.

---

Part of [JavaScript & Frontend](../README.md) · item 4.3
