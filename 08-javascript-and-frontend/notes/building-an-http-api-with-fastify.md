# Building an HTTP API with Fastify

> **In one sentence:** A Fastify service is a tree of plugins that register routes, each route declares a JSON Schema that validates input and filters output before your handler runs, one error handler turns thrown errors into consistent responses, pino writes one JSON line per request, and shutdown means closing the server so in-flight requests finish before the process exits.

**Why it matters:** A Node API that works on a laptop and misbehaves in production usually fails on the parts that are not business logic: unvalidated input that reaches the database, a handler that throws and leaves the client hanging, logs that cannot be searched, and a container that is killed mid-request because nothing listened for `SIGTERM`. These are the same concerns Spring Boot solves with Bean Validation, `@ControllerAdvice`, Logback and the graceful-shutdown property. In Node you wire each one yourself, and the framework choice decides how much help you get.

## The idea

**Express or Fastify.** Express is the older, minimal framework: a chain of `(request, response, next)` middleware functions with no built-in validation, no schema and callback-era error handling (an error thrown inside an `async` handler is only caught by Express 5 or later). Fastify is the modern choice for a new service: it is async-first, validates with JSON Schema, serialises responses from a schema, logs with pino by default and has a plugin system with proper encapsulation. The ideas below transfer to Express, only with more hand-written code.

**Plugins and encapsulation.** Everything in Fastify is registered through `app.register(plugin, options)`. A plugin is an `async function (fastify, options)` that adds routes, hooks and decorators. What a plugin adds is visible to itself and its children, not to its siblings, so a database connection decorated in one plugin does not leak into another. A `prefix` option mounts the plugin's routes under a path.

**Routing with schemas.** A route is `app.get(path, { schema }, handler)`. The schema describes `params`, `querystring`, `body` and `response` per status code in JSON Schema. Fastify compiles it with Ajv once at startup and uses it for two things: rejecting invalid input with a 400 before the handler runs, and serialising the response with `fast-json-stringify`, which only emits the properties the response schema lists. The second behaviour is the one people miss: a response schema is also a whitelist.

**Handlers and errors.** An `async` handler returns the response body; `reply.code(201).send(body)` sets the status. Anything thrown inside a handler or hook lands in `setErrorHandler`, where you decide what the client sees. Validation errors carry an `error.validation` array. Without a custom handler Fastify still answers with JSON and the right status, but the shape is Fastify's, not yours.

**Logging.** `Fastify({ logger: true })` creates a pino logger. pino writes one JSON object per line to stdout and is fast because formatting is deferred to a separate process (`pino-pretty` in development, nothing in production: the log shipper reads JSON). Every request gets `request.log`, a child logger carrying a `reqId`, so every line from one request can be grouped. Log objects first and the message second: `request.log.info({ orderId }, "order created")`, never string concatenation.

**Configuration.** Read environment variables once, at startup, into one object with defaults and conversions (`Number(process.env.PORT ?? 3000)`), and fail fast if a required one is missing. Do not read `process.env` from inside handlers. Secrets come from the environment or a mounted file, never from the image.

**Graceful shutdown.** Orchestrators stop a container by sending `SIGTERM`, waiting (Kubernetes defaults to 30 seconds), then `SIGKILL`. Node's default on `SIGTERM` is to exit immediately, cutting open connections. Listen for the signal, call `await app.close()`, which stops accepting connections and waits for in-flight requests and registered `onClose` hooks (database pools), then exit. One more trap: `npm start` runs your process as a child of npm, and whether the signal reaches it depends on the npm version and the shell. In a Dockerfile use `CMD ["node", "server.mjs"]` so Node is PID 1 and receives the signal, and because PID 1 does not get default signal handling, keep the explicit listener.

## Example: a small orders API

```javascript
// server.mjs
import Fastify from "fastify";

const configuration = {
  port: Number(process.env.PORT ?? 3000),
  logLevel: process.env.LOG_LEVEL ?? "info",
};

const orders = new Map();

async function ordersPlugin(fastify) {
  fastify.get("/orders/:id", async (request, reply) => {
    const order = orders.get(request.params.id);
    if (!order) {
      return reply.code(404).send({ title: "Not Found", status: 404, detail: `No order ${request.params.id}` });
    }
    return order;
  });

  fastify.post("/orders", {
    schema: {
      body: {
        type: "object",
        required: ["customerId", "amount"],
        additionalProperties: false,
        properties: {
          customerId: { type: "string", minLength: 1 },
          amount: { type: "number", exclusiveMinimum: 0 },
        },
      },
      response: {
        201: {
          type: "object",
          properties: { id: { type: "string" }, customerId: { type: "string" }, amount: { type: "number" } },
        },
      },
    },
  }, async (request, reply) => {
    const order = { id: String(orders.size + 1), ...request.body, internalNote: "never leaves the server" };
    orders.set(order.id, order);
    return reply.code(201).send(order);
  });
}

export function buildApp() {
  const app = Fastify({ logger: { level: configuration.logLevel } });

  app.setErrorHandler((error, request, reply) => {
    if (error.validation) {
      return reply.code(400).send({ title: "Bad Request", status: 400, detail: error.message });
    }
    request.log.error(error);
    return reply.code(500).send({ title: "Internal Server Error", status: 500 });
  });

  app.register(ordersPlugin, { prefix: "/api" });
  return app;
}

if (process.argv[1] === new URL(import.meta.url).pathname) {
  const app = buildApp();
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, async () => {
      app.log.info({ signal }, "shutting down");
      await app.close();
      process.exit(0);
    });
  }
  await app.listen({ port: configuration.port, host: "0.0.0.0" });
}
```

`buildApp` is separate from `listen` so tests can create the app without opening a port (see item 3.6). With Node 22 and Fastify 5:

```bash
PORT=3999 node server.mjs &
curl -s -i -X POST localhost:3999/api/orders -H 'content-type: application/json' -d '{"customerId":"c-1","amount":10}'
curl -s localhost:3999/api/orders/1
kill -TERM %1
```

```text
{"level":30,"time":1793252369666,"pid":23828,"hostname":"laptop","msg":"Server listening at http://127.0.0.1:3999"}
{"level":30,"time":1793252370650,"pid":23828,"hostname":"laptop","reqId":"req-1","req":{"method":"POST","url":"/api/orders","host":"localhost:3999","remoteAddress":"127.0.0.1","remotePort":49599},"msg":"incoming request"}
{"level":30,"time":1793252370655,"pid":23828,"hostname":"laptop","reqId":"req-1","res":{"statusCode":201},"responseTime":4.879666999999927,"msg":"request completed"}
HTTP/1.1 201 Created
content-type: application/json; charset=utf-8
content-length: 41

{"id":"1","customerId":"c-1","amount":10}
{"id":"1","customerId":"c-1","amount":10,"internalNote":"never leaves the server"}
{"level":30,"time":1793252372001,"pid":23828,"hostname":"laptop","signal":"SIGTERM","msg":"shutting down"}
```

Two things to notice. The `POST` response omitted `internalNote` because the 201 response schema does not list it; the `GET` route has no response schema and leaked it. And an invalid body never reaches the handler:

```bash
curl -s -X POST localhost:3999/api/orders -H 'content-type: application/json' -d '{"customerId":"","amount":-1}'
```

```text
{"title":"Bad Request","status":400,"detail":"body/customerId must NOT have fewer than 1 characters"}
```

The error objects above follow the field names of RFC 9457 Problem Details, which is also what Spring Boot's `ProblemDetail` emits, so one frontend error handler covers both backends (see item 8.4).

## Pitfalls

- A route without a `response` schema serialises whatever the handler returns, including internal fields and password hashes. Treat the response schema as mandatory for anything read from a database.
- Calling `reply.send(...)` in an async handler without returning `reply`. The handler's promise then resolves with `undefined` after the reply was already sent, and Fastify logs a warning about a promise not fulfilled with a value. Either `return reply.send(...)` or return the body and set the status with `reply.code(...)` first.
- `app.listen({ port })` without `host`. Fastify listens on `localhost` by default, which is unreachable from outside a container. Use `host: "0.0.0.0"` in images.
- Logging with string concatenation (`log.info("user " + id + " logged in")`). The id is not a searchable field any more. Pass an object first.
- `pino-pretty` in production. It is a transport for humans; it costs CPU and produces lines no log pipeline can parse. Leave stdout as JSON.
- Blocking work in a handler (synchronous crypto, large `JSON.stringify`, a regex with catastrophic backtracking). One slow handler stalls every request in the process; see item 3.1.
- A Docker image built from the full `node` image with `devDependencies` installed. Use `npm ci --omit=dev` in a multi-stage build and a slim base image, run as a non-root user and set `NODE_ENV=production`, which some libraries read to disable debug paths.
- `process.exit()` inside the signal handler before `app.close()` resolves. Open responses are cut. Await the close, then exit.

## Check yourself

1. A colleague adds a `passwordHash` column and the `GET /users/:id` route starts returning it. Which single Fastify feature would have prevented that, and why does it also make the route faster?
2. Your Kubernetes deployment reports a few 502 errors on every rollout. Explain the sequence of events that produces them and the two changes (one in code, one in the Dockerfile) that stop them.
3. Why does Fastify's error handler receive an error thrown from an `async` handler, while Express 4 would leave the request hanging?
4. A request fails in production and you have the client's correlation id. What has to be true of your logging for you to find every line that request produced?

## Go deeper

- [Fastify](https://fastify.dev/) · the documentation; read Getting Started, Validation and Serialization, Plugins Guide, and Hooks.
- [pino](https://getpino.io/) · why structured logging is fast and how transports work.
- [Express](https://expressjs.com/) · still the most common framework in existing code bases; the middleware chapter explains what you will meet.
- [Docker: Node.js language-specific guide](https://docs.docker.com/guides/nodejs/) · multi-stage builds, non-root users and `node` as PID 1.
- [Node.js: Don't Block the Event Loop](https://nodejs.org/en/learn/asynchronous-work/dont-block-the-event-loop) · the rules for what a handler may do synchronously.

---

Part of [JavaScript & Frontend](../README.md) · items 3.4, 3.5
