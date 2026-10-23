# Pricing a design and the cost traps that hide in it

> **In one sentence:** Price a design by listing every resource in the diagram with explicit usage assumptions, pulling unit prices from the official calculators, and then hunting for the lines the diagram does not show, because NAT processing, cross-zone and egress transfer, idle balancers, orphaned disks and log ingestion are where real bills diverge from estimates.

**Why it matters:** The compute you chose is rarely the biggest surprise on a cloud bill; the data transfer you did not draw and the resources nobody deleted are. A developer who can produce a line-item estimate with assumptions, and who can read last month's bill and name the three things wasting money, is trusted with production. Both abilities are tested in design interviews.

## The idea

### The method

1. Draw the architecture and list **every** box and every arrow: compute, load balancer, NAT gateway, database (with its high-availability option), cache, object storage, secrets, DNS, logs and metrics, and each data flow with a direction.
2. Write down the **usage assumptions** per line: hours per month (730 for always-on), vCPU and memory, GB stored, GB transferred per path, requests per month, log volume per day. Label them; they are what you will re-check later.
3. Enter the lines into the AWS and Azure pricing calculators (linked below) for the region you will actually use. Never copy prices from blog posts or memory; they change and differ by region.
4. Price the **baseline twice**: on-demand, and with a one-year reservation or savings plan for the parts you know will run all year (the database, the minimum instance count).
5. Add the environments nobody prices: staging, test, the preview environments per branch.
6. Save the estimate next to the design. When the first bill arrives, compare line by line.

### Always-on versus per-request: the break-even

An always-on tier (containers, VMs, PaaS) costs the same whether it serves one request or a million. A per-request tier (Lambda, Azure Functions) costs nothing idle and grows linearly with traffic. There is a request volume where the lines cross, and you can compute it from calculator prices.

Assume, as placeholders from the calculator: `P_vcpu` per vCPU-hour and `P_mem` per GiB-hour for the container platform, `P_req` per million invocations and `P_gbs` per GB-second for functions.

- Always-on monthly cost for `n` tasks of `c` vCPU and `m` GiB: `C_on = n × 730 × (c × P_vcpu + m × P_mem)` plus the load balancer's fixed hourly charge.
- Per-request monthly cost for `R` requests with average duration `d` seconds at `g` GB of memory: `C_req = R × P_req ÷ 1,000,000 + R × d × g × P_gbs`.
- Break-even: `R* = C_on ÷ (P_req ÷ 1,000,000 + d × g × P_gbs)`.

Below `R*` requests per month, functions are cheaper; above it, the always-on tier is. Two things move the line. Longer or heavier invocations (a JVM function at 1 GB taking 300 ms) move `R*` down, so always-on wins sooner. Provisioned concurrency or a Premium plan adds a fixed hourly term to `C_req`, which is the moment the "per-request" option has quietly become always-on with extra steps (see item 4.6).

### The traps

| Trap | What happens | AWS | Azure | Fix |
|---|---|---|---|---|
| NAT gateway data processing | Every byte from private subnets to the internet or to object storage pays an hourly charge *and* a per-GB fee | NAT Gateway | NAT Gateway | Gateway endpoints (S3, DynamoDB) and private endpoints (Blob Storage, other PaaS) keep bulk traffic off the NAT path |
| Cross-zone transfer | Chatty services spread across zones pay per GB for traffic that never leaves the region | Charged per GB in each direction between AZs | Check the bandwidth pricing page; the policy has changed | Zone-aware routing; one NAT gateway per zone |
| Internet egress | Bytes out to the internet are billed per GB after a small monthly allowance; inbound is free | Data transfer out | Bandwidth | A CDN for cacheable content; compression; large files served from storage, not from the API |
| Idle load balancers | Each balancer costs per hour before it carries a request, and every preview environment gets one | ALB, NLB | Application Gateway, Standard Load Balancer | Share one balancer with host-based routing; tear down preview environments |
| Over-provisioned managed databases | The class was picked for launch day; HA doubles the compute line; provisioned IOPS are paid for unused; storage autoscaling never shrinks | RDS, Aurora | Flexible Server | Right-size from CPU and connection metrics; HA in production only; reserve the baseline |
| Unattached disks and old snapshots | Volumes survive the VM they were attached to; snapshots accumulate forever | EBS volumes, EBS snapshots | Managed Disks, disk snapshots | Delete-on-termination; a lifecycle policy for snapshots; a monthly report of unattached disks |
| Log ingestion | Ingesting a GB of logs costs more than storing it; `DEBUG` in production at 1,000 requests per second is a budget line | CloudWatch Logs | Log Analytics workspace | Drop noisy logs at the source; set retention |
| Forgotten environments | Staging runs 730 hours a month to serve a demo once a week | Everything | Everything | Scheduled stop at night and weekends; scale-to-zero platforms for non-production |

### Tagging, budgets and right-sizing

Nothing above is visible unless resources are **tagged** (`service`, `environment`, `owner`, `cost-centre`) and the tags are activated as cost allocation tags in AWS Billing (not retroactive, so do it on day one) or picked up by Azure Cost Management (enforce them with Azure Policy). Set **budgets** with forecast alerts (AWS Budgets, Azure Budgets) and turn on anomaly detection, so a runaway retry loop is a notification rather than a quarterly surprise. **Right-size** from measured utilisation with AWS Compute Optimizer or Azure Advisor, then commit to the baseline you can see.

## Example: a line-item template for "Spring Boot API + PostgreSQL + Redis"

Fill the unit prices from the calculator for your region; the quantities are the labelled assumptions you must defend.

| Line | AWS service | Azure service | Unit | Quantity (assumption) | Unit price | Monthly |
|---|---|---|---|---|---|---|
| Application tasks | ECS on Fargate | Container Apps (dedicated or consumption) | vCPU-hour, GiB-hour | 3 tasks × 2 vCPU × 2 GiB × 730 h off-peak, 6 tasks for 8 h/day peak | from calculator | |
| Load balancer | Application Load Balancer | Application Gateway | hour + capacity unit | 730 h, estimate capacity units from requests and bytes | from calculator | |
| Outbound NAT | NAT Gateway × 3 zones | NAT Gateway | hour + GB processed | 3 × 730 h; 200 GB processed | from calculator | |
| PostgreSQL | RDS for PostgreSQL, Multi-AZ | Flexible Server, zone-redundant HA | instance-hour, GB-month storage, IOPS | 1 instance (HA doubles compute), 200 GB, baseline IOPS | from calculator | |
| Database backups | Automated backups beyond free allowance | Backup storage beyond free allowance | GB-month | 7 days retention, roughly 1× database size | from calculator | |
| Redis | ElastiCache | Azure Cache for Redis or Azure Managed Redis | node-hour | 2 nodes (primary and replica) × 730 h | from calculator | |
| Object storage | S3 Standard | Blob Storage, hot tier | GB-month, requests | 500 GB, 2 million PUT, 20 million GET | from calculator | |
| Secrets | Secrets Manager | Key Vault | secret-month, operations | 5 secrets, 100k operations | from calculator | |
| Logs and metrics | CloudWatch Logs and metrics | Log Analytics, Application Insights | GB ingested, GB-month retained | 30 GB/day ingested, 30 days retention | from calculator | |
| Internet egress | Data transfer out | Bandwidth | GB | 1 TB responses to clients | from calculator | |
| Cross-zone transfer | Inter-AZ data transfer | see bandwidth page | GB | 500 GB app-to-database and app-to-cache | from calculator | |
| Non-production | Everything above, smaller | Everything above, smaller | | staging at one task, single-zone database, stopped nights and weekends | | |
| **Total on-demand** | | | | | | |
| **Total with one-year commitment on database and 3 baseline tasks** | | | | | | |

Reading the finished sheet usually teaches the same lesson: the database with HA and the balancer-plus-NAT fixed charges rival the application tier, and logs plus transfer are not rounding errors.

## Pitfalls

- Pricing only the boxes. Arrows cost money: NAT processing, cross-zone traffic and egress are lines in their own right.
- Comparing an always-on estimate at launch traffic with a per-request estimate at launch traffic. Compute the break-even and ask which side of it you will be in a year.
- Reserving before measuring. Reservations are for the baseline you have observed, not the peak you hope for.
- Turning on verbose logging "temporarily" without a retention policy or a sampling rule.

## Check yourself

1. Your estimate shows the application tier as 60% of the bill, but the first invoice shows it at 30%. Name the four lines most likely to have grown, and how you would confirm each from the bill.
2. Using the placeholder formula, explain what happens to the break-even request volume when a function's memory is doubled to make it faster, and when provisioned concurrency is added.
3. A review finds a single NAT gateway processing 5 TB a month, mostly S3 traffic. Which change removes most of that line, and what does it cost on the other cloud?
4. Which three reports or alerts would you set up on day one so that a runaway retry loop is noticed within a day rather than at month end?

## Go deeper

- [AWS Pricing Calculator](https://calculator.aws/) and [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) · the only sources for unit prices; build and save the estimate from the template above.
- [AWS: Overview of Data Transfer Costs for Common Architectures](https://aws.amazon.com/blogs/architecture/overview-of-data-transfer-costs-for-common-architectures/) · diagrams that show exactly which arrows are billed.
- [Azure: Bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/) · the current egress and inter-zone position; re-read it, it changes.
- [FinOps Foundation: Framework](https://www.finops.org/framework/) · the inform, optimise, operate loop that tagging and budgets feed.
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) and [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/overview-cost-management) · where to read the bill by tag and find the right-sizing recommendations.

---

Part of [Cloud](../README.md) · items 3.6, 5.6, 5.7
