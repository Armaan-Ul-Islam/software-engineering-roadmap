# Redis as a cache and data-structure server

> **In one sentence:** Redis is an in-memory server of data structures (strings, hashes, lists, sets, sorted sets and more) addressed by key, which makes it the standard cache in front of a database when every key has a TTL, the eviction policy is one that evicts, and the application treats a miss as normal; it is also a counter, a queue and a lock, as long as you know exactly what each of those guarantees and what it does not.

**Why it matters:** Almost every backend adds Redis within its first year, usually as a cache, and the classic failures are configuration and discipline rather than code: a cache that grows until the server runs out of memory because `noeviction` is the default and nobody set a TTL; a `KEYS *` in production that freezes every request; a "distributed lock" that two workers hold at once. Interviewers ask about eviction policies and cache-aside because the answers show whether you understand that a cache must be allowed to forget.

## The idea

**Data types and the commands you will use.** Every key maps to a value of one type:

| Type | Commands | Typical use |
|---|---|---|
| String (bytes, up to 512 MB) | `SET key value EX seconds`, `GET`, `SET ... NX`, `INCR`, `MGET` | serialised objects, rendered fragments, counters, locks |
| Hash | `HSET`, `HGET`, `HGETALL`, `HINCRBY` | an object whose fields are read or updated individually |
| List | `LPUSH`, `RPOP`, `LRANGE`, `BLMOVE` | queues, recent items |
| Set | `SADD`, `SISMEMBER`, `SMEMBERS` | tags, membership, deduplication |
| Sorted set | `ZADD`, `ZRANGE ... REV WITHSCORES`, `ZINCRBY` | leaderboards, sliding-window rate limits, scheduling |
| Others | streams (`XADD`), HyperLogLog (`PFADD`), bitmaps, geospatial | event logs, approximate distinct counts, flags |

Redis executes commands on one thread, so every command is atomic and nothing else runs while one executes. That gives you `INCR` and `SET NX` as atomic primitives for free, and it is also why one slow command (`KEYS`, `SMEMBERS` on a huge set, a multi-megabyte `GET`) stalls every client.

**TTLs.** `SET key value EX 300` (or `PX` for milliseconds), `EXPIRE key seconds`, `TTL key` (-1 means no expiry, -2 means no such key). Expired keys are removed lazily on access and by a background sampler. A plain `SET` on an existing key removes its TTL unless you say `KEEPTTL`. Every cache entry gets a TTL: it is the upper bound on staleness and the only thing that reclaims memory if nothing evicts. Add jitter (300 s plus a random 0 to 30) so that entries written together do not expire together.

**Eviction.** `maxmemory` is 0 (unlimited) by default and `maxmemory-policy` is `noeviction`: at the limit, writes fail with `OOM command not allowed when used memory > 'maxmemory'` while reads continue, and with no limit Redis grows until the operating system kills it. A cache wants `maxmemory` set and `allkeys-lru` (or `allkeys-lfu` when a small hot set dominates): evict the least recently used key, whichever it is. `volatile-lru` evicts only keys that carry a TTL, which protects keys you deliberately made permanent, and behaves like `noeviction` when no key has one. The LRU is approximate, sampling `maxmemory-samples` keys (5) and evicting the best candidate, which is cheap and good enough.

**Cache-aside.** The application owns the logic:

```text
read(user 42)                                      write(user 42)
  GET user:42:profile                                UPDATE customer SET ... WHERE id = 42     (PostgreSQL is the truth)
  hit  -> return it                                  DEL user:42:profile                       (delete, never SET the new value)
  miss -> SELECT ... FROM customer WHERE id = 42
          SET user:42:profile <json> EX 300          (always a TTL, with jitter)
          return it
```

The database stays the source of truth, the cache can be flushed at any moment, and a miss costs one database read. Deleting rather than updating on write matters: two concurrent writers can otherwise leave the cache holding the older value until its TTL. Read-through and write-through libraries hide the same steps; write-behind makes Redis the system of record for a while, which is a different class of risk. For hot keys, add a short negative cache for lookups that keep missing, and stampede protection for the moment a popular key expires: a per-key `SET lock:key NX PX 2000` so one request refreshes while the rest wait or serve the old copy.

**Key design and namespacing.** `type:id:field`, as in `user:42:profile` or `ratelimit:client-9:202610240310`; one prefix per use and per format version (`v2:user:42:profile`) so a serialisation change never reads old bytes; never raw user input without a prefix. Keep values small (hundreds of bytes to tens of kilobytes); a multi-megabyte value is a slow command every time it is read. `MEMORY USAGE key` tells you what a key costs and `OBJECT ENCODING` shows the compact `listpack` representation small hashes and sets get. Use prefixes rather than numbered databases (`SELECT 1`) for separation; Redis Cluster supports only database 0.

**Persistence and its limits.** RDB snapshots (`save 3600 1 300 100 60 10000`: after an hour with one change, five minutes with a hundred, one minute with ten thousand) fork the process and write a point-in-time file, and a crash loses everything since the last one. AOF (`appendonly yes`) logs every write; with `appendfsync everysec` a crash loses up to a second, `always` costs an fsync per write. Replication is asynchronous and a failover can lose acknowledged writes. None of this makes Redis a durable store in the sense of item 5.1, and a cache does not need persistence beyond a warm restart. Data that must survive belongs in the database; Redis caches it.

**Redis as a distributed lock, and its limits.** `SET lock:name token NX PX 30000` acquires the lock only if the key does not exist, with a timeout so that a crashed holder does not block forever; release with a Lua script that deletes the key only if it still holds *your* token, so you cannot release someone else's lock after yours expired. On one Redis instance this is correct mutual exclusion in the normal case and fine for "run this job on one worker", provided a rare double run is tolerable. It is not safe for correctness: a holder paused by garbage collection or a network stall beyond the TTL carries on after another worker has acquired the lock, and an asynchronous failover can lose the key. Redlock (a majority of independent instances) does not fix the pause problem. When correctness matters, make the protected resource check a fencing token, or take the lock in the database (`pg_try_advisory_xact_lock`, item 6.6).

## Example: a `redis-cli` session

Redis 8 with its default configuration (`docker run redis:8-alpine`).

```text
127.0.0.1:6379> SET user:42:profile '{"name":"Alice","plan":"pro"}' EX 300
OK
127.0.0.1:6379> TTL user:42:profile
(integer) 300
127.0.0.1:6379> SET user:42:profile '{"name":"Alice","plan":"team"}' KEEPTTL
OK
127.0.0.1:6379> SET user:42:profile '{"name":"Alice","plan":"team"}'
OK
127.0.0.1:6379> TTL user:42:profile
(integer) -1                       the plain SET dropped the TTL; this key now lives forever
127.0.0.1:6379> HSET product:7 name Widget price 9.99 stock 12
(integer) 3
127.0.0.1:6379> HINCRBY product:7 stock -1
(integer) 11
127.0.0.1:6379> INCR ratelimit:client-9:202610240310
(integer) 1
127.0.0.1:6379> EXPIRE ratelimit:client-9:202610240310 60 NX
(integer) 1
127.0.0.1:6379> ZADD leaderboard 1500 alice 1200 bob 1800 carol
(integer) 3
127.0.0.1:6379> ZRANGE leaderboard 0 2 REV WITHSCORES
1) "carol"   2) "1800"   3) "alice"   4) "1500"   5) "bob"   6) "1200"
127.0.0.1:6379> MEMORY USAGE user:42:profile
(integer) 66
```

The lock, held by `worker-a`, released only by the holder:

```text
127.0.0.1:6379> SET lock:nightly-report worker-a NX PX 30000
OK
127.0.0.1:6379> SET lock:nightly-report worker-b NX PX 30000
(nil)
127.0.0.1:6379> EVAL "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end" 1 lock:nightly-report worker-b
(integer) 0
127.0.0.1:6379> EVAL "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end" 1 lock:nightly-report worker-a
(integer) 1
```

`KEYS` against `SCAN`, after loading 500,000 `user:N:profile` keys (49 MB used):

```text
127.0.0.1:6379> KEYS user:4999*
  ... 111 keys ...
127.0.0.1:6379> SLOWLOG GET 1
1) 1) (integer) 0
   2) (integer) 1792822877
   3) (integer) 34771                 34.8 ms, during which the server answered nobody else
   4) 1) "KEYS"
      2) "user:4999*"
127.0.0.1:6379> SCAN 0 MATCH user:4999* COUNT 1000
1) "424192"                           the cursor for the next call
2) (empty array)                      this page of about 1,000 keys held no match
```

Looping `SCAN` until the cursor came back as `0` took 415 calls, found the keys, and none of the calls reached the slow log's 10 ms threshold.

Eviction, at the default policy and then at a sensible one:

```text
127.0.0.1:6379> CONFIG SET maxmemory 40mb
OK
127.0.0.1:6379> SET fresh:key value
(error) OOM command not allowed when used memory > 'maxmemory'.
127.0.0.1:6379> CONFIG SET maxmemory-policy allkeys-lru
OK
127.0.0.1:6379> SET fresh:key value
OK
127.0.0.1:6379> DBSIZE
(integer) 414795                      85,211 keys evicted to get under 40 MB
127.0.0.1:6379> GET user:42:profile
(nil)                                 the profile from the start of the session was one of them
```

With `volatile-lru` instead, and no key carrying a TTL, 29,996 of the next 30,000 `SET`s failed with the same OOM error: the policy had nothing it was allowed to evict.

## Pitfalls

- Keys without a TTL: sessions, "temporary" flags, per-user caches. Memory grows for months, and under `noeviction` the first symptom is writes failing in production.
- `KEYS` in production, or `SMEMBERS` on a set with millions of members, or `DEL` of a huge key. Each blocks the single thread for the duration; use `SCAN`, bounded structures, and `UNLINK` for large keys.
- Leaving `maxmemory-policy` at `noeviction` for a cache. It is the default, and a cache that cannot evict is a cache that fails writes.
- Writing the new value into the cache on update. Two concurrent updates can land in the opposite order in Redis and in the database; delete the key and let the next read repopulate it.
- Identical TTLs for entries loaded together. They expire together and the database takes the whole load at once; add jitter and protect hot keys against stampedes.
- Treating Redis as the system of record because it has persistence. Snapshots lose minutes, AOF loses a second, failover loses acknowledged writes.
- Locks without a unique token or without a TTL, or trusted for correctness. Release-by-token prevents releasing another holder's lock; nothing in Redis prevents a paused holder from continuing after its TTL.
- One hot key or one huge value. Redis Cluster shards by key, so all traffic for one key still lands on one node; split the value or cache it locally in the application.

## Check yourself

1. Why does a cache need both TTLs and an evicting policy, and what exactly happens with `noeviction` and keys that never expire?
2. On a write, why delete the cache key rather than write the new value into it, and what sequence of events goes wrong otherwise?
3. `KEYS` and `SCAN` both examine every key. Why does one hurt production and the other does not?
4. Two workers both believe they hold `lock:nightly-report`. Give one sequence of events that leads there despite `SET NX PX`, and name what would prevent the damage.

## Go deeper

- [Redis documentation](https://redis.io/docs/latest/) · the entry point; the "Develop" section covers data types, patterns and client libraries.
- [Redis: Data types](https://redis.io/docs/latest/develop/data-types/) · every type with the commands and the encoding details.
- [Redis: Key eviction](https://redis.io/docs/latest/develop/reference/eviction/) · every `maxmemory-policy` value and how the approximate LRU and LFU work.
- [Redis: Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/) · RDB against AOF, `appendfsync`, and what each loses on a crash.
- [Redis: Distributed Locks with Redis](https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/) · the single-instance pattern with the release script, and the Redlock proposal.
- [Redis: SCAN](https://redis.io/docs/latest/commands/scan/) · the cursor contract, including why a key can be returned twice.
- [Martin Kleppmann: How to do distributed locking](https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html) · the pause problem, fencing tokens and why Redlock does not solve it.

---

Part of [Databases](../README.md) · item 9.2
