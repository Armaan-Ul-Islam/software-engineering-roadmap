# TypeScript essentials for backend developers

> **In one sentence:** TypeScript is a structural, inference-heavy type layer that is erased before the code runs, so it catches shape mistakes at compile time but guarantees nothing about data that arrives at runtime, and its most useful feature for modelling is the discriminated union, which the compiler narrows for you.

**Why it matters:** Coming from Java you will over-annotate, reach for classes where a union fits, and trust an `as` cast the way you trust a Java cast. The compiler will not stop you; it will just stop helping. Knowing what the type system checks, what it infers, and what disappears at runtime is the difference between TypeScript that documents your API contract and TypeScript that merely compiles.

## The idea

**Structural, not nominal.** Two types are compatible when their shapes are compatible, regardless of their names. A function taking `{ id: string }` accepts any object with a string `id`, including instances of unrelated classes. Interfaces are not contracts a class must declare; they are shapes anything can satisfy. The one place names seem to matter is the excess-property check on object literals: `const customer: Customer = { id: "1", nmae: "Ada" }` is an error, because a typo in a literal is almost always a bug.

**Inference does most of the work.** `const port = 8080` has type `8080` (a literal type), `let port = 8080` has type `number`, and return types, array element types and callback parameter types are inferred from context. Annotate function parameters and public API boundaries; let the compiler infer locals. If you find yourself writing `const items: Array<string> = []`, that one is needed (an empty array infers `never[]` otherwise); most others are noise.

**`strict` is not optional.** `"strict": true` turns on `strictNullChecks` (so `string` does not include `null` or `undefined`), `noImplicitAny`, `strictFunctionTypes`, `strictPropertyInitialization`, `useUnknownInCatchVariables` and a few more. Without it, TypeScript is roughly Java with every reference nullable and no warning. Add `noUncheckedIndexedAccess` so that `array[index]` has type `T | undefined` (see item 2.5).

**`type` and `interface`.** `interface` declares an object shape, can be extended, and merges declarations with the same name. `type` is an alias for any type, including unions, intersections, tuples and mapped types. Use `interface` for object shapes that others may extend and `type` for everything else; the compiler treats them the same where both apply.

**Unions and narrowing.** `string | number` is a union. The compiler narrows a union inside `if`, `switch` and ternaries using `typeof`, `instanceof`, `in`, equality checks, truthiness and user-defined type predicates (`function isCustomer(value: unknown): value is Customer`). A **discriminated union** is a union of object types that share a literal-typed field such as `status: "ok" | "error"`; a `switch` on that field narrows each branch to one member, and a `default` branch that assigns the value to `never` makes the switch exhaustive: adding a variant later becomes a compile error at every incomplete switch.

**`unknown`, `any`, `never`.** `any` turns the checker off for that value and for everything it flows into. `unknown` is the safe version: anything can be assigned to it, but you can do nothing with it until you narrow it. Use `unknown` for `JSON.parse` results, `catch` variables and untyped input. `never` is the empty type: the return type of a function that always throws, and the type a union narrows to when every member has been handled.

**Generics** work as in Java but infer from arguments: `function firstOrUndefined<T>(items: T[]): T | undefined` is called as `firstOrUndefined(customers)` without `<Customer>`. Constrain with `extends`: `<T extends { id: string }>`. Generic *types* such as `ApiResult<T>` below parameterise data shapes the same way.

**Utility types worth knowing.** `Partial<T>` (all optional, for patches), `Required<T>`, `Readonly<T>`, `Pick<T, "id" | "name">`, `Omit<T, "password">`, `Record<string, number>`, `ReturnType<typeof createClient>`, `Parameters<F>`, `Awaited<Promise<T>>`, `NonNullable<T>`. They are built from mapped types (`{ [Key in keyof T]?: T[Key] }`) and conditional types (`T extends U ? X : Y`), which you can read about when you need to write your own.

**What is erased.** Interfaces, type aliases, annotations, generics, `as` casts, `!` non-null assertions and `satisfies` all vanish at compile time. `tsc` emits plain JavaScript (or, with Vite and esbuild, the types are stripped without even being checked). Consequences: you cannot `instanceof` an interface, `typeof` only knows the eight JavaScript types, and `response.json() as Customer` performs no check at all. Classes, `enum` values and decorators do survive. For data that enters at runtime, validate at the boundary (item 2.4).

## Example: an API response as a discriminated union

```typescript
interface Customer {
  id: string;
  name: string;
  email: string;
}

interface ProblemDetails {
  type?: string;
  title: string;
  status: number;
  detail?: string;
}

type ApiResult<T> =
  | { status: "ok"; data: T }
  | { status: "error"; problem: ProblemDetails }
  | { status: "unreachable"; cause: unknown };

async function fetchCustomer(customerId: string): Promise<ApiResult<Customer>> {
  let response: Response;
  try {
    response = await fetch(`/api/customers/${encodeURIComponent(customerId)}`);
  } catch (cause) {
    return { status: "unreachable", cause };
  }
  if (!response.ok) {
    return { status: "error", problem: (await response.json()) as ProblemDetails };
  }
  return { status: "ok", data: (await response.json()) as Customer };
}

function describe(result: ApiResult<Customer>): string {
  switch (result.status) {
    case "ok":
      return `Customer ${result.data.name} <${result.data.email}>`;
    case "error":
      return `${result.problem.status}: ${result.problem.title}`;
    case "unreachable":
      return "The server could not be reached";
    default: {
      const unhandled: never = result;
      return unhandled;
    }
  }
}
```

Inside `case "ok"`, `result` has type `{ status: "ok"; data: Customer }`, so `result.data` is allowed and autocompletes. Outside the switch it is not:

```typescript
function wrong(result: ApiResult<Customer>): string {
  return result.data.name;
}
// error TS2339: Property 'data' does not exist on type 'ApiResult<Customer>'.
//   Property 'data' does not exist on type '{ status: "error"; problem: ProblemDetails; }'.
```

Add a fourth variant, `{ status: "timeout" }`, and every exhaustive switch reports where it needs updating:

```text
error TS2322: Type '{ status: "timeout"; }' is not assignable to type 'never'.
```

Compare with the Java version: a sealed interface with three records and a `switch` with pattern matching gives the same exhaustiveness, but needs three class declarations and nominal subtyping. The TypeScript version is three object shapes and one literal field.

The two `as` casts are the honest weak point. They say "I trust the server to send this shape". If that trust is misplaced, the failure is a `TypeError` far from the fetch. Replace them with a schema parse (Zod, Valibot) or with types generated from the backend's OpenAPI document when the contract matters.

## Pitfalls

- `as` to silence an error. A cast changes the type the compiler believes, not the value. If you need a cast outside the I/O boundary, the types upstream are wrong.
- `any` leaking from one untyped library. `any` is contagious: every value derived from it is `any`. Wrap untyped inputs in a function that returns a proper type, and check with `noImplicitAny`.
- Optional everything. `interface Customer { id?: string; name?: string }` because "the API might not send it" moves every null check to every call site. Model the states instead: a union of `Draft` and `Saved` says which fields exist when.
- Enums. TypeScript `enum` generates runtime objects with surprising semantics (numeric enums are bidirectional). A union of string literals, `type Status = "active" | "suspended"`, is lighter, erases cleanly and narrows the same way.
- Expecting `instanceof` or `typeof` to check an interface. They cannot; write a type predicate or use a schema.
- Trusting the build to type-check. Vite and esbuild strip types without checking them; run `tsc --noEmit` in CI or the red squiggles stay in the editor only.
- Treating the catch variable as `Error`. Under `strict` it is `unknown`; narrow with `instanceof Error` before reading `.message`.

## Check yourself

1. A Java colleague says "an interface that nobody implements is useless". Why is that false in TypeScript, and what does it imply about how libraries accept your objects?
2. Why does `const parsed = JSON.parse(text) as Customer; parsed.email.toLowerCase()` compile cleanly and still throw at runtime? What would make the failure happen at the boundary instead?
3. You add a variant to a discriminated union used in twelve files. Which switches will the compiler flag, and which will it miss?
4. What does `Partial<Customer>` express about a PATCH endpoint that `Customer` with optional fields does not, and why is that distinction useful to the reader of the code?

## Go deeper

- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html) · short enough to read end to end; the Everyday Types, Narrowing and Generics chapters cover this note.
- [Handbook: Narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html) · every narrowing form, including discriminated unions and the `never` exhaustiveness trick.
- [TypeScript for Java/C# Programmers](https://www.typescriptlang.org/docs/handbook/typescript-in-5-minutes-oop.html) · the official page on structural typing for people arriving from nominal languages.
- [Handbook: Utility Types](https://www.typescriptlang.org/docs/handbook/utility-types.html) · the reference list with examples.
- [Total TypeScript Essentials](https://www.totaltypescript.com/books/total-typescript-essentials) · free online book; the chapters on unions, narrowing and the `unknown` type are the best practical treatment.

---

Part of [JavaScript & Frontend](../README.md) · items 2.1, 2.2, 2.3
