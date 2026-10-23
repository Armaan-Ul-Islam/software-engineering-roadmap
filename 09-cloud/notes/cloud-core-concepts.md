# Cloud core concepts: service models, shared responsibility, regions and pricing

> **In one sentence:** Every cloud service sits somewhere on a line from "you manage almost everything" (a virtual machine) to "you manage only your code and data" (a function or a SaaS product), and where it sits decides what you are responsible for, how it fails, and how it is billed.

**Why it matters:** The same Spring Boot service can run on a virtual machine, a container platform, a PaaS or a function, and the choice changes who patches the operating system, whether a single data-centre failure takes you down, and whether you pay by the hour or by the request. People who skip these basics build single-zone databases, leave on-demand instances running for three years, and are surprised by both the outage and the bill.

## The idea

### Service models

The models differ in how much of the stack the provider runs for you.

| Model | You manage | Provider manages | AWS example | Azure example |
|---|---|---|---|---|
| IaaS (infrastructure) | OS, runtime, your app, data, network rules | Physical hosts, hypervisor, storage, network fabric | EC2, EBS, VPC | Virtual Machines, Managed Disks, Virtual Network |
| CaaS (containers) | Container image, app configuration, data | Hosts, OS, orchestration | ECS on Fargate | Azure Container Apps |
| PaaS (platform) | Your app and its configuration, data | Runtime, OS, scaling, patching | Elastic Beanstalk, RDS | App Service, Azure Database for PostgreSQL |
| FaaS (functions) | Function code, data | Everything else, including scaling to zero | Lambda | Azure Functions |
| SaaS (software) | Your data and users | The whole application | Amazon WorkMail, Amazon QuickSight | Microsoft 365, Dynamics 365 |

Moving down the table buys you less operational work and costs you control: on a PaaS you cannot tune the kernel, and on a FaaS you cannot keep a connection pool warm for hours. The right row is a trade, not a ranking (see item 4.6 for the decision table).

### Shared responsibility

AWS phrases it as "security *of* the cloud versus security *in* the cloud"; Azure draws the same picture as a chart that shifts work towards Microsoft as you move from IaaS to SaaS. The provider is always responsible for the physical facilities, hardware and the virtualisation layer. You are always responsible for your data, who may access it, and your application's own security. Everything in between (OS patches, network configuration, encryption settings, identity) moves between the two columns depending on the service model. A managed database still needs *you* to decide who can connect, whether TLS is required, and how long backups are kept.

### Regions, availability zones and edge locations

A **region** is a geographic area (AWS `eu-north-1` in Stockholm, Azure `swedencentral`) with its own set of services, pricing and data-residency boundary. Nothing replicates between regions unless you make it.

An **availability zone (AZ)** is one or more physically separate data centres inside a region, with independent power, cooling and networking, joined by low-latency links. Both providers design AZs so that a fire, flood or power failure in one zone does not touch the others. Not every Azure region has zones; check before assuming.

**Edge locations** are the small points of presence that CloudFront and Azure Front Door use for CDN caching and TLS termination close to users. They do not run your compute.

The rule that follows: **anything stateful runs multi-AZ by default**. A managed PostgreSQL with a synchronous standby in a second zone, an application tier spread across at least two zones behind a load balancer, object storage that already replicates across zones for you (S3 Standard, Azure zone-redundant storage). Multi-*region* is a different and much more expensive decision; it is justified by a regulatory or business requirement, not by habit (see item 8.5).

### Elasticity versus scalability

Scalability means the system *can* grow to handle more load. Elasticity means it grows and shrinks *automatically* with load, and you pay only for what is running. A cluster you resize by hand once a quarter is scalable; an autoscaling group that adds instances at 09:00 and removes them at 18:00 is elastic. Elasticity is where the cloud saves money, and it only works if your service starts fast and holds no local state.

### Pricing models

| Model | How you pay | Commitment | Best for |
|---|---|---|---|
| On-demand | Per second or per hour while the resource exists | None | Development, spiky or unknown load, anything you are still measuring |
| Reserved instances and savings plans (AWS); Reservations and Savings Plan for compute (Azure) | A discount in exchange for a one- or three-year commitment to a family, size or hourly spend | One or three years, paid upfront, partially upfront or monthly | The steady baseline you know will run all year: the database, the minimum instance count |
| Spot (AWS Spot Instances, Azure Spot Virtual Machines) | Deeply discounted spare capacity that the provider can reclaim with short notice (two minutes on AWS, thirty seconds on Azure) | None | Batch jobs, CI runners, stateless workers that can die and be replaced |
| Free tier | Nothing, within monthly limits that change over time | None | Learning and prototypes; read the current terms, not a blog post |

The pattern that works: measure on-demand for a few weeks, commit to the baseline you can see, autoscale the peaks on-demand, and push interruptible work to spot.

## Example: the same service, four placements

A Spring Boot order API with a PostgreSQL database, placed four ways. Prices are deliberately absent; the point is what changes.

| Placement | AWS | Azure | Who patches the OS | Survives one zone failing? | Scales to zero? |
|---|---|---|---|---|---|
| One VM, database on the same VM | EC2 | Virtual Machine | You | No | No |
| Two VMs in two zones behind a load balancer, managed multi-AZ database | EC2 + ALB + RDS Multi-AZ | VMs + Load Balancer + Flexible Server zone-redundant HA | You (VMs), provider (database) | Yes | No |
| Containers on a serverless container platform, managed database | ECS on Fargate + RDS | Container Apps + Flexible Server | Provider | Yes, if you ask for tasks in more than one zone | Container Apps yes, Fargate no |
| Function per endpoint, managed database | Lambda + RDS Proxy + RDS | Azure Functions + Flexible Server | Provider | Yes | Yes |

Read the last two columns together with the pricing table. The single VM is the cheapest line on an invoice and the most expensive line in an incident report. The function placement scales to zero but every cold start pays the JVM's startup cost (see item 4.4), and a database with a fixed connection limit does not enjoy being hit by hundreds of short-lived functions (see item 5.4).

## Pitfalls

- Treating multi-AZ as optional for the database because "the application is stateless anyway". The application tier can be rebuilt from an image in minutes; a single-zone database in a zone outage is data you cannot reach.
- Confusing multi-AZ with multi-region. Multi-AZ is cheap and should be the default. Multi-region doubles the infrastructure, adds replication lag and failover complexity, and is rarely required.
- Buying reservations before measuring. A three-year reservation on an instance family you later abandon is paid for whether or not it runs.
- Running spot for anything that cannot tolerate being killed mid-request. Spot is for work that can be retried.
- Reading "managed" as "someone else's problem". On every model you still own access control, encryption choices, backup retention and your application's vulnerabilities.
- Assuming every region looks the same. Services, instance types, availability zones and prices differ by region; design against the region you will deploy to.

## Check yourself

1. A colleague proposes running PostgreSQL on a single EC2 instance in one availability zone "because the app tier is multi-AZ". What fails, and what would you run instead on each cloud?
2. For a managed PostgreSQL (RDS or Flexible Server), list three security responsibilities that remain yours under the shared responsibility model.
3. Your traffic is flat at night and triples between 09:00 and 17:00 on weekdays. Which pricing model covers the night-time baseline, which covers the daytime peak, and why would you not reserve the peak?
4. What is the difference between a system that is scalable and one that is elastic, and which property of your Spring Boot service most often prevents elasticity?

## Go deeper

- [AWS: Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) · the original diagram; read it once and you will recognise it in every security conversation.
- [Azure: Shared responsibility in the cloud](https://learn.microsoft.com/en-us/azure/security/fundamentals/shared-responsibility) · the same idea drawn per service model, which makes the IaaS/PaaS/SaaS shift visible.
- [AWS: Regions and Availability Zones](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/) · what an AZ actually is and how far apart they are.
- [AWS Pricing](https://aws.amazon.com/pricing/) and [Azure Pricing](https://azure.microsoft.com/en-us/pricing/) · the entry points for every pricing model above; the numbers change, the models do not.

---

Part of [Cloud](../README.md) · items 1.1, 1.2
