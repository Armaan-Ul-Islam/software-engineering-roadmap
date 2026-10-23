# Compute options compared: VMs, containers, PaaS and functions for a Spring Boot service

> **In one sentence:** Every compute option runs the same jar, so choose by how your traffic behaves, how much operations work your team can absorb, and how much latency you can tolerate at start-up, and for most Spring Boot APIs that points at a serverless container platform rather than at raw VMs, Kubernetes or functions.

**Why it matters:** The compute decision fixes your cost model, your deployment story and your failure modes for years. Teams pick Kubernetes because it is impressive and spend a year running it; others pick Lambda for a request-heavy API and discover JVM cold starts and connection limits in production. Interviewers ask "why this platform?" and want a trade-off, not a brand name.

## The idea

### Virtual machines

AWS EC2 and Azure Virtual Machines give you a Linux box. Instance families encode the hardware trade-off: general purpose (AWS `m`, Azure `D`), compute optimised (`c`, `F`), memory optimised (`r`, `E`), and **burstable** (`t`, `B`) which earn CPU credits while idle and spend them under load; run a burstable VM at sustained load and it throttles. A "vCPU" is usually one hardware thread, so a 4 vCPU x86 instance has 2 physical cores (Graviton vCPUs are whole cores). Sizes within a family double vCPU and memory together, which is why right-sizing often means changing family, not size (see item 5.2).

You patch the OS, install the JDK, run the process, ship logs, and replace broken instances. **Auto Scaling groups** (AWS) and **Virtual Machine Scale Sets** (Azure) automate the last two from a launch template and spread instances across zones. VMs make sense when you need the kernel, specific hardware, or software that assumes a long-lived host.

### Container platforms

| Platform | What it is | You still manage | Scales to zero? |
|---|---|---|---|
| ECS on Fargate (AWS) | Amazon's own orchestrator with serverless capacity; you declare a task (vCPU, memory, image) and a service (count, load balancer) | Task definitions, IAM roles, networking | No (minimum one task per service) |
| EKS (AWS), AKS (Azure) | Managed Kubernetes control plane; you run node groups or use serverless nodes | Cluster upgrades, node pools, add-ons, manifests, ingress, the whole ecosystem | Not by default |
| Azure Container Apps | Serverless containers on a managed Kubernetes/KEDA/Envoy foundation; revisions, traffic splitting, HTTP ingress, scale rules built in | A container spec and scale rules | Yes |
| AWS App Runner | Source or image in, HTTPS URL out; autoscaling and TLS handled | Almost nothing | Pauses, but you pay for provisioned memory while idle |

The honest Kubernetes question: do you have many services, a platform team, and a need for the ecosystem (operators, service mesh, custom schedulers)? If you have three Spring services and no platform team, Kubernetes is a second full-time job. Fargate and Container Apps give you the container workflow without the cluster.

### PaaS for Java

**Elastic Beanstalk** orchestrates EC2, a load balancer, an Auto Scaling group and monitoring from a jar or a Dockerfile; you still pay for and can see the underlying instances. **Azure App Service** runs Java SE, Tomcat or JBoss on a shared plan with deployment slots for blue/green swaps and built-in autoscale. Both hide the OS and the deployment mechanics, and both hide the knobs when you need them (kernel settings, sidecars, exotic networking). **Azure Spring Apps is retiring**, so for Spring on Azure the realistic PaaS-like targets are Container Apps and App Service.

### Serverless functions

**AWS Lambda** and **Azure Functions** run a handler per event: an HTTP request, a queue message, a file upload, a schedule. You pay per invocation and per unit of memory-time, and pay nothing when idle. Lambda allocates CPU in proportion to memory (at about 1,769 MB a function has one vCPU), runs for at most 15 minutes, and has a hard size limit per deployment. Azure Functions offers a Consumption plan (cheapest, cold starts, default timeout five minutes), Flex Consumption and Premium plans with pre-warmed instances, and a Dedicated plan on App Service.

The JVM problem: a **cold start** is the time to create the execution environment, start the runtime and run your initialisation code, and a Spring Boot application's initialisation is seconds, not milliseconds. The levers, from cheapest to most invasive:

1. Keep the function small: one handler, few dependencies, no component scanning of a whole application.
2. Favour quick start over peak performance with `JAVA_TOOL_OPTIONS=-XX:TieredStopAtLevel=1`, which stops the JIT at the C1 compiler.
3. **Lambda SnapStart** (Java 11 and later): Lambda initialises the function when you publish a version, snapshots the whole environment, and restores from the snapshot instead of initialising again. No extra charge for the Java runtimes; it requires a published version, and anything unique generated at initialisation (random seeds, connection state) must be regenerated after restore.
4. Provisioned concurrency (Lambda) or a Premium plan (Functions): pre-initialised instances, paid for whether used or not, which quietly turns per-request pricing back into always-on pricing.
5. Native images (GraalVM) or frameworks built for ahead-of-time compilation.

Functions shine for event-driven, bursty, low-volume work: the nightly export, the thumbnail generator, the webhook receiver. For a chatty API with steady traffic they rarely win on cost or latency.

## Example: the decision table, then the recommendation

| Signal | Favours VMs | Favours a container platform | Favours PaaS | Favours functions |
|---|---|---|---|---|
| Traffic pattern | Steady, predictable | Daily cycle with a baseline | Steady, modest | Bursty, idle most of the time |
| Team | Has sysadmin skills, needs the kernel | Ships images already, no platform team (Fargate, Container Apps) or has one (EKS, AKS) | Wants to upload a jar and stop | Event-driven mindset, small handlers |
| Latency requirement | Any | Tight p99 is fine: processes stay warm | Tight p99 is fine | Relaxed, or you have engineered cold starts away |
| Operational budget | High: patching, hardening, fleet management | Medium (ECS, Container Apps) to high (Kubernetes) | Low | Low per function, but grows with the number of functions |
| Cost shape | Per hour, always on | Per vCPU-second and GB-second while tasks run | Per plan hour | Per request and GB-second |

**For a typical Spring Boot API** (an HTTP service with a database, tens to a few thousand requests per second, a team of two to eight developers and no platform team): run it as a container on **ECS on Fargate** (AWS) or **Azure Container Apps** (Azure), at least two replicas spread across availability zones, behind an Application Load Balancer or the platform's built-in ingress, with a managed PostgreSQL (see item 6.2). You keep a warm JVM, a connection pool and the whole Spring ecosystem; the platform keeps the hosts, the scheduler and the rollout mechanics. Move to Kubernetes when the number of services and the platform team justify it; move pieces to functions when they are genuinely event-driven; drop to VMs only for a concrete technical reason you can name.

## Pitfalls

- Load testing on a burstable instance. It performs beautifully for twenty minutes, then the credits run out and your "capacity estimate" is fiction.
- Choosing Kubernetes for three services. You now operate upgrades, node pools, ingress controllers and certificates before you have operated your application.
- A Spring Boot monolith on Lambda with the default settings. Multi-second cold starts on every scale-out, plus one database connection per concurrent execution (see item 5.4).
- Sizing Fargate tasks or Container Apps replicas at the smallest CPU allocation to save money. Below two CPUs the JVM defaults to the serial garbage collector and compiles slowly; measure before shrinking (see item 4.5).
- Treating App Runner or App Service as "free when idle". App Runner bills provisioned memory for paused services and App Service bills the plan around the clock.
- Picking a platform the team cannot debug. If nobody can read a task definition or a revision's logs at 03:00, the saved money is borrowed, not earned.

## Check yourself

1. A team of four runs one Spring Boot API with a steady 200 requests per second. Rank Fargate, EKS and Lambda for them on operational burden and on cost shape, and explain the ranking.
2. Why does enabling provisioned concurrency change the economics of a Lambda-based API, and what always-on alternative does it start to resemble?
3. What does SnapStart snapshot, when, and which two categories of initialisation code must you revisit before enabling it?
4. A nightly job runs for forty minutes and uses 6 GB of memory. Which options are ruled out by the limits above, and which would you pick?

## Go deeper

- [Azure: Choose an Azure compute service](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/compute-decision-tree) · the decision tree Microsoft's architects use; it asks the same questions as the table above.
- [AWS: Choosing an AWS compute service](https://docs.aws.amazon.com/decision-guides/latest/compute-on-aws-how-to-choose/choosing-aws-compute-service.html) · the AWS counterpart, with the full list of options.
- [AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) and [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/overview) · the two recommended targets, in their own words.
- [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html) · supported runtimes, the uniqueness and network caveats, and pricing.
- [Azure Spring Apps retirement announcement](https://learn.microsoft.com/en-us/azure/spring-apps/basic-standard/retirement-announcement) · dates and the recommended migration targets.

---

Part of [Cloud](../README.md) · items 4.1, 4.2, 4.3, 4.4, 4.6
