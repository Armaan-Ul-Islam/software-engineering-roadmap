# GraphQL and gRPC versus REST

> **In one sentence:** GraphQL solves the client's problem (fetch exactly this shape in one request), gRPC solves the service-to-service problem (a typed binary contract with streaming), and both pay for it by giving up what makes plain REST cheap: HTTP caching, tooling that every proxy and engineer already understands, and a request you can read.

**Why it matters:** An API style is a ten-year decision usually made in a one-hour meeting, often on enthusiasm. Each style solves a specific problem well and sends a specific bill: the N+1 queries behind a GraphQL resolver, the load balancer that cannot forward HTTP/2 trailers, the mobile screen that needs seven REST calls. Knowing the bills is what lets you argue for the boring option when it is the right one.

## The idea

**REST** (item 9.1) is the baseline: resources with URLs, methods and status codes that caches, proxies, browsers and curl all understand. Its weaknesses are *over-fetching* (the resource has forty fields, the screen shows three), *under-fetching* (order, then customer, then each line's product: N+1 over the network) and the endpoint sprawl that follows when you fix both with `?fields=` and `?include=` on every resource.

**GraphQL** is a query language and type system served from one endpoint (usually `POST /graphql`). The server publishes a schema of types, fields, queries, mutations and subscriptions; the client sends a query naming exactly the fields it wants, nested as deep as it needs; the server resolves field by field. This fixes over- and under-fetching, gives a screen its data in one round trip, and lets the schema grow without versioning because clients only receive what they ask for. Introspection makes the schema self-describing, so editors and code generators are excellent. The bills:

1. **Server-side N+1.** A naive `lines` resolver runs once per order, so a list of fifty orders is fifty-one queries. Every resolver that loads a relation needs batching (a DataLoader collects the IDs requested in one tick and loads them with one query). Query cost is unbounded unless you add depth and complexity limits and timeouts; one query can be a denial of service.
2. **Caching.** Everything is a `POST` to one URL answered with 200, so HTTP caches and CDNs see nothing cacheable. Caching moves into the client (normalised caches keyed by `id` and `__typename`) and the server; persisted queries sent as `GET` can win some CDN caching back.
3. **Errors.** A response is 200 with a `data` part and an `errors` array, possibly both (partial data). Monitoring by status code goes blind, exactly the "200 with an error body" problem of item 4.2, so you need GraphQL-aware metrics.
4. **Everything else per field.** Authorisation is per type and field rather than per endpoint, rate limiting is by query complexity rather than by request, file uploads are a bolt-on, and the schema becomes a cross-team contract that needs ownership (federation composes several services into one graph).

GraphQL fits a product with many clients and screens over the same data (web and mobile, a backend-for-frontend layer) where the frontend iterates faster than the backend. It does not fit service-to-service calls, simple CRUD with one client, or public APIs that live on HTTP caching.

**gRPC** is a remote procedure call framework. You define services and messages in Protocol Buffers, generate client stubs and server base classes in any supported language, and call methods. Messages are binary (small, fast to parse, with strict schema-evolution rules built around field numbers), transport is HTTP/2, and there are four call types: unary, server streaming, client streaming and bidirectional. Deadlines propagate across hops, status codes are rich (`NOT_FOUND`, `DEADLINE_EXCEEDED`, `UNAVAILABLE`), and interceptors and load-balancing hooks are standard. The bills:

1. **Browsers.** gRPC carries the status in HTTP/2 trailers, which browsers do not expose, so browser clients need gRPC-Web through a proxy such as Envoy, or the Connect protocol. gRPC is not for browser-facing APIs directly.
2. **Debuggability.** Payloads are binary: curl cannot help, and you need `grpcurl` with server reflection enabled. Every proxy and load balancer on the path must speak HTTP/2 end to end, and long-lived HTTP/2 connections pin to one backend behind a layer-4 balancer (item 11.3); you need client-side balancing or a layer-7 proxy that balances per request.
3. **No HTTP caching, no HTTP semantics.** Nothing is a `GET`; status codes, `Cache-Control` and `ETag` do not exist. Schema governance (a shared proto repository and a breaking-change linter such as `buf`) replaces URL design as the discipline.

gRPC fits internal microservices, high-throughput and low-latency paths, streaming (telemetry, chat backends, data pipelines) and polyglot estates. It does not fit public APIs for arbitrary third parties or anything that needs browsers or HTTP caches without a translation layer in front.

**Decision table.**

| Concern | REST | GraphQL | gRPC |
|---|---|---|---|
| Who shapes the response | server | client | server, per method |
| Contract | OpenAPI, optional (item 9.4) | schema, mandatory and introspectable | `.proto`, mandatory and compiled |
| Wire format and transport | JSON over any HTTP version | JSON over HTTP, usually `POST` | protobuf over HTTP/2 |
| HTTP caching and CDNs | yes: `GET`, `ETag`, `Cache-Control` | not by default; persisted queries over `GET` help | no |
| Streaming | SSE or chunked (item 10.1) | subscriptions over WebSocket or SSE | native, four kinds |
| Browser clients | native | native (`fetch`) | via gRPC-Web or Connect proxy |
| Debugging by hand | curl | curl with a query body | grpcurl with reflection |
| Typical failure | endpoint sprawl, N+1 over the network | N+1 in resolvers, unbounded queries, blind monitoring | proxy or balancer incompatibility, opaque payloads |
| Best for | public and partner APIs, CRUD, cacheable reads | many clients and screens over one graph, BFF layers | internal service-to-service, streaming, polyglot |

Plain REST remains the answer when you control the one or two clients, when reads are public and cacheable, when consumers are external, and when the team's HTTP knowledge is the asset you have. REST also fixes over-fetching cheaply when needed: sparse field sets, an `include` parameter for embedding, or a purpose-built endpoint for one screen.

## Example: get an order with its lines, three ways

REST, with embedding to avoid the second round trip:

```http
GET /orders/9f3b2c?include=lines HTTP/1.1
Host: api.example.com
Accept: application/json
```

```json
{"id":"9f3b2c","status":"paid","customer":{"id":"c-42","name":"Smith & Sons"},"lines":[{"sku":"A-100","quantity":2,"unitPrice":"199.00"}]}
```

Without `include` the client makes `GET /orders/9f3b2c`, then `GET /orders/9f3b2c/lines`, then `GET /customers/c-42`: under-fetching. With it, every client gets every field: over-fetching. Both responses are cacheable with an `ETag` (item 4.5).

GraphQL, schema and a query that asks for three fields of the order and two of each line:

```graphql
type Query {
  order(id: ID!): Order
}

type Order {
  id: ID!
  status: OrderStatus!
  customer: Customer!
  lines: [OrderLine!]!
}

type OrderLine {
  sku: String!
  quantity: Int!
  unitPrice: String!
}

type Customer {
  id: ID!
  name: String!
}

enum OrderStatus {
  PENDING
  PAID
  SHIPPED
  CANCELLED
}
```

```graphql
query OrderSummary($id: ID!) {
  order(id: $id) {
    status
    customer { name }
    lines { sku quantity }
  }
}
```

The query goes as `POST /graphql` with `{"query": "...", "variables": {"id": "9f3b2c"}}` and the answer is `{"data": {"order": {...}}}` containing exactly those fields. The `lines` resolver runs once here; in a query for fifty orders it runs fifty times unless a DataLoader batches the fifty IDs into one database call.

gRPC, the service definition:

```protobuf
syntax = "proto3";

package orders.v1;

service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order);
  rpc WatchOrder(GetOrderRequest) returns (stream OrderEvent);
}

message GetOrderRequest {
  string order_id = 1;
}

message Order {
  string id = 1;
  OrderStatus status = 2;
  Customer customer = 3;
  repeated OrderLine lines = 4;
}

message OrderLine {
  string sku = 1;
  int32 quantity = 2;
  string unit_price = 3;
}

message Customer {
  string id = 1;
  string name = 2;
}

message OrderEvent {
  string order_id = 1;
  OrderStatus status = 2;
}

enum OrderStatus {
  ORDER_STATUS_UNSPECIFIED = 0;
  ORDER_STATUS_PENDING = 1;
  ORDER_STATUS_PAID = 2;
  ORDER_STATUS_SHIPPED = 3;
  ORDER_STATUS_CANCELLED = 4;
}
```

The field numbers, not the names, are the wire contract: a field can be renamed freely but its number must never change or be reused (mark deleted numbers `reserved`). Every enum needs a zero value, which is the default when the field is absent, hence `ORDER_STATUS_UNSPECIFIED`. On the wire the call is `POST /orders.v1.OrderService/GetOrder` with `content-type: application/grpc`, a length-prefixed binary message, and the result status in a trailer (`grpc-status: 0`). `WatchOrder` returns a stream, so one call delivers every status change as it happens, which REST would do with SSE and GraphQL with a subscription. Generated Java code gives you `OrderServiceGrpc.newBlockingStub(channel).getOrder(request)`; the client never sees a URL or a status code.

## Pitfalls

- Choosing GraphQL for a single server-rendered client, or gRPC for a browser application, because the demo looked good.
- GraphQL without batching, depth and complexity limits, and timeouts. N+1 appears in production, and one query takes the database down.
- Treating GraphQL's 200 as success on the dashboard. Alert on the `errors` array and on resolver latency instead.
- Losing CDN caching and noticing only when the bill or the latency arrives. Persisted queries over `GET`, or keep cacheable public reads on REST.
- gRPC behind a proxy that does not carry HTTP/2 end to end or drops trailers: `UNAVAILABLE` and `INTERNAL` errors that look like server bugs. Long-lived streams also need keepalive pings and timeouts aligned along the whole path (item 10.1).
- A layer-4 balancer in front of gRPC: one connection, one backend, and a hot spot (item 11.3). Balance per request at layer 7 or in the client.
- Reusing a protobuf field number or changing a field's type, or an enum without a zero value. Silent corruption across versions; `buf breaking` in CI catches it.
- Money as `double` or `Float` in any of the three. Strings or integer minor units.
- Versioning a GraphQL schema (deprecate fields instead) or not versioning a proto package (`orders.v1` in the package name is the convention).

## Check yourself

1. A mobile screen needs data from six REST endpoints. Name two ways to fix that without GraphQL, and the point at which GraphQL becomes the better answer.
2. Why does a GraphQL API lose HTTP caching, and what are the two places teams rebuild some of it?
3. A browser calls a gRPC service directly and fails. What in HTTP/2 does the browser not expose, and what are the two standard workarounds?
4. A developer deletes `unit_price = 3` from `OrderLine` and later adds `discount = 3`. What happens to old clients and old stored messages, and what prevents it?

## Go deeper

- [GraphQL: Learn](https://graphql.org/learn/) · the schema, queries and resolvers in the project's own words.
- [GraphQL: Serving over HTTP](https://graphql.org/learn/serving-over-http/) and [Caching](https://graphql.org/learn/caching/) · why `POST` and 200, and the `id`-based caching conventions.
- [DataLoader](https://github.com/graphql/dataloader) · the batching pattern that fixes N+1 in resolvers; the README explains it in a page.
- [gRPC: Introduction](https://grpc.io/docs/what-is-grpc/introduction/) and [Core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/) · the four call types and the RPC lifecycle.
- [gRPC: Deadlines](https://grpc.io/docs/guides/deadlines/) and [Status codes](https://grpc.io/docs/guides/status-codes/) · what every call should propagate, and how failures are reported.
- [Protocol Buffers: proto3 language guide](https://protobuf.dev/programming-guides/proto3/) and [Proto best practices](https://protobuf.dev/best-practices/dos-donts/) · field numbers, `reserved`, enums and schema evolution.
- [gRPC-Web](https://github.com/grpc/grpc-web) and [Connect](https://connectrpc.com/) · the two ways to reach gRPC services from a browser.
- [Spring for GraphQL](https://docs.spring.io/spring-graphql/reference/) · the Java implementation, including batch loading, if you go this way.

---

Part of [Web & HTTP](../README.md) · item 9.5
