# Debugging a crash-looping Pod

> **In one sentence:** A Pod that will not run tells you where it is stuck through its status word, its events and the log of its *previous* container, so the diagnostic order is always get, describe, logs --previous, events, then exec or port-forward, and the status word narrows the cause before you read a single log line.

**Why it matters:** `CrashLoopBackOff` at three in the morning looks like "Kubernetes is broken" and is almost always a missing Secret, a wrong port, a slow start-up killed by a liveness probe or a memory limit. A fixed five-step routine finds which in minutes, and it is the most common hands-on question in platform and backend interviews: "a Pod is crash looping, what do you do?"

## The idea

**The status word says where the Pod is stuck.**

| Status | Stuck at | Usual cause | Look at |
|---|---|---|---|
| `Pending` | scheduling | no node with enough free CPU or memory for the requests, taints, node selectors, an unbound PersistentVolumeClaim | `describe`, Events: `FailedScheduling` |
| `ContainerCreating` | kubelet set-up | a volume, ConfigMap or Secret to mount does not exist; image still pulling | Events: `FailedMount` |
| `ImagePullBackOff`, `ErrImagePull` | pulling the image | wrong name or tag, private registry without `imagePullSecrets`, registry rate limit | Events: `Failed to pull image` |
| `CreateContainerConfigError` | building the container spec | an `env` entry references a missing Secret or ConfigMap key; `runAsNonRoot` with a root image | Events, no logs exist |
| `CrashLoopBackOff` | the process keeps exiting | application error (exit 1), `OOMKilled` (137), liveness probe kills | `logs --previous`, `Last State` |
| `Running` but `0/1` Ready | readiness probe | wrong path or port, dependency down, start-up slower than expected | Events: `Readiness probe failed`, logs |

The kubelet restarts a failed container with an exponential back-off that starts at 10 seconds, doubles, and is capped at five minutes; it resets after the container has run for ten minutes. So a Pod in `CrashLoopBackOff` spends most of its time waiting, not crashing, and `RESTARTS` tells you how long it has been going on.

**Exit codes.** 0: the process finished, which for a server means the wrong command or an image that is not a server. 1: the application failed; read the log. 137: killed with `SIGKILL`, either `OOMKilled` (the reason says so) or the grace period expired after a liveness failure. 143: `SIGTERM` handled, a normal shutdown. 127 or 126: command not found or not executable, typically an `exec` probe or entrypoint that expects a shell a distroless image does not have.

**The usual Spring Boot causes.**

1. Bad configuration. The log ends with the failure analyser block `APPLICATION FAILED TO START`, for example `Could not resolve placeholder 'DB_PASSWORD'` or a binding error; exit code 1 within seconds.
2. A dependency unreachable at start-up. `Connection to orders-db:5432 refused` from HikariCP or Flyway: wrong Service name or namespace, a NetworkPolicy, or the database is not up yet. Exit code 1 after the pool's `initialization-fail-timeout`.
3. Slow start-up versus the liveness probe. The log stops mid-start-up with no error, and Events show `Liveness probe failed: ... connection refused` followed by `Killing`. A startup probe fixes it (item 4.5).
4. A missing Secret or key. `CreateContainerConfigError` with `secret "orders-db-credentials" not found`; the process never starts and there are no logs.
5. Port mismatch. The application listens on `server.port`, the probes and the Service target another port; readiness fails with connection refused while the log says `Tomcat started on port 8081`.
6. `OOMKilled`. Exit code 137, `Reason: OOMKilled`, a quiet log; see item 3.4.
7. A typo in `JAVA_TOOL_OPTIONS`. The log shows `Picked up JAVA_TOOL_OPTIONS: ...` then `Unrecognized VM option` and exits with 1 before Spring starts.

## Example: the commands in order, and what to look for

```bash
kubectl -n shop get pods -l app=orders -o wide
```

Look at `STATUS`, `READY` and `RESTARTS` (recent versions print `6 (2m ago)`). Many restarts with `CrashLoopBackOff` means the process exits; `Running` with `0/1` means readiness. `-o wide` adds the node, which matters for `Pending` and for node-level problems.

```bash
kubectl -n shop describe pod orders-7c9d6f5b8-x2k4q
```

Look at `State` and `Last State` for the container, then the `Events` at the bottom:

```text
    State:          Waiting
      Reason:       CrashLoopBackOff
    Last State:     Terminated
      Reason:       Error
      Exit Code:    1
      Started:      Fri, 24 Oct 2026 09:12:03 +0000
      Finished:     Fri, 24 Oct 2026 09:12:19 +0000
    Restart Count:  6
Events:
  Type     Reason   Age                  From     Message
  ----     ------   ----                 ----     -------
  Normal   Pulled   3m (x7 over 9m)      kubelet  Container image "ghcr.io/example/orders:sha-9f3c1d2e" already present on machine
  Warning  BackOff  40s (x25 over 8m)    kubelet  Back-off restarting failed container app in pod orders-7c9d6f5b8-x2k4q_shop
```

Exit code 1 after 16 seconds with `Reason: Error` is an application failure: go to the logs. `Reason: OOMKilled` with 137 would send you to the memory budget instead, and probe failures would appear here as `Warning  Unhealthy`.

```bash
kubectl -n shop logs orders-7c9d6f5b8-x2k4q --previous
```

`--previous` reads the crashed container, not the one currently in back-off (which has no output yet). Read from the end:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Could not resolve placeholder 'DB_PASSWORD' in value "${DB_PASSWORD}"

Action:

Check your application configuration or environment variables.
```

```bash
kubectl -n shop get events --sort-by=.lastTimestamp --field-selector involvedObject.name=orders-7c9d6f5b8-x2k4q
```

The full event history for this Pod in time order: scheduling, pulls, probe failures, kills. Events expire after an hour by default, so collect them early in an incident.

```bash
kubectl -n shop exec -it orders-7c9d6f5b8-x2k4q -- sh
env | sort | grep -E 'SPRING|JAVA'
wget -qO- http://localhost:8080/actuator/health/readiness
```

Only possible while the container is up, so this is for readiness problems rather than crash loops, and only if the image has a shell. For a distroless image, `kubectl debug -it orders-7c9d6f5b8-x2k4q --image=busybox:1.36 --target=app` attaches an ephemeral container that shares the process namespace.

```bash
kubectl -n shop port-forward pod/orders-7c9d6f5b8-x2k4q 18080:8080
curl -s localhost:18080/actuator/health/readiness
```

Compare what the application answers on the port you think it listens on with the probe's `path` and `port` in the Deployment, and with the Service's `targetPort`.

```bash
kubectl -n shop get pod orders-7c9d6f5b8-x2k4q -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
kubectl -n shop rollout undo deployment/orders
kubectl -n shop rollout status deployment/orders
```

The first line is the one-liner for "was it OOMKilled". If the previous version worked, roll back first and investigate afterwards; mitigation before diagnosis (item 8.1).

## Pitfalls

- `kubectl logs` without `--previous`. You see an empty or truncated log from the current attempt and conclude the application "prints nothing".
- Deleting the Pod to see if it helps. The ReplicaSet creates an identical one, and the crashed container's log is gone.
- Reading only the last few events. A Pod that has looped for hours has aged out the interesting events; `Restart Count` and `Last State` still tell the story.
- Fixing a slow start by raising `initialDelaySeconds`. It works until the next slower node; a startup probe is the fix.
- Looking at the wrong namespace. `No resources found in default namespace` means `-n` is missing, not that the Pod is gone.
- Trusting the image tag. `latest` may be a different image from the one you tested; `describe` shows the `Image ID` digest actually running.
- Assuming `Running` means working. A readiness failure keeps a healthy-looking Pod out of the Service; `kubectl get endpoints` shows whether it receives traffic.

## Check yourself

1. The Pod shows `CrashLoopBackOff`, `Exit Code: 137` and `Reason: OOMKilled`. Why is the application log empty, and what is the first change you make?
2. Events show `Liveness probe failed` and `Killing`, and `logs --previous` ends while Spring is still initialising beans. What is the cause, what is the wrong fix, and what is the right one?
3. `kubectl logs` prints nothing at all and Events mention `secret "orders-db-credentials" not found`. Which status word do you expect, and why does the kubelet never start the process?
4. The Pod is `Running` and `1/1 Ready` but the Service returns 502. Which step of this workflow still applies, and which object do you inspect next?

## Go deeper

- [Kubernetes: Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/) · the official walkthrough of `Pending`, crash loops and the commands above.
- [Kubernetes: Debug Running Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/) · `kubectl debug`, ephemeral containers and copying a Pod for debugging.
- [Kubernetes: Pod Lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) · container states, restart policy and the back-off rules.
- [kubectl Quick Reference](https://kubernetes.io/docs/reference/kubectl/quick-reference/) · the `jsonpath`, `--field-selector` and `--sort-by` forms used here.

---

Part of [DevOps & Delivery](../README.md) · item 4.8
