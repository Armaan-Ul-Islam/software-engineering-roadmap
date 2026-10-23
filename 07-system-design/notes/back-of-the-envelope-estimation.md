# Back-of-the-envelope estimation

> **In one sentence:** Estimation turns a vague feature request into a handful of numbers (requests per second, bytes per year, bytes per second, cache size) that tell you which part of the design is actually hard, and it only works if you memorise a few constants and round aggressively.

**Why it matters:** Without numbers, every design discussion is a matter of taste. With them, "should we shard?" becomes "we have 60 writes per second, so no". Interviewers use estimation to see whether you can reason about scale; production engineers use it to avoid building a distributed system for a workload one PostgreSQL node handles.

## The idea

You are not computing an answer. You are finding the order of magnitude, so that a decision that depends on "thousands or millions?" can be made. Three groups of constants make this possible.

**Powers of two.** 2^10 ≈ 10^3 (KB), 2^20 ≈ 10^6 (MB), 2^30 ≈ 10^9 (GB), 2^40 ≈ 10^12 (TB), 2^50 ≈ 10^15 (PB). Also 2^32 ≈ 4.3 × 10^9 and 2^64 ≈ 1.8 × 10^19.

**Time.** A day has 86,400 seconds; round it to 10^5 and accept the 15 percent error. A month is about 2.6 × 10^6 seconds, a year about 3.15 × 10^7 (π × 10^7 is an easy mnemonic). So one million events per day is roughly 12 per second, and one billion per month is roughly 400 per second.

**Latency.** Memorise the shape, not the decimals. These are the widely quoted figures from the gist linked in the README; SSD and network numbers have improved since they were written.

| Operation | Approximate time |
|---|---|
| L1 cache reference | 0.5 ns |
| Main memory reference | 100 ns |
| Send 1 KB over a 1 Gbps network | 10 µs |
| Random read from SSD | 100 to 150 µs |
| Read 1 MB sequentially from memory | 250 µs |
| Round trip inside one datacenter | 500 µs |
| Read 1 MB sequentially from SSD | 1 ms |
| Disk seek | 10 ms |
| Round trip across an ocean | 150 ms |

The lesson: memory is a thousand times faster than SSD, a datacenter round trip costs as much as reading a megabyte from memory, and nothing you do inside a region matters if the user is on another continent.

**Per-node capacity** is the group people skip. Rules of thumb for simple operations on ordinary cloud instances, not benchmarks; measure before relying on them: a relational database node serves on the order of 10^3 to 10^4 simple indexed queries per second and a few thousand small writes; Redis serves on the order of 10^5 simple operations per second per instance; a stateless application server serves hundreds to a few thousand requests per second depending on what a request does; a server's network link is 1 to 10 Gbps, roughly 100 MB/s to 1 GB/s.

**The procedure.** State the assumptions before computing anything; a wrong assumption said out loud is correctable, a wrong number pulled from nowhere is not.

1. Fix the inputs: daily active users (DAU), actions per user per day, read to write ratio, size of each object, retention.
2. Convert daily counts to per-second rates by dividing by 10^5.
3. Multiply by a peak factor (2 to 5; say which), because capacity is bought for the peak.
4. Storage: writes per day × bytes per write × days of retention × replication factor.
5. Bandwidth: requests per second × bytes per request, separately for ingress and egress.
6. Cache: the 80/20 rule (cache 20 percent of the daily read volume), or "everything from the last N days", whichever matches the access pattern.
7. Sanity-check against per-node capacity and the latency table. The component whose number is far above one node's capacity is the design problem; the rest is plumbing.

**Rounding discipline.** One significant figure, mantissa times a power of ten, units on every number, and never more precision in the output than went into the input. "About 60 per second" is right; "57.87 per second" is wrong even though it is the same number, because it claims a precision the inputs do not have. Within a factor of three of reality, the estimate did its job.

## Example: a photo-sharing feed

Assumptions: 10 million DAU; each user uploads 0.5 photos per day and opens the feed 10 times per day; a feed page shows 20 photos; an upload is 2 MB and server-generated variants add 1 MB, so 3 MB stored per photo; the variant shown in the feed is 200 KB; metadata per photo is 1 KB; photos are kept forever; peak is 3 × average.

**Writes.** 10^7 × 0.5 = 5 × 10^6 uploads per day. Divided by 10^5 seconds: about 50 per second (57.9 if you insist), round to 60. Peak: about 200 uploads per second.

**Reads.** 10^7 × 10 = 10^8 feed loads per day, about 1,200 per second average and 3,500 at peak, call it 4,000. Each feed load fetches 20 images: 2 × 10^9 image fetches per day, about 23,000 per second average and 70,000 at peak. The read to write ratio is 20:1 for the API and 400:1 for image bytes.

**Storage.** 5 × 10^6 × 3 MB = 15 TB of image data per day, so 15 × 365 ≈ 5.5 PB per year. Three-way replication makes that 16 PB of raw disk per year; erasure coding at roughly 1.5× overhead, about 8 PB. Metadata: 5 GB per day, about 1.8 TB per year, which fits one relational database as far as size goes.

**Bandwidth.** Ingress: 60 × 2 MB = 120 MB/s, about 1 Gbps average and 3 Gbps at peak. Egress: 23,000 × 200 KB = 4.6 GB/s, roughly 40 Gbps average and over 100 Gbps at peak. That number alone says the images are served by a CDN, not by your servers.

**Cache.** Feed traffic concentrates on recent photos. The metadata of the last three days of uploads is 1.5 × 10^7 × 1 KB = 15 GB, one Redis node by size; at peak it answers 4,000 × 20 = 80,000 key reads per second, within one node's capacity, so run three for availability rather than throughput. For the CDN, 20 percent of last week's uploads is 0.2 × 3.5 × 10^7 × 200 KB ≈ 1.4 TB, small for a CDN.

**Sanity check.** 60 inserts and 4,000 reads per second against a 2 TB metadata table is comfortable for one PostgreSQL primary with replicas. The hard parts are petabytes of object storage and 100 Gbps of egress, not the database. The estimate took five minutes and told you where to spend the next forty.

## Pitfalls

- False precision. Carrying decimals wastes time and signals that you do not know which inputs are guesses.
- Designing for the average. A site with 1,000 requests per second on average and a 5× lunchtime spike is a 5,000 request per second system.
- Forgetting replication and indexes. Raw data × 3 for replicas; relational tables often double once indexes and row overhead are added.
- Mixing bits and bytes. Links are quoted in bits per second, storage in bytes. 10 Gbps is 1.25 GB/s.
- Ignoring fan-out. One feed request became 20 image fetches above; one post can become a write to every follower's cache. Count the amplified number, not the user action.
- Skipping the sanity check. "So we need 4,000 QPS" without "and one node does about 10,000" has not answered the question that mattered.

## Check yourself

1. A service receives 3 billion events per month. Roughly how many per second on average, and how did you get there without a calculator?
2. In the photo example, why is egress bandwidth the number that determines the architecture, even though it came from the smallest-sounding input (200 KB)?
3. A colleague estimates 2.3 PB of yearly storage from inputs they described as "roughly". What is wrong with how the result is stated, and how would you restate it?
4. You estimate 8,000 reads per second against a single table. Which two designs are both defensible under the rules of thumb above, and what extra information decides between them?

## Go deeper

- [Latency Numbers Every Programmer Should Know](https://gist.github.com/jboner/2841832) · the table above, with the original relative comparisons.
- [Interactive latency numbers by year](https://colin-scott.github.io/personal_website/research/interactive_latency.html) · the same numbers as they have changed over time, so you know which ones have moved.
- [System Design Primer](https://github.com/donnemartin/system-design-primer) · worked estimates for pastebin, Twitter and others, following this procedure.
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) · where the latency and availability targets you estimate against come from.

---

Part of [System Design](../README.md) · item 1.2
