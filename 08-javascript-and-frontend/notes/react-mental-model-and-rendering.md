# The React mental model: UI as a function of state, and how rendering works

> **In one sentence:** A React component is a function from props and state to a description of the UI; React calls it again whenever its state or its parent changes, compares the new description with the old one, and applies the minimal DOM changes, using `key` to decide which list items are "the same" between two renders.

**Why it matters:** Nearly every React bug a reviewer catches is a mental-model bug: state that is mutated in place and never shows up, a list keyed by index that mixes up rows, derived data stored in state and kept in sync by hand, or `memo` sprinkled everywhere as a superstition. For a backend developer the model is close to something familiar, a pure function over immutable input, and that framing explains the rules.

## The idea

**UI is a function of state.** You do not update the screen; you update state, and React re-runs the function to compute the new screen. A component is a JavaScript function that returns JSX, which compiles to calls that produce plain objects (React elements) describing what should be on screen. Returning a description instead of mutating the DOM is what lets React diff and batch.

**Props and state.** Props are the arguments a parent passes; they are read-only inside the child. State is what a component owns and may change, declared with `useState` (or `useReducer` for state with several related transitions). Data flows one way: down through props. A child that needs to change something asks the parent through a callback prop. When two components need the same state, move it to their closest common ancestor ("lifting state up") and pass it down.

**Render and commit.** A render is React calling your component function (and the functions of its children) to get a new element tree. The commit is React applying the differences to the DOM. Renders must be pure: same props and state, same output, no side effects. Strict Mode calls your functions twice in development to catch impurity.

**What triggers a render.**

| Triggers a render | Does not |
|---|---|
| a state setter called with a different value (`Object.is`) | setting state to the same value (React usually skips) |
| the parent rendering (children render too, by default, whether or not their props changed) | mutating a state object in place: same reference, so "nothing changed" |
| a context value the component reads changing | writing to a `ref` |
| the initial mount | props changing on their own (impossible; props only change because a parent rendered) |

In React 18 and later, state updates inside the same event, timeout or promise callback are batched into one render.

**Reconciliation and keys.** React compares the new element tree with the previous one position by position. Same component type at the same position: keep the instance and its state, update props. Different type: unmount the old subtree (losing its state) and mount the new one. For arrays of children, position is ambiguous, so React uses `key`. A key says "this element is the same entity as the element with this key last time". Keys must be stable (the same across renders), unique among siblings, and attached to the entity, which means a database id, not the array index. Changing a key deliberately is the idiom for resetting a component's state (`<CustomerForm key={customerId} />`).

**Derive, do not store.** If a value can be computed from props and state, compute it during render: `const activeOrders = orders.filter((order) => order.status === "active")`. Storing it in state and syncing it with an effect creates two sources of truth, an extra render, and a window where they disagree. State should hold the minimal set of facts that cannot be derived.

**`memo` and premature optimisation.** `memo(Component)` makes a component skip its render when its props are shallowly equal to last time. It only helps if renders of that component are measurably expensive and its props are actually stable (object and function props must be memoised with `useMemo`/`useCallback`, item 6.5). React renders are usually cheap; the React DevTools Profiler shows you where they are not. Optimise after measuring. The React Compiler can insert this memoisation automatically; check its status for your project before relying on it.

## Example: a list with the wrong key, and the bug it causes

```tsx
interface Guest {
  id: string;
  name: string;
}

interface GuestListProps {
  guests: Guest[];
  onRemove: (guestId: string) => void;
}

function GuestList({ guests, onRemove }: GuestListProps) {
  return (
    <ul>
      {guests.map((guest, index) => (
        <li key={index}>
          {guest.name}
          <input placeholder="Dietary notes" />
          <button onClick={() => onRemove(guest.id)}>Remove</button>
        </li>
      ))}
    </ul>
  );
}
```

Render three guests, Ada, Grace and Linus, type "vegetarian" into Ada's notes field, then remove Ada. The note now appears next to Grace.

What happened: before the removal the items had keys `0, 1, 2`. After it, the array is `[Grace, Linus]` with keys `0, 1`. React matches new `key={0}` to old `key={0}`, decides it is the same list item, keeps its `<li>` and its `<input>` DOM node (whose value, "vegetarian", lives in the DOM because the input is uncontrolled), and updates the text to "Grace". The item with `key={2}` has no match and is unmounted. React did exactly what the keys told it. Any state inside the rows, `useState` in a row component, focus, scroll position, animation, would have moved the same way.

The fix:

```tsx
{guests.map((guest) => (
  <li key={guest.id}>
    {guest.name}
    <input placeholder="Dietary notes" />
    <button onClick={() => onRemove(guest.id)}>Remove</button>
  </li>
))}
```

Now removing Ada unmounts the `<li>` with Ada's key, and Grace's row, input included, is untouched. An index key is acceptable only for a list that is never reordered, filtered or prepended and whose rows hold no state; since lists rarely stay that way, treat it as a smell.

## Example: storing what should be derived

```tsx
function OrderList({ orders }: { orders: Order[] }) {
  const [filter, setFilter] = useState("");
  const [visibleOrders, setVisibleOrders] = useState(orders);

  useEffect(() => {
    setVisibleOrders(orders.filter((order) => order.customerName.includes(filter)));
  }, [orders, filter]);

  // ...
}
```

The first render shows unfiltered orders, the effect runs after the commit and sets state, and a second render shows the right list. Every keystroke renders twice, and for one frame the list is wrong. Compute it instead:

```tsx
const visibleOrders = orders.filter((order) => order.customerName.includes(filter));
```

One render, one source of truth, no effect. If the filtering were genuinely expensive, `useMemo` around it would cache the result; it still would not belong in state.

## Pitfalls

- Mutating state: `items.push(newItem); setItems(items)`. The reference is unchanged, so React skips the render and the UI lags one step behind. Create a new array: `setItems([...items, newItem])`.
- `key={index}` on a list that can change order, or `key={Math.random()}`, which remounts every row on every render and loses all state and focus.
- Effects that copy props into state "so the component can edit them". That is two sources of truth; either lift the state to the parent or derive the value.
- Defining a component inside another component's body. Each render creates a new component type, so React unmounts and remounts the subtree every time; state and focus are lost.
- Wrapping everything in `memo`, `useMemo` and `useCallback` by default. It adds code and comparison cost, and a single unstable prop (an inline object) silently defeats it. Measure first.

## Check yourself

1. A child component re-renders although none of its props changed. Name the three possible reasons, and say which one `memo` addresses.
2. Using the guest list example, explain what React does with the DOM when the keys are stable ids and Ada is removed, compared with index keys. Where exactly did the "vegetarian" note live, and why did that matter?
3. A form shows an editable copy of a `customer` prop in state so that the user can cancel edits. Is that derived state that should be removed, or legitimate state? What would you use to reset it when a different customer is selected?
4. Why must a component function be pure, and what concretely goes wrong in Strict Mode when it is not?

## Go deeper

- [react.dev: Thinking in React](https://react.dev/learn/thinking-in-react) · the official walkthrough of finding the minimal state and where it lives.
- [react.dev: Render and Commit](https://react.dev/learn/render-and-commit) · the two phases, with the restaurant analogy that makes them stick.
- [react.dev: Preserving and Resetting State](https://react.dev/learn/preserving-and-resetting-state) · how position and keys decide whether state survives a render.
- [react.dev: Rendering Lists](https://react.dev/learn/rendering-lists) · the rules for keys and why an index is rarely the right one.
- [Mark Erikson: A (Mostly) Complete Guide to React Rendering Behavior](https://blog.isquaredsoftware.com/2020/05/blogged-answers-a-mostly-complete-guide-to-react-rendering-behavior/) · the long, precise answer to "what triggers a render", including context and `memo`.
- [react.dev: memo](https://react.dev/reference/react/memo) · when it helps and the caveats about prop identity.

---

Part of [JavaScript & Frontend](../README.md) · items 6.1, 6.2, 6.3
