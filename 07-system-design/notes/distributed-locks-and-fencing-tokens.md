# Distributed locks and fencing tokens

> **In one sentence:** A lock across machines must expire (otherwise a crashed holder blocks everyone forever), and anything that expires can be held by two clients at once when one of them pauses, so a distributed lock is only safe if the resource it protects can reject the stale holder, which is what a fencing token does; and very often you do not need the lock at all.

**Why it matters:** "Only one worker may process this job at a time" is a requirement in almost every backend, and the obvious implementation (a Redis key with a TTL) is wrong in a way that passes every test and loses data once a year, after a garbage-collection pause nobody saw. Knowing why that fails, and that the fix lives in the storage layer rather than the lock service, is what the Redlock debate was about and what interviewers probe when they ask "what if the client dies while holding the lock?".

## The idea

**Why it is hard.** Inside one process, a lock is safe because the operating system knows when the holder dies and nobody else can hold the mutex meanwhile. Across machines, the lock service cannot tell a crashed client from a slow one: the client may be mid garbage collection (a stop-the-world pause of seconds is routine, minutes is possible on large heaps), paused by the hypervisor, swapped out, blocked on a disk, or simply on the far side of a congested network. Whatever the lock service decides, it can be wrong. If it never releases the lock, one crash halts the system. If it releases after a timeout, a paused holder may wake up and continue working while someone else holds the lock.

**Leases and TTLs.** The practical compromise is a lease: a lock granted for a fixed time (say 10 s) that the holder must renew before it runs out. A crashed holder's lease lapses and the lock is free again. But the lease is judged by two clocks that do not agree (the grantor's and the holder's, see item 3.5), and renewal is a request that can be delayed by exactly the pause it is meant to detect. Kleppmann's distinction tells you how much this matters: a lock for *efficiency* (avoid doing the same expensive work twice; a rare duplicate is harmless) can tolerate an occasional double holder, and a lock for *correctness* (two holders corrupt data, charge twice, send the wrong email) cannot.

**Fencing tokens.** Make the lock service hand out a number that increases with every grant: 33 to this holder, 34 to the next. The holder sends the token with every write to the protected resource, and the resource remembers the highest token it has seen and rejects anything lower. A stale holder, waking from a pause with token 33 after token 34 has been used, is refused by the storage, not by the lock service, which could never have stopped it. Sources of tokens: ZooKeeper's `zxid` or the znode version, etcd's `ModRevision` of the lock key, a database sequence, a Kubernetes `Lease` object's `resourceVersion`. The requirement that makes or breaks the scheme is that the resource must check the token; a third-party API that ignores an extra header cannot be fenced, and then the lock protects nothing.

**Redlock and the critique.** Redlock is the algorithm in the Redis documentation for locking with N independent Redis nodes: set the key with a random value and a TTL on each node, count a lock as acquired if a majority accepted it within less than the TTL, and subtract the elapsed time from the validity. Kleppmann's 2016 analysis made two points. First, Redlock's safety depends on timing assumptions (bounded network delay, bounded process pauses, bounded clock drift) that real systems violate; a clock jump on one Redis node, or a long pause in the client, produces two holders. Second, and worse, the random value is not a fencing token, so even a correctly implemented Redlock gives the storage no way to tell the stale holder from the current one. Antirez replied that the timing assumptions are reasonable in practice and that lease expiry is a property of every lock with a TTL, not of Redlock alone. The useful conclusion: a single Redis instance with `SET key value NX PX` is a fine *efficiency* lock and Redlock adds little to it; for *correctness* you need fencing tokens from a store with a real ordering guarantee.

**Use the database you already have.** When the protected state lives in a relational database, the database is the lock service, and a far better one:

1. `SELECT ... FOR UPDATE` locks the row for the duration of the transaction. The protected write and the lock release are the same commit, so a paused holder either commits its work atomically or holds nothing; there is no window in which it believes it has the lock but does not. `FOR UPDATE SKIP LOCKED` turns the same idea into a job queue that many workers can drain without coordination.
2. Advisory locks (`pg_advisory_xact_lock(key)`, `pg_try_advisory_lock(key)`) lock an application-defined number rather than a row. They are released when the transaction or session ends, so a crashed client's connection drop frees them without a TTL.
3. A unique constraint. "Only one active job per customer" is `CREATE UNIQUE INDEX ... WHERE status = 'running'`; the second inserter fails. No lock, no lease, no token.

**A consensus store** (etcd, ZooKeeper, Consul; see item 3.6) is the right tool when the protected resource is outside any database: leader election for a scheduler, ownership of a partition, a singleton process across a fleet. They give leases with linearizable grants and a monotonic revision to use as the fencing token, at the cost of running the cluster and understanding its failure modes.

**Do you need a lock at all?** Usually the real requirement is one of: no duplicate effect (make the operation idempotent, see item 3.8 and item 4.4); no lost update (a version column and a conditional `UPDATE ... WHERE version = ?`, or a conditional write in DynamoDB or S3); one owner per unit of work (partition assignment, as Kafka does per consumer group, with an epoch to fence old owners); or at most one row in some state (a constraint). Each of these is checked by the storage at write time, which is where a fencing token ends up anyway. A lock that only exists to make a non-idempotent sequence of calls safe is a sign that the sequence should be redesigned.

## Example: the pause, step by step

A worker locks `invoice:42` to recompute its total. The lease is 10 s. The storage is a PostgreSQL table with a `fencing_token` column.

```text
time (s)   0        2                         10        11    12       17
client 1   lock(33) read, start computing     .         .     .        wake, write(33)  -> rejected
                     [ stop-the-world pause ................................ ]
lease      |<------------- 10 s ------------>| expired
client 2                                               lock(34) read, write(34) ok, unlock
storage                                                        highest token seen = 34
```

1. Client 1 acquires the lock and receives token 33. It reads the invoice and starts computing.
2. At second 2, the JVM stops the world. The thread is frozen mid computation; it cannot renew the lease and does not know that time is passing.
3. At second 10, the lock service expires the lease. From its point of view client 1 is dead.
4. Client 2 acquires the lock with token 34, recomputes the total and writes it. The storage records 34 as the highest token seen. Client 2 releases the lock.
5. At second 17, client 1 resumes exactly where it stopped. Its local code still believes it holds the lock; nothing in the program told it otherwise. It writes its stale result with token 33.
6. The storage compares 33 with 34 and rejects the write. Client 1 sees the rejection, discards its work and either retries from the start or reports failure.

Without the token, step 6 overwrites client 2's result with a value computed from data read before client 2 ran. Nothing fails, nothing logs, and the invoice is wrong.

The storage side is one conditional statement:

```sql
UPDATE invoice
SET total = $1, fencing_token = $2
WHERE id = 42 AND fencing_token < $2;
```

An update count of 0 means a newer holder has written; the client must treat it as "I no longer hold the lock". The same statement is what a version column does for optimistic locking, which is the clue that the token is a version number managed by the lock service instead of by the row.

Where the token comes from in etcd: acquire with a lease (`Grant` with a TTL, then a transaction that creates the lock key only if it does not exist), and use the key's `ModRevision` as the token; it is a cluster-wide, monotonically increasing number, so a later grant always has a higher value.

## Pitfalls

- A Redis key with a TTL as a correctness lock. It works until the first pause or clock step longer than the TTL, then two clients hold it and the storage cannot tell.
- Checking the lock, then writing. "Am I still the holder?" followed by a write is a race whatever the lock service; the check must be part of the write, which is what the token achieves.
- A TTL shorter than the work. Every slow run becomes a double holder by design; size the lease for the slow case and renew it, or split the work.
- Renewing the lease in the same thread that does the work. A pause stops both, so renewal cannot detect it; and a renewal from another thread does not help a paused writer either, which is why the token is checked at the storage.
- Tokens the resource ignores. If the downstream system does not compare tokens, the fencing is theatre; find a resource-side check (conditional write, version, constraint) or make the operation idempotent.
- Reaching for a distributed lock when the state is in one database. `FOR UPDATE` or a unique index is simpler, faster and actually correct.
- Treating "leader" as a fact. A leader-elected process must still assume it may have lost leadership at any instant, and fence every externally visible action with its election epoch.

## Check yourself

1. Why must a distributed lock expire, and what does that force you to accept about the number of simultaneous holders?
2. In the example, client 1 renews its lease from a separate heartbeat thread. Does that prevent the stale write? Explain what does and does not change.
3. A colleague proposes Redlock across five Redis nodes to protect payment processing. What are the two objections, and what would you propose instead if the payments live in PostgreSQL?
4. Name three requirements that sound like "we need a lock" and the storage-level mechanism that satisfies each without one.

## Go deeper

- [Kleppmann: How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) · the pause diagram, fencing tokens, and the analysis of Redlock's assumptions.
- [antirez: Is Redlock safe?](http://antirez.com/news/101) · the author's reply; read both and form your own view.
- [Redis: Distributed Locks with Redis](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/) · the Redlock algorithm as the Redis documentation describes it, including its own caveats.
- [PostgreSQL: Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS) · session and transaction advisory locks and when each releases.
- [Patterns of Distributed Systems: Lease](https://martinfowler.com/articles/patterns-of-distributed-systems/lease.html) · leases implemented over a consensus log, with code.
- [ZooKeeper Recipes: Locks](https://zookeeper.apache.org/doc/current/recipes.html) · the ephemeral sequential znode recipe and why it avoids the herd effect.

---

Part of [System Design](../README.md) · item 3.9
