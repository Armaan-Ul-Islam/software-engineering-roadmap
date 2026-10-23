# Autoscaling and the database bottleneck

> **In one sentence:** Autoscaling adds application instances when a metric says demand rose, but every instance brings its own connection pool, so a fleet that scales from 3 to 12 can quadruple the connections hitting a database whose limit did not move, and the fix is smaller pools, a connection proxy, or a cap on the fleet.

**Why it matters:** The classic cloud outage is self-inflicted: traffic rises, the application tier scales out exactly as designed, and the database starts refusing connections. The stateless tier was elastic and the stateful tier was not. Understanding both the scaling policy and the connection arithmetic is the difference between an autoscaling group that saves you and one that finishes you off.

## The idea

### What triggers a scale-out

| Policy type | How it works | AWS | Azure |
|---|---|---|---|
| Metric-based, target tracking | "Keep this metric near this value"; the platform adds or removes capacity to hold it | EC2 Auto Scaling and ECS Service Auto Scaling target tracking on CPU, `ALBRequestCountPerTarget`, or a custom metric | VMSS autoscale rules; Container Apps scale rules (KEDA) on HTTP concurrency, CPU, memory or a queue |
| Metric-based, step | Thresholds with explicit step sizes ("above 80%, add 2") | Step scaling policies | VMSS metric rules with scale-by counts |
| Scheduled | Change minimum and desired capacity at a time of day | Scheduled actions | Autoscale schedules; Container Apps cron scaler |
| Predictive | Forecast from history and scale ahead of it | Predictive scaling | Predictive autoscale on VMSS |

Scheduled scaling is underrated. If the peak is 09:00 every weekday, scaling at 08:45 beats any metric, because metrics are late by definition: the load has already arrived when CPU rises.

### Why CPU alone is a poor signal for a JVM service

- It lags: by the time average CPU crosses the target, requests have been queueing for a scrape interval or two.
- New instances spike CPU while the JIT warms up, which can trigger another scale-out before the first one has helped (a scale-out storm).
- Many services are I/O bound. They run out of request threads or database connections at 30% CPU, and CPU-based scaling never fires.

Scale on what the users feel: **requests per target** for an API (ALB request count per target on AWS; concurrent HTTP requests per replica on Container Apps, which defaults to 10), or **backlog per worker** for a queue consumer (visible messages ÷ instances, targeting a value that drains within your SLA). Keep CPU as a secondary guard, not the primary trigger.

### Cool-downs and warm-up

A **cool-down** is the pause after a scaling action before the next one, so the new capacity can register in the metrics. Scale-out should be aggressive and scale-in cautious: fast to add, slow to remove, because removing capacity that is still needed causes the next incident. EC2 Auto Scaling's default cool-down is 300 seconds; Kubernetes' Horizontal Pod Autoscaler stabilises scale-in over a 300-second window by default; Container Apps has a cool-down period between scale events. A JVM instance also needs a **warm-up** before it takes full traffic: a health-check grace period, and on an ALB the target group's slow-start mode, which ramps the share of requests a new target receives.

### The multiplication nobody budgets

Each application instance opens a pool of `maximum-pool-size` connections and keeps them open. Connections are per instance, so the database sees `pool size × instance count`. The database's `max_connections` is fixed by its tier (RDS derives the default from instance memory; Azure Database for PostgreSQL Flexible Server publishes a value per compute size), and a few slots are reserved for superusers and the platform's own monitoring. Every PostgreSQL connection is also a backend process that costs memory whether it is busy or idle, so a database near its connection limit is also near its memory limit.

The remedy has three layers, and good systems use all three:

1. **Right-size the pool.** HikariCP's guidance is that a pool of roughly `cores × 2 + effective spindles` on the *database* server saturates it for OLTP work; for a 4-vCPU database that is around 10 active connections *in total*, not per instance. Little's law gives your real need: connections in flight = requests per second × seconds each holds a connection (see item 5.2).
2. **Put a connection proxy in front.** PgBouncer in transaction mode holds a few server connections and hands them to whichever client transaction is active. Azure Database for PostgreSQL Flexible Server ships PgBouncer built in (enable it and connect on port 6432); on AWS, RDS Proxy plays the same role. Transaction pooling breaks session-level state (`SET` without `LOCAL`, advisory locks, `LISTEN`), so check what your code relies on.
3. **Cap the fleet.** Set the autoscaler's maximum to `floor(usable connections ÷ pool size)`. A hard ceiling that degrades into queued requests beats one that turns into connection failures, and it forces the conversation about scaling the database.

## Example: 3 to 12 instances against a connection limit

Assumptions, labelled: the pool is HikariCP with `spring.datasource.hikari.maximum-pool-size=20` (A1); the database tier allows `max_connections = 200` (A2, read it from your tier's limits page); 3 slots are reserved for superusers (PostgreSQL's `superuser_reserved_connections` default) so 197 are usable (A3); autoscaling runs between 3 and 12 instances (A4).

| Instances | Connections with pool 20 | Connections with pool 10 | Clients through PgBouncer (pool 20) | Server connections PgBouncer opens |
|---|---|---|---|---|
| 3 | 60 | 30 | 60 | 20 (its own pool size) |
| 6 | 120 | 60 | 120 | 20 |
| 9 | 180 | 90 | 180 | 20 |
| 10 | 200, exceeds 197 | 100 | 200 | 20 |
| 12 | 240 | 120 | 240 | 20 |

With pool 20, the tenth instance fails to fill its pool: PostgreSQL refuses the extra connections with a `FATAL: remaining connection slots are reserved ...` error (the exact wording varies by version), HikariCP logs connection timeouts, and requests fail with `SQLTransientConnectionException: HikariPool-1 - Connection is not available, request timed out after 30000ms`. Note that instances 1 to 9 keep working; the failure lands only on the newest instances, which the load balancer is sending a fair share of traffic. The outage looks like "10% of requests fail, randomly".

Three fixes, applied to the same fleet:

1. Pool 10: 12 × 10 = 120, inside the limit with 77 spare. Little's law check from item 5.2: at 1,200 requests/s holding a connection for 15 ms, only 18 connections are in flight across the whole fleet, so 10 per instance is still generous.
2. PgBouncer in transaction mode with a server pool of 20: the 240 client connections share 20 real ones; the database sees 20 backends regardless of how far the fleet scales. Latency is unaffected as long as the 20 are rarely all busy, which the 18 in-flight figure says they are not.
3. Cap maximum instances at `floor(197 ÷ 20) = 9` until one of the first two fixes is in place, and alarm when the cap is hit.

Spring Boot exposes what you need to verify it: `hikaricp.connections.active`, `hikaricp.connections.pending` (should be zero) and `hikaricp.connections.timeout` (should never increase).

## Pitfalls

- Scaling the application without a plan for the database. The database is the one component that does not scale horizontally for writes; its limits bound your fleet.
- Setting `maximum-pool-size` by instinct (50, 100). Bigger pools do not make a saturated database faster; they make it slower and eat its connection slots.
- `minimum-idle` lower than `maximum-pool-size` to "save connections". HikariCP recommends a fixed-size pool; the connections are cheap once open and the reconnect storm on a burst is not.
- Scale-in that is as fast as scale-out. The fleet oscillates, and every scale-in drops in-flight requests unless graceful shutdown is configured (see item 8.4).
- Autoscaling on CPU with a JIT warm-up spike and no warm-up period. Each new instance looks overloaded for a minute and recruits another.
- Forgetting that the proxy has limits too. RDS Proxy and PgBouncer have their own maximum client connections and their own CPU; measure them.
- Running the load test with one instance and the real system with twelve. The database was never tested at twelve pools' worth of connections.

## Check yourself

1. Your API scales on average CPU at 70%. Under a burst it fails with request timeouts while CPU reports 35%. Which metric should the policy use instead, and why did CPU stay low?
2. Twelve instances with a pool of 15 each, a database limit of 150. Compute the shortfall, then propose the smallest pool that fits and justify it with Little's law for 900 requests per second holding a connection for 20 ms.
3. Why does PgBouncer's transaction mode let 240 clients share 20 server connections, and name two Spring or SQL habits that break under it.
4. Scale-out and scale-in both have a 60-second cool-down. Describe the oscillation that follows a ten-minute burst and which of the two settings you would change.

## Go deeper

- [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · the argument, with measurements, for why small pools win.
- [Azure Database for PostgreSQL: Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) · connection limits per compute size and the reserved connections.
- [AWS: Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html) · how target tracking, warm-up and cool-down interact.
- [Kubernetes: Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) · the algorithm and the stabilisation window; Container Apps and AKS inherit the model.

---

Part of [Cloud](../README.md) · items 5.4, 5.5
