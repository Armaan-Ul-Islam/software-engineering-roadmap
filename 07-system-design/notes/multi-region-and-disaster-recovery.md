# Multi-region and disaster recovery

> **In one sentence:** Disaster recovery is a purchase: you pick how much data you can lose (RPO) and how long you can be down (RTO) from the business impact, then buy the cheapest arrangement that delivers it, and for most systems that is one region across several availability zones plus backups you have actually restored, not a second region.

**Why it matters:** "We are multi-region" is said far more often than it is true, because the database was replicated and nothing else was, and the failover has never been run. Meanwhile the common disasters (a bad deploy, a deleted table, an expired certificate) replicate to every region instantly and are survived by backups, not by geography. Deciding this well is a matter of two numbers and an honest inventory of what a second region costs.

## The idea

**RTO and RPO.** Recovery time objective: how long after a failure the service must be back. Recovery point objective: how much recently written data you may lose, measured in time ("the last five minutes of writes"). Both follow from the cost of downtime and of lost data (see item 1.1), and both are only real once measured: a restore you have never run has an unknown RTO, and a replica whose lag you do not monitor has an unknown RPO.

**Failure domains.** An instance fails often. An availability zone (a data centre with its own power and network, a millisecond or two from its neighbours in the same region) fails occasionally. A whole region fails rarely, but it does, and usually through a control-plane or network fault that takes every zone with it. Your own change fails most often of all (see item 4.6), and so does your data: a migration that drops a column, a job that overwrites a table. Each domain needs a different defence, and the cheap ones cover most of the risk: multi-AZ with synchronous replication covers instance and zone failures with zero data loss, because the zones are close enough to wait for the standby on every commit. Backups with point-in-time recovery cover the self-inflicted disasters that replication faithfully copies. Only a second region covers regional failure, and it is the expensive one.

**The four tiers.** The AWS whitepaper linked from the README names them, and the names are now common vocabulary:

| Tier | What runs in the second region | RPO | RTO | Relative cost | What it demands of the application |
|---|---|---|---|---|---|
| Backup and restore | Nothing; backups copied there, infrastructure defined as code | Hours (backup interval), minutes with continuous log shipping | Hours to a day: provision, restore, repoint | Storage only | Infrastructure as code, restore runbook, tested restores |
| Pilot light | Data replicated continuously; core infrastructure provisioned but switched off or minimal | Minutes | Tens of minutes to hours: scale up, switch traffic | Small, plus replication egress | Everything stateful has a replication path, not only the database |
| Warm standby | A scaled-down but fully working copy serving no (or little) traffic | Seconds to minutes | Minutes: scale up, switch traffic | Most of a second environment | Continuous deployment to both regions, regular failover tests |
| Active-active | A full copy serving traffic | Near zero | Near zero for the surviving region's users | Two full environments plus the engineering | Writes that tolerate asynchronous replication: partitioned ownership, conflict handling, or a consensus database |

The first three are active-passive: one region serves, the other waits. The jump to active-active is not a bigger version of warm standby; it changes the data model, which is the next point.

**Cross-region replication and consistency.** Regions are 30 to 150 ms apart (see item 1.2), so waiting for a remote replica on every commit multiplies write latency by ten or more; nearly everyone replicates asynchronously. The consequences follow from item 3.1: on failover the last seconds of acknowledged writes are lost (that is your RPO), and if the old primary was not really dead it may still be accepting writes, so it must be fenced before the standby is promoted or you have two histories to reconcile. If both regions accept writes, you are running multi-leader replication: concurrent writes to the same record conflict, last-writer-wins silently drops one of them (see item 3.5), and uniqueness constraints cannot be enforced across regions. The workable patterns are to give every record a home region (users are pinned to the region nearest them, writes are routed home, reads are served locally, and failover re-homes the affected users), to use a database that runs consensus per shard across regions and pay the latency on every write (Spanner, CockroachDB; see item 3.6), or to confine true multi-leader writes to data with mergeable semantics. The database is only one of the stateful things: caches, queues, object storage, search indexes, secrets and sessions each need their own replication plan, and a region whose database has failed over but whose queue has not is not up.

**Steering traffic.** DNS is the usual switch: a failover record whose health check flips it to the standby, or latency and geolocation routing for active-active. Its limits are the TTL (clients and resolvers cache answers, some ignore short TTLs, so a 60-second TTL gives a failover of minutes, not seconds), and the health check, which must exercise the real request path, not a ping, and must have thresholds that stop a flapping check from flipping traffic back and forth. Anycast and global load balancers (see item 2.1) move the switch to the network layer and fail over in seconds, at a price. Whatever the mechanism, decide in advance who or what pulls the switch, because a human deciding under pressure at 03:00 is the slowest component of the whole design.

**Hidden costs.** Cross-region data transfer is billed per gigabyte and replication never stops. Schema migrations, feature flags and deploys must work in two places, in an order that keeps replication valid. Failing back is harder than failing over: the data written in the standby has to be reconciled with the recovered primary. And the test: an untested failover is a hypothesis. Game days (see item 4.7) that actually move production traffic are the only evidence, and their cost, in engineering time and in the incidents they cause, is part of the price of the tier.

**The honest default.** One region, three availability zones, stateless services spread across them, a database with a synchronous standby in another zone and automated failover, automated backups with continuous log archiving copied to a second region and a second account, infrastructure as code that can rebuild the region from nothing, and a restore rehearsed often enough that its duration is a number you know. That is RPO zero for zone failure, RPO of minutes for regional failure, and an RTO for regional failure measured in hours. Move up a tier only when item 1.1's arithmetic shows that a regional outage every few years does not fit the availability budget, or when users on another continent need local latency, which is a different problem (serve reads locally, write to the home region) with a different solution.

## Example: choosing the tier for the checkout service

Take the checkout from item 1.1: 99.9 percent availability for `POST /orders`, an error budget of 43 minutes a month, or about 8.8 hours a year, and a rule that no confirmed order may be lost.

Regional outages at the big providers are rare and long: a few hours, perhaps once every few years. A four-hour regional outage every three years costs 1.3 hours a year, well inside 8.8 hours. The honest default therefore fits: multi-AZ with a synchronous standby (zone failure: RPO zero, RTO about a minute, automated), continuous WAL archiving to object storage replicated to a second region, infrastructure as code, and a rehearsed restore whose measured RTO was three hours on the last game day. Orders confirmed in the final minutes before a regional failure could be lost from the database, so the "no lost order" rule is met by process rather than replication: the payment provider's records are reconciled against the restored database and the missing orders are recreated. Most RPO problems have a business-process answer that is cheaper than the technical one.

Now the business asks for 99.99 percent: 52 minutes a year. One regional outage breaks it, so a warm standby becomes necessary: an asynchronous read replica in the second region (RPO of seconds, monitored), a scaled-down copy of every service deployed there on every release, caches cold but present, the outbox relay and queue consumers ready but paused, a DNS failover record with a 60-second TTL and a deep health check, and a documented decision rule for who promotes. Measured RTO: ten minutes, dominated by DNS propagation and the scale-up. The bill: most of a second environment, replication egress, two deploy targets, a quarterly failover test, and the knowledge that the new tier protects against the rare disaster and does nothing for the common one, so the backups and the restore rehearsals stay.

## Pitfalls

- Replicating the database and calling it multi-region. Queues, caches, object storage, search, secrets and sessions each need a plan, and the first failover finds the one you forgot.
- Never running the failover. The procedure that has not been executed in a year has an RTO of "unknown"; test it with real traffic, on a schedule.
- Trusting replication to protect data. A dropped table replicates in milliseconds; only backups with point-in-time recovery undo it, whatever the tier.
- Promoting the standby without fencing the old primary. A slow primary that keeps accepting writes produces two diverging histories.
- Active-active with naive multi-leader writes. Last-writer-wins drops data, uniqueness cannot be enforced, and the conflicts surface as support tickets months later.
- Standby capacity that does not exist. A standby at ten percent of production that has to autoscale during a regional event competes with everyone else for instances.

## Check yourself

1. State RTO and RPO for a multi-AZ database with a synchronous standby, and for the same database with only nightly backups in another region. Which disasters does each handle, and which does neither?
2. Why does a warm standby not change the application's data model, while active-active does? Name two ways to make writes safe in active-active.
3. Your DNS failover record has a 60-second TTL. Explain why the real failover time is longer, and what alternative steers traffic faster.
4. A team wants a second active region "for safety". Using the arithmetic from the example, what questions would tell you whether the tier is justified, and what would you insist on keeping whatever the answer?

## Go deeper

- [AWS: Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html) · the four tiers with their RPO, RTO and cost, from the whitepaper this note's table follows.
- [AWS Builders' Library: Static stability using Availability Zones](https://aws.amazon.com/builders-library/static-stability-using-availability-zones/) · how to build a region so that a zone can fail without any component having to react.
- [Google SRE Book: Data Integrity](https://sre.google/sre-book/data-integrity/) · why replication is not a backup, defence in depth for data, and the case for rehearsed restores.
- [Amazon Route 53: DNS failover](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/dns-failover.html) · health checks, failover records and the TTL behaviour that bounds failover time.
- [Designing Data-Intensive Applications, chapter 5](https://dataintensive.net/) · multi-leader replication across data centres and the conflict handling it forces.

---

Part of [System Design](../README.md) · item 5.7
