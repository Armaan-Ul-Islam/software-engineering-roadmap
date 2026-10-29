# Cloud security posture basics: exposure review, posture tools, data residency and deletion

> **In one sentence:** Posture is the set of configuration facts an attacker would find first (public buckets, public IPs, security groups open to the world, unencrypted stores, stale keys), the posture tools (AWS Security Hub, Microsoft Defender for Cloud) check those facts continuously against a benchmark, and data residency adds the questions of which region every copy of personal data lives in, who the sub-processors are, and how long each copy is retained before it is actually deleted.

**Why it matters:** The breaches that make the news are rarely clever: a bucket set to public for a demo, a database with a public IP and a weak password, a security group with port 22 open to `0.0.0.0/0`. The posture tools find these within hours of enabling them, which is why reviewers ask whether they are enabled. GDPR questions arrive from customers' procurement teams in the same breath: where is the data, who else processes it, and what happens when we ask you to delete it.

## The idea

### The exposure review

Run it on day one and then let the tools run it for you.

| Check | AWS | Azure | What right looks like |
|---|---|---|---|
| Public object storage | S3 Block Public Access at account level; bucket policies with `"Principal": "*"`; ACLs (disabled by default on new buckets) | Storage account `allowBlobPublicAccess`; container access level | Block public access everywhere; serve public content through a CDN with origin access, never from a public bucket |
| Public IPs on compute and databases | EC2 instances with public IPs in private tiers; RDS `PubliclyAccessible`; `AWS Config` rules | VMs with public IPs; Flexible Server with public network access; Defender recommendations | Only the load balancer or front door has a public address (see item 3.1) |
| Wide-open firewall rules | Security groups allowing `0.0.0.0/0` on anything but 443 on the balancer, especially 22, 3389, 5432, 6379 | NSG rules with source `Any` or `Internet` and action Allow on management or database ports | Group references and specific sources (see item 3.2); management access through SSM Session Manager or Azure Bastion, not open ports |
| Encryption at rest | Unencrypted EBS volumes, RDS instances and snapshots | Disks and databases without customer-managed keys where policy requires them | Encrypted by default; customer-managed keys where required (see item 9.1) |
| Stale and over-privileged identities | IAM users with access keys older than 90 days; `*` policies; unused roles (IAM Access Analyzer finds external access and unused permissions) | Service principals with secrets; `Owner` at subscription scope; guest users | Workload identity and SSO (see items 2.1 and 2.2) |
| Instance metadata | IMDSv1 enabled | Not applicable | IMDSv2 required, so a server-side request forgery cannot steal role credentials |
| Logging | CloudTrail off in some region; S3 access logging off on sensitive buckets | Activity log not exported; diagnostic settings missing | Organisation trail and diagnostic settings everywhere (see item 2.4) |

### The posture tools

**AWS Security Hub** enables security standards (AWS Foundational Security Best Practices, CIS AWS Foundations Benchmark, PCI DSS) and runs their controls as AWS Config rules, aggregating findings from GuardDuty (threat detection from logs), Inspector (vulnerabilities in instances, containers and Lambda functions) and IAM Access Analyzer into one place with a severity and a resource. Enable it in every region of every account through the organisation's delegated administrator account, or it only sees where it was turned on.

**Microsoft Defender for Cloud** gives every subscription a **secure score** computed from recommendations against the Microsoft cloud security benchmark, with the foundational posture features free and paid Defender plans per resource type (servers, databases, storage, containers) adding threat detection. Azure Policy is the enforcement arm: the same misconfiguration can be audited (a finding), denied (the deployment fails) or fixed (a modify effect adds the missing setting).

Both tools produce more findings than any team fixes. Triage by severity and exposure (public plus high severity first), assign each finding an owner, suppress with a written reason rather than by ignoring, and watch the trend rather than the absolute count.

### Data residency and GDPR

The questions a backend developer gets asked, and where the answers live:

1. **Where is the data?** In the regions you chose, and in every place a copy goes: cross-region backups, read replicas, log exports, CDN edge caches, and global services whose control plane sits elsewhere. Both clouds publish which services are regional, and Azure describes an EU Data Boundary for services that keep customer data inside the EU; read the provider's data residency pages for the specific service rather than assuming "region equals residency".
2. **Who are the sub-processors?** The provider is a processor under GDPR when you store personal data with it, under its data processing terms (AWS includes a GDPR data processing addendum in its service terms; Microsoft publishes a Products and Services Data Protection Addendum). Both list their own sub-processors. Your records of processing should name the provider, the regions and these documents; your legal team owns the wording.
3. **How long is each copy kept?** Retention is a setting in several places: database backup retention, object lifecycle rules (see item 6.1), log group and workspace retention (see item 8.2), snapshot policies. "We delete after 30 days" is only true if every one of them is set.
4. **How do we delete?** Deleting the row does not delete it from backups taken before, from logs that contained the email address, or from the search index. The honest answers are: backups expire on their retention schedule (document that); logs are scrubbed of identifiers at the source; and for data that must be unrecoverable sooner than the backup retention, encrypt each tenant's data with its own key and delete the key (crypto-shredding, see item 9.1).

## Example: an exposure review from the command line

Three questions that take a minute each and find most of the problems. Does any bucket lack the account-wide block, and are any security groups open to the world on anything but the balancer?

```bash
aws s3control get-public-access-block --account-id 123456789012
```

```json
{
    "PublicAccessBlockConfiguration": {
        "BlockPublicAcls": true,
        "IgnorePublicAcls": true,
        "BlockPublicPolicy": true,
        "RestrictPublicBuckets": true
    }
}
```

```bash
aws ec2 describe-security-groups \
  --filters Name=ip-permission.cidr,Values=0.0.0.0/0 \
  --query 'SecurityGroups[].{group:GroupName,ports:IpPermissions[?contains(IpRanges[].CidrIp, `0.0.0.0/0`)].[FromPort,ToPort]}'
```

```json
[
    { "group": "sg-alb", "ports": [[443, 443]] },
    { "group": "sg-bastion-old", "ports": [[22, 22]] }
]
```

The second line is the finding: a leftover bastion group with SSH open to the internet. On Azure, the same two questions:

```bash
az storage account list --query "[].{name:name,publicBlobs:allowBlobPublicAccess,publicNetwork:publicNetworkAccess}" --output table

az network nsg rule list --resource-group orders-prod --nsg-name nsg-app \
  --query "[?access=='Allow' && direction=='Inbound' && (sourceAddressPrefix=='*' || sourceAddressPrefix=='Internet')].{name:name,port:destinationPortRange}" --output table
```

The same checks, as the tools express them: Security Hub control `EC2.19` flags security groups that allow unrestricted access to high-risk ports, and `S3.1` flags accounts without block public access; Defender for Cloud lists "Management ports should be closed on your virtual machines" and "Storage account public access should be disallowed" among its recommendations. Reading the identifiers once makes the dashboards legible.

A residency inventory for the orders service, the table a procurement questionnaire wants:

| Data | Store | Region | Copies elsewhere | Retention | Deletion path |
|---|---|---|---|---|---|
| Customer records | RDS for PostgreSQL | `eu-north-1` | Automated backups in the same region, 14 days | Account lifetime plus 30 days | Row delete; backups expire after 14 days |
| Uploaded documents | S3 | `eu-north-1` | None (no cross-region replication) | 365 days via lifecycle rule | Object delete; versions expire after 30 days |
| Application logs | CloudWatch Logs | `eu-north-1` | None | 30 days | Identifiers never logged; retention expiry |
| Audit trail | CloudTrail to S3 (log archive account) | `eu-north-1` | None | 7 years | Not deleted (legal basis: audit) |
| Edge caches | CloudFront | Global edge locations | Cached responses, no personal data (private responses are not cached) | TTL seconds | Not applicable |

The Azure version swaps the services (`swedencentral`, Flexible Server, Blob Storage, Log Analytics, Activity Log exports, Front Door) and the structure stays.

## Pitfalls

- Posture tools enabled in one region or one account. The finding you needed was in the region you forgot.
- Thousands of findings, no owners. The count becomes wallpaper; triage by severity and exposure and assign.
- "Private" bucket, public CDN with no origin access. The distribution is the public door; use origin access control (CloudFront) or a private origin (Front Door Premium) so only the edge can read.
- Logging personal data. Email addresses and IP addresses in request logs with a long retention are personal data you never inventoried.
- Cross-region backups "for safety" from an EU region into a non-EU one. It may be exactly what residency commitments forbid; choose the backup region deliberately.
- Promising deletion the backups cannot deliver. State the backup retention in the privacy documentation, or crypto-shred.
- Treating secure score as the goal. A high score with a public database is still a public database; the score measures coverage of the benchmark, not your actual risk.

## Check yourself

1. List five configuration facts you would check within the first hour of inheriting an AWS account or an Azure subscription, and the command or console page for each.
2. A customer asks "where is our data and who can see it?". Build the residency table for a service you know and mark the rows you are not sure about.
3. Explain why deleting a customer's row in PostgreSQL does not satisfy a deletion request on its own, and what two mechanisms make the remaining copies disappear or unreadable.
4. Security Hub shows 1,200 findings. Describe how you would reach a prioritised list of ten by the end of the day, and what you would do with findings you decide not to fix.

## Go deeper

- [AWS Security Hub](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html) · the standards, the control identifiers and how findings are aggregated across accounts.
- [Microsoft Defender for Cloud](https://learn.microsoft.com/en-us/azure/defender-for-cloud/defender-for-cloud-introduction) · secure score, recommendations and the Defender plans.
- [Azure: Data residency](https://azure.microsoft.com/en-us/explore/global-infrastructure/data-residency/) · which data stays in the region you choose and which services are global.
- [AWS: Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) · the reason every row in the exposure table is on your side of the line.

---

Part of [Cloud](../README.md) · items 9.2, 9.3
