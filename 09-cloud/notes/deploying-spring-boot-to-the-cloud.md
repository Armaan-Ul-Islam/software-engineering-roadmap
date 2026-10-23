# Deploying Spring Boot to the cloud end to end: image, registry, platform, probes, secrets, logs, rollout

> **In one sentence:** A production deployment is a container image in a registry, run by a platform that injects configuration and secrets as environment variables, polls Actuator's liveness and readiness endpoints, gives the JVM a memory limit it must respect, collects stdout as logs, and replaces old instances only after new ones are ready and old ones have drained.

**Why it matters:** Each step has one classic failure: a `latest` tag that deploys the wrong build, a heap sized for the host instead of the container, a readiness probe that passes before the connection pool exists, a rollout that kills in-flight requests. Walking the whole path once, with the exact variables and paths, is what makes the second service a half-day job instead of a week.

## The idea

The path is the same on every platform; the two worked targets here are **Azure Container Apps** and **ECS on Fargate** (the recommendation from item 4.6).

### 1. Build the image

Two good options: `./mvnw spring-boot:build-image -Dspring-boot.build-image.imageName=acme/orders-api:${GIT_SHA}` (buildpacks: a layered, non-root image with a JVM memory calculator and no Dockerfile), or a multi-stage Dockerfile that extracts the layered jar (`java -Djarmode=tools -jar app.jar extract --layers --destination extracted`, Spring Boot 3.3 and later) onto a JRE base image so dependency layers are cached. Either way, run as non-root, pin the base image, and tag with the Git SHA, never only `latest`.

### 2. Push to a registry

Amazon ECR (`aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.<region>.amazonaws.com`) or Azure Container Registry (`az acr login --name acmeregistry`). Turn on scan-on-push and give the pull identity (the ECS task *execution* role; the Container App's managed identity with `AcrPull`) read access only.

### 3. Describe the workload

| Concern | ECS on Fargate | Azure Container Apps |
|---|---|---|
| Unit | Task definition (image, CPU, memory, ports, env, secrets, log driver, health check) + service (count, subnets, load balancer, deployment settings) | Container app (image, CPU, memory, env, secrets, probes, ingress, scale rules) with immutable revisions |
| CPU and memory | Combinations such as 1 vCPU with 2 GB, chosen per task | Combinations such as 1.0 CPU with 2.0 Gi, chosen per replica |
| Placement | Tasks in private subnets across zones, behind an ALB target group | Replicas in the environment; zone redundancy is an environment option |

### 4. Inject configuration and secrets

Spring Boot's relaxed binding turns `SPRING_DATASOURCE_URL` into `spring.datasource.url`, so configuration is plain environment variables set by the platform. Secrets are references, never literals: in ECS, a container definition `secrets` entry with `valueFrom` pointing at a Secrets Manager or Parameter Store ARN, resolved by the execution role at start; in Container Apps, a secret that references a Key Vault secret through the app's managed identity, exposed to the container with `--env-vars DB_PASSWORD=secretref:db-password`. The image and the task definition in Git contain no credential (see items 2.2 and 6.4).

### 5. Map health probes to Actuator

Enable the probe endpoints and decide what readiness means:

```properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,db
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
```

- **Liveness** at `/actuator/health/liveness` answers "is the process alive and not wedged"; it must not depend on the database, or a database outage restarts every instance in a loop.
- **Readiness** at `/actuator/health/readiness` answers "may I receive traffic"; including `db` means an instance that cannot reach the database stops receiving requests, which is what you want during a failover.
- **Startup** (Container Apps) uses the readiness path with a large `failureThreshold`, so a slow JVM start is not mistaken for a dead one.

Container Apps has all three probe types with Kubernetes-style fields (`type`, `httpGet.path`, `httpGet.port`, `initialDelaySeconds`, `periodSeconds`, `failureThreshold`, `timeoutSeconds`; any status from 200 to 399 is success). ECS has one container health check (a command run inside the container, with `interval`, `timeout`, `retries` and `startPeriod`) plus the ALB target group's HTTP health check; point the target group at the readiness path, because the balancer is the thing that must stop sending traffic.

### 6. Size the JVM from the container limit

The JVM reads the container's memory limit and defaults to a quarter of it as max heap. Override with `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=50.0 -XX:+ExitOnOutOfMemoryError`, derived from the measurement in item 5.3, so the heap plus Metaspace, threads, code cache and buffers fit under the limit. With fewer than two available CPUs the JVM selects the serial collector; set the collector explicitly if you want G1 at 1 vCPU, and measure either way. `-XX:+ExitOnOutOfMemoryError` makes the platform replace a broken instance instead of letting it limp.

### 7. Log to the platform

Write structured logs to stdout and nothing to files: `logging.structured.format.console=ecs` (Spring Boot 3.4 and later) emits JSON that CloudWatch Logs and Log Analytics parse. ECS ships stdout through the `awslogs` log driver to a log group; Container Apps streams console output to the environment's Log Analytics workspace. Set a retention period on day one (see item 5.7).

### 8. Roll out without downtime

Start new instances, wait for readiness, shift traffic, then stop old instances gracefully. On ECS that is a rolling update with `minimumHealthyPercent=100` and `maximumPercent=200` plus the deployment circuit breaker, which rolls back when new tasks fail health checks; a stopping task is deregistered from the target group, ECS waits for the deregistration delay (lower it from the 300-second default to about 30 seconds), sends `SIGTERM`, and sends `SIGKILL` after `stopTimeout` (30 seconds by default on Fargate, at most 120). On Container Apps a new revision receives traffic once its readiness probes pass: a rolling replacement in single-revision mode, a percentage split for canaries in multiple-revision mode. On both, `server.shutdown=graceful` (the default since Spring Boot 3.4) makes Spring stop accepting requests on `SIGTERM` and finish in-flight ones within `timeout-per-shutdown-phase`, which must be shorter than the platform's grace period.

## Example: the variables and probe paths for one Spring Boot container

| Setting | Value | Set by |
|---|---|---|
| `SPRING_PROFILES_ACTIVE` | `prod` | Task definition or container app |
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://orders-db.internal:5432/orders?sslmode=verify-full&sslrootcert=/etc/ssl/certs/db-ca-bundle.pem` | Task definition or container app |
| `SPRING_DATASOURCE_USERNAME` | `orders_app` | Task definition or container app |
| `SPRING_DATASOURCE_PASSWORD` | Secret reference (`valueFrom` ARN on ECS; `secretref:db-password` on Container Apps) | Platform, from Secrets Manager or Key Vault |
| `JAVA_TOOL_OPTIONS` | `-XX:MaxRAMPercentage=50.0 -XX:+ExitOnOutOfMemoryError` | Task definition or container app |
| `SERVER_PORT` | `8080` (the container port and ingress target port) | Task definition or container app |
| Liveness probe | `GET /actuator/health/liveness` on 8080, period 10 s, failure threshold 3 | Container Apps probe; ECS container health check command |
| Readiness probe | `GET /actuator/health/readiness` on 8080, period 5 s, failure threshold 3 | Container Apps probe; ALB target group health check |
| Startup probe | `GET /actuator/health/readiness` on 8080, period 5 s, failure threshold 30 (150 s to start) | Container Apps; on ECS use the health check's `startPeriod` |
| Graceful shutdown | `server.shutdown=graceful`, `spring.lifecycle.timeout-per-shutdown-phase=25s` | `application.properties`; must be below `stopTimeout` and the termination grace period |
| Logging | `logging.structured.format.console=ecs` | `application.properties` |

A smoke test after the first deployment: `curl -fsS https://orders-api.example.com/actuator/health/readiness` returns `{"status":"UP"}`; the platform's log view shows JSON lines; stopping one instance by hand produces no 5xx responses at the balancer during the drain.

## Pitfalls

- Deploying `latest`. Two environments run different builds under the same tag, and a rollback has nothing to roll back to.
- Readiness that ignores the database. The instance takes traffic before the pool can connect and the first requests fail.
- Liveness that includes the database. A database failover restarts every instance at once; now you have two outages.
- Heap sized by the default 25%. A 2 GiB task runs a 512 MB heap and throws `OutOfMemoryError` under a load the host could have handled.
- Grace periods that do not line up. Spring is given 25 seconds to drain, the platform kills at 10, and the deregistration delay keeps sending requests to a stopping task.
- One replica in production "until traffic grows". Every deployment and every platform maintenance is then a visible outage.

## Check yourself

1. During a rolling deployment users see a burst of connection errors for about ten seconds. Walk through the shutdown sequence and name the three timeouts that must be ordered correctly.
2. Why should the ALB target group or the Container Apps readiness probe point at `/actuator/health/readiness` rather than `/actuator/health`, and what should liveness never include?
3. A 1 vCPU, 2 GB task with the default JVM settings runs out of heap at 600 MB of live data. Explain why, give the variable that fixes it, and say what else changes at 1 vCPU.
4. Describe how a database password reaches the JVM on each platform without appearing in Git or in the task definition, and what has to happen when it is rotated.

## Go deeper

- [Spring Boot: Container Images](https://docs.spring.io/spring-boot/reference/packaging/container-images/index.html) · layered jars, buildpacks and the Dockerfile the Spring team recommends.
- [Azure Container Apps: Java overview](https://learn.microsoft.com/en-us/azure/container-apps/java-overview) · the Java-specific features of Container Apps, including JVM memory handling and diagnostics.
- [AWS Fargate](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html) · task definitions, CPU and memory combinations and the Fargate-specific limits.
- [Azure Container Apps: Health probes](https://learn.microsoft.com/en-us/azure/container-apps/health-probes) · the three probe types, their fields and the defaults applied when you define none.
- [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview) · heap percentages, garbage collector selection and CPU limits for the JVM in a container.

---

Part of [Cloud](../README.md) · items 4.5, 8.4
