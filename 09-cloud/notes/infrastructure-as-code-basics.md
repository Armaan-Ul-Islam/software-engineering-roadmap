# Infrastructure as code basics: Terraform, Bicep and CDK, state, plan and apply, drift

> **In one sentence:** Infrastructure as code describes your cloud resources in files that are reviewed, versioned and applied by a tool that computes the difference between what you declared and what exists, and the hard parts are not the syntax but the state file, drift, module boundaries and the review workflow.

**Why it matters:** An environment built by clicking cannot be reproduced, reviewed or recovered; the person who built it leaves, and the second region never happens. With infrastructure as code the pull request becomes the change-control record, staging and production are built from the same module, and `plan` tells you before `apply` that you are about to destroy the database. Backend developers who can read a plan are the ones trusted to ship their own infrastructure.

## The idea

### The tools

| Tool | Language | Clouds | Where desired-versus-actual lives | Preview command |
|---|---|---|---|---|
| Terraform, OpenTofu | HCL | Any with a provider (AWS, Azure, GitHub, Datadog, ...) | A **state file** the tool maintains | `terraform plan` |
| Bicep | Bicep DSL, compiled to ARM templates | Azure only | Azure Resource Manager compares against the live resource group; no state file | `az deployment group what-if` |
| AWS CDK | TypeScript, Java, Python, ... synthesising CloudFormation | AWS only (CDK for Terraform exists) | The CloudFormation stack | `cdk diff` |
| CloudFormation | YAML or JSON | AWS only | The stack | Change sets |

OpenTofu is the Linux Foundation fork of Terraform created after the 2023 licence change; the language and providers are the same for everyday work. Pick Terraform or OpenTofu when you span clouds or SaaS tools, Bicep when you are Azure-only and want zero state management, CDK when your team prefers a real programming language and is AWS-only.

### State

Terraform's state maps every resource block to the real resource ID and records the attributes it last saw. Three consequences. It must be **shared and locked**: store it remotely (an S3 bucket with locking, or an Azure Storage blob, which locks with a lease), never in Git. It contains **secrets in plaintext** (database passwords, generated keys), so encrypt the bucket and restrict who can read it. And it must be **small**: one state per environment and per component (network, database, service), so a mistake has a bounded blast radius and `plan` stays fast. Bicep and CloudFormation avoid the file but not the concept; the stack or resource group is the state.

### Plan and apply

```bash
terraform init                      # download providers, connect to the backend
terraform plan -out=orders.tfplan   # compute and save the exact changes
terraform apply orders.tfplan       # apply exactly what was reviewed, nothing else
```

Read a plan by its symbols: `+` create, `~` update in place, `-` destroy, and `-/+` **destroy and recreate**, which on a database or a bucket means data loss. Saving the plan and applying the saved file guarantees that what was reviewed is what runs.

### Drift

Drift is reality diverging from code: a console edit, an auto-generated security group rule, a manual hotfix at 02:00. `terraform plan` shows it as unexpected changes (use `terraform plan -refresh-only` to see drift without proposing changes); CloudFormation has drift detection; Bicep's `what-if` compares against reality directly. The policy that works is simple: nobody edits production by hand, and when someone has to, the next step is a pull request that imports or reverts the change.

### Modules and environments

A module is a folder of resources with inputs (`variable`) and outputs (`output`), versioned and reused: a `network` module, a `postgres` module, a `spring-service` module. Environments reuse the same modules with different variable values, typically a directory per environment (`environments/staging`, `environments/prod`) each with its own state and `.tfvars`. Promote by bumping a module version in staging, then in production, never by editing production's copy.

### The review workflow

1. A pull request changes the code; CI runs `terraform fmt -check`, `validate`, a linter and a security scanner, then `plan`, and posts the plan as a comment.
2. A reviewer reads the plan, not just the diff: any `-/+` on stateful resources needs a reason.
3. On merge, CI runs `apply` with a short-lived identity obtained through OIDC federation (see item 2.2); no human has production credentials on a laptop.
4. `lifecycle { prevent_destroy = true }` on databases and buckets turns a bad plan into an error instead of an outage.

## Example: a minimal Terraform configuration, block by block

```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket  = "acme-terraform-state"
    key     = "orders-api/prod/terraform.tfstate"
    region  = "eu-north-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  type    = string
  default = "eu-north-1"
}

variable "environment" {
  type = string
}

resource "aws_s3_bucket" "uploads" {
  bucket = "acme-orders-uploads-${var.environment}"

  tags = {
    service     = "orders-api"
    environment = var.environment
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id

  versioning_configuration {
    status = "Enabled"
  }
}

output "uploads_bucket_name" {
  value = aws_s3_bucket.uploads.bucket
}
```

- `terraform { ... }` pins the tool version and the provider version range, so a new major provider release cannot silently change behaviour on the next `init`. The `backend "s3"` block says where state lives: a bucket, a key that includes the component and environment, and encryption on.
- `provider "aws"` configures how to talk to AWS; credentials are deliberately absent and come from the environment (your SSO session locally, the OIDC role in CI).
- `variable` blocks are the module's inputs. `environment` has no default, so every `plan` must say which environment it is for.
- `resource "aws_s3_bucket" "uploads"` declares the bucket; `aws_s3_bucket.uploads` is how other blocks refer to it. The `tags` map is what makes the cost report readable (see item 5.7). `prevent_destroy` makes any plan that would delete the bucket fail.
- `resource "aws_s3_bucket_versioning"` configures versioning as a separate resource, as the AWS provider has done since version 4; referencing `aws_s3_bucket.uploads.id` creates the dependency that orders the two operations.
- `output` exposes the real bucket name to callers, for example to a `spring-service` module that injects it as an environment variable.

Run it: `terraform init`, then `terraform plan -var environment=prod -out=prod.tfplan`, read the two `+` lines, then `terraform apply prod.tfplan`. Change the tag and plan again: one `~` line. Change the bucket name and plan again: a `-/+` line, and because of `prevent_destroy` the plan fails, which is the point.

The Bicep equivalent is a `resource` declaration of type `Microsoft.Storage/storageAccounts` with a `sku`, `kind` and `properties` object, deployed with `az deployment group what-if` and then `az deployment group create`; no backend block exists because Azure Resource Manager holds the state.

## Pitfalls

- State in Git, or on one laptop. Two people apply, the second overwrites the first's resources, and the file now in the repository contains the database password.
- One state for everything. A `plan` takes ten minutes and a typo in a tag can touch the database.
- Applying without a saved plan. The infrastructure changed between review and apply, and what ran was not what was approved.
- Ignoring `-/+`. Renaming a resource or changing an immutable attribute recreates it; on a database that is a restore from backup.
- Console hotfixes that stay. The next `apply` reverts them, at the worst moment.
- Copy-pasting resources per environment instead of a module. Staging and production drift apart and "it works in staging" stops meaning anything.
- Hard-coding credentials or account IDs in providers. Use the environment's identity and variables; the same code must run from a laptop and from CI.

## Check yourself

1. A colleague ran `terraform apply` from their laptop with local state last month; CI now plans the same code and proposes creating every resource again. What happened, and how do you recover without duplicating resources?
2. Which line in the example makes `aws_s3_bucket_versioning` wait for the bucket, and what would happen if you referred to the bucket by its literal name string instead?
3. Explain `-/+` to a reviewer who has not seen Terraform, using the bucket example, and name the setting that turns it into an error for stateful resources.
4. Why does Bicep not need a state file, and what does it lose compared with Terraform as a result?

## Go deeper

- [Terraform tutorials](https://developer.hashicorp.com/terraform/tutorials) · the official hands-on path, including remote state and modules.
- [Bicep overview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview) · how Bicep relates to ARM templates and why there is no state.
- [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/home.html) · constructs, stacks and `cdk diff`, for teams that prefer a programming language.
- [Terraform: Up and Running](https://www.terraformupandrunning.com/) · Yevgeniy Brikman's book on state, modules, environments and testing in depth (paid).

---

Part of [Cloud](../README.md) · item 8.3
