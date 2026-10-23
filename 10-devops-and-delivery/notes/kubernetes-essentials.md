# Kubernetes essentials: control loops, Pods, Deployments, Services and configuration

> **In one sentence:** You write the state you want (three replicas of an image, a Service in front of them, configuration in ConfigMaps and Secrets) into the API server, and controllers run reconciliation loops that move the observed state towards it, so every object is connected to the next by a name or a label selector, never by a command run on a machine.

**Why it matters:** Most deployment incidents on Kubernetes are not Kubernetes bugs: a Service selector that matches nothing, a `targetPort` that differs from `server.port`, a Secret that only exists in one namespace. If you can follow the chain Ingress to Service to Pod to ReplicaSet to Deployment, and the chain from a container's environment back to its ConfigMap, you can debug any of them. Interviewers ask for exactly that chain.

## The idea

**Architecture and the control loop.** The control plane is the API server (the only thing anyone talks to), etcd (its store), the scheduler and the controller manager. Each node runs a kubelet (starts containers through the container runtime) and kube-proxy (programs Service routing). Every object has `apiVersion`, `kind`, `metadata`, a `spec` (desired state) and a `status` (observed state). `kubectl apply -f` writes the spec; controllers watch for differences and act: the Deployment controller creates a ReplicaSet, the ReplicaSet controller counts Pods matching its selector and creates or deletes them, the scheduler assigns pending Pods to nodes, the kubelet starts the containers and reports status. Delete a Pod and the ReplicaSet controller replaces it within seconds; that is the loop working, not an error.

**Workloads.** A *Pod* is the unit of scheduling: one or more containers that share a network namespace (one IP, `localhost` between them) and volumes. Pods are ephemeral and get new IPs; nobody creates them directly for a service. A *Deployment* owns *ReplicaSets*, one per Pod template revision; changing the image creates a new ReplicaSet and the rollout shifts Pods from old to new (item 4.6), and `kubectl rollout undo` shifts them back. StatefulSets give stable names and storage, DaemonSets run one Pod per node, Jobs and CronJobs run to completion.

**Labels and selectors** are the glue. Labels are free key-value pairs in `metadata`; a selector picks objects by them. A Deployment's `spec.selector.matchLabels` must match its `template.metadata.labels` (the API rejects a mismatch). A Service's selector is independent, so a typo there silently yields an empty endpoint list, and a Service that selects only `app: orders` sends traffic to every version during a rollout.

**Services and DNS.** A Service gives a changing set of Pods one stable virtual IP and DNS name: `orders` inside the namespace, `orders.shop.svc.cluster.local` from anywhere. `port` is the Service's port; `targetPort` is the container's (a number or a port name). *ClusterIP* is internal only; *NodePort* also opens a port in the 30000 to 32767 range on every node; *LoadBalancer* asks the cloud for an external load balancer in front of a NodePort. An *Ingress* routes external HTTP by host and path to Services and terminates TLS; it needs an ingress controller (nginx, Traefik, a cloud one) selected by `ingressClassName`. The Gateway API is its more expressive successor.

**ConfigMaps and Secrets** hold key-value configuration and are consumed as environment variables (`envFrom`, `valueFrom`) or as mounted files. Mounted files update in place when the object changes (with a delay); environment variables never do, so a config change needs `kubectl rollout restart`. A Secret is base64-encoded, not encrypted: anyone who can `get secrets` in the namespace reads it in one command, and `kubectl get secret -o yaml` prints it. What makes it secret is RBAC, encryption at rest in etcd, and keeping the source of truth in a vault that an external secrets operator syncs from (item 4.4), never in Git.

**Namespaces** scope names, RBAC, quotas and network policies. A Pod can reach a Service in another namespace by its full DNS name, but it cannot reference a ConfigMap or Secret from another namespace.

## Example: a Spring Boot service, complete and annotated

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-config
  namespace: shop
data:
  SPRING_PROFILES_ACTIVE: prod
  SPRING_DATASOURCE_URL: jdbc:postgresql://orders-db.shop.svc.cluster.local:5432/orders
  SPRING_DATASOURCE_USERNAME: orders
  JAVA_TOOL_OPTIONS: -XX:MaxRAMPercentage=75.0
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: shop
  labels:
    app: orders
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
        version: "1.42.0"
    spec:
      securityContext:
        runAsNonRoot: true
      containers:
        - name: app
          image: ghcr.io/example/orders:sha-9f3c1d2e
          ports:
            - name: http
              containerPort: 8080
          envFrom:
            - configMapRef:
                name: orders-config
          env:
            - name: SPRING_DATASOURCE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db-credentials
                  key: password
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              memory: 1Gi
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
---
apiVersion: v1
kind: Service
metadata:
  name: orders
  namespace: shop
  labels:
    app: orders
spec:
  type: ClusterIP
  selector:
    app: orders
  ports:
    - name: http
      port: 80
      targetPort: http
```

1. The ConfigMap holds non-secret settings as environment variable names. Spring Boot's relaxed binding maps `SPRING_DATASOURCE_URL` to `spring.datasource.url`.
2. The Deployment's selector and the template's labels both say `app: orders`. The template carries an extra `version` label that the selector ignores, so changing it per release is allowed.
3. The password comes from a Secret that is not in this file. Create it from the vault or by hand, then apply: `kubectl -n shop create secret generic orders-db-credentials --from-literal=password='change-me'`.
4. `requests` size the scheduling and `limits.memory` gives the JVM a limit to work from (item 3.4); there is deliberately no CPU limit (item 4.5).
5. The probes point at Spring Boot Actuator's Kubernetes groups with default timings; the full probe discussion is item 4.5.
6. The Service selects `app: orders` only and maps port 80 to the container port named `http`, so renumbering `containerPort` needs no change here. Clients in the namespace call `http://orders/`.

Apply and follow the chain:

```bash
kubectl apply -f orders.yaml
kubectl -n shop get deploy,rs,pods,svc -l app=orders
kubectl -n shop get endpoints orders                 # the Pod IPs the Service currently routes to
kubectl -n shop rollout status deployment/orders
kubectl -n shop get secret orders-db-credentials -o jsonpath='{.data.password}' | base64 -d
```

An Ingress for the same Service, if the cluster has an nginx ingress controller:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: orders
  namespace: shop
spec:
  ingressClassName: nginx
  rules:
    - host: orders.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: orders
                port:
                  name: http
```

## Pitfalls

- A Service selector that matches no Pods. Everything is `Running` and `Ready`, yet clients get connection refused or timeouts. `kubectl get endpoints <service>` shows `<none>`.
- `targetPort`, `containerPort` and `server.port` disagree. The Service forwards to a port nobody listens on; the readiness probe fails with "connection refused".
- Expecting a changed ConfigMap to reach running Pods through environment variables. It never does; run `kubectl rollout restart deployment/orders`, or mount it as a file and have the application reload.
- Committing Secrets to Git "because they are base64". They are plain text to every reader of the repository and of the cluster.
- Omitting `resources`. The Pod is `BestEffort`, first to be evicted under node pressure, and the JVM sizes itself from the node (items 3.4 and 4.5).
- Editing live objects with `kubectl edit`. The next `apply` from Git reverts the fix, or worse, nobody knows which cluster has which configuration. Put every change through Git (item 4.7).
- `runAsNonRoot: true` with an image that runs as root. The container never starts; the status is `CreateContainerConfigError` with "container has runAsNonRoot and image will run as root".

## Check yourself

1. You change `replicas: 3` to `5` and apply. Name each controller that acts, in order, until five Pods receive traffic.
2. Pods are `Running` and `1/1 Ready`, but `curl http://orders` from another Pod in the namespace times out. Which three fields do you compare, and which command shows the answer in one line?
3. Why is a Kubernetes Secret not secret on its own, and which two measures make it one in practice?
4. During a rollout, Pods labelled `version: "1.41.0"` and `"1.42.0"` both receive traffic through the Service. Why, and what would you change to route only to the new version?

## Go deeper

- [Kubernetes: Concepts](https://kubernetes.io/docs/concepts/) · the reference for every object above; read the Overview and Workloads sections first.
- [Kubernetes Basics tutorial](https://kubernetes.io/docs/tutorials/kubernetes-basics/) · hands-on: deploy, expose, scale, update.
- [Kubernetes: Services, Load Balancing, and Networking](https://kubernetes.io/docs/concepts/services-networking/) · Service types, DNS, Ingress and the Gateway API.
- [Kubernetes: Configuration](https://kubernetes.io/docs/concepts/configuration/) · ConfigMaps, Secrets and the honest page on what Secrets do and do not protect.
- [External Secrets Operator](https://external-secrets.io/) · syncing Secrets from a vault instead of storing them in Git.
- [kubectl Quick Reference](https://kubernetes.io/docs/reference/kubectl/quick-reference/) · the commands used here and the ones you will need next.

---

Part of [DevOps & Delivery](../README.md) · items 4.1, 4.2, 4.3, 4.4
