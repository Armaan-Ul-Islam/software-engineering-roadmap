# Latency percentiles and tail latency

> **In one sentence:** Latency is a distribution, not a number; the mean hides the slow requests that users actually notice, fan-out turns a rare slow backend into a common slow page, and most latency measurements are wrong because of how they were collected.

**Why it matters:** A service with a 20 ms average and a 3 s p99 is a slow service: one request in a hundred takes 3 s, and a user who makes fifty requests per session hits that most sessions. Any system that assembles a response from many backends inherits the worst of their tails, which is why Google's "Tail at Scale" paper treats tail tolerance as a design requirement rather than a tuning exercise.

## The idea

**Why averages lie.** Latency distributions are skewed to the right: most requests are fast, a few are very slow (a garbage collection pause, a cache miss that went to disk, a retry, a lock wait). The mean is pulled up by the few and tells you nothing about either group. Two services can have the same mean while one is uniformly mediocre and the other is fast with a horrible tail, and users have very different opinions of them.

**Percentiles.** The p50 (median) is the typical request. p95 and p99 describe the slow minority; p99.9 describes what the busiest users and the fan-out paths see. An SLO is written as a percentile over a window: "99 percent of requests in a 30-day window complete within 300 ms". The gap between p50 and p99 is itself a diagnostic: a wide gap means a bimodal distribution, usually a cache or a pause, not a uniformly slow system.

**Fan-out multiplies the tail.** If a page waits for N backends called in parallel, the page is slow when any one of them is slow. With each backend slow with probability p, the page is slow with probability 1 − (1 − p)^N:

| Share of slow calls per backend | N = 1 | N = 3 | N = 10 | N = 30 | N = 100 |
|---|---|---|---|---|---|
| 1 percent (its p99) | 1 % | 3 % | 9.6 % | 26 % | 63 % |
| 0.1 percent (its p99.9) | 0.1 % | 0.3 % | 1 % | 3 % | 9.5 % |

The p99 of each backend becomes roughly the p90 of a page that calls ten of them. For a hundred backends, the backend's p99 is the page's median. Sequential calls are different but no better: their latencies add, so the sum's tail is at least as long as the longest component's.

**Hedged requests.** The Tail at Scale fix for read paths: send the request to one replica; if no answer arrives within, say, the p95 latency, send the same request to a second replica and take whichever answers first, cancelling the other. Hedging at p95 adds at most about 5 percent extra load and cuts the tail dramatically, because the two replicas' slow moments are mostly uncorrelated. Only hedge idempotent operations, cap the number of hedges, and make sure the second request carries the same deadline. A variant, tied requests, sends both at once with cross-cancellation when one starts executing.

Other tail-tolerant techniques from the same paper: finer partitioning so load can be rebalanced, putting consistently slow replicas on probation, and returning good-enough partial results when a few shards are late.

**Measuring correctly.**

1. Use histograms, never a running average. HdrHistogram, Prometheus histograms with well-chosen buckets, or OpenTelemetry's exponential histograms let you read any percentile later and merge data across hosts.
2. Never average percentiles. The mean of ten hosts' p99 values is not the fleet's p99; merge the histograms, then read the percentile.
3. Measure from the caller's side (client, load balancer, service mesh) as well as inside the service. Queueing in front of the service is invisible to the service.
4. Avoid coordinated omission. A closed-loop load generator waits for each response before sending the next request, so during a stall it sends fewer requests, and the stall is recorded once instead of for every request that should have been sent during it. The reported percentiles are then far better than what a real client population would have seen. Fix: generate load on a fixed schedule (open loop, as `wrk2` does) and record each request's latency from its intended start time, which HdrHistogram supports directly.
5. Collect enough samples. The p99.9 of a thousand requests is one request; the number is noise.

## Example: how a 1 percent slow backend becomes a 10 percent slow page

A product page calls ten services in parallel: pricing, stock, reviews, recommendations, shipping estimate and five more. Each is healthy by its own dashboard: p99 of 50 ms, p50 of 5 ms, and only 1 percent of calls exceed 200 ms.

Probability that none of the ten is slow: 0.99^10 = 0.904. So 9.6 percent of page loads wait on at least one 200 ms call. The page's p90 is now about 200 ms, although every dependency's p90 is a few milliseconds.

```java
import java.util.List;

public final class FanOut {

    public static void main(String[] arguments) {
        double slowShare = 0.01;
        for (int backendCount : List.of(1, 3, 10, 30, 100)) {
            double slowPageShare = 1 - Math.pow(1 - slowShare, backendCount);
            System.out.printf("%3d backends -> %.1f%% of pages slow%n", backendCount, slowPageShare * 100);
        }
    }
}
```

```text
  1 backends -> 1.0% of pages slow
  3 backends -> 3.0% of pages slow
 10 backends -> 9.6% of pages slow
 30 backends -> 26.0% of pages slow
100 backends -> 63.4% of pages slow
```

Three responses to that page: hedge the read-only calls at their p95 (about 20 ms here) so a single slow replica no longer decides the page's latency; give the non-essential calls (recommendations, reviews) a short deadline and render without them when they miss it; and fix the dependency whose tail is caused by something avoidable, such as a stop-the-world pause or an unindexed query. Reducing N by merging chatty calls helps too, and is often the cheapest option.

## Pitfalls

- Dashboards that show only averages, or "p99 over 10 s windows, then averaged over an hour". The second is an average wearing a percentile's clothes.
- Measuring inside the server only. The request spent 400 ms in the accept queue before your timer started; your p99 says 20 ms.
- Load tests with a closed-loop tool and a fixed number of virtual users. The stall your system had at minute 12 is recorded as one slow request instead of thousands.
- Setting the SLO at the mean. A "100 ms average" target is met by a system that gives 10 percent of users one-second pages.
- Retries as the tail fix. A retry after a timeout doubles the tail for the unlucky request and adds load exactly when the dependency is struggling. Hedge earlier and idempotently, or do not.
- Treating the tail as random. It usually has a cause: garbage collection, connection pool exhaustion, lock contention, a cold cache, a noisy neighbour. Trace the slowest 1 percent before adding replicas.

## Check yourself

1. Two services both report a 30 ms mean. One has p99 = 40 ms, the other p99 = 2 s. Describe what each distribution probably looks like and what is likely causing the second one's tail.
2. A page calls 20 backends in parallel, each with 0.5 percent slow calls. Roughly what share of pages is slow, and what would hedging at p95 cost in extra backend load?
3. Your load tester reports p99 = 15 ms, but production users complain about multi-second pauses every few minutes. Which measurement error fits, and how would you change the test?
4. Why is the mean of each host's p99 not the fleet's p99? What should you store so that the fleet-wide percentile can be computed?

## Go deeper

- [The Tail at Scale](https://research.google/pubs/the-tail-at-scale/) · Dean and Barroso's paper: the fan-out arithmetic, hedged and tied requests, and the other tail-tolerant techniques.
- [Gil Tene: How NOT to Measure Latency](https://www.youtube.com/watch?v=lJ8ydIuPFeU) · coordinated omission explained by the person who named it; watch it once and you will never trust a load test report again.
- [HdrHistogram](https://github.com/HdrHistogram/HdrHistogram) · the histogram library built for latency, including correction for coordinated omission.
- [Prometheus: Histograms and summaries](https://prometheus.io/docs/practices/histograms/) · why histograms aggregate across instances and summaries do not.
- [Google SRE Book: Service Level Objectives](https://sre.google/sre-book/service-level-objectives/) · how to express latency targets as percentiles over windows.

---

Part of [System Design](../README.md) · item 1.4
