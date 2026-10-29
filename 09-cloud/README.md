# Cloud

> Cloud fundamentals for backend developers who ship to AWS and Azure: service models, identity, networking, compute options, managed databases and messaging, observability, infrastructure as code, and above all how to estimate what your Spring service needs and what it will cost.

**Prerequisites:** [Web & HTTP](../02-web-and-http/README.md), [Databases](../04-databases/README.md), [DevOps & Delivery](../10-devops-and-delivery/README.md)

**Done when you can:**

- Explain the shared responsibility model, regions and availability zones, and the IaaS/PaaS/FaaS trade-offs with concrete AWS and Azure services.
- Design a VPC/VNet layout with public and private subnets, and justify every rule in a security group.
- Measure a Spring Boot service under load, turn the numbers into a vCPU, memory and instance-count estimate with headroom, and price it on both clouds.
- Pick the right compute for a service (VM, container platform, serverless, PaaS) and defend it with cost and operational burden.
- Run a managed PostgreSQL with high availability, tested backups and a correctly sized connection pool.
- Read a cloud bill and name the three things most likely to be wasting money.

## Roadmap

### 1. Core concepts

- [ ] 1.1 Service models (IaaS, PaaS, SaaS, FaaS), the shared responsibility model, regions, availability zones and edge locations · [notes](notes/cloud-core-concepts.md) · [AWS: Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) · [Azure: Shared responsibility in the cloud](https://learn.microsoft.com/en-us/azure/security/fundamentals/shared-responsibility) · [AWS: Regions and Availability Zones](https://aws.amazon.com/about-aws/global-infrastructure/regions_az/)
- [ ] 1.2 Elasticity vs scalability; pricing models: on-demand, reserved and savings plans, spot; free tiers · [notes](notes/cloud-core-concepts.md) · [AWS Pricing](https://aws.amazon.com/pricing/) · [Azure Pricing](https://azure.microsoft.com/en-us/pricing/)
- [ ] 1.3 Accounts and subscriptions, resource groups, tags, organisations and landing zones; separating environments · [notes](notes/accounts-subscriptions-and-landing-zones.md) · [AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html) · [Azure: Landing zones](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/)
- [ ] 1.4 The service map: AWS to Azure (and GCP) equivalents · [notes](notes/aws-vs-azure-service-map.md) · [Azure: AWS to Azure services comparison](https://learn.microsoft.com/en-us/azure/architecture/aws-professional/services) · [Google Cloud: Compare AWS and Azure services to Google Cloud](https://cloud.google.com/docs/get-started/aws-azure-gcp-service-comparison)
- [ ] 1.5 Well-Architected frameworks: the pillars as a review checklist · [notes](notes/well-architected-review-in-practice.md) · [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) · [Azure Well-Architected Framework](https://learn.microsoft.com/en-us/azure/well-architected/)

### 2. Identity and access

- [ ] 2.1 IAM concepts: principals, policies, roles and groups; least privilege; deny by default; how policies are evaluated · [notes](notes/iam-and-workload-identity.md) · [AWS IAM: How IAM works](https://docs.aws.amazon.com/IAM/latest/UserGuide/intro-structure.html) · [Azure RBAC overview](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview)
- [ ] 2.2 Workload identity instead of secrets: IAM roles for compute, managed identities, OIDC federation for CI pipelines · [notes](notes/iam-and-workload-identity.md) · [Azure: Managed identities](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview) · [GitHub Actions: Configuring OpenID Connect in AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [ ] 2.3 Secrets and keys: Secrets Manager and Parameter Store, Key Vault, KMS; rotation; envelope encryption · [notes](notes/secrets-and-key-management-in-the-cloud.md) · [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) · [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [ ] 2.4 Human access: single sign-on, MFA, break-glass accounts, audit logs (CloudTrail, Azure Activity Log) · [notes](notes/accounts-subscriptions-and-landing-zones.md) · [AWS CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html)

### 3. Networking

- [ ] 3.1 VPC/VNet, public and private subnets, route tables, internet and NAT gateways; why NAT gateways show up on the bill · [notes](notes/vpc-networking-basics.md) · [AWS: How Amazon VPC works](https://docs.aws.amazon.com/vpc/latest/userguide/how-it-works.html) · [Azure: Virtual Network overview](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-overview)
- [ ] 3.2 Security groups and network security groups vs network ACLs; stateful vs stateless filtering · [notes](notes/vpc-networking-basics.md) · [AWS: Security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html) · [Azure: Network security groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview)
- [ ] 3.3 Load balancers: ALB/NLB vs Azure Load Balancer, Application Gateway and Front Door; TLS termination; health checks · [notes](notes/vpc-networking-basics.md) · [AWS Elastic Load Balancing](https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/what-is-load-balancing.html) · [Azure: Load-balancing options](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/load-balancing-overview)
- [ ] 3.4 Private connectivity: PrivateLink and private endpoints, peering, VPN, Direct Connect and ExpressRoute · [notes](notes/private-connectivity-and-the-edge.md) · [AWS PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/what-is-privatelink.html) · [Azure Private Link](https://learn.microsoft.com/en-us/azure/private-link/private-link-overview)
- [ ] 3.5 DNS, CDN and edge protection: Route 53 and Azure DNS, CloudFront and Front Door, WAF, DDoS protection · [notes](notes/private-connectivity-and-the-edge.md) · [Amazon CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html) · [Azure Front Door](https://learn.microsoft.com/en-us/azure/frontdoor/front-door-overview)
- [ ] 3.6 Data transfer (egress) costs and how architectures accidentally multiply them · [notes](notes/pricing-a-design-and-cost-traps.md) · [AWS: Overview of Data Transfer Costs for Common Architectures](https://aws.amazon.com/blogs/architecture/overview-of-data-transfer-costs-for-common-architectures/) · [Azure: Bandwidth pricing](https://azure.microsoft.com/en-us/pricing/details/bandwidth/)

### 4. Compute

- [ ] 4.1 Virtual machines: instance families and sizes, vCPU vs physical cores, burstable instances, autoscaling groups and scale sets · [notes](notes/compute-options-compared.md) · [Amazon EC2 instance types](https://aws.amazon.com/ec2/instance-types/) · [Azure VM sizes](https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/overview)
- [ ] 4.2 Containers: ECS on Fargate, EKS, AKS, Azure Container Apps, App Runner; when you need Kubernetes and when you do not · [notes](notes/compute-options-compared.md) · [Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/overview) · [AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [ ] 4.3 PaaS for Java: Elastic Beanstalk and Azure App Service; what they manage and what they hide (Azure Spring Apps is retiring) · [notes](notes/compute-options-compared.md) · [Azure App Service: Java apps](https://learn.microsoft.com/en-us/azure/app-service/configure-language-java-deploy-run) · [Azure Spring Apps retirement announcement](https://learn.microsoft.com/en-us/azure/spring-apps/basic-standard/retirement-announcement)
- [ ] 4.4 Serverless functions: Lambda and Azure Functions; cold starts and the JVM, SnapStart, limits, event sources, the cost model · [notes](notes/compute-options-compared.md) · [AWS Lambda: Execution environment](https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html) · [AWS Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html) · [Azure Functions overview](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview)
- [ ] 4.5 The JVM on a VM or in a container: memory limits vs heap, `MaxRAMPercentage`, CPU quotas and GC threads, startup time · [notes](notes/deploying-spring-boot-to-the-cloud.md) · [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview) · [Spring Boot: Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html)
- [ ] 4.6 Choosing compute: a decision table by traffic pattern, team size, latency needs and budget · [notes](notes/compute-options-compared.md) · [Azure: Choose an Azure compute service](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/compute-decision-tree) · [AWS: Choosing an AWS compute service](https://docs.aws.amazon.com/decision-guides/latest/compute-on-aws-how-to-choose/choosing-aws-compute-service.html)

### 5. Sizing, estimation and cost

- [ ] 5.1 Measure before guessing: load test a Spring Boot service (k6, Gatling, JMeter) for throughput, p99 latency, CPU and memory · [notes](notes/sizing-a-spring-boot-service.md) · [Grafana k6](https://grafana.com/docs/k6/latest/) · [Gatling](https://docs.gatling.io/)
- [ ] 5.2 From measurements to a size: Little's law, utilisation targets (CPU under roughly 60-70% at peak), headroom, N+1 instances across zones · [notes](notes/sizing-a-spring-boot-service.md) · [Little's law](https://en.wikipedia.org/wiki/Little%27s_law)
- [ ] 5.3 Memory sizing for the JVM: heap, Metaspace, thread stacks, off-heap, container overhead; reading the real RSS · [notes](notes/sizing-a-spring-boot-service.md) · [Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html) · [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview)
- [ ] 5.4 Sizing the data tier: pool size × instances vs database connection limits; IOPS and storage; Redis memory · [notes](notes/autoscaling-and-the-database-bottleneck.md) · [HikariCP: About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing) · [Azure Database for PostgreSQL: Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits)
- [ ] 5.5 Autoscaling: metric-based (CPU, requests, queue depth), scheduled, cool-downs; why scaling the app without the database fails · [notes](notes/autoscaling-and-the-database-bottleneck.md) · [AWS: Target tracking scaling policies](https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html) · [Kubernetes: Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [ ] 5.6 Pricing a design: calculators, on-demand vs reserved vs spot, egress, managed-service premiums, always-on vs per-request break-even · [notes](notes/pricing-a-design-and-cost-traps.md) · [AWS Pricing Calculator](https://calculator.aws/) · [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/)
- [ ] 5.7 Cost management: budgets and alerts, tagging, right-sizing, idle resources, FinOps basics · [notes](notes/pricing-a-design-and-cost-traps.md) · [FinOps Foundation: Framework](https://www.finops.org/framework/) · [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) · [Azure Cost Management](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/overview-cost-management)

### 6. Storage and databases

- [ ] 6.1 Object, block and file storage: S3 and Blob Storage, EBS and Managed Disks, EFS and Azure Files; storage classes, lifecycle rules, versioning · [notes](notes/storage-options.md) · [Amazon S3 storage classes](https://aws.amazon.com/s3/storage-classes/) · [Azure Blob Storage: Access tiers](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview)
- [ ] 6.2 Managed relational databases: RDS and Aurora, Azure Database for PostgreSQL Flexible Server; HA, backups and point-in-time recovery, read replicas, maintenance windows, parameters · [notes](notes/managed-postgresql-in-the-cloud.md) · [Amazon RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html) · [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview)
- [ ] 6.3 Managed NoSQL and caches: DynamoDB vs Cosmos DB, ElastiCache vs Azure Cache for Redis; their pricing models · [notes](notes/managed-nosql-and-caches.md) · [DynamoDB: Core components](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html) · [Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/introduction)
- [ ] 6.4 Connecting from Spring: TLS to the database, IAM or Entra authentication, secrets from vaults, connection limits on PaaS tiers · [notes](notes/managed-postgresql-in-the-cloud.md) · [Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/) · [Spring Cloud AWS](https://awspring.io/)

### 7. Messaging and integration

- [ ] 7.1 Queues and topics: SQS, SNS and EventBridge vs Service Bus and Event Grid; visibility timeouts, dead-letter queues, FIFO · [notes](notes/queues-and-topics-in-the-cloud.md) · [Amazon SQS](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html) · [Azure Service Bus](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-messaging-overview)
- [ ] 7.2 Streams: Kinesis and MSK vs Event Hubs; managed Kafka options · [Amazon MSK](https://docs.aws.amazon.com/msk/latest/developerguide/what-is-msk.html) · [Azure Event Hubs](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-about)
- [ ] 7.3 Cloud design patterns: queue-based load levelling, competing consumers, retry, circuit breaker, cache-aside · [notes](notes/queues-and-topics-in-the-cloud.md) · [Azure Architecture Center: Cloud Design Patterns](https://learn.microsoft.com/en-us/azure/architecture/patterns/)

### 8. Observability, infrastructure as code and operations

- [ ] 8.1 Logs, metrics and traces: CloudWatch vs Azure Monitor and Application Insights; OpenTelemetry as the vendor-neutral path · [notes](notes/cloud-observability-cloudwatch-azure-monitor-and-otel.md) · [Amazon CloudWatch](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html) · [Azure Monitor: Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview) · [OpenTelemetry](https://opentelemetry.io/docs/)
- [ ] 8.2 Alerting on symptoms, dashboards, and the cost of log retention · [notes](notes/cloud-observability-cloudwatch-azure-monitor-and-otel.md) · [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [ ] 8.3 Infrastructure as code: Terraform or OpenTofu, Bicep, CDK and CloudFormation; state, drift, modules, environments · [notes](notes/infrastructure-as-code-basics.md) · [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials) · [Bicep overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview) · [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html)
- [ ] 8.4 Deploying Spring Boot end to end: image build, registry, platform configuration, health probes, secrets, logs, zero-downtime rollout · [notes](notes/deploying-spring-boot-to-the-cloud.md) · [Azure Container Apps: Java overview](https://learn.microsoft.com/en-us/azure/container-apps/java-overview) · [AWS App Runner](https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html)
- [ ] 8.5 Resilience in the cloud: multi-AZ by default, multi-region only when justified, tested backups, game days · [notes](notes/well-architected-review-in-practice.md) · [AWS: Disaster recovery options in the cloud](https://docs.aws.amazon.com/whitepapers/latest/disaster-recovery-workloads-on-aws/disaster-recovery-options-in-the-cloud.html) · [Azure Well-Architected: Reliability](https://learn.microsoft.com/en-us/azure/well-architected/reliability/)

### 9. Security and compliance in the cloud

- [ ] 9.1 Encryption at rest and in transit by default; KMS and Key Vault; certificate management · [notes](notes/secrets-and-key-management-in-the-cloud.md) · [AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/overview.html) · [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview)
- [ ] 9.2 Exposure review: public buckets, public IPs, permissive security groups; posture tools (Security Hub, Defender for Cloud) · [notes](notes/cloud-security-posture-basics.md) · [AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html) · [Microsoft Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-cloud-introduction)
- [ ] 9.3 Data residency and GDPR considerations: regions, sub-processors, retention, deletion · [notes](notes/cloud-security-posture-basics.md) · [Azure: Data residency](https://azure.microsoft.com/en-us/explore/global-infrastructure/data-residency/)

### 10. Learning paths and certifications as scaffolding

- [ ] 10.1 Azure Fundamentals (AZ-900), then Azure Developer Associate (AZ-204) · [Microsoft Learn: Azure Fundamentals](https://learn.microsoft.com/en-us/credentials/certifications/azure-fundamentals/) · [Microsoft Learn: Azure Developer Associate](https://learn.microsoft.com/en-us/credentials/certifications/azure-developer/)
- [ ] 10.2 AWS Cloud Practitioner, then Solutions Architect Associate or Developer Associate · [AWS Skill Builder](https://skillbuilder.aws/) · [AWS Certification](https://aws.amazon.com/certification/)
- [ ] 10.3 Hands-on: build and tear down the reference deployment from the Projects list on both clouds inside the free tier · [AWS Free Tier](https://aws.amazon.com/free/) · [Azure free account](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account)

## Resources

### Start here

- [Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/) · reference architectures, the cloud design patterns catalogue, and technology choice guides. Useful even if you deploy to AWS.
- [AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/welcome.html) · the pillars and the questions to ask of any design.
- [AWS Builders' Library](https://aws.amazon.com/builders-library/) · how Amazon runs large systems; the articles on timeouts, retries, load shedding and deployments are essential.
- [Microsoft Learn: Azure Fundamentals learning path](https://learn.microsoft.com/en-us/training/paths/microsoft-azure-fundamentals-describe-cloud-concepts/) · free, structured, and a good first pass over every service category.
- [AWS Skill Builder](https://skillbuilder.aws/) · free digital courses including Cloud Practitioner Essentials.

### Books

- [The Good Parts of AWS](https://dvassallo.gumroad.com/l/aws-good-parts) · Daniel Vassallo and Josh Pschorr; a short, opinionated guide to the services worth defaulting to (paid).
- [Terraform: Up and Running](https://www.terraformupandrunning.com/) · Yevgeniy Brikman (paid).
- [Learning Microsoft Azure](https://www.oreilly.com/library/view/learning-microsoft-azure/9781098113315/) · Jonah Carrio Andersson (paid).

### Courses and videos

- [John Savill's Technical Training](https://www.youtube.com/@NTFAQGuy) · the best free Azure explanations, including full AZ-900 and AZ-104 study cram videos.
- [Adrian Cantrill](https://learn.cantrill.io/) · deep, hands-on AWS certification courses (paid).
- [Stéphane Maarek](https://www.udemy.com/user/stephane-maarek/) · popular AWS certification courses on Udemy (paid).
- [ExamPro](https://www.youtube.com/@ExamProChannel) · free full-length certification courses, also published on freeCodeCamp.
- [Azure Friday](https://learn.microsoft.com/en-us/shows/azure-friday/) · short weekly videos with the Azure engineering teams.

### References

- [AWS Documentation](https://docs.aws.amazon.com/) and [Microsoft Learn: Azure documentation](https://learn.microsoft.com/en-us/azure/) · the primary sources.
- [AWS Pricing Calculator](https://calculator.aws/) and [Azure Pricing Calculator](https://azure.microsoft.com/en-us/pricing/calculator/) · price every design before you build it.
- [instances.vantage.sh](https://instances.vantage.sh/) · compare EC2 (and RDS) instance types and prices in one table.
- [Last Week in AWS](https://www.lastweekinaws.com/) · Corey Quinn's newsletter; irreverent and sharp on AWS costs.
- [roadmap.sh: AWS](https://roadmap.sh/aws) and [roadmap.sh: Terraform](https://roadmap.sh/terraform) · visual overviews.
