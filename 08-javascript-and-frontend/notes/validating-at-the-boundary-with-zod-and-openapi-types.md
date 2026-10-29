# Validating at the boundary with Zod and OpenAPI-generated types

> **In one sentence:** TypeScript types vanish at compile time, so data that crosses a boundary (an HTTP response, a form, an environment variable) must be checked at runtime by a schema library such as Zod, or come through a client whose types were generated from the backend's OpenAPI document and whose contract the backend therefore cannot silently break; dates, pagination and Problem Details errors are the three parts of that contract that go wrong most often.

**Why it matters:** The classic frontend production bug is a `TypeError: cannot read properties of undefined` thrown three components away from the `fetch` that received an unexpected shape. The type checker said everything was fine because the `as OrderDto` cast told it so. The same mistake on the Node side lets a malformed request reach the database. Every boundary needs one of two things: a runtime check, or a generated contract that is rebuilt whenever the other side changes.

## The idea

**Why types are not enough.** `const order = (await response.json()) as Order` is a promise, not a check. Item 2.1 covers why: TypeScript is erased, and `response.json()` returns `any`. Inside your own code, types are trustworthy because the compiler verified every producer. At the edge, the producer is a server, a user or an environment, none of which the compiler saw.

**Schema libraries.** Zod (and the smaller Valibot, which has the same idea with a tree-shakeable API) lets you declare a schema once and get two things from it: a runtime parser and a static type via `z.infer`. `schema.parse(value)` throws on mismatch; `schema.safeParse(value)` returns `{ success, data }` or `{ success, error }` so you can report without exceptions. Schemas can transform while validating (`z.iso.datetime().transform((value) => new Date(value))`), apply defaults, and compose. Use them for request bodies in Node (Fastify also accepts JSON Schema natively, see item 3.4), for `import.meta.env` and `process.env` at startup, for `localStorage` reads, and for responses from APIs you do not own.

**Generated types.** For an API you do own, do not describe it twice. Spring Boot with springdoc-openapi publishes `/v3/api-docs`; `openapi-typescript` turns that document into a `.d.ts` file of `paths`, `operations` and `components["schemas"]`; `openapi-fetch` is a thin `fetch` wrapper that uses those types so the path, parameters, body and every documented response are checked at compile time. The generated file is committed or built in CI, and a backend change that breaks the frontend now fails the type check instead of a user's session. Generated types do not validate at runtime; they encode what the server promised. Pair them with a schema only where the server is outside your control.

**Dates over JSON.** JSON has no date type. Jackson serialises `Instant` and `OffsetDateTime` as ISO 8601 strings (`2026-10-29T07:15:00Z`) when `WRITE_DATES_AS_TIMESTAMPS` is off, which Spring Boot does by default. JavaScript's `Date` is an instant with no zone, so it maps cleanly to `Instant` and `OffsetDateTime` but not to `LocalDate`: `new Date("2026-10-29")` is parsed as UTC midnight and displays as 28 October in the Americas. Keep `LocalDate` values as strings in the frontend and format them with `Intl.DateTimeFormat` only when rendering. Convert to `Date` at the boundary, never in components.

**Pagination.** Spring Data's `Page<T>` serialises as `{ content, totalElements, totalPages, number, size, ... }`; with `spring.data.web.pageable` defaults the client sends `?page=0&size=20&sort=createdAt,desc`. Spring Data 3.3 added `PagedModel` and the `spring.data.web.pageable.serialization-mode=via_dto` setting so the JSON shape is stable; the raw `PageImpl` serialisation is marked unstable and logs a warning. Whatever the shape, declare it once (in the OpenAPI document or a Zod schema) and have components consume `content` plus a cursor or page number, not the whole object.

**Problem Details.** RFC 9457 defines the error body `{ type, title, status, detail, instance }` with media type `application/problem+json`. Spring Boot emits it from `ResponseEntityExceptionHandler` when `spring.mvc.problemdetails.enabled=true`, and `ErrorResponseException` lets you throw one. On the client, read the body once in the fetch wrapper, map it to a typed error, and let components switch on `status` or `type` rather than parsing `detail` strings.

## Example: a Zod schema for an API you do not own

```typescript
import { z } from "zod";

const OrderSchema = z.object({
  id: z.string(),
  customerId: z.string().min(1),
  amount: z.number().positive(),
  status: z.enum(["NEW", "PAID", "SHIPPED"]),
  createdAt: z.iso.datetime({ offset: true }).transform((value) => new Date(value)),
  tags: z.array(z.string()).default([]),
});

type Order = z.infer<typeof OrderSchema>;

function parseOrder(payload: unknown): Order {
  const result = OrderSchema.safeParse(payload);
  if (!result.success) {
    throw new Error(`Invalid order: ${z.prettifyError(result.error)}`);
  }
  return result.data;
}

const good = parseOrder({ id: "1", customerId: "c-1", amount: 42.5, status: "NEW", createdAt: "2026-10-29T08:15:00+01:00" });
console.log(good.createdAt instanceof Date, good.createdAt.toISOString(), good.tags);

try {
  parseOrder({ id: 1, customerId: "", amount: "42.5", status: "CANCELLED", createdAt: "yesterday" });
} catch (error) {
  console.log((error as Error).message);
}
```

Run with `npx tsx order-schema.ts` (Zod 4.6):

```text
true 2026-10-29T07:15:00.000Z []
Invalid order: ✖ Invalid input: expected string, received number
  → at id
✖ Too small: expected string to have >=1 characters
  → at customerId
✖ Invalid input: expected number, received string
  → at amount
✖ Invalid option: expected one of "NEW"|"PAID"|"SHIPPED"
  → at status
✖ Invalid ISO datetime
  → at createdAt
```

`Order` is inferred as `{ id: string; customerId: string; amount: number; status: "NEW" | "PAID" | "SHIPPED"; createdAt: Date; tags: string[] }`. Note `createdAt: Date` and `tags: string[]` (not optional): the inferred type is the output of the schema, after transforms and defaults.

## Example: types generated from a Spring OpenAPI document

Given a document with one operation, `getOrder`, returning `OrderDto` on 200 and `ProblemDetail` on 404 (the shape springdoc produces for a controller returning `ResponseEntity<OrderDto>`):

```bash
npx openapi-typescript http://localhost:8080/v3/api-docs -o src/api.d.ts
```

The relevant part of the output (openapi-typescript 7.13):

```typescript
export interface components {
    schemas: {
        OrderDto: {
            id: string;
            customerId: string;
            amount: number;
            /** @enum {string} */
            status: "NEW" | "PAID" | "SHIPPED";
            /** Format: date-time */
            createdAt: string;
        };
        ProblemDetail: {
            /** Format: uri */
            type?: string;
            title?: string;
            /** Format: int32 */
            status?: number;
            detail?: string;
            /** Format: uri */
            instance?: string;
        };
    };
}
```

`createdAt` is a `string`: the generator preserves the wire format, and converting to `Date` is your job. A typed client on top:

```typescript
import createClient from "openapi-fetch";
import type { paths } from "./api.d.ts";

const client = createClient<paths>({ baseUrl: "http://localhost:8080" });

export async function loadOrder(id: string) {
  const { data, error, response } = await client.GET("/api/orders/{id}", { params: { path: { id } } });
  if (error) {
    return { kind: "problem" as const, status: response.status, title: error.title };
  }
  return { kind: "order" as const, amount: data.amount, createdAt: new Date(data.createdAt) };
}
```

`data` is typed from the 200 response and `error` from the 404 (`ProblemDetail`), so the compiler forces the `if (error)` branch before `data` can be read. Rename `amount` to `total` on the Spring side, regenerate, and `tsc` reports:

```text
client.ts(11,49): error TS2339: Property 'total' does not exist on type '{ id: string; customerId: string; amount: number; status: "NEW" | "PAID" | "SHIPPED"; createdAt: string; }'.
```

That is the whole point: the contract break is a compile error on the day it happens, not a support ticket.

## Pitfalls

- Validating twice. A Zod schema for every response of your own API duplicates the OpenAPI document and drifts from it. Generated types for your API, schemas for external input.
- Committing a hand-edited `api.d.ts`. Regenerate in CI (or a `prebuild` script) and fail the build when the file differs from what the current backend publishes; a hand edit hides exactly the break you wanted to catch.
- `z.date()` on JSON input. JSON carries strings; `z.date()` expects a `Date` instance and rejects every response. Use `z.iso.datetime()` with a transform, or `z.coerce.date()` when you accept its looser parsing.
- `new Date("2026-10-29")` for a `LocalDate`. Parsed as UTC midnight, shown as the previous day west of Greenwich. Keep calendar dates as strings.
- Reading `response.json()` on a 204 or on an error whose body is HTML (a proxy timeout page). Check `response.ok` and `content-type` before parsing; the wrapper in item 4.4 shows the shape.
- Inferring the schema type with `z.input` when you meant `z.infer`. Input is the shape before transforms (`createdAt: string`), output is after (`createdAt: Date`). Components want the output type.
- Spring's `Page` shape changing between versions. Pin the serialization mode (`via_dto`) and generate types from it, or expose your own `{ items, nextCursor }` DTO, which also ages better than offset pagination.
- A nullable field in Java (`String note` without `@NotNull`) generated as required in TypeScript, or the reverse. Annotate DTOs with Bean Validation or `@Schema(requiredMode = ...)` so springdoc emits `required` correctly; otherwise every property is optional and every access needs a null check.

## Check yourself

1. A response is cast with `as OrderDto` and a field the backend removed is read two screens later. Describe where the failure surfaces and what each of the two approaches in this note would have done instead.
2. Why does `z.infer<typeof OrderSchema>` give `createdAt: Date` while the generated `components["schemas"]["OrderDto"]` gives `createdAt: string`? Which one should a component receive?
3. A customer in Los Angeles sees their invoice dated one day early. What JSON value and what line of frontend code together cause it?
4. Your fetch wrapper receives a 400 with `content-type: application/problem+json` and `type: "https://example.com/problems/insufficient-stock"`. Which field should the component switch on to show a specific message, and why not `detail`?

## Go deeper

- [Zod](https://zod.dev/) · the reference; the sections on transforms, `safeParse` and error formatting cover what the example uses.
- [openapi-typescript](https://openapi-ts.dev/) · generating types and the `openapi-fetch` client; the CLI page explains running it against a live `/v3/api-docs` URL.
- [RFC 9457: Problem Details](https://www.rfc-editor.org/rfc/rfc9457.html) · short, and it defines the exact meaning of `type` versus `title` versus `detail`.
- [MDN: Intl](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl) · `Intl.DateTimeFormat` with a `timeZone` option is how a calendar date is rendered without ever becoming a `Date`.
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) · the chapter on `unknown` explains why a boundary value should start as `unknown`, not `any`.

---

Part of [JavaScript & Frontend](../README.md) · items 2.4, 8.4
