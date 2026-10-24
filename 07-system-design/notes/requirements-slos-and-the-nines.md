# Requirements, SLOs and the nines

> **In one sentence:** A non-functional requirement is only real once it is written as a measurable indicator with a numeric target over a window (an SLO), and each extra nine of availability is a tenfold cut in allowed downtime that has to be paid for with redundancy, automation and stricter change control.

**Why it matters:** "It should be fast and always up" is not a requirement; it is a wish that will be satisfied by whatever the first load test happens to show. Systems get built for the wrong availability because nobody turned the adjective into a number, and design interviews go wrong in the first five minutes for the same reason (see item 6.1). Knowing what 99.99 percent means in minutes, and what it costs, is the difference between an architecture and a diagram.

## The idea

**Functional versus non-functional.** Functional requirements say what the system does: a customer can pay for a basket, an order can be cancelled within an hour. Non-functional requirements say how well it must do it: how many users, how fast, how often it may fail, how stale a value may be, how long data is kept, who may see it. Functional requirements shape the API and the data model; non-functional ones shape everything else, and a vague request leaves them out.

**SLI, SLO, SLA.** The SRE vocabulary makes a non-functional requirement precise.

1. An SLI (service level indicator) is a measurement, almost always a ratio of good events to all events: successful responses over all responses, responses under 300 ms over all responses, stock figures fresher than 30 s over all stock figures shown.
2. An SLO (service level objective) is a target for an SLI over a window: 99.9 percent of `POST /orders` requests succeed, measured over 30 days. It is internal, and it is what engineering designs and alerts against.
3. An SLA (service level agreement) is a contract with a customer that attaches consequences (credits, penalties) to missing a target. The SLA target is looser than the SLO, so that the team is paged long before money is owed.

Availability is a ratio of good requests, not the uptime of a server. A server that is up and returning 500s is down for the user.

**The nines in minutes.** Allowed downtime at each target, per 30-day month (43,200 minutes) and per year:

| Target | Per month | Per year | What it rules out |
|---|---|---|---|
| 99% | 7.2 hours | 3.65 days | Very little; a weekend outage fits. |
| 99.9% | 43.2 minutes | 8.76 hours | Unmonitored failures; a human must be paged and finish acting inside the budget. |
| 99.95% | 21.6 minutes | 4.38 hours | Any single instance on the critical path. |
| 99.99% | 4.3 minutes | 52.6 minutes | Human-driven failover of any kind; recovery must be automatic, and one bad deploy is the month's budget. |
| 99.999% | 26 seconds | 5.3 minutes | Any dependency not itself at five nines, most deployment strategies, and most teams. |

Each step down the table divides the downtime by ten and multiplies the cost by more than that. The budget is consumed by everything, not only incidents: deploys that need a rollback, a cloud provider's bad hour, database failovers (a managed-database failover takes on the order of a minute, so a handful of them is a whole month at 99.99 percent). It is also capped by your dependencies. Components called in series multiply: a service that synchronously calls three dependencies at 99.9 percent each is at best 99.7 percent, whatever its own code does. The practical framing is the **error budget**, 100 percent minus the SLO: at 99.9 percent you have 43 minutes a month to spend, and when it is spent, feature work stops and reliability work starts.

**Latency as percentiles.** A latency requirement is a percentile over a window, never a mean: "99 percent of requests complete within 300 ms over 30 days" (see item 1.4). State two points (p50 and p99) so the target describes both the typical and the slow experience, and state where it is measured (at the load balancer, not inside the service, because queueing in front of the service is invisible from inside).

**Consistency as a requirement.** For each read, ask: must a user see their own write immediately? May two users see different values for a moment? How stale may a value be, in seconds? The answers decide whether a read may come from a cache or a replica, whether a write needs synchronous replication, and whether a counter may be approximate (see item 3.3). "It must be consistent" means nothing until it names an anomaly the business cannot tolerate.

**Extracting it from a vague request.** The questions that turn "fast and reliable" into requirements:

1. Who and how many: users per day, the peak hour, growth over two years. These feed the estimation (see item 1.2).
2. Which operation is the critical path: the one losing money by the minute. Different operations get different SLOs.
3. What an outage costs: revenue per minute, contractual penalties, customers who do not return. The nines follow from the cost, not from pride.
4. What staleness is visible: for each number on the screen, "would it be acceptable if this were 10 seconds old? Ten minutes?" Stop at the first no.
5. What must never happen: double charges, lost orders, leaked data. These are invariants, designed in (idempotency, transactions, authorisation), not targets to approach at 99.9 percent.
6. What the dependencies promise: a provider's SLA bounds your own.

## Example: the requirements interview for a checkout service

The request: "customers should be able to pay for their basket, and it has to be reliable, we lose money when it is down."

| Question | Answer | What it fixes |
|---|---|---|
| How many orders, and when? | 200,000 a day, 40 percent of them between 18:00 and 21:00; Black Friday is 5× a normal day. | About 2.3 orders per second on average, 7 at the evening peak, 35 on Black Friday. One database primary is fine. |
| What does a minute of downtime cost? | Around 400 orders at the evening peak at an average of 60 euros, so about 25,000 euros a minute, and customers who leave rarely come back. | Justifies multi-AZ and automated failover; not an active-active second region (see item 5.7). |
| Is browsing the basket as critical as paying? | No. If the basket is slow, people wait; if payment fails, they leave. | Two SLOs: `POST /orders` stricter than `GET /cart`. |
| May a customer ever be charged twice? | Never. | An invariant: an idempotency key on the payment call (see item 4.4), not an availability number. |
| May an order be accepted and later cancelled for lack of stock? | Yes, if it is rare and the customer hears within minutes. | Stock may be checked against a value up to 30 s old; no reservation on the request path. |
| How fast must the confirmation appear? | "Instant." After probing: under two seconds feels fine; at five, people click twice. | p50 under 500 ms, p99 under 2 s, measured at the load balancer, including the provider call. |
| What does the payment provider promise? | 99.9 percent monthly in its SLA, p99 of 800 ms. | The synchronous path cannot beat 99.9 percent. Either accept that, or accept the order first and confirm payment asynchronously, which changes the product. |

The SLO table that results:

| SLI | SLO | Window | Consequence for the design |
|---|---|---|---|
| `POST /orders` availability: responses that are not 5xx and not timed out, over all requests | 99.9 percent (43 minutes a month), capped by the provider | 30 days | Multi-AZ, automated database failover, no single instance anywhere, deploys through canaries (see item 4.6). |
| `POST /orders` latency at the load balancer | 50 percent under 500 ms, 99 percent under 2 s | 30 days | Provider call with an 1,800 ms timeout and no retry on the request path; retries happen in an asynchronous reconciliation job. |
| `GET /cart` availability | 99.5 percent | 30 days | Served from a cache that survives a database failover; a lost basket is acceptable, a lost order is not. |
| Stock shown at checkout fresher than 30 s | 99 percent | 7 days | Inventory read from a replica or cache; a reservation is taken only when the order is confirmed. |
| Duplicate charges, from daily reconciliation against the provider's report | 0 tolerated | daily | Idempotency key stored with the payment; an alert on any mismatch, not a budget. |

Spend the first line's budget on paper: a 60-second database failover, two canary rollbacks of 5 minutes each and a 20-minute provider incident add up to 31 minutes. Before any code exists, the team knows that a third bad deploy in the month means the rest of the month goes to reliability work, and the product owner agreed to that in the same meeting.

## Pitfalls

- Promising more nines than the weakest synchronous dependency. Your SLO is capped by the product of your dependencies' availabilities unless you can degrade around them.
- Measuring availability as server uptime. The load balancer's ratio of good responses to all requests is the only view that matches what users see.
- Latency targets as averages, or percentiles without a window. A one-minute p99 is noise; a 30-day p99 is a commitment.
- One SLO for the whole service. Checkout and "edit my profile" do not deserve the same budget; a single target overbuilds the cheap paths and underbuilds the expensive one.
- Writing invariants as SLOs. "99.99 percent of orders are not double charged" is a bug count, not a target; correctness is designed in and reconciled, not budgeted.
- An SLO with no error budget policy. If nothing changes when the budget is spent, the number is decoration.

## Check yourself

1. Your checkout calls a database at 99.99 percent, an inventory service at 99.95 percent and a payment provider at 99.9 percent, all synchronously. What availability can you promise, in minutes per month, and what design change would raise it?
2. A product owner asks for "five nines". What do you ask next, and what will the answer teach them?
3. Write the SLI and SLO for "the basket page must feel instant", and say where it is measured and over what window.
4. Why is "customers are never charged twice" not expressed as an SLO, and how is it handled instead?

## Go deeper

- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) · the definitions of SLI, SLO and SLA, and how to choose targets you can keep.
- [Google SRE Book: Embracing Risk](https://sre.google/sre-book/embracing-risk/) · the availability table, the cost of each nine, and the error budget as the contract between product and engineering.
- [The Site Reliability Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/) · a worked example of writing SLIs and SLOs for a real service, including what to measure where.
- [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/) · why the latency target has to be a percentile, and how fan-out makes the tail the common case.

---

Part of [System Design](../README.md) · item 1.1
