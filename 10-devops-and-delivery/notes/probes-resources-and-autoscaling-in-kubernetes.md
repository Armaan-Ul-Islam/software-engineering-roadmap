# Probes, resources, autoscaling and graceful rollouts in Kubernetes

> **In one sentence:** Probes tell Kubernetes when a container has started, is ready for traffic and is beyond saving; requests and limits tell the scheduler and the kernel what it may use; and the rollout, termination and disruption settings decide whether a deploy or a node drain drops requests.

**Why it matters:** A liveness probe that checks the database turns a database blip into a restart storm. A CPU limit of one core turns a Spring Boot start-up into minutes and p99 latency into seconds. A missing `preStop` drops in-flight requests at every deploy. These settings are the difference between a service that runs on Kubernetes and one that stays up while Kubernetes does its job.

## The idea

**Three probes, three questions.**

| Probe | Question | On failure | Spring Boot endpoint |
|---|---|---|---|
| startup | has the application finished starting? | after `failureThreshold` failures the container is restarted; liveness and readiness are not checked until it succeeds | `/actuator/health/liveness` |
| readiness | can it take traffic right now? | the Pod is removed from the Service's endpoints; nothing is restarted | `/actuator/health/readiness` |
| liveness | is it broken beyond recovery? | the container is killed and restarted | `/actuator/health/liveness` |

Spring Boot Actuator exposes those two groups when `management.endpoint.health.probes.enabled=true` (enabled automatically when it detects Kubernetes). Liveness reflects only the application's internal `LivenessState`; readiness reflects `ReadinessState`, which Spring flips to refusing traffic on shutdown. Add the database to the *readiness* group only if the service is useless without it (`management.endpoint.health.group.readiness.include=readinessState,db`); never add external dependencies to liveness, because restarting your Pod does not fix their outage. Probe timing fields: `periodSeconds` (default 10), `timeoutSeconds` (1), `failureThreshold` (3), `successThreshold` (1, and it must stay 1 for liveness and startup). A startup probe with `failureThreshold: 30` and `periodSeconds: 5` gives a slow JVM 150 seconds without guessing an `initialDelaySeconds`.

**Requests, limits and QoS.** `requests` are what the scheduler reserves on a node and, for CPU, the weight used when CPUs are contended. `limits` are enforced: exceeding `limits.memory` means an OOM kill (item 3.4); `limits.cpu` is a CFS quota per 100 ms period, so a JVM allowed one CPU that runs four JIT and GC threads at start-up burns its quota in 25 ms and sleeps for 75 ms, over and over. That is why a CPU-limited JVM starts slowly and shows latency spikes under load; `container_cpu_cfs_throttled_periods_total` in cAdvisor metrics counts the throttled periods. The common practice for JVMs: memory request equal to its limit, an honest CPU request, and no CPU limit (or a generous one if policy requires). Without a limit the JVM sees all node CPUs, so set `-XX:ActiveProcessorCount` (item 3.4). The QoS class follows from the numbers: *Guaranteed* when every container has requests equal to limits for both CPU and memory, *Burstable* when some requests are set, *BestEffort* when none are; under node memory pressure, BestEffort Pods are evicted first.

**Horizontal Pod Autoscaler.** The HPA (`autoscaling/v2`) adjusts a Deployment's replica count to hit a target, most often CPU utilisation, which is measured as a percentage of the *request*, so an HPA without CPU requests shows `<unknown>`. Memory is a poor signal for a JVM because the heap fills to its maximum regardless of load. Custom metrics (requests per second per Pod, queue lag) come through a metrics adapter such as Prometheus Adapter or KEDA. `behavior.scaleDown.stabilizationWindowSeconds` (default 300) stops flapping. Do not keep `replicas` in a Deployment that an HPA manages: every `kubectl apply` would reset the count.

**Rollouts.** A `RollingUpdate` replaces Pods in steps bounded by `maxSurge` (extra Pods allowed, default 25 percent) and `maxUnavailable` (default 25 percent). `maxUnavailable: 0` with `maxSurge: 1` never reduces capacity. `minReadySeconds` makes a new Pod count as available only after it has been Ready for that long, so a Pod that crashes ten seconds in does not let the rollout continue. `progressDeadlineSeconds` (default 600) marks a stuck rollout as failed but does not roll it back; `kubectl rollout undo` does.

**Graceful termination.** When a Pod is deleted, two things happen at once: the endpoint controllers start removing it from Services (which takes time to reach every node and ingress), and the kubelet runs the `preStop` hook and then sends `SIGTERM`. After `terminationGracePeriodSeconds` (default 30) it sends `SIGKILL`. Because endpoint removal is asynchronous, requests still arrive for a few seconds after `SIGTERM`. The fix is a `preStop` sleep of a few seconds, so traffic drains before the application starts shutting down, plus Spring Boot's graceful shutdown (`server.shutdown=graceful`, the default since Spring Boot 3.4, with `spring.lifecycle.timeout-per-shutdown-phase`), which stops accepting new requests and finishes in-flight ones. The grace period must be longer than the sleep plus the shutdown timeout. Distroless images have no `sh` for the `exec` hook; recent clusters offer the `sleep` lifecycle action instead.

**PodDisruptionBudgets** (`policy/v1`) protect against *voluntary* disruptions: node drains, cluster upgrades, autoscaler scale-downs. `maxUnavailable: 1` lets the drain proceed one Pod at a time; `minAvailable` equal to the replica count blocks drains forever. A PDB does nothing against a node crash.

## Example: the probe, resource and rollout blocks, annotated

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  selector:
    matchLabels:
      app: orders
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  template:
    metadata:
      labels:
        app: orders
    spec:
      terminationGracePeriodSeconds: 40
      containers:
        - name: app
          image: ghcr.io/example/orders:sha-9f3c1d2e
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: JAVA_TOOL_OPTIONS
              value: -XX:MaxRAMPercentage=75.0 -XX:ActiveProcessorCount=2
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 2
            timeoutSeconds: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            failureThreshold: 3
            timeoutSeconds: 3
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 5"]
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders
spec:
  maxUnavailable: 1
  selector:
    matchLabels:
      app: orders
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
```

And on the Spring Boot side:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.group.readiness.include=readinessState,db
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

1. The startup probe gives the JVM up to 150 seconds; until it passes, the liveness probe cannot kill a slow start.
2. Readiness is checked every 5 seconds with 2 failures allowed, so a Pod leaves the endpoints within about 10 seconds of a problem. `timeoutSeconds: 3` tolerates a GC pause; the default of 1 second does not.
3. Liveness is deliberately lenient (30 seconds of failure) and only reflects Spring's own `LivenessState`.
4. Memory request equals limit (Guaranteed for memory); CPU has a request and no limit, so there is no throttling, and `ActiveProcessorCount` keeps the JVM from sizing pools for the whole node.
5. The termination arithmetic: `preStop` sleeps 5 s while endpoints drain, Spring then gets up to 20 s to finish in-flight requests, and both fit inside the 40 s grace period with margin for the JVM to exit.
6. `maxUnavailable: 0`, `maxSurge: 1` and `minReadySeconds: 10` mean a rollout adds one new Pod, waits until it has been Ready for 10 seconds, then removes one old Pod.
7. The PDB allows a drain to take one Pod at a time, and the HPA keeps at least two, so a single-node failure or drain never removes the last replica. The Deployment has no `replicas` field because the HPA owns the count.

## Pitfalls

- A liveness probe that includes the database or a downstream service. The dependency flickers, every Pod restarts at once, and the connection storm on reconnect makes it worse.
- Liveness timing shorter than start-up. The classic `CrashLoopBackOff` of a healthy application; a startup probe fixes it, raising `initialDelaySeconds` only hides it until the next slower start.
- The default `timeoutSeconds: 1`. Health endpoints that touch a connection pool, plus a GC pause, exceed it and the Pod drops out of the Service for no reason.
- `limits.cpu` on a JVM. Watch `container_cpu_cfs_throttled_periods_total` and compare start-up time with and without the limit.
- Memory request lower than the limit. The node is overcommitted; when neighbours use their limits, the kernel kills someone.
- No `preStop` and a grace period shorter than the shutdown phase: 502s at every deploy, and `SIGKILL` mid-request when the sleep plus shutdown exceeds the grace period.
- `minAvailable: 1` with `replicas: 1`. The PDB blocks every drain and cluster upgrades stall; with one replica, no setting gives you availability.

## Check yourself

1. A Pod is `Running`, never restarts, and receives no traffic. Which probe is failing, how do you confirm it, and what does Spring's readiness group probably contain?
2. Why does `limits.cpu: 1` hurt a JVM whose steady-state use is 0.2 CPU, and which metric proves it?
3. Walk through the 40 seconds after `kubectl delete pod` with the example configuration. At which moment could a request still be lost, and which setting addresses it?
4. The HPA shows `<unknown>/70%`. What is missing from the Deployment, and why does the HPA need it?

## Go deeper

- [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) · every probe field, with the startup-probe pattern for slow applications.
- [Kubernetes: Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) · requests, limits, QoS and how CPU limits are enforced.
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) · rolling update parameters, `rollout` commands and progress deadlines.
- [Kubernetes: Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) · the termination sequence, `preStop` and the grace period in detail.
- [Kubernetes: Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/) · the algorithm, stabilisation and custom metrics.
- [Spring Boot: Kubernetes probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes) · the liveness and readiness groups and how graceful shutdown changes readiness.

---

Part of [DevOps & Delivery](../README.md) · items 4.5, 4.6
