# Consistent hashing

> **In one sentence:** Consistent hashing places both servers and keys on the same circular hash space and assigns each key to the next server clockwise, so that adding or removing one server moves only the keys that server owns, instead of reshuffling almost everything the way `hash(key) mod N` does.

**Why it matters:** Any system that spreads keys over a changing set of nodes (a cache cluster, a sharded key-value store, a stateful load balancer) has to answer "which node owns this key?" in a way that survives nodes joining and leaving. Get it wrong and every scaling event is a cache-miss storm or a data migration of the whole dataset. It appears in nearly every system design interview that involves more than one cache or database node.

## The idea

**The problem with modulo.** With N nodes, `node = hash(key) mod N` spreads keys evenly and costs nothing. But when N changes to N + 1, a key stays put only if `hash mod N == hash mod (N + 1)`, which is true for about one key in N + 1. Going from 3 to 4 nodes moves roughly 75 percent of the keys; from 99 to 100, 99 percent. For a cache that means the hit rate drops to near zero at the moment you added capacity; for a database it means migrating almost all the data.

**The ring.** Hash node identifiers and keys into the same space, say 0 to 2^32 − 1, and imagine the space as a circle. A key belongs to the first node whose position is at or after the key's position, wrapping around at the top. Adding a node claims only the keys between its predecessor and itself, taken from one successor; removing a node hands its keys to its successor. The expected share of keys that move is 1/N, which is the minimum possible for a balanced assignment.

**Virtual nodes.** With one position per node, a few nodes own uneven arcs, and when a node dies, its whole arc lands on one neighbour. Giving each physical node many positions (100 to 200 is common) evens the arcs out statistically and spreads a departed node's keys across many successors. Virtual node counts can also be weighted: twice the positions for a machine with twice the capacity.

**Where it is used.** Memcached client libraries (the ketama algorithm), Amazon's Dynamo and the systems it inspired (Cassandra, Riak, DynamoDB's partitioning), Akamai's CDN (the 1997 paper that introduced the idea), and load balancers that need the same client or key to reach the same backend (ring hash in Envoy and NGINX). Two relatives are worth knowing: rendezvous hashing (pick the node with the highest `hash(key, node)`), which needs no ring and is often simpler, and jump consistent hash, which is tiny and fast but only works for numbered buckets without arbitrary removal.

**Replication.** To store a key on several nodes, walk clockwise from its position and take the next R distinct physical nodes (skipping virtual nodes of a node already chosen). Dynamo calls this list the preference list.

## Example: a ring with six keys

Positions are mod 100 to keep the arithmetic readable. Nodes: A at 10, B at 40, C at 75.

| Key | Position | Owner (first node clockwise) |
|---|---|---|
| user:1 | 5 | A |
| user:2 | 33 | B |
| user:3 | 50 | C |
| user:4 | 62 | C |
| user:5 | 90 | A (wraps past 99 to 10) |
| user:6 | 20 | B |

Add node D at 55. Only keys in the arc (40, 55] change owner: user:3 moves from C to D. The other five keys stay where they are, and no node other than C lost anything.

Remove node B at 40. Its keys (user:2 at 33, user:6 at 20) go to the next node clockwise, which is now D at 55. Again, nothing else moves.

Compare with modulo on the same hash values, 3 nodes to 4: 5 → 2 then 1, 33 → 0 then 1, 50 → 2 then 2, 62 → 2 then 2, 90 → 0 then 2, 20 → 2 then 0. Four of six keys moved.

## Example: a compact Java implementation with `TreeMap`

`TreeMap.ceilingEntry` finds "the first node at or after this position" in O(log N); `firstEntry` handles the wrap-around.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class ConsistentHashRing<N> {

    private final TreeMap<Long, N> ring = new TreeMap<>();
    private final int virtualNodesPerNode;

    public ConsistentHashRing(int virtualNodesPerNode, List<N> nodes) {
        this.virtualNodesPerNode = virtualNodesPerNode;
        nodes.forEach(this::addNode);
    }

    public void addNode(N node) {
        for (int replicaIndex = 0; replicaIndex < virtualNodesPerNode; replicaIndex++) {
            ring.put(hash(node + "#" + replicaIndex), node);
        }
    }

    public void removeNode(N node) {
        for (int replicaIndex = 0; replicaIndex < virtualNodesPerNode; replicaIndex++) {
            ring.remove(hash(node + "#" + replicaIndex), node);
        }
    }

    public N nodeFor(String key) {
        if (ring.isEmpty()) {
            throw new IllegalStateException("ring has no nodes");
        }
        Map.Entry<Long, N> entry = ring.ceilingEntry(hash(key));
        return entry != null ? entry.getValue() : ring.firstEntry().getValue();
    }

    static long hash(String input) {
        try {
            byte[] digest = MessageDigest.getInstance("MD5").digest(input.getBytes(StandardCharsets.UTF_8));
            return ((long) (digest[0] & 0xff) << 24) | ((digest[1] & 0xff) << 16) | ((digest[2] & 0xff) << 8) | (digest[3] & 0xff);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    public static void main(String[] arguments) {
        int keyCount = 100_000;
        ConsistentHashRing<String> ring = new ConsistentHashRing<>(150, List.of("A", "B", "C"));
        Map<String, String> before = new HashMap<>();
        for (int index = 0; index < keyCount; index++) {
            before.put("key-" + index, ring.nodeFor("key-" + index));
        }
        ring.addNode("D");
        int movedOnRing = 0;
        int movedWithModulo = 0;
        for (int index = 0; index < keyCount; index++) {
            String key = "key-" + index;
            if (!ring.nodeFor(key).equals(before.get(key))) {
                movedOnRing++;
            }
            if (hash(key) % 3 != hash(key) % 4) {
                movedWithModulo++;
            }
        }
        System.out.printf("ring:   %d of %d keys moved (%.1f%%)%n", movedOnRing, keyCount, 100.0 * movedOnRing / keyCount);
        System.out.printf("modulo: %d of %d keys moved (%.1f%%)%n", movedWithModulo, keyCount, 100.0 * movedWithModulo / keyCount);
    }
}
```

```text
ring:   22738 of 100000 keys moved (22.7%)
modulo: 74973 of 100000 keys moved (75.0%)
```

The ring moved close to the ideal quarter of the keys (the fourth node should own a quarter of the space); modulo moved three quarters, exactly as predicted. The two-argument `remove(position, node)` makes sure a hash collision between two nodes' virtual positions cannot delete the wrong node's point. `String.hashCode` would not do as the hash: it clusters similar strings together, so arcs become uneven.

## Pitfalls

- Too few virtual nodes. With one point per node, load imbalance between nodes is commonly tens of percent. Measure the distribution with your real key set before choosing the count.
- Hashing something unstable as the node identifier. If the identifier is an IP address and the node is rescheduled with a new one, every key it owned moves. Use a stable node name.
- Expecting it to solve hot keys. A single key is still on a single node; a celebrity's profile still saturates one cache server. That needs key replication or a local cache (see item 2.5).
- Forgetting the data has to move. For a cache, a reassigned key is just a miss. For a database, the owner change is only the start: the data must be streamed to the new owner while reads are still served correctly (see item 3.2).
- Changing the hash function or the virtual node count in a running cluster. Both reassign most keys at once, which is the exact outcome the technique exists to avoid.
- Confusing it with consistency models. "Consistent" here means stable key placement, nothing to do with linearizability or CAP (see item 3.3).

## Check yourself

1. Why does moving from 3 to 4 nodes under modulo hashing move about 75 percent of keys, while the ring moves about 25 percent?
2. A node with a single position dies. What happens to its successor's load, and how do virtual nodes change the outcome?
3. In the small example, which keys would move if you added a node at position 95, and from whom?
4. Your cache cluster uses consistent hashing and one product page is receiving 100,000 requests per second. What does consistent hashing do for you here, and what do you still have to build?

## Go deeper

- [Tom White: Consistent Hashing](https://tom-e-white.com/2007/11/consistent-hashing.html) · the classic short explanation, with a Java implementation very close to the one above.
- [Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) · section 4 on partitioning, virtual nodes and preference lists; the paper the NoSQL generation copied.
- [Designing Data-Intensive Applications, chapter 6](https://dataintensive.net/) · partitioning, rebalancing strategies and why "hash mod N" is the wrong default.
- [A Fast, Minimal Memory, Consistent Hash Algorithm](https://arxiv.org/abs/1406.2294) · Google's jump consistent hash, for when the buckets are numbered and never removed from the middle.

---

Part of [System Design](../README.md) · item 2.6
