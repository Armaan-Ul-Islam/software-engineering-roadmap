# Monolith vs microservices

> **In one sentence:** Microservices buy independent deployment and scaling for separate teams at the price of a distributed system (network failures, no cross-service transactions, an operations platform, harder testing), so the default is a modular monolith with honest boundaries, and you split only where a boundary has proved itself and the price is justified.

**Why it matters:** The most expensive architecture mistake a small team can make is to start with twenty services; the most expensive one a large organisation can make is to keep eighty people in one deploy queue. Both are decided by the same reasoning about boundaries, data ownership and team shape, and interviewers ask about it to see whether you understand costs, not just diagrams.

## The idea

**What microservices actually cost.** Fowler calls it the microservice premium: a tax paid on every feature, which only pays back when the system is complex enough that a monolith's coupling costs more.

- Network. Every call between modules becomes a remote call that can be slow, fail partially, or time out. You now need timeouts, retries, circuit breakers (see item 4.2), service discovery, serialisation and API versioning, and the fallacies of distributed computing (see item 1.5) apply to code that used to be a method call.
- Data consistency. No transaction spans two services. A change that touched three tables becomes a saga with compensations (see item 3.7); a report that joined them becomes a data pipeline or a read model that is eventually consistent, and every "simple" invariant across services needs a design.
- Operations. N services mean N pipelines, N dashboards, N on-call surfaces, distributed tracing to find out where a request went, a platform team to make all that bearable, and the certainty that some service nobody owns is running an old library.
- Testing. Unit tests still work; the behaviour of the system exists only when the services are deployed together, so you need contract tests, test environments that are never quite like production, and the discipline to deploy independently anyway.
- People. Conway's law runs both ways: services end up mirroring the teams, and teams end up owning whatever the services force on them. Nobody holds the whole picture, so cross-cutting changes need coordination that a single codebase gave you for free.

**The modular monolith as the default.** One deployable, several modules with enforced boundaries: each module has a public API (a Java package or Gradle module that others may call) and private internals, owns its own tables (one schema per module, no foreign keys or joins across modules), and talks to other modules through those APIs or in-process events. Tools make the boundaries real: ArchUnit tests fail the build on a forbidden dependency, Spring Modulith verifies module structure and publishes application events with an outbox. You get the structure that microservices promise, keep a single transaction and a single deploy, and if a module later needs to be a service, the seam already exists.

**Finding boundaries.** Good boundaries line up on several axes at once:

1. Bounded contexts from domain-driven design: where the same word means different things (a "product" in the catalogue has descriptions and images; in the warehouse it has dimensions and bin locations), you have found an edge.
2. Data ownership: exactly one module writes each piece of data; others read it through an API or a published event. If two candidate modules both need to update the same row, they are one module.
3. Rate and reason for change: code that changes together in the same pull requests belongs together. If every feature touches modules A and B, the boundary between them is in the wrong place.
4. Team ownership: a boundary that cuts through a team's daily work will be ignored; a boundary between teams will hold.
5. Different runtime needs: a CPU-heavy image processor and a CRUD API, or a component with PCI compliance scope, have reasons to be separate that have nothing to do with the domain.

**The distributed monolith.** Services that cannot be deployed independently: a change needs releases in three repositories in a fixed order, services call each other synchronously in long chains, several of them read and write the same database tables, and a shared domain library forces everyone to upgrade at once. You pay the full microservice premium and get none of the autonomy. The shared database is the usual root: a schema that five services depend on cannot change without coordinating five teams, so it never changes.

**When splitting is justified.** A module whose boundary has been stable for a while, whose coupling to the rest is low (few calls, no shared tables), and which has at least one concrete reason: a scaling profile that differs by an order of magnitude; a team that needs to deploy on its own cadence and is blocked by the shared pipeline; a security or compliance scope that must be isolated; a technology that the rest of the system should not carry. Also required before the first split: automated deployment, centralised logging and tracing, and monitoring that tells you which service is failing. Fowler's prerequisites list is short and non-negotiable. Extract one service at a time, using the strangler fig (see item 5.5), and measure whether the premium is paying back before extracting the next.

## Example: a decision table

| Situation | Default decision | Why |
|---|---|---|
| New product, one team of 4 to 8, domain not yet understood | Modular monolith | Boundaries will move; moving a package is cheap, moving a service is a project. |
| 50 engineers in one codebase, deploys queue for days, unrelated changes break each other | Split along team boundaries where data ownership is already clean | The coupling cost now exceeds the premium; split where the seam exists, not everywhere. |
| One component needs 20× the compute of the rest (video transcoding, ML inference) | Extract that component | Independent scaling is a real, measurable benefit; the rest stays together. |
| Payments must sit inside PCI scope | Separate service with its own data store | Isolation is the requirement; scope reduction pays for the premium. |
| Two services always deploy together and share tables | Merge them, or give one of them the data and an API | This is a distributed monolith; the boundary is fictional. |
| Service B is called synchronously by A on every request and nothing else uses it | Fold B into A, or make the call asynchronous | A boundary with one caller and a synchronous dependency adds latency and failure modes for nothing. |
| Spiky, event-driven glue work (image resize on upload, nightly exports) | Serverless functions | Pay-per-use and zero idle capacity fit; cold starts and limits do not matter for this work. |

Read across the table and the pattern is constant: split for a reason you can measure, along a boundary that already holds, with the platform in place to run the result.

## Pitfalls

- Starting with microservices to be "ready for scale". The scale that arrives is rarely the one you prepared for, and the boundaries you guessed are wrong; now they are expensive to move.
- Splitting by technical layer (a "user service", an "order service" that are thin CRUD wrappers). Every feature then touches every service; this is the distributed monolith by design.
- Sharing a database "temporarily". The temporary coupling becomes permanent because changing it requires the coordination the split was meant to avoid.
- Shared domain libraries across services. A change to `Order` forces a lockstep upgrade of everyone who imports it; share contracts (schemas), not implementations.
- Calling a monolith a "modular monolith" without enforcement. Without ArchUnit or module boundaries in the build, every module reaches into every other within a year.

## Check yourself

1. Name three costs that appear when a method call becomes a service call, and the pattern that addresses each.
2. Two modules in your monolith both update the `inventory` table. What does that tell you about the boundary, and what would you change before considering a split?
3. Describe the symptoms that would make you call a system a distributed monolith, and the two most common root causes.
4. A team proposes extracting the notification module into a service because "it is clearly separate". Which questions decide whether that is justified?

## Go deeper

- [Fowler: MonolithFirst](https://martinfowler.com/bliki/MonolithFirst.html) · why almost every successful microservice system started as a monolith.
- [Fowler: Microservice Premium](https://martinfowler.com/bliki/MicroservicePremium.html) · the cost curve in one picture.
- [Fowler: Microservice Prerequisites](https://martinfowler.com/bliki/MicroservicePrerequisites.html) · the minimum platform you need before the first split.
- [Fowler & Lewis: Microservices](https://martinfowler.com/articles/microservices.html) · the original characterisation, including decentralised data and smart endpoints.
- [microservices.io: Decompose by subdomain](https://microservices.io/patterns/decomposition/decompose-by-subdomain.html) · bounded contexts as the boundary-finding tool.
- [Spring Modulith](https://docs.spring.io/spring-modulith/reference/) · enforced module boundaries, verified in tests, inside one Spring Boot application.

---

Part of [System Design](../README.md) · items 5.1, 5.2
