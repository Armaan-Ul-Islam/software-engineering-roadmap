# Case study: a news feed

> **In one sentence:** A news feed is a read-heavy merge of many people's writes, and the whole design turns on one choice, whether to do the merge when a post is written (fan-out on write, fast reads, expensive and wasteful writes) or when a feed is read (fan-out on read, cheap writes, slow reads), with the standard answer being both: precomputed feeds for ordinary authors and a read-time merge for the few authors with millions of followers.

**Why it matters:** The feed is the interview problem that tests whether you can let numbers decide: the same design is right or wrong depending on the follower distribution, and the celebrity case breaks any single strategy. It also contains the pieces of most consumer systems: a precomputed cache keyed by user, cursor pagination, ranking added later, and consistency that differs for your own actions and other people's. The framework is in item 6.1; this note follows it.

## The idea

Separate the feed's three jobs and give each its own store and consistency: *generation* (which post IDs belong in a user's feed), *hydration* (turning IDs into posts, authors and counts) and *ranking* (reordering candidates). Generation is where the fan-out decision lives; hydration is a cache problem; ranking is a stateless function that must be replaceable without touching the other two.

## Example: the worked design

### Requirements

Functional: a user publishes a post (text, up to a few images); follows and unfollows other users; views a home feed of posts from the people they follow, newest first at launch and ranked later; sees like and comment counts on each post. Out of scope after asking: search, notifications, messaging.

Non-functional: the feed must open fast (server time under 300 ms at p99 for the first page) and stay available even if posting is degraded; a user's own post must appear in their own feed immediately; other people's posts may take a few seconds to appear; counts may be approximate; media goes through a CDN (see item 2.4).

### Estimates

20 million daily active users, each opening the feed 10 times a day and posting 0.3 times a day. Feed loads: 2 × 10^8 a day, about 2,300 per second on average and 7,000 at a 3× peak. Posts: 6 × 10^6 a day, about 70 per second average and 200 at peak.

The follower distribution decides the design. The median user has 200 followers; a few thousand accounts have more than 100,000, and a handful have 20 million. Fan-out on write for an ordinary post is 70 × 200 = 14,000 feed insertions per second on average, 40,000 at peak: comfortable for a Redis cluster. One post by a 20-million-follower account is 20 million insertions, which at 100,000 per second takes over three minutes and lands on followers' feeds in a wave. That number is why the design is hybrid.

Storage: post metadata at about 1 KB is 6 GB a day, 2.2 TB a year: one relational primary with replicas, partitioned by post ID later (see item 3.2). Feed cache: post IDs only, 500 per user, about 10 KB with sorted-set overhead, so 200 GB for 20 million daily active users, spread over a Redis cluster; inactive users get no cache and are rebuilt on demand.

### API

- `POST /posts` with `{"text": "...", "mediaIds": ["..."]}` returns 201 with the post, including its ID.
- `GET /feed?limit=20&cursor=<opaque>` returns `{"items": [...], "nextCursor": "..."}`. The cursor encodes the last post ID returned (and, once ranking exists, a feed-session identifier).
- `POST /users/{userId}/follow` and `DELETE /users/{userId}/follow`.

### Data model

```sql
CREATE TABLE post (
    id          bigint      PRIMARY KEY,          -- time-ordered Snowflake ID
    author_id   bigint      NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    text        text        NOT NULL,
    media       jsonb       NOT NULL DEFAULT '[]',
    deleted     boolean     NOT NULL DEFAULT false
);
CREATE INDEX post_author_idx ON post (author_id, id DESC);

CREATE TABLE follow (
    follower_id bigint NOT NULL,
    followee_id bigint NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX follow_followee_idx ON follow (followee_id, follower_id);
```

Post IDs are Snowflake-style (see item 2.12), so sorting by ID is sorting by time and the cursor is a plain ID. The `follow` table is indexed both ways: by follower for "whom do I follow" (fan-out on read) and by followee for "who follows this author" (fan-out on write). In Redis: `feed:{userId}`, a sorted set of post IDs capped at 500; `post:{postId}`, a hash of the post; `author_recent:{authorId}`, a celebrity's recent post IDs; `counts:{postId}` for likes and comments.

### Write path

1. `POST /posts` inserts the row and, in the same transaction, an outbox row (see item 3.7); the response returns immediately. The author's own `feed:{authorId}` is updated synchronously before responding, so the post appears for them at once.
2. A relay publishes `PostCreated` to a log partitioned by author (see item 2.7).
3. Fan-out workers consume it. If the author's follower count is below the celebrity threshold (say 100,000), the worker reads the follower list and, for each follower active in the last month, does `ZADD feed:{follower} postId postId` and trims the set to 500. Fan-out is idempotent (a set add), so redelivery is harmless (see item 3.8).
4. If the author is a celebrity, the worker only adds the post ID to `author_recent:{authorId}` and stops.

### Read path

1. `GET /feed` reads the user's cached followee list and splits it into ordinary authors and celebrities.
2. Fetch the precomputed IDs: `ZREVRANGEBYSCORE feed:{userId} (cursor -inf LIMIT 0 20`.
3. For each followed celebrity (bounded, typically a few dozen), fetch recent IDs from `author_recent:{celebrity}` below the cursor, and merge the two lists by ID.
4. Hydrate: a multi-get of `post:{id}` for the 20 winners, falling back to the database on misses and dropping posts whose row is deleted; a multi-get of author profiles and `counts:{id}`.
5. Apply ranking if enabled (below), return the page and `nextCursor` set to the last ID.

A user with no `feed:{userId}` (inactive, or a lost cache node) takes the slow path: fan-out on read across all followees through `post_author_idx`, the query the cache exists to avoid. The result seeds the cache, and the slow path is rate-limited so that a cache loss does not become a database outage.

### Deep dive 1: fan-out on write, on read, and the hybrid

| | Fan-out on write | Fan-out on read | Hybrid |
|---|---|---|---|
| Post cost | One insertion per follower | One row insert | Per follower, except for celebrities |
| Feed load cost | One sorted-set read plus hydration | A query per followee and a merge | One read plus a merge for a few celebrities |
| Celebrity post | Millions of writes, minutes of delay | Nothing special | Handled at read time |
| Inactive users | Work wasted on feeds nobody opens | No waste | Skip users inactive for a month |
| Freshness | Seconds (worker lag) | Immediate | Seconds for ordinary authors, immediate for celebrities |

The threshold is a tuning knob: measure fan-out lag and read-side merge cost, and move it. A new follow backfills the followee's last few posts into the follower's feed so it has a visible effect; an unfollow is filtered at hydration and cleaned up by an asynchronous `ZREM` sweep.

### Deep dive 2: ranking as a separate concern

The cache stores the chronological candidate list; ranking is a service that takes candidates (say the top 200 IDs by recency) plus features (author affinity, engagement counts, recency, media type) and returns a reordered page. Keeping it out of the generation step means the cache layout never changes when the model does, the model can be A/B tested per request, and "sort by newest" remains a trivial fallback when the ranking service is slow or down (see item 4.2). The cost is the cursor: a ranked page is not a prefix of a sorted set, so the cursor carries a feed-session identifier under which the ranked order is frozen for a few minutes and paginated by position; otherwise scores change between pages and the client sees duplicates and gaps.

### Deep dive 3: caching and hot posts

Three layers: the CDN for media; the post and profile caches (cache-aside with TTLs, see item 2.5); and the feed cache, the precomputed result and the only one whose loss is expensive. A celebrity's post is a hot key in the post cache: replicate it under several suffixes or add a small in-process cache on the feed servers (see item 2.5). Counts are write-hot: increment in Redis and flush to the database in batches (write-behind), accepting that a crash loses a few seconds of likes, which the requirements allowed.

### Deep dive 4: consistency

Own posts: synchronous insertion into the author's feed set gives read-your-writes without touching replication (see item 3.3). Others' posts: eventual, within worker lag, which is monitored. Deletions: the row is marked deleted and the ID is left in caches; hydration drops it, so a deleted post disappears everywhere at once without a fan-out of removals. Counts: approximate by design. Replica lag: a brand-new post that misses the cache could be absent on a lagging replica, so the post hash is written to the cache at creation time.

### Failure modes and scaling

Fan-out workers fall behind: posting still works, feeds go stale, lag pages someone, and lowering the celebrity threshold cuts write amplification. A feed-cache shard is lost: its users take the rate-limited slow path and are rebuilt. The ranking service is down: chronological order. Ten times the users: the feed cache shards by user ID (see item 2.6), the `post` table partitions by ID range, the fan-out log adds partitions, and the celebrity merge cost is unchanged because it depends on followees per user, not on total users.

## Pitfalls

- Fan-out on write for everyone. The first celebrity post delays every feed and saturates the workers; the follower distribution, not the average, must drive the design.
- Fan-out on read for everyone. Feed latency grows with the number of followees and the database does the merge 7,000 times a second.
- Offset pagination. New posts arrive at the top between pages, so page two repeats items from page one; use an ID cursor for chronological feeds and a frozen session for ranked ones.
- Storing posts in the feed cache. Ten kilobytes of IDs per user becomes megabytes of content per user, and an edit or deletion must be fanned out to every copy.

## Check yourself

1. Redo the fan-out arithmetic for a network where the median user has 2,000 followers and nobody has more than 50,000. Does the hybrid still earn its complexity?
2. A user follows someone and opens the feed one second later. What do they see under each strategy, and what does the design do so the follow has a visible effect?
3. Why does a ranked feed need a different cursor from a chronological one, and what would a user observe if you kept the ID cursor?
4. The feed cache cluster loses a third of its nodes at peak. Walk through what happens to the affected users' requests and name the two mechanisms that keep the database alive.

## Go deeper

- [System Design Primer: Design the Twitter timeline and search](https://github.com/donnemartin/system-design-primer/blob/master/solutions/system_design/twitter/README.md) · a worked solution with the same fan-out reasoning and estimates.
- [Raffi Krikorian: Timelines at Scale (InfoQ)](https://www.infoq.com/presentations/Twitter-Timeline-Scalability/) · Twitter's hybrid fan-out, the celebrity problem and the numbers behind it, from the people who built it.
- [ByteByteGo: System Design 101](https://github.com/ByteByteGoHq/system-design-101) · visual summaries of this and the other classic problems.
- [Scaling Memcache at Facebook](https://www.usenix.org/system/files/conference/nsdi13/nsdi13-final170_update.pdf) · the hydration-cache problems (leases, hot keys, replication) at feed scale.

---

Part of [System Design](../README.md) · item 6.3.2
