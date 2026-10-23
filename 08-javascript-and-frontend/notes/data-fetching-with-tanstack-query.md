# Data fetching with TanStack Query

> **In one sentence:** TanStack Query treats data from the server as a cache keyed by what you asked for, shows cached data immediately while refetching it in the background when it is stale, and after a mutation you *invalidate* the affected keys rather than updating the cache by hand, so loading, error, deduplication and refresh logic disappear from your components.

**Why it matters:** Server state is not like component state: it lives elsewhere, is shared by many components, becomes stale the moment it arrives, and arrives asynchronously with failures. Hand-written `useEffect` fetching re-implements a cache badly in every component (see item 6.4 for the race alone). Interviewers for full-stack roles ask how you keep the list fresh after a POST; the answer they want is "invalidate the query", and knowing why is the point of this note.

## The idea

**Server state versus client state.** Client state (is the dialog open, what is typed in the search box) is owned by the UI and is always correct. Server state (the customer list) is owned by the backend; the frontend holds a *copy* that may be out of date. TanStack Query manages the copy: fetching, caching, deduplicating identical requests across components, refetching when stale, retrying failures, and garbage-collecting what nobody is using.

**Queries and keys.** `useQuery({ queryKey, queryFn })` declares a dependency on server data. The `queryKey` is an array that identifies the data and must include every variable the `queryFn` uses: `["customers", "list", { status: "active" }]`, `["customers", "detail", customerId]`. Two components with the same key share one cache entry and one request. Keys are hierarchical so that `["customers"]` matches all of them, which is what makes invalidation precise.

**Staleness and caching.** Data is `fresh` for `staleTime` milliseconds (default 0, so immediately stale) and `stale` afterwards. Stale data is still shown instantly from the cache; it is refetched in the background when a component mounts with that key, when the window regains focus, when the network reconnects, or on an interval you configure. This is stale-while-revalidate. Cache entries with no observers are garbage collected after `gcTime` (default five minutes). Set `staleTime` per query according to how often the data actually changes; a reference table can be fresh for an hour, an order list for a few seconds.

**States.** A query is `pending` (no data yet), `error`, or `success`; separately, its `fetchStatus` says whether a request is in flight. The flags you use most are `isPending` (show a skeleton), `isError` with `error`, and `isFetching` (a small spinner during background refetches, when you want one). The `queryFn` must *throw* on failure; since `fetch` does not throw for HTTP errors, use a wrapper that does.

**Mutations and invalidation.** `useMutation({ mutationFn })` wraps a write. After it succeeds, call `queryClient.invalidateQueries({ queryKey: ["customers"] })`: every query whose key starts with `["customers"]` is marked stale, and those currently on screen refetch. You never compute the new list in the client; the server, which owns the data, is asked again. Returning the invalidation promise from `onSuccess` keeps the mutation in its pending state until the refetch completes, which is usually what you want for a "saving" indicator.

**Optimistic updates** show the result before the server confirms it. In `onMutate`, cancel in-flight refetches for the key, snapshot the cached value, write the optimistic value with `setQueryData`, and return the snapshot; in `onError`, restore the snapshot; in `onSettled`, invalidate. The simpler alternative for a single list is to render the mutation's `variables` as a pending row while `isPending` is true and let invalidation replace it.

**Pagination.** Put the page in the key (`["orders", "list", { page }]`) and pass `placeholderData: keepPreviousData` so the previous page stays on screen while the next loads instead of flashing a spinner. For infinite scroll, `useInfiniteQuery` with `initialPageParam` and `getNextPageParam` accumulates pages and exposes `fetchNextPage` and `hasNextPage`.

## Example: a query and a mutation that invalidates it

`apiFetch` is any function that returns parsed JSON and throws on HTTP errors, such as the wrapper in [fetch, CORS and authentication from the browser](fetch-cors-and-auth-from-the-browser.md).

```tsx
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./apiFetch";

interface Customer {
  id: string;
  name: string;
  email: string;
}

type NewCustomer = Omit<Customer, "id">;

const customerKeys = {
  all: ["customers"] as const,
  list: (status: string) => ["customers", "list", { status }] as const,
  detail: (customerId: string) => ["customers", "detail", customerId] as const,
};

function useCustomers(status: string) {
  return useQuery({
    queryKey: customerKeys.list(status),
    queryFn: () => apiFetch<Customer[]>(`/api/customers?status=${encodeURIComponent(status)}`),
    staleTime: 30_000,
  });
}

function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (newCustomer: NewCustomer) =>
      apiFetch<Customer>("/api/customers", { method: "POST", body: JSON.stringify(newCustomer) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: customerKeys.all }),
  });
}

function CustomerList() {
  const customersQuery = useCustomers("active");
  const createCustomer = useCreateCustomer();

  if (customersQuery.isPending) {
    return <p>Loading customers...</p>;
  }
  if (customersQuery.isError) {
    return <p role="alert">Could not load customers: {customersQuery.error.message}</p>;
  }

  return (
    <>
      <ul>
        {customersQuery.data.map((customer) => (
          <li key={customer.id}>{customer.name}</li>
        ))}
      </ul>
      <button
        disabled={createCustomer.isPending}
        onClick={() => createCustomer.mutate({ name: "Ada Lovelace", email: "ada@example.com" })}
      >
        {createCustomer.isPending ? "Saving..." : "Add Ada"}
      </button>
      {createCustomer.isError && <p role="alert">{createCustomer.error.message}</p>}
    </>
  );
}

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <CustomerList />
    </QueryClientProvider>
  );
}
```

What happens on the click: the POST is sent and `isPending` disables the button. On success, `invalidateQueries` marks every `["customers", ...]` entry stale; the active list is on screen, so it refetches and the new row appears when the GET returns, with no client-side list manipulation. The detail queries are marked stale too and will refetch the next time someone looks at one. If the POST fails, the error is shown and the list is untouched, because nothing in the cache was changed.

Adding a second `<CustomerList />` elsewhere on the page costs nothing: same key, one request, one cache entry. Moving the `status` filter into state and passing it to `useCustomers(status)` gives each filter its own cache entry and switching back is instant.

## Pitfalls

- A `queryFn` that does not throw. `fetch` resolves on a 500, so the query reports success with an error payload as `data`. Throw on `!response.ok`.
- A key that misses a variable the function uses. Two different requests share one cache entry and the UI shows the wrong one. If the function reads it, the key includes it.
- `staleTime: 0` everywhere, then complaining about "too many requests" on window focus. Set `staleTime` to match the data, or disable `refetchOnWindowFocus` for queries where it makes no sense.
- Updating the cache by hand after every mutation instead of invalidating. It duplicates server logic (sorting, filtering, computed fields) in the client and drifts. Invalidate; reserve `setQueryData` for optimistic updates and for seeding a detail from a list.
- Treating the hook as a replacement for client state. Form input, selected tab and dialog visibility are not server state; keep them in `useState`.
- Putting the `QueryClient` inside a component without `useState` or a module-level constant. A new client per render throws the cache away every time.
- Showing a full-page spinner on `isFetching`. Background refetches are frequent and the data is already on screen; use `isPending` for the first load and a subtle indicator, if any, for refetches.

## Check yourself

1. Two components on one page call `useQuery` with the key `["customers", "list", { status: "active" }]`. How many requests are sent on mount, and what happens when a third component mounts with that key ten seconds later with `staleTime: 30_000`?
2. After a successful `DELETE /api/customers/42`, which keys would you invalidate and why is invalidating `["customers"]` safe even though it also marks unrelated customer details stale?
3. Why is "throw on HTTP error" a requirement for the `queryFn`, and what would the component show if you forgot it?
4. Write down the four steps of an optimistic update and explain why `cancelQueries` is the first one.

## Go deeper

- [TanStack Query](https://tanstack.com/query/latest) · the documentation; read "Important Defaults" first, then the guides on queries, mutations and query invalidation.
- [TanStack Query: Important Defaults](https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults) · `staleTime`, `gcTime`, refetch triggers and retries, in one page.
- [TanStack Query: Optimistic Updates](https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates) · both approaches, with the cancel, snapshot, rollback sequence.
- [TkDodo: Practical React Query](https://tkdodo.eu/blog/practical-react-query) · the maintainer's guide to defaults, keys and where server state belongs.
- [TkDodo: Effective React Query Keys](https://tkdodo.eu/blog/effective-react-query-keys) · the key factory pattern used above and why keys are hierarchical.
- [TkDodo: Mastering Mutations in React Query](https://tkdodo.eu/blog/mastering-mutations-in-react-query) · invalidation versus direct updates, callbacks, and awaiting the refetch.

---

Part of [JavaScript & Frontend](../README.md) · item 6.7
