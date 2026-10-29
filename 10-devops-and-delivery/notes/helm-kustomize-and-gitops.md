# Helm, Kustomize and GitOps

> **In one sentence:** Helm packages Kubernetes manifests as templated charts with versioned releases, Kustomize layers patches over plain YAML without templates, and GitOps makes a Git repository the only way to change the cluster, with a controller such as Argo CD or Flux continuously reconciling the cluster to what the repository says.

**Why it matters:** A service needs a Deployment, a Service, a ConfigMap, probes and resource limits per environment; copying YAML per environment is how staging and production drift apart silently. `kubectl apply` from laptops is how nobody knows what is running or who changed it. The combination of a packaging tool and a GitOps controller gives you a reviewable, auditable, rollback-able history of every environment, and it is what most Kubernetes teams you join will be running.

## The idea

**Helm.** A chart is a directory: `Chart.yaml` (name, version, appVersion), `values.yaml` (defaults), and `templates/` with Go-templated manifests that read `.Values`, `.Release` and `.Chart`. `helm install` renders the templates with the values and applies them; `helm upgrade --install` is the idempotent form used from pipelines; every install or upgrade is a numbered *release revision* stored in the cluster (as a Secret in the release namespace), so `helm history` and `helm rollback` work without Git. Helm is the format third-party software ships in (PostgreSQL operators, ingress controllers, Prometheus), so you will consume charts even if you never write one. The cost is the template language: logic lives in `{{ if }}` blocks, indentation is handled with `nindent`, and a rendering error is found with `helm template`, not by the API server.

**Kustomize.** No templates. A *base* holds complete, valid manifests; an *overlay* references the base and declares changes: a namespace, a name prefix, common labels, image tags, replicas, and *patches* (strategic merge or JSON patch) that are merged into the base by resource name. The output is plain YAML you can read and diff, and `kubectl` has it built in (`kubectl kustomize <dir>` to render, `kubectl apply -k <dir>` to apply). Kustomize has no release history; rollbacks happen in Git. It fits your own services; Helm fits things you install from outside. They combine: an overlay can patch the output of `helm template`, and both Argo CD and Flux render either.

**GitOps.** Four properties: the desired state is declarative; it is versioned in Git; approved changes are applied automatically; and software agents continuously reconcile the live state with the desired state. In practice a *manifests repository* holds overlays or chart values per environment; the application pipeline's promotion step (item 2.4) is a commit that changes an image digest in the production overlay; a controller in the cluster notices the commit, renders, applies, and reports health. Nobody holds production credentials on a laptop. Drift (a `kubectl edit` in production) is detected and, with self-heal enabled, reverted. A rollback is `git revert`. The controller also gives you the diff between Git and the cluster at any time, which is the answer to "what is actually running".

**Argo CD and Flux.** Argo CD models an `Application` resource (source repository, path, target revision, destination cluster and namespace, sync policy) and ships a UI that shows the resource tree, health and diffs. Flux models the same with `GitRepository` plus `Kustomization` or `HelmRelease` resources and no UI of its own. Both support Helm, Kustomize and plain directories, automated sync with pruning, and health checks on the rolled-out resources.

## Example: one base, a production overlay, rendered for real

The base is a complete Deployment with one replica, the default profile and an untagged image:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 1
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
        - name: orders
          image: ghcr.io/example/orders
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: default
```

`base/kustomization.yaml` just lists it:

```yaml
resources:
  - deployment.yaml
```

The production overlay sets the namespace, pins the image tag, and patches replicas, profile and resources. `overlays/production/kustomization.yaml`:

```yaml
namespace: orders-production
resources:
  - ../../base
patches:
  - path: replicas.yaml
images:
  - name: ghcr.io/example/orders
    newTag: sha-000f05c
```

`overlays/production/replicas.yaml` is a strategic merge patch: only the fields to change, identified by kind, name and, inside lists, by the container's `name`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: orders
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: production
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              memory: 1Gi
```

Rendering it with the Kustomize built into `kubectl`:

```bash
$ kubectl kustomize overlays/production
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders
  namespace: orders-production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders
  template:
    metadata:
      labels:
        app: orders
    spec:
      containers:
      - env:
        - name: SPRING_PROFILES_ACTIVE
          value: production
        image: ghcr.io/example/orders:sha-000f05c
        name: orders
        ports:
        - containerPort: 8080
        resources:
          limits:
            memory: 1Gi
          requests:
            cpu: 500m
            memory: 1Gi
```

The env entry was replaced rather than appended because strategic merge patches merge list items by their `name` key; `ports` from the base survived untouched. The promotion from item 2.4 is a one-line change to `newTag` (or `digest:` for a digest) in this file, in a pull request.

The same Deployment as a Helm template fragment, to show the trade:

```yaml
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: {{ .Values.springProfile | quote }}
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
```

with `values-production.yaml` supplying `replicaCount: 3`, `springProfile: production` and the `resources` map, deployed by `helm upgrade --install orders ./chart -f values-production.yaml --set image.tag=sha-000f05c --namespace orders-production`. Run `helm template orders ./chart -f values-production.yaml` first and read the output; a `nindent` off by two produces YAML that is valid but means something else.

The Argo CD `Application` that keeps the overlay applied:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: orders-production
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/manifests.git
    targetRevision: main
    path: orders/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: orders-production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
```

`prune: true` deletes resources removed from Git; `selfHeal: true` reverts manual changes in the cluster. Both are what you want for a GitOps-managed service, and both are what people switch off when they are not ready to stop using `kubectl edit`.

## Pitfalls

- Templating everything. A chart whose `values.yaml` mirrors the entire Deployment is an indirection with no benefit; template what varies between environments and leave the rest literal.
- A strategic merge patch that does not match. A typo in `metadata.name` or a missing container `name` makes Kustomize fail with "no matches for Id", or, for a list without a merge key, replace the whole list. Always render and read the output before applying.
- Secrets in the manifests repository. GitOps makes the repository the source of truth, including for anything you commit by mistake. Use an external secrets operator or Sealed Secrets (item 4.4).
- `latest` in `newTag` or in values. The controller sees no change in Git and never redeploys; the digest or SHA tag is what makes a promotion a diff (item 6.4).
- Disabling `selfHeal` "just for now". The cluster drifts from Git within a week and the next sync surprises everyone.
- Helm release history as the rollback plan while GitOps is in charge. `helm rollback` changes the cluster; the controller sees the drift and rolls it forward again. Under GitOps, revert the commit.
- Application repository and manifests repository in one. A manifest change then triggers the full build pipeline, and a pipeline commit that bumps the tag triggers itself; separate them, or filter paths carefully.
- Trusting `helm upgrade` to wait. Without `--wait` it returns as soon as the API server accepted the objects, not when the Pods are ready; with it, a failed rollout fails the command, which is what a pipeline needs.

## Check yourself

1. Your team maintains three environments with three copies of the same YAML. Describe the Kustomize layout that replaces them and what goes in the base versus the overlays.
2. A patch adds a second entry to a container's `args` and the rendered output shows only the new one, while a patch adding a second `env` entry keeps both. Why do the two lists behave differently under a strategic merge patch?
3. An engineer fixed a production incident with `kubectl scale deployment/orders --replicas=10`. Under Argo CD with `selfHeal: true`, what happens next, and what should the fix have been?
4. When would you choose Helm over Kustomize for a service you own, and what do you give up?

## Go deeper

- [Helm](https://helm.sh/docs/) · chart structure, template functions, `helm template` and the release lifecycle.
- [Kubernetes: Declarative Management of Kubernetes Objects Using Kustomize](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/) · bases, overlays, patches and the built-in `kubectl -k` commands.
- [Argo CD](https://argo-cd.readthedocs.io/) · the `Application` resource, sync policies, health assessment and the UI.
- [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) · what the controller is reconciling once your manifests are applied (item 4.6).

---

Part of [DevOps & Delivery](../README.md) · item 4.7
