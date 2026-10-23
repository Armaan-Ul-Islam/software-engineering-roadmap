# The AWS to Azure service map for backend developers

> **In one sentence:** Almost every AWS service a backend developer meets has an Azure counterpart with a different name and slightly different limits, so learn the categories once, keep a translation table, and read the official comparison pages for vocabulary before reading each service's own documentation for the facts.

**Why it matters:** Teams run on both clouds, job descriptions name one and the project uses the other, and interviewers switch providers mid-question. A developer who knows that a managed identity is an IAM role, that Container Apps is the Fargate-shaped option, and that Event Grid is not Service Bus can design and debug on either side in a week. Without the map, every service is learned twice from scratch.

## The idea

The categories are stable; the names are not. Within a category the services are **roughly** equivalent: the same job, usually a different pricing model, different limits, and sometimes a different concept hiding under the name (Azure's resource groups and management groups, AWS's accounts as the isolation boundary). The table below is the working set for a backend developer, with the one difference most likely to matter.

| Category | AWS | Azure | Notable difference |
|---|---|---|---|
| Virtual machines | EC2 | Virtual Machines | Same idea; size names differ (`m7g.large` versus `Standard_D2s_v5`), burstable families are `t` and `B` |
| Serverless containers | ECS on Fargate | Azure Container Apps | Container Apps scales to zero and has built-in HTTP ingress and KEDA scalers; Fargate needs a load balancer and a minimum of one task |
| Managed Kubernetes | EKS | AKS | EKS charges per cluster-hour for the control plane; AKS has a free tier for the control plane and paid tiers with an uptime SLA |
| Container registry | ECR | Azure Container Registry | ACR has geo-replication and tasks; both support scan-on-push |
| Functions | Lambda | Azure Functions | Lambda has SnapStart for Java cold starts; Functions has plan tiers (Consumption, Flex Consumption, Premium) that trade cold starts for fixed cost |
| PaaS for Java | Elastic Beanstalk | App Service | App Service has deployment slots for swaps; Beanstalk exposes the underlying EC2 instances |
| Relational database | RDS, Aurora | Azure Database for PostgreSQL Flexible Server, Azure SQL | Aurora has a shared storage layer and up to 15 low-lag replicas; Flexible Server ships PgBouncer built in |
| NoSQL | DynamoDB | Cosmos DB | DynamoDB is one data model with capacity units; Cosmos DB offers several APIs priced in request units |
| Cache | ElastiCache | Azure Cache for Redis, Azure Managed Redis | Both managed Redis; check tier features (clustering, persistence, zones) rather than names |
| Object storage | S3 | Blob Storage | Both strongly consistent; S3 has more storage classes, Azure has Hot, Cool, Cold and Archive tiers |
| Block storage | EBS | Managed Disks | Both zonal by default; Azure offers zone-redundant disk SKUs |
| File storage | EFS, FSx | Azure Files, Azure NetApp Files | EFS is NFS and elastic; Azure Files offers SMB and NFS with provisioned premium tiers |
| Queues | SQS | Service Bus queues, Storage Queues | Service Bus has sessions, transactions and scheduled messages; SQS has a simpler model and higher default scale |
| Pub/sub topics | SNS | Service Bus topics, Event Grid | SNS pushes to subscribers; Service Bus subscriptions are pulled like queues |
| Event bus | EventBridge | Event Grid | Both route by content with at-least-once delivery; EventBridge adds a schema registry and archive/replay |
| Streams | Kinesis Data Streams, MSK | Event Hubs | Event Hubs exposes a Kafka-compatible endpoint; MSK is actual Kafka |
| Secrets | Secrets Manager, Systems Manager Parameter Store | Key Vault (secrets), App Configuration | Key Vault holds secrets, keys and certificates in one service; AWS splits them across Secrets Manager, KMS and ACM |
| Identity and access | IAM (users, roles, policies) | Microsoft Entra ID plus Azure RBAC (principals, role assignments, scopes) | AWS writes JSON policies; Azure assigns built-in or custom roles at a scope, additively (see item 2.1) |
| Workload identity | IAM roles for EC2, ECS, Lambda, EKS | Managed identities | Same purpose; the SDK credential chains find both automatically |
| Monitoring | CloudWatch (metrics, logs, alarms), X-Ray | Azure Monitor, Log Analytics, Application Insights | Both bill mainly on log ingestion; OpenTelemetry works with both |
| DNS | Route 53 | Azure DNS, Traffic Manager | Route 53 includes routing policies and health checks; Azure splits DNS-based routing into Traffic Manager |
| CDN and edge | CloudFront | Azure Front Door, Azure CDN | Front Door combines global load balancing, CDN and WAF in one service |
| Load balancing | ALB (layer 7), NLB (layer 4) | Application Gateway (layer 7), Azure Load Balancer (layer 4) | Application Gateway includes an optional WAF; AWS WAF attaches to an ALB separately |
| Virtual network | VPC, subnets, security groups, network ACLs | Virtual Network, subnets, network security groups | Azure has no stateless network ACL and no internet gateway object (see item 3.1) |
| Infrastructure as code | CloudFormation, CDK | ARM templates, Bicep | Bicep has no state file; CloudFormation stacks hold the state (see item 8.3) |
| Organisation and billing | Organizations, accounts, cost allocation tags, Budgets, Cost Explorer | Management groups, subscriptions, resource groups, tags, Cost Management, Budgets | The AWS isolation unit is the account; Azure's is the subscription, with resource groups below it |

## Example: translating a design

An AWS design reads: "ECS on Fargate tasks in private subnets behind an ALB, RDS PostgreSQL Multi-AZ, ElastiCache, S3 for uploads, SQS for order events with a dead-letter queue, Secrets Manager, CloudWatch, Route 53, deployed by Terraform with a GitHub Actions OIDC role."

Row by row, the Azure version is: "Container Apps replicas in a VNet-integrated environment with built-in ingress (or Application Gateway in front for WAF), Azure Database for PostgreSQL Flexible Server with zone-redundant HA, Azure Cache for Redis, Blob Storage for uploads, Service Bus queue for order events with its dead-letter sub-queue, Key Vault, Azure Monitor with Log Analytics, Azure DNS, deployed by Terraform or Bicep with a federated identity credential for GitHub Actions."

Three rows need a second look rather than a straight swap. The *ingress* row: Container Apps includes HTTP ingress, so the ALB may have no counterpart until you need a WAF. The *queue* row: Service Bus adds sessions and duplicate detection, so a design that implemented ordering or deduplication in application code on SQS can simplify. The *identity* row: the IAM policy JSON becomes a role assignment of `Storage Blob Data Contributor` at container scope to the app's managed identity (see item 2.1).

### How to use the official comparison pages

Microsoft publishes [AWS to Azure services comparison](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/services) and Google publishes [Compare AWS and Azure services to Google Cloud](https://cloud.google.com/docs/get-started/aws-azure-gcp-service-comparison), both organised by category. Use them in three steps:

1. **Translate the vocabulary.** Find the row, note both names, and read the one-line description to check it is the same job and not a neighbour (Event Grid versus Service Bus is the classic trap).
2. **Then read the service's own documentation for limits and pricing.** The comparison pages say "equivalent"; they do not say that the connection limit, message size, or retention differs. Those details decide the design.
3. **Check the date and the retirements.** Services are renamed and retired (Azure Spring Apps, Azure Cache for Redis tiers, AWS services in maintenance mode); a comparison page lags by months. Confirm the target still exists and is still recommended.

## Pitfalls

- Assuming "equivalent" means "same limits". Message size, connection counts, retention and throughput caps differ and are the things that break a design.
- Mapping Event Grid to SQS or SNS to Service Bus topics without checking push versus pull. Push-based delivery needs an endpoint that is always up; pull-based needs a consumer loop.
- Translating the account model literally. One AWS account per environment becomes one Azure subscription, or resource groups within one subscription, depending on isolation needs.
- Carrying a Kubernetes reflex across. The Fargate-shaped option on Azure is Container Apps, not AKS; and the AKS-shaped option on AWS is EKS, with a per-cluster fee.

## Check yourself

1. A design uses SNS fanning out to three SQS queues. Give two valid Azure translations and explain when you would choose each.
2. What does Azure's split between Entra ID and Azure RBAC correspond to on AWS, and which AWS construct has no direct Azure equivalent in that area?
3. Translate "Lambda with SnapStart behind API Gateway, reading from DynamoDB" to Azure, and point out the two places where the equivalence is weakest.
4. Why should the official comparison page be the first thing you read about a service and never the last?

## Go deeper

- [Azure: AWS to Azure services comparison](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/services) · Microsoft's category-by-category table, maintained with the Azure Architecture Center.
- [Google Cloud: Compare AWS and Azure services to Google Cloud](https://cloud.google.com/docs/get-started/aws-azure-gcp-service-comparison) · the three-column version; useful even if you never touch GCP because it forces precise category names.
- [Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/) · the "for AWS professionals" section sits here alongside the reference architectures.
- [AWS Documentation](https://docs.aws.amazon.com/) and [Microsoft Learn: Azure documentation](https://learn.microsoft.com/en-us/azure/) · step two of the method: the primary sources for limits and pricing.

---

Part of [Cloud](../README.md) · item 1.4
