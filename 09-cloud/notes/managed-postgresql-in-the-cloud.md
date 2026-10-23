# Managed PostgreSQL in the cloud: RDS, Aurora and Flexible Server from a Spring service

> **In one sentence:** A managed PostgreSQL gives you provisioning, patching, backups with point-in-time recovery, a synchronous standby in another zone and read replicas as checkboxes, and leaves you the decisions that still cause outages: the HA option, the connection limit of the tier, the maintenance window, TLS verification and where the password comes from.

**Why it matters:** The database is the one stateful, non-horizontally-scalable component in a typical Spring deployment, so its configuration decides your availability and your recovery time. "We had backups" is not the same as "we restored to 14:32 last Tuesday in staging and it worked". The connection and TLS details also decide whether the service even starts after the first scale-out or certificate rotation.

## The idea

### The offerings

| | Amazon RDS for PostgreSQL | Amazon Aurora PostgreSQL | Azure Database for PostgreSQL Flexible Server |
|---|---|---|---|
| What it is | Community PostgreSQL on a managed instance with EBS storage | Amazon's PostgreSQL-compatible engine with a shared storage layer replicated six ways across three zones | Community PostgreSQL on a managed VM with zone options |
| High availability | Multi-AZ DB instance (synchronous standby, automatic failover, standby not readable) or Multi-AZ DB cluster (two readable standbys) | Replicas share the storage; failover promotes one in seconds to tens of seconds | Zone-redundant HA (synchronous standby in another zone) or same-zone HA |
| Read scaling | Asynchronous read replicas, also cross-region | Up to 15 replicas on the shared storage, low lag | Asynchronous read replicas, also cross-region |
| Storage | Provisioned, with optional autoscaling upwards | Grows automatically, billed per use | Provisioned, with autogrow |
| Serverless option | No | Aurora Serverless v2 scales capacity units | No |

Multi-AZ or zone-redundant HA is the default for production (see item 1.1). It roughly doubles the compute line and is worth it. Read replicas are for read scaling and reporting, not for HA: replication is asynchronous, so promoting one loses the last transactions.

### Backups and point-in-time recovery

Both clouds take automated backups and ship transaction logs continuously, so you can restore to any second within the retention window (up to 35 days on both). Two details matter. First, a point-in-time restore creates a **new server** with a new endpoint; your configuration must be able to point at it. Second, the only backup that counts is one you have restored. Schedule a restore drill into staging and time it; that number is your real recovery time objective. Geo-redundant backup storage is an option on both clouds; on Flexible Server it is chosen when the server is created.

### Maintenance windows and parameters

Minor version upgrades and OS patches run in a weekly **maintenance window** you choose. They restart the instance; with HA the standby is patched first and a failover of seconds replaces a restart of minutes. Pick a low-traffic window and make sure the connection pool recovers from dropped connections (HikariCP does). Major version upgrades are manual and need a rehearsal.

Server settings live in a **parameter group** (RDS) or **server parameters** (Flexible Server). The defaults cannot be edited on RDS, so create a custom group on day one. Static parameters need a reboot; dynamic ones apply live. The ones a backend developer touches: `max_connections` (derived from instance memory on RDS, published per compute size on Azure; see item 5.4), `log_min_duration_statement` for slow-query logging, `rds.force_ssl` on RDS and `require_secure_transport` on Azure to refuse plaintext, and on Azure `pgbouncer.enabled` for the built-in connection pooler on port 6432.

### Connecting from Spring

**TLS.** `sslmode=require` encrypts but accepts any certificate, so a man in the middle is still possible. Use `sslmode=verify-full` with the provider's CA bundle (`sslrootcert`), which verifies both the chain and the hostname. Download the bundle from the provider's documentation and bake it into the image or mount it; rotate it when the provider announces a root change.

**Password or token.** The plain option is a database password stored in AWS Secrets Manager or Azure Key Vault, injected into the container as an environment variable by the platform (see items 2.3 and 8.4), and read by Spring with `${DB_PASSWORD}`. The better option removes the password: RDS **IAM database authentication** issues short-lived tokens used in place of the password (grant the role `rds_iam` to the database user; the AWS Advanced JDBC Wrapper has a plugin that refreshes them), and Flexible Server **Microsoft Entra authentication** does the same with Entra tokens, which Spring Cloud Azure's `spring-cloud-azure-starter-jdbc-postgresql` handles when you set `spring.datasource.azure.passwordless-enabled=true` and the workload has a managed identity (see item 2.2).

**Pool against the tier.** The pool size times the instance count must fit inside the tier's connection limit with room for the platform's own monitoring connections. Use the built-in PgBouncer (Azure) or RDS Proxy (AWS) when the fleet scales (see item 5.4).

## Example: datasource properties for a verified TLS connection with the password from the environment

```properties
spring.datasource.url=jdbc:postgresql://${DB_HOST}:5432/orders?sslmode=verify-full&sslrootcert=/etc/ssl/certs/db-ca-bundle.pem
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}

spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.minimum-idle=10
spring.datasource.hikari.connection-timeout=3000
spring.datasource.hikari.max-lifetime=1500000
spring.datasource.hikari.keepalive-time=300000
```

What each line buys you:

- `sslmode=verify-full` plus `sslrootcert` makes the driver refuse a server whose certificate does not chain to the bundle or whose name does not match `${DB_HOST}`. With Flexible Server the host is `<server>.postgres.database.azure.com`; with RDS it is the instance or cluster endpoint, and the bundle is the regional one AWS publishes.
- The three `${...}` placeholders are filled from environment variables that the platform injects from Secrets Manager or Key Vault at start-up. The image contains no credentials; rotating the secret means restarting the tasks, not rebuilding.
- `maximum-pool-size=10` with `minimum-idle=10` is a fixed-size pool, which HikariCP recommends; 10 is a starting point derived from Little's law, not a constant.
- `connection-timeout=3000` fails fast when the pool is exhausted instead of holding a request thread for the default 30 seconds.
- `max-lifetime=1500000` (25 minutes) retires connections before any idle timeout on a proxy or the server does, so the pool never hands out a connection the other side has already closed; `keepalive-time` pings idle connections every five minutes for the same reason.

For the passwordless variant on Azure, drop `spring.datasource.password`, add the Spring Cloud Azure starter and `spring.datasource.azure.passwordless-enabled=true`, and point `DB_USERNAME` at the Entra principal created for the managed identity. On AWS, swap the driver for the AWS Advanced JDBC Wrapper with its IAM plugin and grant the database user `rds_iam`.

Verify the TLS claim rather than trusting the configuration: `psql "host=$DB_HOST dbname=orders user=$DB_USERNAME sslmode=verify-full sslrootcert=/etc/ssl/certs/db-ca-bundle.pem"` and then `SELECT ssl, version, cipher FROM pg_stat_ssl WHERE pid = pg_backend_pid();` should return `t` and a TLS version.

## Pitfalls

- `sslmode=require` and calling it secure. It encrypts and verifies nothing; use `verify-full`.
- No HA in production because "it is only a restart". Maintenance, instance class changes and storage events all restart a single instance; HA turns each into a short failover.
- Never restoring. A backup you have not restored is a hypothesis; the restore endpoint is different and your configuration may not cope.
- The default parameter group. On RDS it cannot be changed, so the first slow-query or SSL setting forces a new group and a reboot under pressure.
- Pool size chosen per instance without multiplying by the fleet. The tenth instance hits the connection limit (see item 5.4).
- Promoting a read replica as if it were a standby. Replication is asynchronous; you lose the tail of transactions and the replica's configuration may differ.
- Forgetting the CA bundle rotation. The provider announces a new root months ahead; an image with the old bundle fails every new connection on the cut-over day.

## Check yourself

1. Your Multi-AZ RDS instance fails over during the maintenance window. What does the application see, what does HikariCP do about it, and which two settings decide how quickly it recovers?
2. Explain the difference between `sslmode=require` and `sslmode=verify-full`, and what an attacker on the network path can do under the first.
3. A colleague proposes a read replica "so we have a failover target". Why is that not HA, and what would you provision instead on each cloud?
4. Describe a restore drill: what you restore, where, how you point a staging deployment at it, and which number you write down afterwards.

## Go deeper

- [Amazon RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_PostgreSQL.html) · Multi-AZ options, backups, parameter groups, IAM authentication and the TLS bundle, all from the primary source.
- [Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/overview) · HA modes, backups, read replicas, server parameters and the built-in PgBouncer.
- [Azure Database for PostgreSQL: Limits](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/concepts-limits) · connection limits per compute size, which bound your pool arithmetic.
- [Spring Cloud Azure](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/) and [Spring Cloud AWS](https://awspring.io/) · the passwordless JDBC support and the Secrets Manager and Key Vault property sources.

---

Part of [Cloud](../README.md) · items 6.2, 6.4
