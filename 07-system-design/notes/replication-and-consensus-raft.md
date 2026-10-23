# Replication and consensus: Raft in one page

> **In one sentence:** Replication keeps copies of data on several nodes so that reads scale and failures do not lose data; the hard part is agreeing who is in charge and what has been committed when nodes crash and the network misbehaves, and consensus algorithms such as Raft are the only correct answer to that question.

**Why it matters:** Every outage story that ends with "two primaries" or "the failover lost the last ten seconds of orders" is a replication story. Knowing why those happen, and what consensus costs, decides whether you put etcd under a coordination problem or a cron job and a hope.

## The idea

**Three ways to replicate.**

1. Single-leader (PostgreSQL, MySQL, MongoDB, Kafka partitions). All writes go to the leader, which ships them to followers; reads may go to followers. Synchronous replication waits for a follower to acknowledge before confirming the write (no lost writes, but one slow follower stalls everything); asynchronous replication confirms at once (fast, but acknowledged writes can be lost if the leader dies before shipping them).
2. Multi-leader (multi-datacenter databases, offline-capable clients, collaborative editors). Each site accepts writes and replicates to the others. Writes to the same record on two leaders conflict, and somebody has to resolve it: last-writer-wins silently discards data, merging needs application logic or CRDTs. Auto-increment keys collide and constraints cannot be checked across leaders.
3. Leaderless (Dynamo, Cassandra, Riak). Clients write to N replicas and wait for W acknowledgements; reads ask R replicas and take the newest version. With W + R > N a read overlaps at least one up-to-date replica in the simple case; replicas missed by a write are repaired later (read repair, anti-entropy, hinted handoff). Concurrent writes produce siblings that something must merge, and the quorum condition alone does not give linearizability (see item 3.3).

**Why failover is hard.** When the leader stops answering, three questions have no safe answer without coordination. Is it dead or merely slow? A short timeout causes failovers under load; a long one extends the outage. Which follower becomes leader? One that is behind will overwrite or discard committed writes; a well-known GitHub incident in 2012 promoted a lagging MySQL replica and reused primary keys that other systems had already seen. What if the old leader comes back? If both accept writes you have split brain and two diverging histories. The fixes are the same ingredients consensus formalises: a majority must agree on the new leader, each leadership has a number (epoch, term, generation) that is attached to every message, and anything stamped with an old number is rejected.

**What consensus solves.** Consensus makes a set of nodes agree on a sequence of values (a replicated log) so that every node applies the same operations in the same order, with safety guaranteed always and progress guaranteed whenever a majority is up and can talk. Leader election, atomic broadcast and a linearizable compare-and-set are all equivalent to it. The FLP result says no deterministic algorithm can guarantee progress in a fully asynchronous network with one crash, so practical algorithms use timeouts and may stall, but never return a wrong answer.

**Raft in one page.**

- Terms. Time is divided into numbered terms. Each term has at most one leader. Every message carries the sender's term; a node that sees a higher term adopts it and becomes a follower. This is the fencing that kills a stale leader.
- Roles and election. Followers expect periodic AppendEntries heartbeats from the leader. If a follower hears nothing for an election timeout (randomised, say 150 to 300 ms), it increments its term, becomes a candidate, votes for itself and asks the others for votes. A node grants one vote per term, and only to a candidate whose log is at least as up to date as its own (compare the last entry's term, then its index). A majority of votes makes a leader; a split vote times out and tries again with new random timeouts.
- Log replication. The leader appends a client's command to its log and sends it to all followers. When a majority have stored it, the entry is committed: the leader applies it, replies to the client, and tells followers the new commit index in later heartbeats. The AppendEntries message carries the index and term of the preceding entry; a follower rejects it if its own log disagrees, and the leader backs up until the logs match, then overwrites the follower's divergent tail. Committed entries are never overwritten because the election rule guarantees the new leader already has them.
- The rest. Snapshots compact the log; membership changes go through a joint configuration or one server at a time; reads must either go through the log or use a leader lease to stay linearizable.

**The cost, and where to pay it.** Every write waits for a majority round trip, so a cluster spread across regions pays cross-region latency on every commit; 2f + 1 nodes tolerate f failures (3 tolerate 1, 5 tolerate 2); the leader handles every write and becomes the throughput ceiling; a minority side of a partition cannot make progress at all. That is why consensus is used for small, critical state: cluster membership and metadata (ZooKeeper, etcd, Consul, Kafka's KRaft controller), leader election for other systems, configuration, distributed locks and leases (see item 3.9). Databases that run Raft or Paxos for the data itself (Spanner, CockroachDB, TiKV) do so per shard and accept the latency. For bulk data, caches, analytics and anything that tolerates eventual consistency, ordinary replication with consensus only for "who is the leader" is the cheaper design.

## Example: a Raft election with three nodes

Nodes S1, S2, S3. S1 is leader in term 1, sending heartbeats every 50 ms; all logs end at index 10, term 1.

1. S1 crashes. Heartbeats stop.
2. S2's election timeout fires at 170 ms (S3's would fire at 260 ms). S2 sets its term to 2, becomes a candidate, votes for itself and sends RequestVote(term 2, lastLogIndex 10, lastLogTerm 1) to S1 and S3.
3. S3 receives it. Term 2 is higher than its term 1, so it adopts term 2. It has not voted in term 2, and S2's log (index 10, term 1) is at least as up to date as its own, so it grants the vote and resets its election timer.
4. S2 has two votes out of three, a majority, and becomes leader for term 2. It immediately sends heartbeats so that S3 does not time out.
5. S1 restarts believing it is leader of term 1 and sends a heartbeat. S2 and S3 reply with term 2; S1 steps down to follower and adopts term 2. The old leader is fenced off without any human deciding it was dead.

Two variations show why the rules are shaped as they are:

- Split vote. If S2 and S3 time out within a few milliseconds of each other, both become candidates for term 2, both vote for themselves and both refuse the other (one vote per term). Neither has a majority. They wait new random timeouts; whichever fires first starts term 3 and wins. Randomised timeouts make this rare, and a fixed timeout would make it repeat forever.
- An entry only the old leader had. Suppose S1 appended index 11 and replicated it to S3 before crashing. It reached a majority (S1 and S3) and may have been committed. S3 therefore refuses S2's vote request: its log (index 11) is more up to date than S2's (index 10). S2 cannot win; S3 times out, starts term 3, S2 grants the vote, and S3 leads with index 11 intact. Had S1 replicated index 11 to nobody, no client could have received a commit for it, and overwriting it later is correct.

## Pitfalls

- Asynchronous replication with automatic failover and no fencing. You have chosen to lose acknowledged writes on failover; make sure the business knows.
- Two nodes. A majority of two is two; a cluster of two cannot survive the loss of either. Consensus clusters have odd sizes for a reason.
- Reading from a Raft follower and expecting linearizability. Followers lag; only leader reads through the log (or with a lease) are linearizable.

## Check yourself

1. Why can an asynchronously replicated leader-follower database lose a write it acknowledged, and what does synchronous replication cost to prevent it?
2. In the election example, why must S3 refuse S2's vote when S3's log is longer? What could go wrong if it granted it?
3. A five-node etcd cluster is split 3 to 2. Describe what each side can and cannot do, and why.
4. You need to make sure only one instance of a scheduler runs at a time across 20 pods. Why is consensus the right tool here but the wrong tool for storing the scheduler's job history?

## Go deeper

- [The Raft consensus algorithm](https://raft.github.io/) · the paper, the interactive visualisation, and implementations in every language.
- [The Secret Lives of Data: Raft visualised](https://thesecretlivesofdata.com/raft/) · step through elections and log replication exactly as in the example above.
- [Designing Data-Intensive Applications, chapters 5 and 9](https://dataintensive.net/) · replication topologies and their anomalies, then consensus and why total order broadcast is the same problem.
- [Kleppmann: Distributed Systems lectures](https://www.youtube.com/playlist?list=PLeKd45zvjcDFUEv_ohr_HdUFe97RItdiB) · the quorum, replication and consensus lectures in a rigorous but followable form.

---

Part of [System Design](../README.md) · items 3.1, 3.6
