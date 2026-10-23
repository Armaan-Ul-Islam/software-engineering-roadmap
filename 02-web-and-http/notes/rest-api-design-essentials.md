# REST API design essentials

> **In one sentence:** A good HTTP API models nouns as resources with stable URLs, lets the methods and status codes carry the verbs and the outcomes, paginates with cursors where the data grows, and reports every failure in one machine-readable shape (RFC 9457 Problem Details).

**Why it matters:** APIs outlive the teams that built them. The decisions in this note (how to name things, how to page through them, how to change a field, how to say "no") are the ones you cannot revert once a client depends on them, and the inconsistencies between endpoints are what every integrator remembers about you.

## The idea

**REST as Fielding defined it, and what people build.** Fielding's REST is a set of constraints (client-server, stateless, cacheable, layered, a uniform interface) whose hypermedia constraint says a client should discover what it can do from links in responses, like a browser does. Almost nobody builds that; what the industry calls REST is level 2 of the Richardson maturity model: resources with URLs, HTTP methods used for their meaning, and status codes used honestly. Level 3 (hypermedia links) pays off mainly for public APIs with long-lived third-party clients. Know the difference so you can answer "is this RESTful?" without a fight, then aim deliberately for level 2 done well.

**Resources and naming.** Resources are nouns, URLs identify them, methods act on them. Use plural nouns (`/orders`, `/orders/{orderId}`), lowercase with hyphens, no verbs and no file extensions. Nest only when the child cannot exist without the parent and is always accessed through it (`/orders/{orderId}/items`); otherwise keep it top-level and filter (`/shipments?orderId=…`). Two levels of nesting is the practical limit. An action that is not CRUD becomes a resource too: cancelling an order is `POST /orders/{orderId}/cancellation` (or a state change via `PATCH`), not `POST /cancelOrder`. Use identifiers that are not database sequences (UUIDs or similar) so that IDs reveal nothing and can be generated anywhere.

**Collections.** Filtering is query parameters named after fields (`?status=paid&customerId=…`). Sorting is one parameter with a sign for direction (`?sort=-createdAt,id`); always include a unique tiebreaker so order is deterministic. Pagination has two shapes:

- **Offset** (`?offset=40&limit=20`): trivial to implement and lets clients jump to page N. But `OFFSET 40000` makes the database read and discard forty thousand rows, and when rows are inserted or deleted between pages, items are skipped or repeated.
- **Cursor** (`?limit=20&after=eyJjcmVhdGVkQXQiOi…`): the server returns an opaque token encoding the sort key of the last item (`(createdAt, id)`), and the next query is `WHERE (created_at, id) > (?, ?) ORDER BY created_at, id LIMIT 20`, which uses the index and is stable under concurrent writes. No random access, which clients that page through everything never needed anyway.

Default to cursors for anything that grows; return the next cursor in the body (`"nextCursor"`) or a `Link: <…>; rel="next"` header, and omit total counts unless you can afford a `COUNT(*)` per request.

**Versioning.** The options are a path prefix (`/v1/orders`, what Google's AIPs do), a media type (`Accept: application/vnd.example.v2+json`, what the Zalando guidelines prefer) or a custom header. All of them work; what matters more is making most changes additive (new optional fields, new endpoints), never removing or retyping a field in place, and treating a new major version as a new product with a deprecation schedule for the old one. Clients must ignore unknown fields; say so in the contract.

**Partial updates.** `PUT` replaces the whole representation and is idempotent. `PATCH` changes part of it; use a standard document format rather than an invented one: JSON Merge Patch (`application/merge-patch+json`, RFC 7396) sends the fields to change with `null` meaning "remove", and JSON Patch (`application/json-patch+json`, RFC 6902) sends an operation list for cases where the difference between "absent" and "null" matters. Protect updates against lost writes with `ETag` and `If-Match`, answering `412 Precondition Failed` when the version moved (item 4.5).

**Errors.** Every error response uses the same shape, `Content-Type: application/problem+json`, with the RFC 9457 members: `type` (a URI identifying the error class, `about:blank` when the status code says it all), `title`, `status`, `detail` (human-readable, about this occurrence) and `instance`, plus extension members for validation detail. Spring Framework 6 implements it as `ProblemDetail`, and Spring Boot 3 turns it on for framework exceptions with `spring.mvc.problemdetails.enabled=true`. Validation errors are the one place to go beyond the base members: list the fields.

## Example: an order API surface

| Request | Success | Notes |
|---|---|---|
| `GET /orders?status=paid&sort=-createdAt,id&limit=20` | 200, items plus `nextCursor` | Filtering, deterministic sort, cursor pagination |
| `GET /orders?limit=20&after=<cursor>` | 200 | The next page; the cursor is opaque to clients |
| `POST /orders` | 201 with `Location: /orders/{orderId}` | `Idempotency-Key` header makes retries safe (item 4.1) |
| `GET /orders/{orderId}` | 200 with `ETag` | 404 when unknown; 410 when purged |
| `PATCH /orders/{orderId}` with `If-Match` | 200 | Merge Patch body; 412 when the `ETag` is stale; 409 for an illegal state transition |
| `POST /orders/{orderId}/cancellation` | 201 or 200 | The action as a sub-resource; 409 when already shipped |
| `GET /orders/{orderId}/items` | 200 | Items exist only within an order, so nesting is right |
| `DELETE /orders/{orderId}` | 204 | Idempotent; a second call may return 404 |

A merge-patch request and a validation failure:

```http
PATCH /orders/9f3b2c HTTP/1.1
Host: api.example.com
Content-Type: application/merge-patch+json
If-Match: "orders-9f3b2c-v3"

{"shippingAddress":{"postalCode":"0150","line2":null},"requestedDeliveryDate":"2026-10-20"}
```

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/validation-error",
  "title": "The request body failed validation.",
  "status": 422,
  "detail": "requestedDeliveryDate must not be in the past.",
  "instance": "/orders/9f3b2c",
  "errors": [
    {"field": "requestedDeliveryDate", "code": "past_date", "message": "must not be in the past"}
  ]
}
```

`line2: null` removes the field (merge-patch semantics); `postalCode` is replaced; everything not mentioned is untouched. The `errors` array is an extension member, allowed by the RFC, and the `type` URI is a stable identifier clients can switch on, which the human-readable `title` and `detail` are not.

## Pitfalls

- Verbs in URLs (`/getOrder`, `/orders/create`). They duplicate the method and multiply endpoints. Model the noun; let the method be the verb.
- Offset pagination on a table that grows. Works in the demo, times out at page 2,000, and duplicates rows under concurrent inserts.
- Sorting without a unique tiebreaker. Two rows with the same `createdAt` can swap between pages, and a cursor on a non-unique key either skips or repeats.
- `COUNT(*)` on every list response. The most expensive query in the API, run for a number most clients never show. Offer it as an opt-in or an estimate.
- Deep nesting (`/customers/{id}/orders/{id}/items/{id}/discounts`). Every level is a lookup and an authorisation check; past two, use top-level resources with filters.
- Breaking changes disguised as additive ones: changing a field's type, making an optional field required, tightening validation on existing input. Each is a new major version in disguise.
- Errors as `{"error": "something went wrong"}` with varying shapes per endpoint. Clients write one error handler per endpoint, and then none. One shape, one content type.
- Exposing database sequences as public IDs. They leak volume, enable enumeration, and tie the API to one table.

## Check yourself

1. A client asks for "page 37 of 500" on an endpoint you paginate with cursors. What do you tell them, and what do they gain in exchange?
2. Design the URL and method for "mark this invoice as paid", and explain why `POST /invoices/{id}/pay` is a weaker choice than the alternatives.
3. Two clients `PATCH` the same order within a second. Which headers and status code prevent the second from silently undoing the first?
4. Name the five RFC 9457 members and say which one a client should branch on, and why neither `title` nor `detail` is suitable for that.

## Go deeper

- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/) · a complete, opinionated style guide; adopt it or disagree with it point by point.
- [Google API Improvement Proposals](https://google.aip.dev/) · especially [AIP-158 Pagination](https://google.aip.dev/158), [AIP-185 Versioning](https://google.aip.dev/185) and [AIP-193 Errors](https://google.aip.dev/193).
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) · short, with examples of extension members.
- [Richardson Maturity Model](https://martinfowler.com/articles/richardsonMaturityModel.html) and [Fielding: REST APIs must be hypertext-driven](https://roy.gbiv.com/untangled/2008/rest-apis-must-be-hypertext-driven) · the levels, and the author of REST explaining what level 3 means.
- [Use The Index, Luke: no offset](https://use-the-index-luke.com/no-offset) · why keyset (cursor) pagination is faster, with the SQL.
- [Spring Framework: Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) · `ProblemDetail` and `ErrorResponse` in Spring MVC.

---

Part of [Web & HTTP](../README.md) · items 9.1, 9.2, 9.3
