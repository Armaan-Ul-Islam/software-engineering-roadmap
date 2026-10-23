# Sizing a Spring Boot service: from a load test to vCPU, memory and instance count

> **In one sentence:** Measure CPU-time per request and memory footprint under a realistic load test, then apply Little's law and a utilisation target to turn the target peak into a number of vCPUs, a container memory limit and an instance count with redundancy, and treat the result as a hypothesis to re-measure in production.

**Why it matters:** Guessing sizes produces one of two bills: an oversized fleet that idles at 8% CPU, or an undersized one that falls over on launch day. Being able to say "we need six 2-vCPU, 2 GiB tasks across three zones, and here is the arithmetic" is what separates an engineer who deploys from one who estimates. It is also a standard interview exercise.

## The idea

Sizing has four inputs you measure and three decisions you make.

Measured: **CPU-time per request** (how many vCPU-seconds one request burns), **service time** (how long a request occupies the service), **memory footprint** of one instance at its working concurrency, and **the point where latency degrades** as load rises.

Decided: the **target peak throughput** (from product forecasts, not hope), the **utilisation target** (CPU at roughly 60-70% at peak; above that, queueing makes tail latency explode and there is no room for a zone failure), and the **redundancy rule** (N+1 instances, spread across zones).

Two laws tie them together:

- Capacity: `vCPU needed = peak requests per second × CPU-seconds per request ÷ utilisation target`.
- **Little's law**: `in-flight requests (L) = arrival rate (λ) × time in system (W)`. It tells you how many requests are inside one instance at once, which sizes thread pools, connection pools and off-heap buffers.

For memory, the heap is only part of the story. A JVM's resident set is heap plus Metaspace, thread stacks, the code cache, garbage-collector data structures, direct (off-heap) buffers and JVM internals, and the container also holds the OS page cache and any agents. Read the real number with Native Memory Tracking, not from `-Xmx`.

## Example: a worked sizing

Every number below is an assumption to be replaced by your own measurement; they are labelled so the arithmetic is reproducible.

### Step 1: load test at a fixed arrival rate

Use an arrival-rate executor, not a fixed number of virtual users: a closed loop of users slows down as the service slows down and hides saturation.

```javascript
import http from 'k6/http';

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: 400,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 100,
      maxVUs: 400,
    },
  },
  thresholds: {
    http_req_duration: ['p(99)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  http.get('https://orders-api.test.internal/orders/42');
}
```

Run it at 200, 400, 600 and 800 requests per second against **one** instance with production-like data and a warmed JVM, and record the highest rate at which p99 stays inside the SLO. Gatling's `constantUsersPerSec` does the same job.

### Step 2: read the measurements

| Label | Assumption (measured on the test instance) |
|---|---|
| A1 | Test container: 2 vCPU, 2 GiB memory limit, `-XX:MaxRAMPercentage=50` (max heap 1 GiB) |
| A2 | Highest rate inside the SLO: 400 requests/s, mean service time 40 ms, p99 180 ms |
| A3 | CPU at that rate: 70% of 2 vCPU = 1.4 vCPU |
| A4 | Resident set at that rate: 1,150 MB; Native Memory Tracking committed: heap 1,024, Metaspace 95, threads 60, code cache 60, GC 55, internal and symbols 80, direct buffers 40 (MB) |
| A5 | Target peak: 1,200 requests/s |
| A6 | Utilisation target 60%; three availability zones |

CPU in a container comes from the platform's metrics (CloudWatch Container Insights, Azure Monitor) or `docker stats`; the resident set from `ps -o rss -p <pid>`; the breakdown from `jcmd <pid> VM.native_memory summary` after starting with `-XX:NativeMemoryTracking=summary`.

### Step 3: CPU and instance count

1. CPU-seconds per request = 1.4 vCPU ÷ 400 requests/s = 0.0035 vCPU-s, i.e. 3.5 ms of CPU per request.
2. CPU work at peak = 1,200 × 0.0035 = 4.2 vCPU.
3. Provisioned CPU at 60% target = 4.2 ÷ 0.60 = 7.0 vCPU.
4. Instances of 2 vCPU = 7.0 ÷ 2 = 3.5, rounded up: **N = 4** instances serve the peak.

### Step 4: concurrency with Little's law

1. Average in-flight requests at peak = 1,200 × 0.040 s = 48; per instance (4 instances) = 12.
2. Planning for the tail with p99 as W: 1,200 × 0.180 s = 216 in flight, 54 per instance. Tomcat's default of 200 request threads per instance is comfortable; the pools do not need enlarging.
3. If a request holds a database connection for 15 ms on average, connections in flight = 1,200 × 0.015 = 18 across the fleet, under 5 per instance. A HikariCP pool of 10 per instance is plenty (see item 5.4 for why bigger is worse).

### Step 5: redundancy across zones

- Instance failure: N+1 = **5** instances keeps peak capacity when one instance dies.
- Zone failure with three zones: losing a zone removes a third of the fleet, so you need N × 3 ÷ 2 = **6** instances (two per zone) to still have 4 after the loss. Pick 6 if the SLO must hold during a zone outage at peak, 5 if instance-level failure is the agreed risk. Off-peak, autoscaling can run fewer, but never below one per zone (see item 5.5).

### Step 6: memory per instance

Budget each component from A4 with headroom for growth:

| Component | Measured (MB) | Budget (MB) | Why the budget differs |
|---|---|---|---|
| Heap (max) | 1,024 | 1,024 | Live data after GC was about 350 MB; keeping it under roughly half the max heap keeps G1 pauses short |
| Metaspace | 95 | 128 | Grows with loaded classes; cap with `-XX:MaxMetaspaceSize` if you want a hard ceiling |
| Thread stacks | 60 | 100 | 200 request threads could each commit up to the 1 MB default stack under load |
| Code cache | 60 | 96 | Grows as the JIT compiles more methods |
| GC data structures | 55 | 64 | Scales with heap size |
| Internal, symbols, direct buffers | 120 | 160 | Netty or Tomcat NIO buffers grow with concurrency |
| **JVM total** | **1,414** | **1,572** | |
| Container overhead (page cache, agents, shell) | | 100 | |
| **Limit needed** | | **1,672** | A 2 GiB limit leaves 376 MB (18%) headroom; a 1.5 GiB limit would be OOM-killed at peak |

Result: **6 × (2 vCPU, 2 GiB)** at peak, scaling down to 3 off-peak, with `-XX:MaxRAMPercentage=50`. The heap is only about 60% of the footprint; that is the number most people get wrong.

### Step 7: re-measure after deploying

Compare the hypothesis with production for a week: CPU at the real peak (should sit near the 60% target), p99 at the load balancer (`TargetResponseTime` on an ALB, request duration in Container Apps), container working set against the limit, restart and OOM-kill counts, GC pause time (`jvm.gc.pause`), pool saturation (`hikaricp.connections.pending` should be zero) and request-thread saturation (`tomcat.threads.busy`, after enabling `server.tomcat.mbeanregistry.enabled=true`). Every one of those is a Micrometer metric Spring Boot already exposes. Adjust, then write the new numbers down next to the old ones.

## Pitfalls

- Load testing with a fixed number of virtual users. The test slows down with the service and reports a comfortable p99 at a throughput you never asked for.
- Testing a cold JVM or a burstable instance. The first minutes are JIT warm-up; the last minutes of a burstable instance are CPU throttling. Neither is your capacity.
- Sizing memory from `-Xmx`. The resident set is heap plus everything in the table; containers die on the resident set.
- Sizing to 100% CPU. Queueing theory is unkind above 70%: tail latency rises steeply, and a zone failure lands the survivors at 150%.
- Forgetting that "N+1" does not survive a zone. One extra instance is instance redundancy; zone redundancy costs N ÷ (zones − 1) extra.
- Never re-measuring. Dependencies get slower, data grows, a new endpoint allocates more; last year's size is a guess about this year.

## Check yourself

1. The service above is rewritten so that a request takes 6 ms of CPU but completes in 25 ms. Recompute vCPU at peak and the in-flight requests per instance. Which pool, if any, now needs attention?
2. Why does a closed-loop load test with 100 virtual users overstate your capacity, and which executor avoids that?
3. The container limit is 2 GiB and the heap is capped at 1 GiB, yet the task is OOM-killed under load. List four places the other gigabyte can go and the command that shows them.
4. You have two zones instead of three. How many instances do you need to keep N = 4 of capacity during a zone outage, and what does that say about the cost of two-zone regions?

## Go deeper

- [Grafana k6](https://grafana.com/docs/k6/latest/) · executors, thresholds and the scenario model used above.
- [Gatling](https://docs.gatling.io/) · the JVM-native alternative, with the same open-model injection profiles.
- [Little's law](https://en.wikipedia.org/wiki/Little%27s_law) · the one formula in this note; the derivation is short and worth reading once.
- [Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html) · how to get the per-component breakdown in step 2.
- [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview) · practical guidance on heap percentages, GC choice and CPU limits for the JVM in containers.

---

Part of [Cloud](../README.md) · items 5.1, 5.2, 5.3
