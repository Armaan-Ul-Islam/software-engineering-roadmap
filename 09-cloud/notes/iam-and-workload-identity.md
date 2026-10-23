# IAM and workload identity: who may do what, without long-lived keys

> **In one sentence:** Cloud access control is a set of policies that say which principal may perform which action on which resource, evaluated as "deny by default, explicit deny wins", and the safest principal for your service is a role or managed identity whose credentials the platform issues and rotates for you.

**Why it matters:** Most cloud breaches start with a leaked long-lived key: an access key in a Git history, a connection string in a build log, a service principal secret in a wiki. The fix is structural, not procedural: give compute an identity it does not have to store, and give that identity only the permissions it uses. Interviewers ask "how does your service authenticate to S3?"; the wrong answer is a key in an environment variable.

## The idea

### The vocabulary, on both clouds

| Concept | AWS IAM | Azure (Entra ID + Azure RBAC) |
|---|---|---|
| Principal (who) | IAM user, IAM role, root user, federated identity, AWS service | User, group, service principal, managed identity |
| Permission definition (what) | Policy document (JSON) with `Effect`, `Action`, `Resource`, `Condition` | Role definition with `Actions`, `NotActions`, `DataActions`, `NotDataActions` |
| Attaching permissions | Attach a policy to a user, group or role; or a resource-based policy on the resource itself | Role assignment = principal + role definition + scope |
| Where it applies | Resource ARNs listed in the policy | A scope: management group, subscription, resource group or single resource; assignments inherit downwards |
| Grouping people | IAM groups (users only, not roles) | Entra ID groups (assign the role to the group) |
| Temporary identity for workloads | IAM role, assumed through STS | Managed identity (system-assigned or user-assigned) |

Two Azure distinctions trip people up. First, Entra ID *directory* roles (Global Administrator, User Administrator) are not Azure RBAC roles; one controls the identity tenant, the other controls Azure resources. Second, Azure separates **control plane** actions (create or list a storage account) from **data plane** actions (read a blob). `Contributor` on a storage account lets you reconfigure it but does not let you read blobs through Entra authentication; for that you need a data role such as `Storage Blob Data Reader`.

### How AWS evaluates a request

1. Start from an implicit **deny**.
2. If any applicable policy contains an explicit `"Effect": "Deny"` that matches, the result is deny. Nothing overrides it.
3. Otherwise the request must be allowed by every layer that applies: the organisation's service control policies, the permission boundary on the principal (if any), the session policy (if any), and finally either an identity-based policy on the principal or a resource-based policy on the target (within one account, either is enough; across accounts, both sides must allow).
4. If no allow is found, the implicit deny stands.

### How Azure RBAC evaluates a request

Permissions are **additive**: the effective permissions of a principal are the union of every role assigned to it or to any group it is in, at the requested scope or any scope above it. Deny assignments exist but are created by specific Azure services (for example deployment stacks), not written by hand, so in practice you narrow access by assigning smaller roles at smaller scopes rather than by writing denies.

### Least privilege in practice

- Name resources, not `*`. `arn:aws:s3:::orders-uploads-prod/*`, not `arn:aws:s3:::*`. A container scope, not the whole subscription.
- Name actions, not `s3:*`. Start from what the code calls; the SDK method names map to IAM action names almost one to one.
- Use the tooling that reads what actually happened: IAM Access Analyzer can generate a policy from CloudTrail activity, and the Azure Activity Log shows which operations a principal performed.
- One role per service, never a shared "backend" role. Blast radius and audit both improve.

### Workload identity instead of secrets

| Compute | AWS | Azure |
|---|---|---|
| Virtual machine | Instance profile (a role attached to the instance), credentials from the instance metadata service (use IMDSv2) | System- or user-assigned managed identity, token from the instance metadata endpoint |
| Containers | ECS task role (not the task *execution* role, which the agent uses to pull images and read secrets); EKS Pod Identity or IAM Roles for Service Accounts | Managed identity on the Container App; AKS workload identity |
| Functions | Lambda execution role | Managed identity on the Function App |

The AWS SDK's default credential provider chain and Azure's `DefaultAzureCredential` both find these identities automatically, so the same code runs locally with your developer credentials and in production with the workload identity. There is nothing to store, nothing to rotate, nothing to leak.

### OIDC federation for CI pipelines

A pipeline also needs an identity, and storing a cloud key as a CI secret recreates the problem. Instead, the CI provider issues a short-lived OpenID Connect token that describes the job (repository, branch, environment), and the cloud exchanges it for temporary credentials when the token matches a trust rule. On AWS this is an IAM OIDC identity provider plus a role whose trust policy allows `sts:AssumeRoleWithWebIdentity` for a specific `sub` claim. On Azure it is a *federated identity credential* on an app registration or user-assigned managed identity, with the issuer, subject and audience set to the CI provider's values.

## Example: a service that may read one bucket

Identity-based policy attached to the ECS task role of the orders service. Listing and reading are different actions on different resources, which is the most common mistake in S3 policies:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListOnlyThisBucket",
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::orders-uploads-prod"
    },
    {
      "Sid": "ReadObjectsInThisBucket",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-uploads-prod/*"
    }
  ]
}
```

The role's trust policy says who may wear it. For an ECS task:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

For a GitHub Actions deployment role, the trust policy instead names the OIDC provider and pins the repository and branch:

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:acme/orders-api:ref:refs/heads/main"
    }
  }
}
```

Without the `sub` condition, any GitHub repository in the world could assume the role.

The Azure equivalent has no policy document to write. Give the Container App a user-assigned managed identity, then assign a built-in data-plane role at the narrowest scope, here a single blob container:

```bash
az role assignment create \
  --assignee-object-id "$IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Reader" \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/orders-prod/providers/Microsoft.Storage/storageAccounts/ordersuploadsprod/blobServices/default/containers/uploads"
```

`Storage Blob Data Reader` grants the data actions to read and list blobs, and the scope restricts them to that container. In Spring, the Azure SDK's `DefaultAzureCredential` picks the managed identity up at runtime; locally it falls back to your `az login` session. The AWS side is the same story with the default credential chain and `aws sso login`.

## Pitfalls

- Access keys in environment variables, `application.properties` or CI secrets. Every one of them is a credential that never expires until someone remembers to rotate it. Use a role or managed identity.
- Confusing the ECS task role with the task execution role. Permissions your *code* needs belong on the task role.
- Assigning `Contributor` and wondering why blob reads fail with 403. Control-plane roles do not grant data-plane access; assign a data role.
- Assigning roles at subscription scope "to be safe". Inheritance means every resource group in the subscription is now in scope. Assign at the resource group or resource.
- Writing an OIDC trust policy without pinning `sub` (and `aud`). The role is then assumable from any pipeline on that provider.
- Granting the pipeline identity the same permissions as the application. A deployment role needs to update a service definition and push an image; it does not need to read customer data.

## Check yourself

1. An IAM user has an identity policy allowing `s3:*` on everything, and the bucket policy on `finance-reports` denies `s3:GetObject` to everyone except one role. Can the user read a report? Walk through the evaluation order.
2. Your Spring service on Azure Container Apps gets `403` from Blob Storage even though its managed identity has `Contributor` on the storage account. Why, and what is the smallest change that fixes it?
3. Why is a GitHub Actions OIDC token a better deployment credential than an IAM access key stored as a repository secret? Name two properties.
4. A Lambda function and an ECS service both need to read the same bucket. Should they share one role? Argue both sides, then pick.

## Go deeper

- [AWS IAM: How IAM works](https://docs.aws.amazon.com/IAM/latest/UserGuide/intro-structure.html) · principals, requests, authentication and authorisation, in AWS's own words.
- [AWS IAM: Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) · the flow chart behind the four steps above, including the cross-account case.
- [Azure RBAC overview](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview) · principals, role definitions, scopes and assignments, with the additive model spelled out.
- [Azure: Managed identities](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview) · system-assigned versus user-assigned, and which services support them.
- [GitHub Actions: Configuring OpenID Connect in AWS](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services) and [in Azure](https://docs.github.com/en/actions/security-for-github-actions/security-hardening-your-deployments/configuring-openid-connect-in-azure) · the exact claims, audiences and trust configuration for both clouds.

---

Part of [Cloud](../README.md) · items 2.1, 2.2
