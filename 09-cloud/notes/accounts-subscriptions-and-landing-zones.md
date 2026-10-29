# Accounts, subscriptions and landing zones: isolating environments and governing human access

> **In one sentence:** The account (AWS) or subscription (Azure) is the unit of isolation, billing and quota, so each environment gets its own, they are arranged in an organisation tree where guard-rail policies and single sign-on are applied once at the top, and every human action is written to an audit log that is exported before its 90 days run out.

**Why it matters:** A team that starts with one account "for now" ends up with staging able to delete production, one bill nobody can split by team, and an engineer with a permanent administrator key because that was easier than setting up SSO. The structure is cheap to get right on day one and expensive to retrofit; it is also the first thing an auditor or a security reviewer asks to see.

## The idea

### The hierarchy on both clouds

| Level | AWS | Azure | Used for |
|---|---|---|---|
| Identity directory | AWS IAM Identity Center (users and groups, usually synced from an external identity provider) | Microsoft Entra ID tenant | Who people are; SSO; MFA policies |
| Root of the tree | AWS Organizations, with a management account that should run nothing | Tenant root management group | Organisation-wide policies and billing |
| Grouping | Organizational units (OUs), nestable | Management groups, nestable | Attaching policies to many accounts or subscriptions at once |
| Isolation and billing unit | Account | Subscription | Blast radius, service quotas, cost reports, environment separation |
| Grouping inside the unit | None built in; use tags | Resource group | Lifecycle of related resources (Azure); cost allocation |
| Resource | Resource with tags | Resource with tags | |

The difference that confuses people moving between clouds: an AWS account is a hard boundary with its own IAM, and resources in two accounts cannot see each other without explicit cross-account grants. An Azure subscription is a boundary for billing and quotas, but RBAC assignments and policies inherit from the management group above, so "one tenant, many subscriptions" behaves like "one organisation, many accounts" only if you assign roles at subscription scope rather than at the root.

### Separating environments

One account or subscription per environment per workload (`orders-dev`, `orders-staging`, `orders-prod`), plus shared accounts for logging, security tooling and networking. The benefits are concrete: an IAM mistake in staging cannot reach production data; a runaway test cannot consume production's service quotas; the bill is already split without perfect tagging; and production can have stricter guard rails (no public IPs, only approved regions) without slowing development down.

Tags still matter inside the unit: `service`, `environment`, `owner` and `cost-centre` on every resource, enforced with AWS Config rules or Azure Policy, because cost reports and incident pages both start from "whose is this?" (see item 5.7).

### Landing zones and guard rails

A **landing zone** is the pre-built set of accounts, networking, identity and policies that a new workload lands in. AWS Control Tower creates one (a management account, a log archive account, an audit account, OUs and guard rails) and the Azure Cloud Adoption Framework publishes reference landing zones with Bicep and Terraform. The guard rails are **service control policies** (SCPs) in AWS Organizations and **Azure Policy** assignments at management-group scope. An SCP never grants anything; it is a ceiling on what IAM inside the account can allow. Azure Policy can audit, deny or modify resource operations and is evaluated by Azure Resource Manager before the request reaches the service.

### Human access

- **Single sign-on.** Nobody gets an IAM user with a password or access keys. People sign in through IAM Identity Center (which issues short-lived credentials for a chosen account and permission set) or through Entra ID (which assigns Azure RBAC roles to groups). Developer laptops use `aws sso login` or `az login`; the SDK credential chain then works with no stored keys (see item 2.2).
- **MFA.** Enforced at the identity provider, preferably with phishing-resistant methods (hardware keys or passkeys). On Azure this is a Conditional Access policy; on AWS it is a setting in Identity Center or the external provider. The AWS root user of every account gets a hardware MFA device and no access keys.
- **Just-in-time elevation.** Entra Privileged Identity Management makes administrator roles activatable for a few hours with approval and a reason. On AWS the equivalent is a permission set that is only assigned on request, or a role with a short session duration that requires MFA to assume.
- **Break-glass accounts.** Two emergency identities that bypass SSO and Conditional Access (because the outage you are fixing may be the identity provider), stored offline, with alerts on every sign-in. On AWS this is the root user of the management account and a documented emergency role; on Azure, the emergency access accounts that Microsoft's guidance describes, excluded from Conditional Access policies.
- **Audit logs.** AWS CloudTrail records every API call with the identity, source IP and parameters; the account's event history keeps 90 days, so create an organisation trail that writes to an S3 bucket in the log archive account. The Azure Activity Log records control-plane operations per subscription for 90 days; a diagnostic setting exports it to a Log Analytics workspace or a storage account. Entra sign-in and audit logs cover who logged in and who changed a role.

## Example: a small organisation with one guard rail

```text
AWS Organizations                               Azure tenant
================                                ============
management account (billing, nothing else)      tenant root management group
|                                               |
+-- OU: security                                +-- mg: platform
|   +-- log-archive  (CloudTrail bucket)        |   +-- sub: logging   (Log Analytics)
|   +-- audit        (Security Hub)             |   +-- sub: security  (Defender for Cloud)
|                                               |
+-- OU: workloads                               +-- mg: workloads
    +-- OU: prod     <- SCP: approved regions       +-- mg: prod  <- Policy: allowed locations
    |   +-- orders-prod                             |   +-- sub: orders-prod
    +-- OU: non-prod                                +-- mg: non-prod
        +-- orders-dev                                  +-- sub: orders-dev
        +-- orders-staging                              +-- sub: orders-staging
```

The SCP attached to the `prod` OU, in simplified form. It denies any action outside two regions, except for the global services that have no region:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyOutsideApprovedRegions",
      "Effect": "Deny",
      "NotAction": [
        "iam:*", "organizations:*", "sts:*", "support:*",
        "cloudfront:*", "route53:*", "budgets:*", "health:*"
      ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": { "aws:RequestedRegion": ["eu-north-1", "eu-west-1"] }
      }
    }
  ]
}
```

On Azure the same intent is the built-in policy definition **Allowed locations**, assigned to the `prod` management group with the parameter set to `swedencentral` and `westeurope`. Every subscription created under that group inherits it. In both cases a developer with full administrator rights in `orders-prod` still cannot create a database in another region, because the guard rail sits above the account.

Reading the audit log when something changed and nobody admits to it:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteDBInstance \
  --start-time 2026-10-28T00:00:00Z \
  --query 'Events[].{when:EventTime,who:Username,source:EventSource}'
```

```bash
az monitor activity-log list \
  --resource-group orders-prod --offset 1d \
  --query "[?operationName.value=='Microsoft.DBforPostgreSQL/flexibleServers/delete'].{when:eventTimestamp,who:caller,status:status.value}"
```

## Pitfalls

- Running workloads in the management account or at the tenant root. SCPs do not apply to the management account, and roles assigned at the root scope inherit everywhere.
- One account for all environments. The first `terraform destroy` with the wrong workspace is the lesson.
- Root user or Global Administrator for daily work. Both bypass most guard rails; both belong in a safe with alerts on use.
- Relying on the 90-day event history. By the time an incident is investigated, the evidence has expired; export trails and activity logs on day one.
- Break-glass accounts that are subject to the same Conditional Access or SSO they are meant to bypass.
- Writing an SCP as an allow list. SCPs only limit; a `Deny` with a condition is the normal shape, and forgetting the global services in `NotAction` locks everyone out of IAM.
- Treating subscriptions as free. Each has its own quotas, policies and role assignments to maintain; a platform team and automation (Control Tower account factory, landing zone pipelines) keep the sprawl manageable.

## Check yourself

1. A developer has `AdministratorAccess` in the `orders-prod` account. Explain why an SCP on the OU still stops them from creating an EC2 instance in `us-east-1`, and what the equivalent mechanism is on Azure.
2. Why does the inheritance of Azure RBAC make "one subscription per environment" weaker than "one AWS account per environment" unless you assign roles carefully?
3. The identity provider is down and production needs an urgent change. Which identity do you use, what must have been true about it beforehand, and what should fire the moment it is used?
4. A production table was dropped at 03:12 three weeks ago. Which log answers "who", and what must have been configured for it to still exist?

## Go deeper

- [AWS Organizations](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_introduction.html) · accounts, OUs and service control policies, including the policy evaluation rules.
- [Azure: Landing zones](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/) · the reference hierarchy of management groups and subscriptions, with the design areas for identity, networking and governance.
- [AWS CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html) · event history versus trails, organisation trails and the event record format.
- [AWS: Shared Responsibility Model](https://aws.amazon.com/compliance/shared-responsibility-model/) · the reason identity, logging and configuration remain your job regardless of the service model.

---

Part of [Cloud](../README.md) · items 1.3, 2.4
