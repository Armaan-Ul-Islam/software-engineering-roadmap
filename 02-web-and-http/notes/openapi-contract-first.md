# OpenAPI and contract-first API development

> **In one sentence:** An OpenAPI document is a machine-readable contract for an HTTP API (paths, operations, parameters, schemas, responses, security), and the decision that matters is whether that contract is the source your code is generated from and validated against, or a by-product that drifts.

**Why it matters:** Integrations fail at the seams: a field that is nullable in practice but required in the docs, a date format that differs between two endpoints, an enum value the client has never heard of. A contract that is reviewed, versioned and enforced at build time and at runtime turns those into compile errors and 400s instead of production incidents, and it is what lets a frontend team start work before the backend exists.

## The idea

**What OpenAPI describes.** `info` (title and the API's version), `servers`, and `paths`: for each path, operations (`get`, `post`, `patch`, ...) with an `operationId`, `parameters` (path, query, header, cookie), a `requestBody` per media type, and `responses` keyed by status code, each with headers and content schemas. Reusable pieces live under `components` (`schemas`, `parameters`, `responses`, `headers`, `securitySchemes`); `security` says which scheme (bearer token, API key, OAuth 2 flows, OpenID Connect) protects which operation; `tags` group operations for documentation and generators. Schemas are JSON Schema: in OpenAPI 3.1 the full 2020-12 dialect, so nullability is `type: [string, "null"]` rather than 3.0's `nullable: true`. OpenAPI 3.1 also added a top-level `webhooks` section for the calls your API makes to its clients (item 9.6). It does not describe behaviour, ordering, rate limits or the meaning of errors beyond the status code; those go in `description` fields and in a Problem Details schema (item 9.3).

**Code-first versus contract-first.**

- *Code-first*: annotate the controllers and let a library such as springdoc generate the document from the running application. Fast when one team owns both ends and the document stays in step with the code by construction. But the design is whatever the code happened to do, review happens after the fact, clients cannot start early, and the generated schemas leak implementation details (Java type names, nullability by accident, inconsistent naming across controllers).
- *Contract-first*: write the YAML first, review it as the design, generate server interfaces and clients from it, validate traffic against it, publish it. Fits several teams or external consumers, public and partner APIs, polyglot clients, and any API you want to review as a design artefact. The cost: the YAML is code you maintain, generators impose structure on your controllers, and 3.1 support in tooling arrived later than the specification and still has gaps.
- *Hybrid*: generate from code, commit the generated document, and diff it in CI against the last release so that any breaking change fails the build. Reasonable for internal services with a handful of consumers.

**Generating.** OpenAPI Generator (CLI, Maven and Gradle plugins) has a `spring` generator that produces annotated interfaces; with `interfaceOnly=true` you implement them in your own `@RestController`, and the compiler tells you when the contract changed. Typed clients come from the `java` generator (with `library` set to the HTTP client you use) and from `typescript-fetch` or `typescript-axios`. Generate into the build output at compile time and never commit generated code: the document is the source.

**Validating at runtime.** Generated interfaces carry bean-validation annotations for the basics (required, ranges, patterns), but not for everything a schema can express. Dedicated validators check requests and responses against the document itself: swagger-request-validator in Java (with adapters for Spring MVC filters, MockMvc, REST Assured and WireMock), express-openapi-validator in Node, and Prism as a validating proxy or mock server. Use request validation in production (a violation becomes a 400 before your code runs) and response validation in tests, where every MockMvc response is checked against the contract. Response validation in production belongs in log-only mode: your own schema bug should not become a user-facing 500.

**Versioning the document.** `info.version` is the API's version; keep it semantic (additive changes bump the minor). The file lives with the server (or in a contracts repository with clear ownership), CI runs a breaking-change diff against the last released version (openapi-diff or oasdiff) and a linter (Spectral with a ruleset for naming, required descriptions, Problem Details on error responses, pagination parameters), and rendered docs are published per release. Breaking changes include a new required request field, a removed or retyped field, a narrowed response enum, and, for clients that switch exhaustively, a new enum value in a response; say in the contract that unknown enum values must be tolerated, or make such enums open (`x-extensible-enum`, as the Zalando guidelines do). Keep `operationId`s stable, because generated method names come from them.

**Reviewing it.** Review the YAML diff like code, with a checklist: consistent resource naming and pagination (item 9.2); every error response declared with `application/problem+json`; `required` versus nullable as intended; formats (`uuid`, `date-time`, `int64`, decimals as strings) chosen on purpose; a security scheme on every operation; examples that validate against their schemas; descriptions that say what the operation does to state. Lint before a human reads it.

## Example: a minimal OpenAPI 3.1 document for one resource

```yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.2.0
servers:
  - url: https://api.example.com/v1
security:
  - bearerAuth: []
paths:
  /orders/{orderId}:
    parameters:
      - name: orderId
        in: path
        required: true
        schema:
          type: string
          format: uuid
    get:
      operationId: getOrder
      summary: Fetch one order with its lines
      responses:
        "200":
          description: The order
          headers:
            ETag:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "404":
          $ref: "#/components/responses/Problem"
    patch:
      operationId: updateOrder
      summary: Change the mutable fields of an order
      parameters:
        - name: If-Match
          in: header
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema:
              $ref: "#/components/schemas/OrderPatch"
      responses:
        "200":
          description: The updated order
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "412":
          $ref: "#/components/responses/Problem"
        "422":
          $ref: "#/components/responses/Problem"
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    Order:
      type: object
      required: [id, status, lines, createdAt]
      properties:
        id:
          type: string
          format: uuid
        status:
          type: string
          enum: [pending, paid, shipped, cancelled]
        requestedDeliveryDate:
          type: [string, "null"]
          format: date
        lines:
          type: array
          items:
            $ref: "#/components/schemas/OrderLine"
        createdAt:
          type: string
          format: date-time
    OrderLine:
      type: object
      required: [sku, quantity, unitPrice]
      properties:
        sku:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPrice:
          type: string
          description: Decimal amount as a string, for example "199.00", to keep binary floating point out of money.
    OrderPatch:
      type: object
      properties:
        requestedDeliveryDate:
          type: [string, "null"]
          format: date
    Problem:
      type: object
      properties:
        type: { type: string, format: uri }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        instance: { type: string }
  responses:
    Problem:
      description: An RFC 9457 problem
      content:
        application/problem+json:
          schema:
            $ref: "#/components/schemas/Problem"
```

Everything a reviewer needs is visible: the `If-Match` header is required on the write and `412` is declared (item 4.5), every error shares one schema and media type, `requestedDeliveryDate` is optional *and* nullable on purpose, and money is a string. Paste it into the Swagger Editor to see it validated and rendered.

The shape of the Maven plugin configuration that turns this into a Spring server interface (the version is an example; use the current release):

```xml
<plugin>
  <groupId>org.openapitools</groupId>
  <artifactId>openapi-generator-maven-plugin</artifactId>
  <version>7.12.0</version>
  <executions>
    <execution>
      <goals>
        <goal>generate</goal>
      </goals>
      <configuration>
        <inputSpec>${project.basedir}/src/main/resources/openapi/orders.yaml</inputSpec>
        <generatorName>spring</generatorName>
        <apiPackage>com.example.orders.api</apiPackage>
        <modelPackage>com.example.orders.api.model</modelPackage>
        <configOptions>
          <interfaceOnly>true</interfaceOnly>
          <useSpringBoot3>true</useSpringBoot3>
          <useTags>true</useTags>
          <skipDefaultInterface>true</skipDefaultInterface>
          <documentationProvider>none</documentationProvider>
        </configOptions>
      </configuration>
    </execution>
  </executions>
</plugin>
```

The build then produces an interface with the request-mapping and validation annotations and model classes for `Order`, `OrderLine`, `OrderPatch` and `Problem`; your controller implements the interface, and a changed contract is a compile error rather than a surprise. The remaining options are documented on the generator's page, linked below.

## Pitfalls

- Committing generated code and then editing it. Regenerate in the build; the document is the source.
- Drift. Code-first with a document nobody reviews, or contract-first with a hand-edited controller that no longer matches. Close the loop with validation in tests and a CI diff.
- Confusing optional with nullable. `required` means present; nullability is in the type. Mixing them up produces generated clients that throw on valid responses or reject valid requests.
- `number` for money, which becomes `double` in every generated client. Use string decimals or integer minor units, and say so, as in the example.
- Unstable `operationId`s. Renaming one renames a method in every generated client.
- Response enums that grow. Clients with exhaustive switches break on the new value; declare that unknown values must be tolerated, or use an open enum.
- Enforcing response validation in production. Your schema bug becomes a user-facing 500.
- Mixing 3.0 and 3.1 idioms. `nullable: true` next to `type: [string, "null"]` means one of them is silently ignored somewhere in the toolchain; check what your generator and validator support.
- Treating the document as documentation only: no examples, no error responses, no security scheme, so the generated client cannot even authenticate.

## Check yourself

1. Your team owns the backend and its only frontend. Make the case for code-first, then name two developments that would flip you to contract-first.
2. A response field changes from `type: string` to `type: [string, "null"]`. Is that breaking for a generated Java client? For a TypeScript client? Why can the answers differ?
3. Where in the pipeline would you validate requests against the document, where responses, and in which mode in each place?
4. What must stay stable between versions of a document for generated clients to keep compiling, and which tool tells you when you broke it?

## Go deeper

- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html) · the reference; the Paths, Components and Schema Object sections cover everything in the example.
- [Swagger Editor](https://editor.swagger.io/) · paste the example above and watch it validate and render.
- [OpenAPI Initiative: learn.openapis.org](https://learn.openapis.org/) · the official tutorial, from a first document to best practices.
- [OpenAPI Generator: Spring generator](https://openapi-generator.tech/docs/generators/spring) and [Maven plugin](https://openapi-generator.tech/docs/plugins/) · every `configOptions` entry above, and the rest.
- [Spectral](https://github.com/stoplightio/spectral) · linting rules for consistency, run in CI before review.
- [swagger-request-validator](https://bitbucket.org/atlassian/swagger-request-validator) · request and response validation against the document in Java tests and filters.
- [openapi-diff](https://github.com/OpenAPITools/openapi-diff) and [oasdiff](https://github.com/oasdiff/oasdiff) · breaking-change detection between two versions of a document.
- [Zalando RESTful API Guidelines](https://opensource.zalando.com/restful-api-guidelines/) · the contract-first position and `x-extensible-enum`, argued in full.

---

Part of [Web & HTTP](../README.md) · item 9.4
