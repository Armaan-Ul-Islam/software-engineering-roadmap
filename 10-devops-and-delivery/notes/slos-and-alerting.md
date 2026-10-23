# SLOs, error budgets and burn-rate alerting

> **In one sentence:** An SLO is a target for a user-facing indicator over a window (99.9 percent of requests succeed, 99 percent finish within 300 ms, over 30 days), the gap to 100 percent is an error budget you are allowed to spend, and alerting on how fast that budget is burning, over a long and a short window at once, pages you for real user impact and for nothing else.

**Why it matters:** CPU alerts page at night for things users never notice and stay silent while a dependency returns errors in two milliseconds. Burn-rate alerts invert that. The error budget also gives engineering and product one shared number for the argument about features versus reliability, which otherwise is settled by whoever shouts loudest after the last outage.

## The idea

**SLI.** A service level indicator is a ratio of good events to valid events, measured as close to the user as possible: successful responses over all responses, or responses faster than a threshold over all responses. Two or three per service are enough: availability and latency for an API, freshness or correctness for a pipeline.

**SLO and error budget.** The objective is a target for the SLI over a rolling window. With 99.9 percent over 30 days, the budget is 0.1 percent of requests, or 43.2 minutes of total failure per month. Choose the target from what users need and what the service has actually achieved, not from the number of nines that sounds good. The budget comes with a policy: when it is spent, risky launches wait and reliability work is prioritised; when it is comfortably unspent, you can move faster.

**Symptoms, not causes.** Page on what users experience (the SLI), because it is the only thing that is certainly worth waking someone for. Causes (CPU, pool saturation, disk space) belong on dashboards and in tickets; they explain a page, they do not justify one. Every page needs a runbook link.

**Burn rate.** Burn rate is the observed error ratio divided by the budget ratio: a burn rate of 1 spends exactly the budget by the end of the window; 14.4 spends it in about two days. Alerting on the SLI over a single short window is noisy; over a single long window it is slow to fire and slow to clear. The SRE Workbook's multi-window, multi-burn-rate rules fix both: a page requires the burn rate to be high over a long window (significance) *and* over a short window one twelfth as long (the problem is still happening).

| Budget consumed | Long window | Short window | Burn rate | Action |
|---|---|---|---|---|
| 2 percent | 1 h | 5 min | 14.4 | page |
| 5 percent | 6 h | 30 min | 6 | page |
| 10 percent | 3 d | 6 h | 1 | ticket |

With a 99.9 percent SLO the thresholds are 14.4 × 0.001 = 1.44 percent errors, 0.6 percent and 0.1 percent.

**Dashboards, runbooks, on-call hygiene.** A dashboard answers questions in order: is the SLO healthy, how fast is the budget burning, which endpoint is responsible (RED), which resource is saturated (USE). A runbook is per alert: what it means, user impact, first checks, known mitigations, who to escalate to. On-call hygiene means a shift with a handful of pages at most, every page reviewed afterwards, noisy alerts deleted or demoted the same week, and alerts tested when their expressions change.

## Example: an SLO for the orders API with the alert rules

SLOs: availability 99.9 percent (non-5xx responses), latency 99 percent of requests under 300 ms, both over 30 days. Spring Boot emits the needed bucket with `management.metrics.distribution.slo.http.server.requests=300ms`, which adds `le="0.3"` to the histogram.

```yaml
groups:
  - name: orders-slo
    rules:
      - record: orders:sli_errors:ratio_rate5m
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[5m]))
            / sum(rate(http_server_requests_seconds_count{job="orders"}[5m]))
      - record: orders:sli_errors:ratio_rate1h
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[1h]))
            / sum(rate(http_server_requests_seconds_count{job="orders"}[1h]))
      - record: orders:sli_errors:ratio_rate30m
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[30m]))
            / sum(rate(http_server_requests_seconds_count{job="orders"}[30m]))
      - record: orders:sli_errors:ratio_rate6h
        expr: |
          sum(rate(http_server_requests_seconds_count{job="orders", status=~"5.."}[6h]))
            / sum(rate(http_server_requests_seconds_count{job="orders"}[6h]))
      - record: orders:sli_slow:ratio_rate5m
        expr: |
          1 - sum(rate(http_server_requests_seconds_bucket{job="orders", le="0.3"}[5m]))
                / sum(rate(http_server_requests_seconds_count{job="orders"}[5m]))
      - record: orders:sli_slow:ratio_rate1h
        expr: |
          1 - sum(rate(http_server_requests_seconds_bucket{job="orders", le="0.3"}[1h]))
                / sum(rate(http_server_requests_seconds_count{job="orders"}[1h]))

      - alert: OrdersAvailabilityBurnRateFast
        expr: |
          orders:sli_errors:ratio_rate1h > (14.4 * 0.001)
            and orders:sli_errors:ratio_rate5m > (14.4 * 0.001)
        labels:
          severity: page
        annotations:
          summary: "orders API is burning its 30-day availability budget at 14.4x (2% per hour)"
          runbook_url: https://runbooks.example.internal/orders/availability
      - alert: OrdersAvailabilityBurnRateSlow
        expr: |
          orders:sli_errors:ratio_rate6h > (6 * 0.001)
            and orders:sli_errors:ratio_rate30m > (6 * 0.001)
        labels:
          severity: page
        annotations:
          summary: "orders API is burning its availability budget at 6x (5% per 6 hours)"
          runbook_url: https://runbooks.example.internal/orders/availability
      - alert: OrdersLatencyBurnRateFast
        expr: |
          orders:sli_slow:ratio_rate1h > (14.4 * 0.01)
            and orders:sli_slow:ratio_rate5m > (14.4 * 0.01)
        labels:
          severity: page
        annotations:
          summary: "more than 14.4% of orders requests slower than 300 ms over the last hour"
          runbook_url: https://runbooks.example.internal/orders/latency
```

1. Recording rules compute each SLI over each window once, so the alerts stay readable and cheap; the naming `level:metric:operations` is the Prometheus convention.
2. The latency SLI is "share of requests slower than 300 ms", one minus the share inside the `le="0.3"` bucket. Its budget is 1 percent, so the fast threshold is 14.4 percent slow requests.
3. The fast page catches an outage within minutes; the slow page catches a 0.6 percent error rate that would otherwise quietly spend the month's budget in five days. The 3-day burn rate 1 rule, built the same way with 3d and 6h windows, goes to a ticket, not a pager.
4. Budget remaining for the dashboard: `1 - orders:sli_errors:ratio_rate30d / 0.001`, with a 30-day recording rule added in the same way.

## Pitfalls

- Measuring the SLI where it is convenient instead of where the user is. Pods that are down emit no 5xx; a server-side SLI reads 100 percent during a total outage. Measure at the load balancer or ingress, or add a synthetic probe.
- An SLO higher than the dependencies allow. A service on a 99.9 percent database cannot promise 99.99 percent, except by not needing the database.
- Alerting on causes and per instance. "CPU over 80 percent on pod 7" is noise; the SLI already covers the consequence if there is one.
- Low traffic. At three requests per minute, one failure is a 33 percent error rate; use longer windows or require a minimum request count before alerting.
- Counting client errors as failures. A 404 for a missing order is correct behaviour; a 4xx storm is worth a dashboard, rarely a page.
- Treating the budget as decoration. If nothing changes when it is exhausted, nobody will believe the next SLO conversation either.
- Dashboards as wallpaper. Sixty panels answer no question; a dashboard is a sequence of questions from user impact to cause.

## Check yourself

1. The service has returned 1 percent errors for the last hour against a 99.9 percent, 30-day SLO. What is the burn rate, how much budget did the hour consume, and does `OrdersAvailabilityBurnRateFast` fire?
2. Why does the fast rule require both the 1-hour and the 5-minute window to exceed the threshold? What goes wrong with each window on its own?
3. Every Pod is `OOMKilled` and restarting, and the server-side error ratio shows 0 percent. Explain, and fix the SLI.
4. Pick three alerts your team has today and classify each as symptom or cause. Which would you demote from page to ticket?

## Go deeper

- [SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) · the derivation of the windows and burn rates in the table, with the Prometheus rules.
- [SRE Workbook: Implementing SLOs](https://sre.google/workbook/implementing-slos/) · choosing SLIs, setting targets and writing the error-budget policy.
- [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/) · symptoms versus causes and the four golden signals.
- [Prometheus: Alerting rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/) · the rule syntax, `for`, labels and annotations.
- [Grafana tutorials](https://grafana.com/tutorials/) · building the SLO dashboard and wiring alerts to it.

---

Part of [DevOps & Delivery](../README.md) · items 5.4, 5.5
