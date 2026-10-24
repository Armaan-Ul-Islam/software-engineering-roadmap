# Clocks, ordering and Lamport timestamps

> **In one sentence:** Wall clocks on different machines disagree by more than the gap between the events you want to order, so distributed systems order events by causality instead (Lamport timestamps give an order consistent with it, vector clocks also detect when two events are concurrent) or buy clocks with a known error bound and wait it out, as Spanner does.

**Why it matters:** "Last write wins" with wall-clock timestamps silently discards writes from any node whose clock is a little behind, and the loss is invisible until a customer asks where their update went. Leases, lock expiry, cache TTLs, token expiry and conflict resolution all depend on time, and each has a failure mode that only appears when a clock jumps. Interviewers ask about Lamport clocks to find out whether you know that "which happened first?" has no answer in a distributed system unless you build one.

## The idea

**Why wall clocks lie.** A machine's time-of-day clock is a quartz oscillator corrected by NTP. The oscillator drifts (DDIA quotes Google's assumption of 200 parts per million, about 17 seconds a day uncorrected). NTP corrects it, but synchronisation over a network is only as accurate as the round-trip asymmetry, a few milliseconds inside a datacenter and tens of milliseconds or worse across the internet; and when the error is large, NTP steps the clock rather than slewing it, so time jumps, forwards or backwards. Leap seconds have produced minutes with 61 seconds that crashed systems, which is why the big clouds smear them over hours. A virtual machine paused for a live migration wakes with its clock behind and then jumps. The result: two machines' timestamps can differ by more than the time between two events, so comparing them says nothing about which event came first.

**Two clocks in every process.** The time-of-day clock (`System.currentTimeMillis()`, `Instant.now()`) answers "what time is it" and may jump. The monotonic clock (`System.nanoTime()`) answers "how much time has passed" and never goes backwards, but its absolute value means nothing outside the process. Use monotonic for timeouts, durations and rate limits; use time-of-day for timestamps that humans or other machines read, and never subtract two time-of-day readings to measure anything.

**Happens-before.** Lamport's definition: event a happens before event b (a → b) if they are on the same node and a came first, or a is the sending of a message and b its receipt, or there is a chain of such steps. If neither a → b nor b → a, the events are concurrent: nobody could tell which was first, because no information flowed between them. This is the only notion of order a distributed system can observe without synchronised clocks.

**Lamport timestamps.** Each node keeps a counter. Increment it for every local event and stamp outgoing messages with it; on receiving a message, set the counter to `max(local, received) + 1`. The guarantee: if a → b then L(a) < L(b). Break ties with the node identifier and you have a total order of all events that respects causality. Two limits matter. The converse fails: L(a) < L(b) does not mean a → b; the events may be concurrent. And the order is only knowable in hindsight: a node cannot know whether a message with a smaller timestamp is still on its way, so Lamport timestamps alone cannot decide "is this username still free" (that needs consensus, see item 3.6).

**Vector clocks.** Replace the counter with a vector, one entry per node. A node increments its own entry for each event and on each send; on receive it takes the element-wise maximum of its vector and the message's, then increments its own entry. Now comparison tells the whole story: if every entry of V(a) is less than or equal to the matching entry of V(b) and the vectors differ, then a → b; if each vector has an entry greater than the other's, the events are concurrent. This is how Dynamo-style stores (Riak, the original Dynamo) detect that two clients wrote the same key without seeing each other, and keep both versions as siblings for the application to merge rather than guessing. The cost is a vector that grows with the number of writers and must be pruned.

**Hybrid logical clocks.** A Lamport timestamp has no relation to real time, which makes it useless for "give me a snapshot as of 14:05" or for humans reading logs. An HLC is a pair: a physical component that is the maximum of the local wall clock and any physical time seen in messages, and a logical counter that increments when the physical part would not move. It stays within a bounded distance of real time, never goes backwards, and preserves happens-before like a Lamport clock. CockroachDB uses HLCs for transaction timestamps and refuses to run a node whose clock offset exceeds a configured bound (500 ms by default), because the correctness argument needs the bound.

**Where this shows up.**

1. Last-writer-wins. Cassandra resolves concurrent writes to a cell by the larger timestamp, supplied by the client or coordinator. A node with a clock a second fast wins every conflict for a second, and a delete whose timestamp is older than a later write resurrects the data. LWW is a choice to lose data silently; it is only acceptable when a lost update genuinely does not matter.
2. Leases and locks. A lease that expires at a wall-clock time is judged by two clocks, the holder's and the grantor's, that do not agree (see item 3.9).
3. Spanner's TrueTime. Google equips datacenters with GPS receivers and atomic clocks, and the API returns an interval `[earliest, latest]` that is guaranteed to contain the true time, typically a few milliseconds wide. A transaction takes its commit timestamp from the interval and then waits until `latest` has passed before releasing its locks (commit wait), so any transaction that starts afterwards gets a later timestamp. Clock uncertainty is not eliminated; it is measured and waited out, and that is what buys external consistency across continents.
4. Everything with an expiry: TLS certificates, JWTs, cache TTLs, rate-limit windows. A node an hour behind accepts expired tokens; a node an hour ahead rejects valid ones.

## Example: three nodes, Lamport and vector clocks side by side

Nodes A, B and C. Each node's counter starts at 0; vectors are written (A, B, C). The messages are m1 from A to B, m2 from B to C, m3 from C to A.

| Step | Node | Event | Lamport rule | Lamport | Vector rule | Vector |
|---|---|---|---|---|---|---|
| 1 | A | local event a1 | 0 + 1 | 1 | increment A | (1, 0, 0) |
| 2 | B | local event b1 | 0 + 1 | 1 | increment B | (0, 1, 0) |
| 3 | A | send m1 | 1 + 1 | 2 | increment A | (2, 0, 0) |
| 4 | B | receive m1 | max(1, 2) + 1 | 3 | max((0,1,0), (2,0,0)), then increment B | (2, 2, 0) |
| 5 | C | local event c1 | 0 + 1 | 1 | increment C | (0, 0, 1) |
| 6 | B | send m2 | 3 + 1 | 4 | increment B | (2, 3, 0) |
| 7 | C | receive m2 | max(1, 4) + 1 | 5 | max((0,0,1), (2,3,0)), then increment C | (2, 3, 2) |
| 8 | C | send m3 | 5 + 1 | 6 | increment C | (2, 3, 3) |
| 9 | A | local event a2 | 2 + 1 | 3 | increment A | (3, 0, 0) |
| 10 | A | receive m3 | max(3, 6) + 1 | 7 | max((3,0,0), (2,3,3)), then increment A | (4, 3, 3) |

Reading the table:

- Causality is respected. a1 → send m1 → receive m1 → send m2 → receive m2 → send m3 → receive m3 has Lamport values 1, 2, 3, 4, 5, 6, 7, strictly increasing, and each vector in that chain is less than or equal to the next in every entry.
- The converse fails for Lamport. c1 has Lamport 1 and a2 has Lamport 3, yet nothing that happened on C had reached A when a2 occurred (m3 arrives at step 10, after a2), and nothing from A after a2 reached C. They are concurrent, and the Lamport values cannot show it.
- The vectors can. c1 is (0, 0, 1) and a2 is (3, 0, 0): the first entry is larger in a2, the third is larger in c1, so neither is less than or equal to the other, which is the definition of concurrent. A Dynamo-style store would keep both as siblings.
- Equal Lamport values (a1 and b1, both 1) are always concurrent; the node identifier breaks the tie for the total order, arbitrarily but consistently.

The clock itself is a few lines:

```java
public final class LamportClock {

    private long counter;

    public synchronized long tick() {
        counter++;
        return counter;
    }

    public synchronized long receive(long receivedTimestamp) {
        counter = Math.max(counter, receivedTimestamp) + 1;
        return counter;
    }
}
```

`tick()` stamps a local event or an outgoing message; `receive()` is applied to every incoming message before the message is processed.

## Pitfalls

- Ordering events from different machines by their wall-clock timestamps. The skew between the machines is usually larger than the interval you are trying to resolve; the order you get is the order of their clock errors.
- Measuring elapsed time with `System.currentTimeMillis()` or `Instant.now()`. An NTP step makes a timeout fire instantly or never; use `System.nanoTime()` for durations.
- Last-writer-wins as a default conflict strategy. It is data loss by design, biased towards the node with the fastest clock; choose it only for data where that is acceptable, and say so in the design.
- Reading L(a) < L(b) as "a caused b". Lamport timestamps order causally related events correctly and order everything else arbitrarily; only a vector clock distinguishes the two cases.
- Assuming the cloud's clocks are good enough. Managed NTP in the big clouds keeps instances within a millisecond or so of each other in normal operation, and a stalled VM or a misconfigured container image still gives you a clock that is seconds off; design for the error you cannot see.
- Ignoring the clock in lease and lock protocols. Expiry judged by two different clocks is the root of the stale-writer problem in item 3.9.

## Check yourself

1. Two servers log the same request, one at 10:00:00.120 and the other at 10:00:00.090. What can you conclude about which server handled it first, and what would you need to conclude anything?
2. In the table, which pairs of events have Lamport values that put them in the "wrong" order relative to real time, and why is that not a bug in Lamport's scheme?
3. Why can a Lamport clock not be used on its own to decide whether a username is still available, and which mechanism can?
4. Spanner's commit wait makes every transaction slower by the clock uncertainty. What does the system get in return, and why would the same idea not work with ordinary NTP-synchronised clocks?

## Go deeper

- [Lamport: Time, Clocks, and the Ordering of Events in a Distributed System](https://lamport.azurewebsites.net/pubs/time-clocks.pdf) · the 1978 paper; short, readable, and the source of happens-before and logical clocks.
- [Designing Data-Intensive Applications, chapter 8](https://dataintensive.net/) · unreliable clocks, process pauses, and why timestamps are not enough for ordering.
- [Kleppmann: Distributed Systems lectures](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB) · the lectures on physical time, logical time and vector clocks, with worked traces like the one above.
- [Justin Sheehy: There Is No Now](https://queue.acm.org/detail.cfm?id=2745385) · why "simultaneous" has no meaning across machines, written for practitioners.
- [Cloud Spanner: TrueTime and external consistency](https://cloud.google.com/spanner/docs/true-time-external-consistency) · how bounded clock uncertainty plus commit wait gives a global order.

---

Part of [System Design](../README.md) · item 3.5
