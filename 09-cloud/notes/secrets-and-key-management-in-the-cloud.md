# Secrets and key management in the cloud: Secrets Manager, Parameter Store, Key Vault, KMS and envelope encryption

> **In one sentence:** A secret store holds the values your service must present (passwords, API tokens) and hands them out at start-up to an identity that is allowed to read them; a key management service holds keys that never leave the service and encrypts small things with them, which is why everything larger is protected with a data key that the master key wraps (envelope encryption).

**Why it matters:** Every connection string in a Git history or a build log started as "we will move it to a vault later". The vault is cheap and the integration is a few lines; what takes understanding is the difference between a secret and a key, why KMS refuses to encrypt your 10 MB file directly, and what has to happen when a secret rotates while twelve instances hold the old value in memory.

## The idea

### Three kinds of thing

| What | AWS | Azure | Notes |
|---|---|---|---|
| Secret (a value you present to something else) | AWS Secrets Manager; SSM Parameter Store `SecureString` for the simple cases | Azure Key Vault secrets | Versioned; read at start-up by the workload identity (see item 2.2) |
| Key (a value that encrypts other values and never leaves the service) | AWS KMS keys | Azure Key Vault keys; Azure Key Vault Managed HSM for dedicated hardware | Used through `Encrypt`, `Decrypt`, `GenerateDataKey`, `Sign`; the key material is not exportable |
| Certificate (a key pair plus a chain for TLS) | AWS Certificate Manager (ACM) | Key Vault certificates; App Service and Front Door managed certificates | ACM issues and renews public certificates for free, but only for use on AWS load balancers, CloudFront and API Gateway |

Parameter Store is the pragmatic choice for configuration that is not secret (feature flags, endpoint names) and for a few `SecureString` values; Secrets Manager adds rotation, cross-account sharing and a per-secret price. Key Vault covers all three kinds in one resource, which is convenient and also means one access configuration governs passwords and signing keys together.

### Envelope encryption

KMS `Encrypt` takes at most 4 KB of plaintext, and a round trip to the service per record would be slow and expensive anyway. The pattern both clouds expect:

```text
   your service                                  KMS / Key Vault
   ------------                                  ---------------
1. GenerateDataKey(key-id)  ------------------>  creates a random 256-bit data key,
   <--- plaintext data key + encrypted data key  returns both; the encrypted copy is
                                                 wrapped with the master key
2. encrypt the payload locally with the
   plaintext data key (AES-GCM), then discard
   the plaintext key
3. store  [encrypted data key | ciphertext]
   together, in S3, Blob Storage or a column

to read:
4. Decrypt(encrypted data key)  -------------->  unwraps it with the master key
   <--- plaintext data key                       (an audited, access-controlled call)
5. decrypt the payload locally
```

The master key is only ever asked to wrap and unwrap 32-byte data keys. Revoking access to the master key makes every payload unreadable at once, which is also how **crypto-shredding** works for deletion requirements (see item 9.3). The AWS Encryption SDK and the Azure Storage client-side encryption libraries implement exactly this; S3, EBS, RDS and Azure Storage do it for you when you pick a customer-managed key.

### Encryption at rest and in transit by default

At rest is now mostly on by default: S3 encrypts every new object with S3-managed keys, Azure Storage always encrypts with Microsoft-managed keys, RDS and Flexible Server encrypt storage at creation. What you choose is **who manages the key**: provider-managed (free, no control), customer-managed in KMS or Key Vault (you control the key policy, rotation and deletion, and the audit log shows every use), or bring-your-own-key for regulated workloads. In transit means TLS everywhere: between the balancer and the client (ACM or Key Vault certificate), from the service to the database (`sslmode=verify-full`, see item 6.2) and to the cache (see item 6.3). Internal hops do not get a pass because they are "inside the VPC".

### Rotation

Rotating a **secret** means producing a new value and telling the consumer. Secrets Manager runs a rotation function on a schedule (managed rotation exists for RDS and a few other services; otherwise you write the Lambda function); Key Vault stores a new secret version and can fire an Event Grid event near expiry, and the rotation itself is your code or an Azure Automation runbook. Rotating a **KMS key** is different: the key keeps its identifier, new material is used for new encryptions, and the old material is retained so old data keys still unwrap. Nothing you stored needs re-encrypting.

The consumer side is the part teams forget. A Spring Boot process reads the secret at start-up and keeps it in a `DataSource`. Rotation therefore means either a restart (the simplest and most reliable option: rotate, then roll the deployment) or a two-password overlap where the old password stays valid until every instance has picked up the new one.

## Example: a Spring Boot service reading its database password from the vault

With Spring Cloud AWS, the secret is imported as a property source. A JSON secret with the keys `username` and `password` becomes two properties:

```properties
spring.config.import=aws-secretsmanager:/prod/orders/database
spring.datasource.url=jdbc:postgresql://${DB_HOST}:5432/orders?sslmode=verify-full&sslrootcert=/etc/ssl/certs/db-ca-bundle.pem
spring.datasource.username=${username}
spring.datasource.password=${password}
```

With Spring Cloud Azure, Key Vault becomes a property source and each secret is a property; a secret named `orders-db-password` is reachable as `orders-db-password`:

```properties
spring.cloud.azure.keyvault.secret.property-sources[0].endpoint=https://orders-prod-kv.vault.azure.net/
spring.datasource.username=orders_app
spring.datasource.password=${orders-db-password}
```

Both starters authenticate with the workload identity (the ECS task role or the managed identity), so the only permission to grant is `secretsmanager:GetSecretValue` on that one secret's ARN, or the `Key Vault Secrets User` role on that one vault. Nothing is stored in the image, the task definition or the pipeline.

The envelope pattern from the command line, to see what the SDK does for you:

```bash
aws kms generate-data-key --key-id alias/orders-prod --key-spec AES_256 \
  --query '[Plaintext, CiphertextBlob]' --output text
```

The first value is the key you encrypt with and then throw away; the second is what you store next to the ciphertext. Later, `aws kms decrypt --ciphertext-blob fileb://data-key.enc` returns the plaintext key, and that call appears in CloudTrail with the caller's identity.

## Pitfalls

- Secrets in environment variables set by hand. Anyone who can describe the task definition or the container app can read them. Use a secret *reference* that the platform resolves at start (see item 8.4).
- Encrypting payloads with `kms:Encrypt` directly. It stops at 4 KB and bills per call; use data keys.
- Deleting a KMS key or purging a Key Vault. KMS enforces a waiting period before deletion and Key Vault has soft delete and purge protection for this reason; a deleted key is every byte it protected.
- Rotating the database password without a consumer plan. The secret changes, the running JVMs keep the old one, and the next pool connection fails with an authentication error. Rotate, then redeploy, or overlap two passwords.
- Granting access to the vault instead of to the secret. Key Vault RBAC at vault scope and `secretsmanager:*` on `*` both turn one compromised service into every secret.
- Fetching the secret on every request. Secrets Manager and Key Vault bill per operation and throttle; read at start-up or use the caching clients.
- `sslmode=require` to the database and plain TCP to Redis while calling the design "encrypted in transit".

## Check yourself

1. Why can a KMS key with a 4 KB limit protect a 5 GB object in S3? Draw the two calls your service makes and name what is stored alongside the object.
2. A customer-managed KMS key rotates automatically. Does the data encrypted last year need re-encrypting, and why does revoking access to that key count as deletion?
3. Describe what happens to a running Spring Boot fleet when the database password in Secrets Manager rotates, and two ways to make the rotation invisible to users.
4. What is the difference between `Contributor` on a Key Vault and `Key Vault Secrets User`, and which one does a Container App need?

## Go deeper

- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html) · secret structure, rotation functions and the managed rotation for RDS.
- [AWS KMS](https://docs.aws.amazon.com/kms/latest/developerguide/overview.html) · key types, key policies, envelope encryption and automatic rotation, from the primary source.
- [Azure Key Vault](https://learn.microsoft.com/en-us/azure/key-vault/general/overview) · secrets, keys and certificates in one resource, with the RBAC and soft-delete model.
- [Spring Cloud AWS](https://awspring.io/) and [Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/) · the `spring.config.import` and Key Vault property source integrations used above.

---

Part of [Cloud](../README.md) · items 2.3, 9.1
