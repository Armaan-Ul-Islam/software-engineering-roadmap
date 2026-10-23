# API design guidelines: resources, errors, pagination, idempotency and evolution

> **In one sentence:** Treat an API as a product: model resources around what consumers do, keep naming and behaviour consistent across the whole surface, return machine-readable errors (Problem Details), make retries safe with idempotency keys, page with cursors, and evolve additively under a written deprecation policy, because a new version is the expensive fallback, not the plan.

**Why it matters:** An API outlives the code behind it. A bad field name shipped to a partner is permanent in a way a bad class name never is, and every inconsistency ("why does `/orders` paginate differently from `/customers`?") is paid for by every consumer, forever. Interviewers probing API design are looking for whether you think about the consumer, the error path and change over time, not just the happy `GET`.

## The idea

**An API is a product.** Design from the consumer's job, not from your tables. Write the conventions down once (Zalando's guidelines are a good base) and apply them to every endpoint, so that the second endpoint is predictable from the first. Publish an OpenAPI document before the code (item 8.3) and document every response, including the errors, with examples.

**Resources and naming.** Plural nouns for collections (`/orders`), an identifier for an item (`/orders/{orderId}`), nesting only for true containment (`/orders/{orderId}/lines`). Actions that are not plain CRUD are state transitions with rules, so give them a name rather than letting clients `PATCH` a status: `POST /orders/{orderId}/cancellation` or, in Google's style, `POST /orders/{orderId}:cancel`. Identifiers are opaque strings, never sequential integers that can be enumerated. Pick one JSON casing (camelCase or snake_case) and never mix; timestamps are ISO 8601 in UTC; money is a decimal string with a currency (`{"amount": "12.50", "currency": "EUR"}`), never a floating-point number.

**Collections.** Filter with query parameters named after fields (`?status=PLACED&customerId=...`), sort with an explicit field and direction (`?sort=createdAt,desc`), and cap `limit`. Offset pagination (`?page=37&size=50`) is simple and wrong for anything large: the database reads and discards every earlier row, and concurrent inserts shift the pages so clients see duplicates and gaps. Keyset (cursor) pagination orders by a unique key, returns an opaque `nextCursor`, and the client passes it back; every page costs the same and nothing shifts. Give up random access to page 37, which almost nobody uses.

**Errors.** The status code classifies (400 malformed, 401 and 403, 404, 409 conflict, 422 valid syntax but unprocessable, 429 with `Retry-After`, 500), and the body explains, in one shape for the whole API: Problem Details (RFC 9457), served as `application/problem+json`, with `type` (a URI you document), `title`, `status`, `detail`, `instance`, and extensions such as a list of field violations and a trace id. Spring Framework 6 has `ProblemDetail` built in; returning one from an `@ExceptionHandler` renders it correctly, and `spring.mvc.problemdetails.enabled=true` makes Spring MVC's own errors use the same shape.

**Idempotency.** `GET`, `PUT` and `DELETE` are idempotent by definition; implement them so (a second `DELETE` returns 404 or 204, never 500). `POST` that creates is not, and clients retry after timeouts, so accept an `Idempotency-Key` header: store the key with a hash of the request and the response for a retention window, return the stored response on a repeat, and reject the same key with a different payload (422). The IETF HTTP API working group has a draft standardising the header. Any payment or order endpoint without this will create duplicates in production.

**Versioning, and avoiding it.** The strategies and their trade-offs:

| Strategy | Example | For | Against |
|---|---|---|---|
| URI | `/v2/orders` | visible, easy to route and cache | versions the whole API at once; invites big-bang breaks |
| Media type or header | `Accept: application/vnd.shop.v2+json` | clean URIs, per-resource versions | invisible in browsers and logs; caches need `Vary` |
| Query parameter | `?version=2` | debuggable | ugly, cache-unfriendly, easy to forget |
| Date pinned per client | Stripe's `Stripe-Version` header carrying a release date | consumers upgrade when ready, one change at a time | expensive to implement: the server keeps every transformation |

Zalando's and Google's guidance agree on the main point: the best version strategy is not needing one. Change additively, and version only when a breaking change is unavoidable.

**Additive evolution and deprecation.** Compatible: adding an optional field or endpoint, adding an optional request parameter, relaxing a validation. Breaking: removing or renaming anything, changing a type or meaning, making an optional field required, tightening validation, changing an error code clients branch on. Adding an enum value is breaking for clients that `switch` exhaustively, so document that enums are open or treat additions as breaking. Consumers must be tolerant readers and ignore unknown fields (Spring Boot's Jackson configuration does this by default; plain Jackson does not). To retire something: announce it, add the `Deprecation` header and a `Sunset` header (RFC 8594) with the removal date, link to the migration notes, watch usage per consumer, and remove on the date only when traffic is gone. Run the existing consumers' contract tests (item 8.3) against every provider change.

## Example: a checklist, and one field's evolution

The checklist a reviewer walks through before an endpoint ships:

1. Product
   1.1 The endpoint maps to a consumer job, not to a table.
   1.2 The OpenAPI document was reviewed before the implementation.
   1.3 Every response, including each error, has an example.
2. Resources and naming
   2.1 Plural nouns, no verbs except documented custom actions.
   2.2 One JSON casing, ISO 8601 UTC timestamps, money as amount string plus currency.
   2.3 Identifiers are opaque strings.
3. Collections
   3.1 Filters are named after fields; `sort` is explicit; `limit` is capped.
   3.2 Cursor pagination with an opaque `nextCursor`, ordered by a unique key.
4. Errors
   4.1 Problem Details with documented `type` URIs.
   4.2 Validation errors list every violation, not only the first.
   4.3 No stack traces, no internal class names.
5. Safety
   5.1 `PUT` and `DELETE` are idempotent; creating `POST`s accept `Idempotency-Key`.
   5.2 Rate limits answer 429 with `Retry-After`.
6. Evolution
   6.1 Only additive changes without a version bump; a written list of what counts as breaking.
   6.2 `Deprecation` and `Sunset` headers, usage tracked per consumer, removal date documented.
   6.3 Existing consumers' contract tests run in CI.

A validation error in that shape:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "2 fields are invalid",
  "instance": "/orders",
  "errors": [
    {"field": "lines[0].quantity", "message": "must be at least 1"},
    {"field": "customerId", "message": "must be a UUID"}
  ],
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

Now the evolution scenario. Today an order looks like this:

```json
{"id": "ord_01JAZ3", "status": "PLACED", "total": 1250.00, "createdAt": "2026-10-24T08:15:30Z"}
```

**Adding a field.** Delivery instructions are needed. Add `"deliveryInstructions"` as an optional string, absent or `null` when not set. Existing clients ignore it, new clients use it, no version changes. The only risk is a consumer that rejects unknown fields; your compatibility policy must state that new fields may appear at any time, so that such a consumer is in breach, not you.

**Changing a type.** Multi-currency arrives, and `total` must become `{"amount": "1250.00", "currency": "EUR"}`. Same name, different type: every client parsing a number breaks. Three ways out:

1. Add a new field `totalMoney` with the object shape next to `total`, mark `total` deprecated in the OpenAPI document, send `Deprecation` and `Sunset` on responses, remove `total` after the sunset date once usage is zero. Additive, no version, two fields for a while.
2. Ship `/v2/orders` where `total` has the new shape. Everyone migrates at once, and every other difference between v1 and v2 rides along; expensive for the consumer with a yearly release cycle.
3. Pin behaviour per client by version date, Stripe style, and transform the response for old dates. Best for consumers, most work for you.

For one field, option 1 wins. Option 2 is for when breaking changes have accumulated and a clean break is cheaper than carrying them. Option 3 is for an API that is the product.

## Pitfalls

- Exposing the database: table names as resources, columns as fields, integer ids. Every schema change becomes a public break.
- Offset pagination on a growing table, or a sort without a unique tie-breaker, which produces duplicates and gaps between pages even with keyset.
- `200 OK` with `{"error": "..."}` in the body, or a different error shape per endpoint. Clients end up with a parser per endpoint.
- `POST` without idempotency on anything a client will retry. The duplicate payment is found by the customer.
- Enum values added silently. The client's exhaustive `switch` throws on the first new value in production.
- Deprecating without usage data, then removing on the date while the largest customer still calls.
- Booleans that should be enums (`isExpress` becomes untenable the day a third option appears) and floats for money.
- A `/v1` prefix from day one and then breaking changes inside v1 "because it was only a small required field". The prefix is harmless; the break is not.

## Check yourself

1. A client times out on `POST /payments` and retries with the same `Idempotency-Key`. What must the server have stored, what does it return, and what does it return if the retry carries a different amount?
2. Why can offset pagination skip or duplicate rows under concurrent inserts, and which property of the sort key does keyset pagination require to avoid the same problem?
3. Classify as compatible or breaking, and say for whom: adding an enum value; adding an optional request field; making a response field nullable that was never null before; renaming `createdAt` to `created_at`.
4. You must change `total` from a number to an object, and your biggest consumer is a mobile app with a quarterly release. Compare the three strategies for that consumer.

## Go deeper

- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/) · the most complete public guideline; its [compatibility chapter](https://opensource.zalando.com/restful-api-guidelines/#compatibility) is the policy this note summarises.
- [Google API Improvement Proposals](https://google.aip.dev/) · resource-oriented design, custom methods, pagination and errors as numbered, reviewable proposals.
- [Microsoft REST API Guidelines](https://github.com/microsoft/api-guidelines) · a second large-organisation guideline; compare where it differs from Zalando and decide deliberately.
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457) · the error format; short and readable.
- [RFC 8594: The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594) · the header that announces when a resource will stop working.
- [Stripe: APIs as infrastructure, future-proofing Stripe with versioning](https://stripe.com/blog/api-versioning) · how date-based versioning works internally and what it costs.
- [Markus Winand: We need tool support for keyset pagination](https://use-the-index-luke.com/no-offset) · why `OFFSET` is the wrong tool, with the SQL for the alternative.
- [Martin Fowler: Tolerant Reader](https://martinfowler.com/bliki/TolerantReader.html) · the consumer-side half of additive evolution.

---

Part of [Architecture & Craft](../README.md) · items 8.1, 8.2, 8.4
