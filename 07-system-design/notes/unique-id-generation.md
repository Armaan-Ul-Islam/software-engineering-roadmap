# Unique ID generation

> **In one sentence:** Every ID scheme is a trade between coordination (who has to agree so that two nodes never hand out the same value), ordering (whether IDs sort by creation time, which decides how a B-tree index behaves under inserts), size, and what the ID reveals; sequences, UUID v4, UUID v7, Snowflake IDs and content hashes each make that trade differently.

**Why it matters:** The primary key is copied into every index on the table and every table that references it, so a careless choice costs storage and cache hits for the life of the system. Random UUIDs are the usual way to make a write-heavy table slow for no reason; sequential integers are the usual way to let a competitor count your orders. Interviews ask for an ID generator because the question exposes whether you understand coordination.

## The idea

**Database sequences.** `bigint GENERATED ALWAYS AS IDENTITY` in PostgreSQL asks the database for the next number on every insert. Eight bytes, dense, roughly time-ordered, and simple. The cost is that one component allocates every ID: fine with a single primary, a problem once writes are sharded or clients need an ID before they reach the database. Workarounds exist (each shard owns an interleaved range, like Flickr's two ticket servers with odd and even numbers; or application servers fetch blocks of 1,000 and hand them out locally, the hi/lo pattern), and two properties surprise people: sequences have gaps (a rolled-back transaction consumes its value), and the order of IDs is the order of allocation, not of commit, so ID 101 can become visible before ID 100 (see item 3.8 for why this breaks relays that track a "last seen" ID).

**UUID v4.** 122 random bits in 16 bytes, generated anywhere with no coordination, and unguessable. Its one real problem is the index. A B-tree keeps keys in sorted order, so a random key lands on a random leaf page: every insert touches a page that is probably not in memory, splits pages at random positions and leaves them half full, and the index's working set is the whole index. A time-ordered key always lands on the rightmost leaf: the pages fill completely, the hot set is a handful of pages, and the index stays compact. (In some engines that single hot page becomes a contention point; SQL Server's last-page insert contention is the well-known case.) Random keys also defeat any locality between rows created together, which is exactly what most queries want.

**UUID v7** (RFC 9562, 2024) fixes that while keeping the format. The first 48 bits are a Unix timestamp in milliseconds, the remaining bits are random (optionally with a counter for ordering inside a millisecond). Same 16 bytes, same `uuid` column type, no coordination, sorts by creation time, and inserts append to the right of the index. What you give up: the creation time is readable from the ID, and 16 bytes is still twice a `bigint`. PostgreSQL 18 ships a `uuidv7()` function; Java's `UUID.randomUUID()` is v4 only, so v7 comes from a library or a few lines of your own.

**ULID** is the same shape (48-bit millisecond timestamp plus 80 random bits) with a 26-character Crockford base32 text form that sorts lexicographically, and a rule that IDs generated inside one millisecond by one process increment the random part so they stay ordered. It stores as a `uuid` column unchanged, since it is 128 bits.

**Snowflake IDs.** Twitter's design packs a 64-bit integer: 41 bits of milliseconds since a custom epoch (about 69 years), 10 bits of node ID (1,024 generators) and 12 bits of sequence (4,096 IDs per node per millisecond). Eight bytes, time-ordered across nodes to within their clock skew, and millions of IDs per second with no shared component at generation time. The coordination moves to deployment: each node needs a unique ID, from configuration, a coordination service such as ZooKeeper (see item 3.6), or a StatefulSet ordinal. The clock is the weak point. If a node's clock jumps backwards (an NTP correction, a VM migration), the same timestamp comes round again and the sequence could repeat; the generator must remember the last timestamp and refuse or wait (see item 3.5). The 41-bit field also means ordering is only as good as the clocks: node A's ID can sort before node B's although B's event happened first.

**Content hashing.** Make the ID a hash of the content (SHA-256, perhaps truncated). Deterministic, so the same content always gets the same ID and deduplication is free; no coordination; what Git and every content-addressable store do. Two consequences: identical content is one object whether you wanted that or not, and the ID carries no ordering at all.

**Choosing.** Ask four questions. Must IDs sort by time (range scans on recent rows, compact indexes)? How many bytes can every index afford? Is it harmful if outsiders can predict or count IDs (`/orders/10452` invites `/orders/10453` and tells a competitor your daily volume)? Must clients or offline nodes mint IDs before they talk to a server? A common answer is two IDs per entity: a sequence or Snowflake value as the internal key that indexes and foreign keys use, and a random public identifier (UUID v4 or a short random string) in URLs.

## Example: a Snowflake-style generator

Bit layout, most significant bit first:

```text
 0 | 41 bits: milliseconds since 2024-01-01 | 10 bits: node id | 12 bits: sequence
sign  up to 2,199,023,255,551 (about 69 years)   0 to 1,023          0 to 4,095
```

```java
import java.time.Instant;

public final class SnowflakeIdGenerator {

    private static final long CUSTOM_EPOCH_MILLIS = 1_704_067_200_000L;
    private static final int NODE_ID_BITS = 10;
    private static final int SEQUENCE_BITS = 12;
    private static final long MAX_NODE_ID = (1L << NODE_ID_BITS) - 1;
    private static final long SEQUENCE_MASK = (1L << SEQUENCE_BITS) - 1;
    private static final int NODE_ID_SHIFT = SEQUENCE_BITS;
    private static final int TIMESTAMP_SHIFT = SEQUENCE_BITS + NODE_ID_BITS;

    private final long nodeId;
    private long lastTimestamp = -1L;
    private long sequence = 0L;

    public SnowflakeIdGenerator(long nodeId) {
        if (nodeId < 0 || nodeId > MAX_NODE_ID) {
            throw new IllegalArgumentException("nodeId must be between 0 and " + MAX_NODE_ID);
        }
        this.nodeId = nodeId;
    }

    public synchronized long nextId() {
        long timestamp = currentTimestamp();
        if (timestamp < lastTimestamp) {
            throw new IllegalStateException("clock moved backwards by " + (lastTimestamp - timestamp) + " ms");
        }
        if (timestamp == lastTimestamp) {
            sequence = (sequence + 1) & SEQUENCE_MASK;
            if (sequence == 0) {
                timestamp = waitForNextMillisecond(lastTimestamp);
            }
        } else {
            sequence = 0L;
        }
        lastTimestamp = timestamp;
        return (timestamp << TIMESTAMP_SHIFT) | (nodeId << NODE_ID_SHIFT) | sequence;
    }

    private long waitForNextMillisecond(long previousTimestamp) {
        long timestamp = currentTimestamp();
        while (timestamp <= previousTimestamp) {
            Thread.onSpinWait();
            timestamp = currentTimestamp();
        }
        return timestamp;
    }

    private static long currentTimestamp() {
        return System.currentTimeMillis() - CUSTOM_EPOCH_MILLIS;
    }

    public static Instant creationTime(long id) {
        return Instant.ofEpochMilli((id >>> TIMESTAMP_SHIFT) + CUSTOM_EPOCH_MILLIS);
    }

    public static void main(String[] arguments) {
        SnowflakeIdGenerator generator = new SnowflakeIdGenerator(7);
        long first = generator.nextId();
        long second = generator.nextId();
        System.out.println(first);
        System.out.println(second);
        System.out.println("node=" + ((second >>> NODE_ID_SHIFT) & MAX_NODE_ID)
                + " sequence=" + (second & SEQUENCE_MASK)
                + " created=" + creationTime(second));
    }
}
```

Output from one run (the values depend on the clock):

```text
372218869181345792
372218869181345793
node=7 sequence=1 created=2026-10-24T03:04:53.905Z
```

Both calls fell inside the same millisecond, so the IDs differ only in the sequence. The sequence wrapping to zero means 4,096 IDs were issued in one millisecond on this node, and the generator spins until the next millisecond rather than reuse a value. The backwards-clock check is the part people leave out; without it a 50 ms NTP step can produce duplicates. The `CUSTOM_EPOCH_MILLIS` must never change once IDs exist, and the whole method is `synchronized` because the sequence and the last timestamp are read and written together.

## Example: the schemes side by side

| Scheme | Size | Sorted by time | Coordination needed | Predictable | Minted offline | Reveals |
|---|---|---|---|---|---|---|
| Sequence or identity column | 8 bytes | By allocation, not by commit | Every insert asks the database | Yes, enumerable | No | Volume and rate |
| UUID v4 | 16 bytes | No | None | No | Yes | Nothing |
| UUID v7 | 16 bytes | To the millisecond | None | Only the timestamp | Yes | Creation time |
| ULID | 16 bytes, 26 characters as text | To the millisecond, monotonic within a process | None | Only the timestamp | Yes | Creation time |
| Snowflake-style | 8 bytes | To the millisecond, within clock skew | Unique node IDs at deployment | Partly (time and node are visible) | Yes, given a node ID | Creation time, node, rate |
| Content hash | 20 to 32 bytes | No | None | Deterministic from content | Yes | Whether two objects are identical |

## Pitfalls

- UUID v4 as the primary key of a large, write-heavy table. Random inserts across the whole index, half-empty pages, and a working set that does not fit in memory; the symptom is insert throughput falling as the table grows. Use v7, ULID or a Snowflake ID if you need to generate IDs outside the database.
- Storing UUIDs as `varchar(36)`. Thirty-six bytes plus overhead instead of sixteen, in every index that includes the key. PostgreSQL has a `uuid` type; use it.
- Sequential IDs in public URLs. Enumeration (every order, every invoice) and the German tank problem (your volume estimated from a sample of IDs). Expose a random identifier, or make the ID unpredictable.
- Trusting Snowflake ordering across nodes. Two IDs from different nodes are ordered by those nodes' clocks, not by the events; for "happened before" you need the mechanisms in item 3.5.
- Letting two generators share a node ID. A copied configuration file or a container restarted with a reused ordinal, and duplicates appear only when both are busy in the same millisecond, which makes the bug rare and hard to find.
- Assuming `UUID.randomUUID()` is time-ordered, or that a `uuid` column sorts by creation time. v4 has no time component at all.

## Check yourself

1. Why do random primary keys make inserts slower as a table grows, and which property of UUID v7 removes the problem while keeping the 16-byte format?
2. A Snowflake node's clock is corrected backwards by 30 ms. What exactly could go wrong without the `timestamp < lastTimestamp` check, and what does the check cost?
3. You need IDs that a mobile app can create while offline, that must not reveal creation time, and that will be the primary key of a 500-million-row table. Which scheme, and what do you give up?
4. A relay publishes outbox rows in ID order and remembers the highest ID it has sent. Explain, using how sequences allocate values, how it can skip a row.

## Go deeper

- [RFC 9562: UUIDs](https://www.rfc-editor.org/rfc/rfc9562.html) · the current specification, including the v7 layout and the guidance on monotonic counters.
- [Twitter Snowflake](https://github.com/twitter-archive/snowflake) · the original 64-bit layout and the reasons behind it.
- [ULID specification](https://github.com/ulid/spec) · the format, the base32 alphabet and the monotonicity rule.
- [Flickr: Ticket servers](https://code.flickr.net/2010/02/08/ticket-servers-distributed-unique-primary-keys-on-the-cheap/) · odd and even sequences on two MySQL servers; the simplest way to shard a sequence.
- [PostgreSQL: UUID functions](https://www.postgresql.org/docs/current/functions-uuid.html) · the built-in generators, including `uuidv7()`.

---

Part of [System Design](../README.md) · item 2.12
