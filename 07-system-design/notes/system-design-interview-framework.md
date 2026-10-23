# A framework for the system design interview

> **In one sentence:** A system design interview is a 45-minute collaborative design review in which you are graded on how you reason, not on arriving at a particular diagram, so the winning approach is a fixed sequence (requirements, numbers, high-level design, deep dives, trade-offs) that you drive out loud and adjust to what the interviewer signals.

**Why it matters:** Strong engineers fail these interviews for predictable reasons: they design before they know what they are designing, they never say a number, or they talk for forty minutes without checking whether the interviewer wanted to go somewhere else. A framework fixes the structure so your attention goes to the actual problem, and the same habit makes real design meetings shorter.

## The idea

**The timeline.** Forty-five minutes, with the first and last few taken by introductions and questions. Keep an eye on the clock and say when you are moving on.

| Minutes | Phase | What you produce | What the interviewer is checking |
|---|---|---|---|
| 0 to 5 | Requirements | The three core features, the explicit non-goals, and the non-functional targets (scale, latency, consistency, availability). | Can you narrow an open problem and find out what matters? |
| 5 to 10 | Estimation | Requests per second (average and peak), storage per year, bandwidth, cache size, and the one number that shapes the design (see item 1.2). | Do you know what scale you are designing for, and does it change your decisions? |
| 10 to 20 | High-level design | The API (a few endpoints with request and response), the data model (entities, keys, which store), the components (clients, edge, services, cache, database, queue, object storage) and the write path and read path drawn as numbered arrows. | Does the design satisfy the requirements end to end? Can you trace a request? |
| 20 to 35 | Deep dives | Two or three hard parts, chosen with the interviewer: the hot path, the consistency problem, the component that does not fit on one node. Alternatives for each, with a choice and the reason. | Depth. Do you know how the pieces actually work and where they break? |
| 35 to 42 | Trade-offs and failure | What breaks first under 10× load, what happens when each component fails, what you would monitor, what you would build differently with more time or a different requirement. | Judgement and honesty about limits. |
| 42 to 45 | Wrap-up | A one-minute summary of the design and its biggest open risk. | Can you communicate a design to someone who was not in the room? |

**Questions to ask in the first five minutes.** Who are the users and how many? Which three features matter most, and which are explicitly out of scope? Read-heavy or write-heavy, and by how much? How fresh must data be (can a user see a result that is seconds old)? Latency target for the main operation? Availability target, and is it the same for reads and writes? How much data, kept for how long? One region or global? Any constraints on technology or team? And the most useful one: "Which part of this would you like me to spend the most time on?"

**Driving the conversation.** State the plan ("I will clarify requirements, estimate, draw the high-level design, then go deep on the parts you find most interesting") and then follow it audibly. Talk while you draw; silence while drawing reads as being stuck. After each phase, summarise in one sentence and check in ("The write path is clear; shall I go deeper into the feed generation or the storage layout?"). Name trade-offs explicitly, as pairs: "Option A gives us strict ordering at the cost of one partition per user; option B scales but reorders events; given the requirement that comments appear in order, A." Tie choices to the numbers from the estimation: "40 writes per second means a single primary; 12,000 reads per second means a cache in front, not more database replicas." Keep the diagram tidy: clients on the left, data stores on the right, numbered arrows for the main flows, a legend for anything invented.

**Handling pushback.** Pushback is the interview working as designed; the interviewer is probing whether the design survives contact. Clarify what exactly is being challenged before answering. If they are right, say so, change the design, and say what else that change affects; recovering well scores higher than being right first time. If you disagree, defend with the requirement and the number that led you there, then offer what you would do under their assumption. Never bluff: "I have not operated that at scale; I would expect X because of Y, and I would verify by Z" is a strong answer. When asked "what if this component fails?", walk the request through the failure and name the symptom the user sees and the mechanism that limits the damage (see items 4.1 and 4.2).

**The mistakes that fail candidates.**

1. Designing before clarifying. Five minutes in, drawing a Kafka cluster for a system whose requirements nobody has stated.
2. No numbers, or numbers that do not influence anything. Estimation is wasted unless a decision depends on it.
3. Buzzword components. Every technology on the board must answer "what requirement does it serve, and what would happen without it?"
4. No API or data model. Boxes and arrows without the shape of the data are not a design.
5. A monologue. Not checking in, missing hints, spending twenty minutes on a part the interviewer did not care about.
6. Hand-waving the hard part. "It is eventually consistent, so it is fine" or "we shard it" without saying by what key and what happens to queries that do not have the key.
7. Not knowing your own design. Being unable to trace one request from the client to the database and back.
8. Running out of time with half a design, because the first phase took twenty minutes.
9. Defending a mistake. The interviewer shows you a real flaw and you argue instead of fixing it.

## Example: the framework applied in miniature

Prompt: "Design a service that shortens URLs." Requirements in one minute: create a short link for a long URL (optional custom alias), redirect, basic click counts; out of scope: user accounts beyond an API key. Non-functional: redirects must be fast and highly available; creation can be slower. Estimation in two: 100 million new links per month is about 40 writes per second; 100 reads per write gives 4,000 redirects per second, 12,000 at peak; 6 billion links over five years at 500 bytes is 3 TB. The decision those numbers drive: writes are trivial, reads need a cache and stateless servers, storage fits a single primary with replicas. High-level design: `POST /urls`, `GET /{code}`; a `url` table keyed by code; load balancer, redirect servers, Redis, PostgreSQL, a click event stream. Deep dives offered to the interviewer: code generation (collisions and predictability), 301 versus 302, and surviving a database outage on the redirect path. The complete version of this design, with the trade-offs an interviewer will probe, is in [the URL shortener case study](case-study-url-shortener.md).

## Pitfalls

- Memorising one solution per classic problem. Interviewers change a requirement on purpose ("now links expire", "now it is global"); a memorised design cannot adapt, a framework can.
- Treating estimation as a ritual. If a number does not change a decision, skip it and say why.
- Going deep too early. A beautiful cache design for a system with no API yet earns nothing.
- Hiding uncertainty. Interviewers can tell; stating what you would check is credited, guessing confidently is not.
- Letting the diagram sprawl. Every box you draw is one you may be asked about; draw what the requirements need.
- Skipping failure modes. "What happens when Redis is down?" is asked in almost every interview; have the answer ready before it is asked.

## Check yourself

1. You have ten minutes left and no deep dive done yet. What do you do with the remaining time, and what do you say to the interviewer?
2. The interviewer says "I don't think a relational database works here". What are your first two sentences?
3. For each component in your last design, can you name the requirement it serves and what would break without it?
4. Which three questions in the first five minutes most change the design of a chat system, and how?

## Go deeper

- [Hello Interview: System Design in a Hurry](https://www.hellointerview.com/learn/system-design/in-a-hurry/introduction) · the current, interviewer-written version of this framework, with what is expected at each level.
- [Hello Interview: Delivery](https://www.hellointerview.com/learn/system-design/in-a-hurry/delivery) · how to run the conversation, from the same authors.
- [System Design Primer: How to approach a system design interview question](https://github.com/donnemartin/system-design-primer#how-to-approach-a-system-design-interview-question) · the classic step list with worked examples for each classic problem.
- [ByteByteGo](https://bytebytego.com/) · Alex Xu's worked case studies, which follow a four-step version of this timeline (paid, with a free [System Design 101](https://github.com/ByteByteGoHq/system-design-101) repository).

---

Part of [System Design](../README.md) · items 6.1, 6.2
