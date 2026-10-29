# A Well-Architected review in practice: the pillars as a checklist, and resilience you have actually tested

> **In one sentence:** A Well-Architected review asks the same set of questions of every design (how it fails, how it is secured, what it costs, how it is operated, how it performs) and the useful output is not a score but a short list of findings with an owner, the most common of which are an untested backup, a single-zone component and a recovery objective nobody wrote down.

**Why it matters:** The frameworks are long and most teams never read them; the questions, though, are exactly what a senior reviewer or an interviewer asks about your design. Walking a real service through them once produces findings you can fix in an afternoon and a vocabulary (RTO, RPO, multi-AZ, game day) that makes later design discussions shorter and more honest.

## The idea

### The pillars

| Pillar | AWS Well-Architected | Azure Well-Architected | The question behind it |
|---|---|---|---|
| Reliability | Yes | Yes | What fails, what happens when it does, and how fast do we recover? |
| Security | Yes | Yes | Who can do what, is data encrypted, and would we notice a breach? |
| Cost optimisation | Yes | Yes | What are we paying for that we do not use, and do we know the unit cost? |
| Operational excellence | Yes | Yes | Can we deploy, observe and roll back safely, and do we learn from incidents? |
| Performance efficiency | Yes | Yes | Did we measure before sizing, and does it scale with load? |
| Sustainability | Yes | Folded into the others | Are we running what we need and nothing more? |

AWS publishes the questions in the AWS Well-Architected Tool, where you answer them per workload and get a list of high and medium risks; Azure offers the Well-Architected Review assessment on Microsoft Learn with the same shape. Both are free. The questions are generic by design; the work is answering them for your system with evidence, not with intentions.

### Reliability, the pillar with numbers

Two numbers turn reliability from a feeling into a requirement:

- **RTO (recovery time objective):** how long the service may be down after a failure.
- **RPO (recovery point objective):** how much data, measured in time, may be lost.

They decide the architecture. The AWS disaster recovery whitepaper names four strategies, from cheapest to dearest:

| Strategy | What runs in the second region | Typical RTO | Typical RPO | Cost |
|---|---|---|---|---|
| Backup and restore | Nothing; backups are copied there | Hours | Minutes to hours (backup frequency) | Backup storage only |
| Pilot light | The data tier replicates; compute is defined but off | Tens of minutes | Seconds to minutes | Database replica |
| Warm standby | A scaled-down copy of everything | Minutes | Seconds | A smaller second environment |
| Multi-site active/active | Everything, serving traffic | Near zero | Near zero | Double, plus the engineering to make writes safe in two places |

Most backend services do not need a second region at all: **multi-AZ is the default** and covers hardware, power and most software failures within a region (see item 1.1). Multi-region is justified by a regulatory requirement or a business case that survives being priced, not by a reflex (see item 3.6 for what the replication traffic costs).

### Tested backups and game days

A backup you have not restored is a hypothesis. The review question is not "do you have backups" but "when did you last restore one, how long did it take, and did the application work against the result". The same applies to failover: the first time the standby takes over should not be during an incident. A **game day** is a scheduled exercise where you break something on purpose (stop the primary database, kill a zone's worth of tasks, revoke a secret) with the team watching, and record what the monitoring showed, what the runbook said, and what actually happened. AWS Fault Injection Service and Azure Chaos Studio can inject the faults; a console button and a stopwatch are enough to start.

## Example: reviewing the orders service

The system: Spring Boot on ECS Fargate (or Azure Container Apps), RDS for PostgreSQL (or Flexible Server), Redis, S3 (or Blob Storage) for uploads, one region. Each row is one question from the review, the honest answer and the resulting finding.

| Pillar | Question | Answer found | Finding and fix |
|---|---|---|---|
| Reliability | Is every stateful component in more than one zone? | Database Multi-AZ: yes. Redis: single node. | Add a replica in a second zone; the cache failing means a database overload, not just slower responses |
| Reliability | What are the RTO and RPO? | Nobody had written them down | Agreed RTO 1 hour, RPO 5 minutes, which point-in-time recovery meets; recorded in the runbook |
| Reliability | When was a restore last tested? | Never | Restore drill into staging scheduled; the first run took 38 minutes and found that the service's configuration hard-coded the old endpoint |
| Reliability | Are retries bounded and idempotent? | Retries on every HTTP client, no budget | Add a retry budget and jitter; the payment call was not idempotent (see item 7.3) |
| Security | Does any resource have a public IP it does not need? | The database had `PubliclyAccessible` from early debugging | Disabled; connections now go through the private subnet only (see item 9.2) |
| Security | How does the service authenticate to the cloud? | Task role, no keys | No finding |
| Cost | What is running at night? | Staging at full size | Scheduled scale-to-zero outside working hours (see item 5.7) |
| Operational excellence | Can you roll back in under five minutes? | Images tagged `latest` | Tag with the Git SHA; keep the previous task definition revision |
| Operational excellence | Does an alert fire before users call? | CPU alarm only | Alert on p99 latency and 5xx rate at the balancer (see item 8.2) |
| Performance | Was the task size measured or guessed? | Guessed at 2 vCPU | Load test and resize (see item 5.1) |

Ten questions, eight findings, each with an owner and most fixable in a day. That is a typical first review.

A game-day runbook for one of the findings, written before the exercise and corrected afterwards:

```text
Game day: database failover, 2026-11-05 14:00, staging, 45 minutes

1. Baseline: note p99 latency, error rate and pool metrics on the dashboard.
2. 14:05  Trigger: reboot the RDS instance with failover (or restart the Flexible Server standby promotion).
3. Expect: connection errors for under 60 seconds; HikariCP evicts dead connections;
          readiness probe fails on affected tasks; balancer stops routing to them; recovery without restart.
4. Observe: time to first error, time to last error, whether the alert fired, whether anyone was paged.
5. Record: actual numbers against the expectation; anything the runbook got wrong.
6. Follow-ups: tickets for every gap, with owners.
```

The first run of this exercise usually finds that the connection pool's `max-lifetime` and the failover DNS change interact badly, or that the alert threshold was set so high that a one-minute outage never pages anyone. Those are the findings worth having before the real failover.

## Pitfalls

- Treating the review as a form. The value is the findings list; a workload with "no high risks" that has never restored a backup is a workload with an honest answer missing.
- Multi-region as the answer to "is it reliable?". It doubles cost and adds data consistency problems that most services never needed; multi-AZ first, and a written business case before the second region.
- RTO and RPO that nobody agreed. Without the numbers, every design is both over-built and under-tested.
- Backups that exist and are never restored. The restore target has a new endpoint and your configuration may not cope (see item 6.2).
- Game days on production first. Start in staging, with the same architecture, and move to production only when the runbook has survived there.
- Reviewing once. Architectures drift; a short review per quarter or per major change keeps the findings list honest.

## Check yourself

1. Your product owner wants "the service to never go down". Turn that into RTO and RPO questions, and explain which of the four DR strategies each plausible answer leads to.
2. Why is multi-AZ the default and multi-region the exception? Name two costs of multi-region that are not on the bill.
3. Design a game day for "the Redis cache is lost". What do you expect to see, which metric proves the system coped, and what finding would make you add a replica?
4. Pick three questions from the example table and answer them for a service you know. Which answer are you least sure of, and what evidence would settle it?

## Go deeper

- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) · the pillars and their questions; read the reliability and operational excellence pillars first.
- [Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/) · the same pillars with Azure-specific checklists and trade-offs.
- [AWS: Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html) · the four strategies with their RTO and RPO ranges.
- [Azure Well-Architected: Reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/) · recovery targets, failure mode analysis and testing, with a checklist.
- [AWS Builders' Library](https://aws.amazon.com/builders-library/) · the articles on timeouts, retries and backoff, which answer the "are retries bounded" question properly.

---

Part of [Cloud](../README.md) · items 1.5, 8.5
