# Project spec: deploy the same service to Azure and AWS, then price both

> **In one sentence:** Take one containerised Spring Boot service with PostgreSQL, deploy it to Azure Container Apps and to AWS ECS on Fargate with Terraform, measure it, price it at two traffic levels, and tear everything down.

**Why it matters:** Reading about cloud services does not teach you what a VPC rule, a managed identity or an egress charge feels like. Deploying the same thing twice does, and it leaves you with the one artefact interviewers and managers actually want from a "cloud-literate" backend developer: a defensible cost and sizing estimate with the measurements behind it.

## The idea

You will reuse a service you already built (the URL shortener or the order service) and deploy it to both clouds with infrastructure as code. The comparison is the deliverable: a table of what each cloud needed, what it cost, and what surprised you.

Scope:

- 1.1 One container image, pushed to each cloud's registry (Azure Container Registry, Amazon ECR).
- 1.2 Managed PostgreSQL on each side (Azure Database for PostgreSQL Flexible Server, Amazon RDS for PostgreSQL), reachable only from the application's private network, with TLS.
- 1.3 The application on Azure Container Apps and on ECS Fargate behind an Application Load Balancer, with health probes mapped to Spring Boot Actuator.
- 1.4 Secrets from Key Vault and Secrets Manager, read through a managed identity or an IAM task role; no credentials in environment variables committed to the repo.
- 1.5 Logs and metrics in Azure Monitor and CloudWatch; one dashboard each showing request rate, p99 latency and CPU.
- 1.6 Everything defined in Terraform, with one `apply` and one `destroy` per cloud.

Concepts exercised: Cloud 2.2, 3.1, 3.2, 4.2, 4.5, 5.1 to 5.6, 6.2, 8.3, 8.4; DevOps & Delivery 3.3, 3.4; Spring 2.6, 8.3.

## Example: the measurement and pricing method

Milestones, each with a concrete output:

1. **Local baseline.** Run the service in Docker with a 1 GiB memory limit and 1 CPU. Load test with k6 at increasing arrival rates until p99 latency exceeds your target (say 200 ms). Record: sustained requests per second, p99, CPU, RSS. This is the number everything else is derived from.
2. **Sizing.** Apply Little's law: concurrency = arrival rate × average latency. Pick a utilisation target (CPU under 70% at peak), add headroom, and derive vCPU and memory per instance and the instance count for two traffic levels, for example 50 and 500 requests per second at peak, with N+1 instances across two zones. Write the arithmetic down before touching a console.
3. **Azure deployment.** Terraform: resource group, virtual network with a delegated subnet, PostgreSQL Flexible Server with private access, Key Vault, Container Apps environment and app with a system-assigned managed identity, probes, scaling rules. Verify: the app reaches the database over TLS, `/actuator/health/readiness` is green, logs appear in Log Analytics.
4. **AWS deployment.** Terraform: VPC with public and private subnets, NAT gateway, security groups, RDS in private subnets, Secrets Manager, ECR, ECS cluster and Fargate service with a task role, Application Load Balancer with a target group health check on the Actuator endpoint, CloudWatch log group. Same verification.
5. **Measure in the cloud.** Repeat the k6 test against each deployment at the two traffic levels. Record the same four numbers plus cold-start time after a scale-to-zero (Azure) or a new task (AWS). Compare with the local baseline and explain any gap (network hop, smaller vCPU share, database latency).
6. **Price it.** Fill the table below from the official calculators for your region, at both traffic levels, for one month. Include every line, especially the ones people forget.

| Line item | Azure service | AWS service | 50 req/s | 500 req/s | Notes |
|---|---|---|---|---|---|
| Compute | Container Apps (vCPU-s, GiB-s) | Fargate (vCPU-h, GiB-h) | | | always-on vs per-request break-even |
| Load balancer | included in Container Apps ingress | ALB hours + LCU | | | ALB is billed even when idle |
| Database | Flexible Server tier + storage + backup | RDS instance + storage + backup | | | multi-AZ roughly doubles compute |
| NAT and egress | NAT gateway (if used) + bandwidth | NAT gateway hours + per-GB processing + egress | | | often the surprise line |
| Secrets and identity | Key Vault operations | Secrets Manager per secret + API calls | | | |
| Logs and metrics | Log Analytics ingestion + retention | CloudWatch ingestion + storage + custom metrics | | | retention drives cost |
| Registry | ACR tier | ECR storage | | | |
| Total | | | | | |

Definition of done:

- 2.1 `terraform apply` and `terraform destroy` succeed on both clouds from a clean state, and the README records the wall-clock time for each.
- 2.2 The README contains the baseline, the sizing arithmetic, the cloud measurements, and the filled cost table, plus a paragraph on what you would change for production (multi-AZ database, reserved capacity, WAF).
- 2.3 No secret appears in the repository, the Terraform state is stored remotely (Azure Storage or S3 with locking), and both environments are destroyed at the end, verified in the billing console a day later.

Stretch goals:

- 3.1 Add a Redis cache on each side (Azure Cache for Redis, ElastiCache) and measure the change in database load and cost.
- 3.2 Replace the NAT gateway with private endpoints on Azure and VPC endpoints on AWS; compare the cost lines.
- 3.3 Run the same service as a Lambda or Azure Function with SnapStart or an equivalent, measure cold starts, and find the request rate at which serverless becomes more expensive than the container.

## Pitfalls

- Sizing from the laptop's numbers alone. A cloud vCPU is often a hyper-thread, not a core; re-measure after deploying and adjust.
- Forgetting the JVM's non-heap memory. A 512 MiB container with a 400 MiB heap gets killed; set `-XX:MaxRAMPercentage` around 70 to 75 and measure RSS.
- Leaving the database publicly reachable "for testing". Private access from the start; use a bastion or cloud shell for one-off queries.
- Letting Terraform state live on your laptop. Remote state with locking from the first `apply`, or two people will corrupt it.
- Forgetting to destroy. Set a budget alert on day one and check the bill after the destroy; a stray NAT gateway or snapshot keeps charging.
- Comparing apples to oranges. Keep the image, the JVM flags, the load profile and the region class identical on both sides, or the comparison is noise.

## Check yourself

1. Which three cost lines are most likely to be missing from a first estimate, and why do architectures tend to multiply the NAT and egress line?
2. Your service needs 4 instances at 500 requests per second. How many database connections does that imply with a pool of 20, and what do you compare that number against?
3. Why does the ALB cost money while the Container Apps ingress does not appear as a separate line, and what does that tell you about comparing clouds line by line?
4. What is the always-on versus per-request break-even, and which measurement from milestone 5 do you need to compute it?

## Go deeper

- [Azure Container Apps: Java overview](https://learn.microsoft.com/en-us/azure/container-apps/java-overview) · the Azure target for this project.
- [AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) · the AWS target.
- [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview) · JVM memory settings in containers.
- [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials) · remote state, modules and the workflow.
- [AWS: Overview of Data Transfer Costs for Common Architectures](https://aws.amazon.com/blogs/architecture/overview-of-data-transfer-costs-for-common-architectures/) · the egress line explained.
- [Grafana k6](https://grafana.com/docs/k6/latest/) · the load tests for milestones 1 and 5.

---

Part of [Projects](../README.md) · item 4.5
