# Consistency models, CAP and PACELC

> **In one sentence:** A consistency model is the contract about which values a read may return given the writes that happened elsewhere; CAP says only that during a network partition a replicated system must give up either linearizable reads or answering every request, and PACELC adds the trade-off you pay every day: latency against consistency when there is no partition at all.

**Why it matters:** "Eventually consistent" is used to excuse bugs that are really missing session guarantees, and "we are AP" is used to describe databases that are nothing of the kind. Knowing the precise models lets you say which anomaly a user can see, choose a database whose defaults match, and answer the interview question "what does CAP actually say?" without repeating the two-out-of-three myth.

## The idea

Models for a single object (a register, a row, a key), from strongest to weakest, each with the anomaly it rules out:

| Model | Guarantee | The anomaly that distinguishes it |
|---|---|---|
| Linearizable | Every operation appears to happen atomically at one instant between its start and its response, and real time is respected: once any client has seen a write, every later read sees it. | Alice refreshes and sees the final score; she tells Bob; Bob refreshes a second later and sees the match still running. Impossible under linearizability, allowed by everything below. |
| Sequential | All clients observe the same order of operations, consistent with each client's own program order, but that order need not match real time. | Alice and Bob both eventually see the new score, in the same order as every other change, yet Bob's read can lag Alice's by seconds. A system that serves everyone from the same replication stream, delayed, is sequential. |
| Causal | Operations that are causally related (a reply after the message it answers, a read followed by a write) are seen in that order by everyone; concurrent operations may be seen in different orders. | Prevented: a reply appearing before the question. Allowed: two unrelated comments posted at the same moment appear in different orders on different screens. |
| Eventual | If writes stop, all replicas converge to the same value. No bound on when, and no guarantee about what you see in between. | You post a comment, refresh, and it is gone (the read went to a lagging replica); refresh again and it is back. |

Between causal and eventual sit the **session guarantees**, which are what most applications actually need and what "eventual consistency" usually fails to provide out of the box:

- Read-your-writes: after I write, my own reads see it. Violation: you change your profile photo and the page still shows the old one. Implementations: route a user's reads to the leader for a short time after their write, or send the write's position (a log sequence number) with the read and wait for the replica to catch up.
- Monotonic reads: once I have seen a value, I never see an older one. Violation: a comment thread grows, you refresh, it shrinks. Implementation: pin each user to one replica, or carry the last-seen version.
- Monotonic writes and writes-follow-reads complete the set and together give causal consistency for a session.

Transactions have a separate ladder (Read Committed, snapshot isolation, serializable) about isolation between multi-object operations, not about replicas. Strict serializability is the top of both ladders; that is what Spanner means by external consistency.

**What CAP says.** For a replicated system, the formal theorem (Gilbert and Lynch, 2002) is: you cannot have all three of linearizability (C), availability in the sense that every request to a non-failed node gets a non-error response (A), and tolerance of a network partition (P). Because networks do partition, the real statement is: when a partition happens, each operation either waits or errors (giving up A) or answers from what the local side knows (giving up C). That is all.

The common misreadings:

1. "Pick two of three." Partition tolerance is not a choice; a system that stops working during a partition has not chosen CA, it has failed.
2. "CA systems exist." A single-node database is not distributed, so CAP does not describe it.
3. "AP means eventually consistent, so any staleness is acceptable." CAP's A is a formal property about partitions; it says nothing about normal operation, latency, or which weaker model you provide.
4. "Our database is CP." Most databases are neither: a leader-based system whose minority side refuses writes is not A, and if clients read from asynchronous replicas it is not C either. Kleppmann's advice is to describe the actual guarantees instead.

**PACELC** (Abadi) repairs the framing: *if* there is a Partition, trade Availability against Consistency; *Else*, trade Latency against Consistency. The second half is where most daily decisions live. A synchronous replica write costs a round trip on every commit (EC); an asynchronous one returns at once and risks stale reads or lost writes on failover (EL). In Abadi's classification Dynamo, Cassandra and Riak are PA/EL; VoltDB and Megastore are PC/EC; MongoDB is PA/EC; Yahoo's PNUTS is PC/EL. Many systems let you choose per operation, so a database's position is a setting, not a fact.

## Example: what common systems offer by default

| System | Default behaviour | How to get stronger reads |
|---|---|---|
| PostgreSQL, MySQL with asynchronous replicas | Reads on the primary are strong; reads on replicas can be stale (eventual, no session guarantees). | Read from the primary, or use synchronous replication and wait for apply on the replica you read from. |
| MongoDB replica set | Reads from the primary with read concern `local`, which can return data that is later rolled back after a failover. | Read concern `majority` or `linearizable`; causally consistent sessions for read-your-writes. |
| Cassandra | Tunable per query; consistency level `ONE` is eventual. | `QUORUM` reads and writes (R + W > N) for single-key strong reads in normal operation; lightweight transactions for linearizable compare-and-set. |
| DynamoDB | Eventually consistent reads. | `ConsistentRead = true` on the table (not on global secondary indexes); transactions for multi-item atomicity. |
| Redis with replicas | Single-threaded, so one node is strong; replication is asynchronous and failover can lose acknowledged writes. | There is no setting that makes a replicated Redis linearizable; design for it. |
| ZooKeeper | Writes are linearizable; reads are served locally by any server and can be stale (sequential consistency). | Call `sync()` before the read. |
| etcd | Linearizable reads and writes. | Already strong; opt into serializable (possibly stale) reads for speed. |
| Google Spanner | External consistency (strict serializability) for reads and writes. | Already strong; opt into bounded-staleness reads for latency. |
| Amazon S3 | Strong read-after-write consistency for all operations. | Not needed. |

Read the pattern: the systems that are strong by default pay for it with latency on every operation; the ones that are eventual by default offer strength as an option that you must ask for on each read.

## Pitfalls

- Reading from a replica right after writing to the leader. The classic "I saved it and it is not there" bug; fix with read-your-writes routing, not with a retry.
- Assuming a quorum read is linearizable. R + W > N prevents stale reads in the simple case, but concurrent and partially failed writes still produce anomalies; see DDIA chapter 5.
- Calling a system AP because it uses asynchronous replication. Asynchronous replication during normal operation is the EL in PACELC; it says nothing about how the system behaves under partition.
- Mixing up the two ladders. Serializable isolation does not imply linearizability (a serializable database with stale replicas is still stale), and linearizable single-key operations do not give you transactions.

## Check yourself

1. Alice sees the new value and tells Bob, whose later read returns the old value. Which model forbids this, and which weaker model would still allow it while keeping everyone's view in the same order?
2. A user updates their address and the confirmation page shows the old one. Name the missing guarantee and two ways to implement it on a leader-with-replicas database.
3. A colleague says "we chose availability over consistency, so we are AP". Which two assumptions in that sentence does CAP not support?
4. For DynamoDB and Cassandra, where does each sit in PACELC by default, and what single change moves it?

## Go deeper

- [Jepsen: Consistency Models](https://jepsen.io/consistency) · the map of models with precise definitions; the reference to keep open.
- [Kleppmann: Please stop calling databases CP or AP](https://martin.kleppmann.com/2015/05/11/please-stop-calling-databases-cp-or-ap.html) · the clearest account of what CAP does and does not say.
- [PACELC design principle](https://en.wikipedia.org/wiki/PACELC_design_principle) · the framing and the classification table of systems.
- [Brewer: CAP Twelve Years Later](https://www.infoq.com/articles/cap-twelve-years-later-how-the-rules-have-changed/) · the author of the conjecture on how it has been misunderstood.
- [Designing Data-Intensive Applications, chapters 5 and 9](https://dataintensive.net/) · replication lag anomalies and linearizability, with the football score example.

---

Part of [System Design](../README.md) · items 3.3, 3.4
