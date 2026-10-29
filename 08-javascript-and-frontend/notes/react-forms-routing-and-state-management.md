# React forms, routing and state management

> **In one sentence:** Forms are either controlled (React state is the source of truth, every keystroke re-renders) or uncontrolled (the DOM holds the value and you read it on submit, which is what React Hook Form does with a schema for validation); routing maps URLs to components and is the natural place to split code; and client state belongs in the smallest scope that works, `useState` first, Context for rarely changing values, and a store such as Zustand or Redux Toolkit only when many distant components share state that changes often.

**Why it matters:** These three decisions shape every React code base, and the common mistakes compound: a forty-field form written with forty `useState` calls re-renders on every keystroke, a Context holding the whole application state re-renders every consumer on every change, and a single-bundle app with twelve routes makes every visitor download all twelve. For a backend developer reviewing frontend pull requests, these are the structural questions to ask, and they have fairly settled answers.

## The idea

### Forms

A **controlled** input has `value={state}` and `onChange={...}`; React state is the single source of truth, which makes it trivial to format, disable or derive from the value, at the cost of a render per keystroke across the whole form. An **uncontrolled** input keeps its value in the DOM; you read it with a ref or from `FormData` on submit. Native validation (`required`, `type="email"`, `minLength`) works with both and is a reasonable baseline (see item 5.1).

**React Hook Form** makes the uncontrolled approach practical for real forms: `register("email")` returns the `ref`, `name`, `onChange` and `onBlur` props for an input; `handleSubmit(onValid)` collects the values, runs validation and only calls `onValid` with typed data when it passes; `formState.errors` holds field errors. Validation can be inline rules or a schema through a resolver, so one Zod schema types the form, validates it in the browser and can be shared with a Node backend (see item 2.4). Because inputs are uncontrolled, typing in one field does not re-render the others.

### Routing

**React Router** maps a URL to a component tree. Routes nest: a layout route renders its matched child through `<Outlet />`, so a navigation bar is rendered once. `useParams()` reads `:orderId` segments, `<Link>` navigates without a full page load, `useNavigate()` does it from code. In React Router 7 the package is `react-router` (the `react-router-dom` name still works as a re-export); `createBrowserRouter` plus `<RouterProvider>` is the data-router API with loaders and actions, and the older `<BrowserRouter>` with `<Routes>` is still supported.

Routes are where **code splitting** pays off: `React.lazy(() => import("./pages/ReportsPage"))` makes the bundler emit the page as its own chunk, and a `<Suspense>` boundary shows a fallback while it downloads (see item 4.6). React Router's `lazy` route property does the same at the route level.

**Application structure.** Group by feature, not by file type: `features/orders/` holds that feature's components, hooks, API calls and tests, with a small public surface; `pages/` maps URLs to feature components; `components/` is for truly shared UI. Top-level `hooks/`, `utils/` and `services/` folders grow into dumping grounds.

### Client state

The first question is whether the state is **server state** (data the backend owns: orders, users, prices) or **client state** (UI: the open dialog, the selected tab, the draft in a form, the shopping cart before checkout). Server state goes to TanStack Query (see item 6.7); nothing below applies to it. For client state, in order of preference:

1. `useState` in the component that uses it. Lift it to the nearest common ancestor when two components need it (see item 6.3).
2. **Context** for values that many components read and that rarely change: the current user, the theme, the locale, an injected API client. Every consumer re-renders whenever the Provider's `value` changes, and a `value={{ user, setUser }}` object literal is a new object on every render of the provider. Context is a dependency-injection mechanism, not a store; using it for frequently changing state is the classic performance trap.
3. **Zustand** when state changes often and is read in many distant places. A store is created outside React with `create`, components subscribe to a slice with a selector (`useCart((state) => state.lines)`) and re-render only when that slice changes. No providers, little boilerplate, usable outside components (`useCart.getState()` in a fetch wrapper).
4. **Redux Toolkit** for large applications with many developers: slices, reducers, serialisable actions, time-travel debugging and a style guide that enforces structure. Modern Redux is Redux Toolkit; hand-written reducers with string constants are the legacy that gave Redux its reputation.

Choose by scale: a three-page dashboard needs `useState` and Context; a forty-screen application with a cart, notifications and permissions needs a store, and which one is mostly team convention.

## Example: a form with a shared schema

```tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

const CustomerFormSchema = z.object({
  email: z.email(),
  name: z.string().min(2, "At least two characters"),
  newsletter: z.boolean(),
});

type CustomerForm = z.infer<typeof CustomerFormSchema>;

export function CustomerFormView({ onSave }: { onSave: (values: CustomerForm) => Promise<void> }) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CustomerForm>({
    resolver: zodResolver(CustomerFormSchema),
    defaultValues: { email: "", name: "", newsletter: false },
  });

  return (
    <form onSubmit={handleSubmit(onSave)} noValidate>
      <label>
        Email
        <input type="email" {...register("email")} aria-invalid={errors.email ? "true" : "false"} />
      </label>
      {errors.email && <p role="alert">{errors.email.message}</p>}

      <label>
        Name
        <input {...register("name")} />
      </label>
      {errors.name && <p role="alert">{errors.name.message}</p>}

      <label>
        <input type="checkbox" {...register("newsletter")} /> Send me the newsletter
      </label>

      <button type="submit" disabled={isSubmitting}>Save</button>
    </form>
  );
}
```

`onSave` receives a `CustomerForm` whose type came from the schema; nothing is cast. `noValidate` turns off the browser's own popups so the schema's messages are the ones shown. `isSubmitting` is true while the `onSave` promise is pending, which is how the double-submit is prevented. Type-checked with React Hook Form 7.91, Zod 4.6 and `@hookform/resolvers`.

## Example: nested routes with a lazy page

```tsx
import { lazy, Suspense } from "react";
import { createBrowserRouter, Link, Outlet, RouterProvider, useParams } from "react-router";

const OrdersPage = lazy(() => import("./pages/OrdersPage.tsx"));

function Layout() {
  return (
    <>
      <nav><Link to="/orders">Orders</Link></nav>
      <Suspense fallback={<p>Loading...</p>}>
        <Outlet />
      </Suspense>
    </>
  );
}

function OrderPage() {
  const { orderId } = useParams();
  return <h1>Order {orderId}</h1>;
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { path: "orders", element: <OrdersPage /> },
      { path: "orders/:orderId", element: <OrderPage /> },
    ],
  },
]);

export function App() {
  return <RouterProvider router={router} />;
}
```

Visiting `/orders/42` renders `Layout`, and inside its `Outlet`, `OrderPage` with `orderId === "42"`. `OrdersPage` is a separate chunk that is fetched the first time `/orders` is visited. A deep link to `/orders/42` only works in production if the server returns `index.html` for unknown paths (see item 8.5).

## Example: a Zustand store, used outside React

```typescript
import { create } from "zustand";

type CartLine = { productId: string; quantity: number };

type CartState = {
  lines: CartLine[];
  add: (productId: string) => void;
  clear: () => void;
};

export const useCart = create<CartState>((set) => ({
  lines: [],
  add: (productId) =>
    set((state) => {
      const existing = state.lines.find((line) => line.productId === productId);
      const lines = existing
        ? state.lines.map((line) => (line === existing ? { ...line, quantity: line.quantity + 1 } : line))
        : [...state.lines, { productId, quantity: 1 }];
      return { lines };
    }),
  clear: () => set({ lines: [] }),
}));

const unsubscribe = useCart.subscribe((state) => console.log("changed:", JSON.stringify(state.lines)));
useCart.getState().add("p-1");
useCart.getState().add("p-1");
useCart.getState().add("p-2");
unsubscribe();
useCart.getState().clear();
console.log("final:", JSON.stringify(useCart.getState().lines));
```

Run with `npx tsx store.ts` (Zustand 5.0):

```text
changed: [{"productId":"p-1","quantity":1}]
changed: [{"productId":"p-1","quantity":2}]
changed: [{"productId":"p-1","quantity":2},{"productId":"p-2","quantity":1}]
final: []
```

Inside a component, `const lines = useCart((state) => state.lines)` subscribes to that slice only; a component that selects `state.add` never re-renders when `lines` changes. The update in `add` is immutable (`map` and spread), the same rule as `useState` (see item 6.3).

## Pitfalls

- A controlled form with one `useState` per field and an expensive component on the same page. Each keystroke re-renders everything; use React Hook Form or move the form into its own component.
- `<input value={value}>` without `onChange`. React warns and the field becomes read-only. Either add the handler or use `defaultValue`.
- Validating only in the browser. The schema in the form is for feedback; the backend validates again, always.
- `value={{ user, setUser }}` on a Context provider. A new object every render re-renders every consumer; memoise the value or split the context into one for the value and one for the setter.
- Putting server data in Zustand or Redux and refetching by hand. That is a cache without invalidation; TanStack Query already solves it (see item 6.7).
- Selecting the whole store: `useCart((state) => state)`. The component now re-renders on every change; select the slice you render.
- `React.lazy` without a `Suspense` boundary above it. React throws; put the boundary at the layout level so one fallback covers all pages.
- A `features/` structure where features import each other's internals. Export a small index per feature and lint for deep imports, or the folders become decoration.

## Check yourself

1. Explain why typing in a React Hook Form field does not re-render the surrounding form, and what you give up compared with a controlled input.
2. A Context holds `{ filters, setFilters }` for a search page and every keystroke in the filter box makes the whole results table re-render. Give two different fixes and say when each is appropriate.
3. What decides whether a piece of state belongs in TanStack Query, in `useState`, or in Zustand? Classify: the logged-in user's profile, the open state of a sidebar, the contents of an unsaved cart.
4. Why does a lazily loaded route work in development with `vite` but return a 404 on a deep link in production, and whose job is it to fix?

## Go deeper

- [React Hook Form](https://react-hook-form.com/) · Get Started, then the `useForm` API page; the resolver section covers Zod.
- [React Router](https://reactrouter.com/) · the data-router tutorial walks through nested routes, loaders and lazy routes.
- [react.dev: Managing State](https://react.dev/learn/managing-state) · the official reasoning for lifting state and when Context fits.
- [Zustand](https://zustand.docs.pmnd.rs/) · short enough to read entirely; the selector and slices pages are the important ones.
- [Redux Toolkit](https://redux-toolkit.js.org/) and the [Redux Style Guide](https://redux.js.org/style-guide/) · what modern Redux looks like and the rules a large team follows.

---

Part of [JavaScript & Frontend](../README.md) · items 6.6, 6.8, 6.9
