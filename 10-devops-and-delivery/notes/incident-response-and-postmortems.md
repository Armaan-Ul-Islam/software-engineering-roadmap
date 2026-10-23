# Incident response and blameless postmortems

> **In one sentence:** An incident is run like a small operation with named roles, a declared severity and a fixed communication rhythm; mitigation comes before diagnosis; and the postmortem afterwards looks for the conditions that let it happen, not for the person who typed the command.

**Why it matters:** Outages are rarely prolonged by technical difficulty. They are prolonged by five people debugging in parallel, nobody telling the business what is going on, and nobody feeling allowed to roll back. Teams with a routine recover in minutes and learn something each time; teams without one relive the same incident. Interviewers ask for an incident story, and this structure is what makes a story credible.

## The idea

**Roles.** The *incident commander* owns the incident: decides, delegates, keeps the timeline moving, and does not debug. *Operations* (one or more subject-matter experts) diagnose and apply mitigations. *Communications* owns the status page, stakeholders and customer support, so engineers are not interrupted. A *scribe* records times and decisions in the incident channel. In a small team one person holds several roles, but the commander still says out loud who holds which.

**Severity** sets the response. A typical scale: SEV1, most users cannot use the product or data is at risk, everyone is paged and executives are informed; SEV2, a major feature is down or badly degraded, the on-call team responds with full ceremony; SEV3, degradation with a workaround, handled in business hours; SEV4, cosmetic or internal. Declare early and downgrade later; declaring costs nothing, hesitating costs minutes.

**The first fifteen minutes.**

1. Declare: open the incident channel or bridge, page the commander role, name the roles.
2. Assess impact in user terms (which indicator, how many users, since when) and set the severity.
3. Mitigate with reversible actions before you understand the cause: roll back the latest deploy, turn a feature flag off, scale out, fail over, shed load, restart. The fastest question is "what changed?": deploys, configuration, flags, traffic, dependencies, expiring certificates.
4. Communicate: the first update goes out within fifteen minutes and states what users see, what you are doing, and when the next update comes.
5. Preserve evidence if it is cheap: a thread dump, a heap dump, a copy of the logs, before the restart destroys them.

**Communication cadence.** Internally every fifteen to thirty minutes for SEV1 and SEV2, even when the update is "no change". Externally on the status page at declaration, at each material change and at resolution, in one voice, describing impact and the time of the next update, never speculating about the cause.

**Blameless postmortems.** Written within days by someone who was there, reviewed in a meeting, and shared widely. The question is never "who" but "what about our system made this possible and made it take this long to fix". A postmortem that ends at "human error" has stopped one question too early; ask what allowed the error to reach production and why it was not caught. List contributing factors rather than one root cause, note where you got lucky, and finish with action items that each have an owner, a priority, a due date and a ticket. Action items that are not tracked do not exist.

**Template.** Title, date, authors, status. Severity. Summary (three sentences). Impact (users, duration, budget consumed). Detection (how, time to detect). Response (time to mitigate, time to resolve). Timeline in UTC. Contributing factors. What went well. What went badly. Where we got lucky. Action items table. Lessons learned.

## Example: the template filled in for a connection-pool exhaustion

**Title:** Orders API returned 503 for 38 minutes after connection pool exhaustion. **Date:** 2026-10-14. **Severity:** SEV2. **Authors:** the on-call engineer and the incident commander. **Status:** action items 1 and 2 done, 3 to 5 in progress.

**Summary.** Release 1.42.0 added an order-history export endpoint that called the PDF rendering service from inside a `@Transactional` method, holding a database connection for the whole call (p99 of that call: 12 s). Under normal traffic the HikariCP pool of 10 connections was exhausted within five minutes of the rollout, and every endpoint that needed the database failed with `HikariPool-1 - Connection is not available, request timed out after 30000ms`. Rolling back the deploy mitigated the incident.

**Impact.** 38 minutes; about 62 percent of requests to the orders API failed; roughly 4,100 users saw errors at checkout. Equivalent to 23.6 minutes of full outage, about 55 percent of the 30-day availability budget (43.2 minutes).

**Detection.** The `OrdersAvailabilityBurnRateFast` alert (item 5.5) paged at 09:49, eight minutes after the first failures.

**Timeline (UTC).**

| Time | Event |
|---|---|
| 09:41 | Rollout of orders 1.42.0 completes. |
| 09:46 | First `Connection is not available` warnings in the logs; nobody is looking at logs. |
| 09:49 | Burn-rate alert pages on-call. Acknowledged 09:51. |
| 09:53 | Incident declared SEV2; channel opened; on-call takes commander, a second engineer takes operations, the team lead takes communications. |
| 09:58 | Dashboard shows `hikaricp_connections_pending` above 40 and active connections at 10 of 10; the database itself is at 15 percent CPU. |
| 10:02 | Hypothesis "database degraded"; the database team is paged. |
| 10:08 | First status page update: degraded performance at checkout. Database team reports the database is healthy. |
| 10:11 | "What changed?" The only change is the 09:41 deploy. Commander decides to roll back. |
| 10:13 | `kubectl rollout undo deployment/orders` started. |
| 10:19 | Error ratio back to baseline. Mitigated. |
| 10:35 | Status page resolved; incident closed. |
| 11:30 | Cause confirmed by reading the export endpoint's code. |

**Contributing factors.**

1. The export endpoint made a remote call inside a database transaction, holding a pooled connection for up to 12 seconds per request.
2. The pool size was the HikariCP default of 10, never load-tested, and nothing alerted on `hikaricp_connections_pending`.
3. The HTTP client used for the PDF service had no timeout, so slow exports became whole-pool starvation rather than slow exports.
4. The rollout reached 100 percent of traffic within two minutes; there was no canary stage to limit the blast radius.
5. Twelve minutes went to the wrong hypothesis because the service dashboard had no pool-saturation panel and the database's own metrics looked fine.

**What went well.** The alert paged on user impact, not on a cause. Rollback was one practised command. Roles were named within four minutes.

**Where we got lucky.** The export endpoint was used by few customers; with more usage the pool would have been exhausted in seconds, before anyone was awake enough to see the trend.

**Action items.**

| # | Action | Owner | Priority | Due | Ticket |
|---|---|---|---|---|---|
| 1 | Move the PDF call outside the transaction; add a 3 s timeout to the client | orders team | P1 | 2026-10-18 | ORD-1412 |
| 2 | Alert `hikaricp_connections_pending > 0` for 2 minutes (ticket severity) and add a pool USE panel to the service dashboard | orders team | P1 | 2026-10-21 | ORD-1413 |
| 3 | Canary stage in the orders pipeline: 10 percent for 10 minutes gated on burn rate | platform team | P2 | 2026-11-15 | PLAT-702 |
| 4 | ArchUnit rule: no `@Transactional` method may call a class in the `..client..` package | orders team | P2 | 2026-11-01 | ORD-1420 |
| 5 | Load test with a slow-dependency scenario before the next release | orders team | P3 | 2026-11-30 | ORD-1421 |

## Pitfalls

- No commander, or a commander who also debugs. Nobody decides, everybody investigates, and the rollback waits for consensus that never comes.
- Diagnosing before mitigating. "We almost have it" is the most expensive sentence in an incident. Roll back first; the code is still there to read afterwards.
- Silence. Stakeholders who hear nothing join the channel and ask; a fixed next-update time is what keeps them out.
- Blame in disguise. "The developer forgot the timeout" stops the analysis; "the client library defaults to no timeout and nothing checks for it" produces an action item.
- Vague or unowned action items. "Be more careful with transactions" is not an action; item 4 in the table is.
- Hero shifts. Rotate the commander after a few hours; tired people make the second incident.
- Public speculation. A status page that names a cause before it is confirmed has to be corrected, and the correction costs more trust than the outage.
- Restarting first. The thread dump that would have explained everything is gone.

## Check yourself

1. At 10:02 the commander paged the database team. Was that a mistake? Which question, asked at 09:58, would have ordered the hypotheses better?
2. Rewrite "the developer forgot to add a timeout" as a contributing factor that leads to an action item.
3. Write the 10:08 status page update in two sentences, following the cadence rules above.
4. Which action item most reduces the chance of recurrence, and which most reduces time to mitigate? Why does a good postmortem need both kinds?

## Go deeper

- [PagerDuty Incident Response](https://response.pagerduty.com/) · the roles, severity levels and call etiquette in full, free to adopt.
- [Google SRE Book: Managing Incidents](https://sre.google/sre-book/managing-incidents/) · the incident command system applied to software, with an unmanaged incident for contrast.
- [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) · why blameless, and how to make the culture stick.
- [Google SRE Book: Example Postmortem](https://sre.google/sre-book/example-postmortem/) · a complete, real postmortem to compare the template against.

---

Part of [DevOps & Delivery](../README.md) · items 8.1, 8.2
