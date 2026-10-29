# DevOps & Delivery

> Getting code from a laptop to production and keeping it there: Git workflows, CI/CD pipelines, Docker and the JVM in containers, Kubernetes essentials, observability (logs, metrics, traces), deployment strategies, Linux troubleshooting and incident response.

**Prerequisites:** [Foundations](../01-foundations/README.md)

**Done when you can:**

- Write a Dockerfile for a Spring Boot service that builds fast, stays small, runs as non-root, and sizes the JVM from the container limits.
- Set up a CI pipeline that builds, tests, scans and publishes an image, and a delivery step that deploys it safely.
- Explain Kubernetes pods, deployments, services, ingress, probes, requests and limits, and autoscaling, and debug a crash-looping pod.
- Instrument a service with structured logs, RED metrics and traces, and alert on SLOs rather than on CPU.
- Run a zero-downtime deployment that includes a database migration, using expand-contract.
- Lead an incident: triage, mitigate, communicate, and write a blameless postmortem.

## Roadmap

### 1. Git and collaboration workflows

- [ ] 1.1 Trunk-based development vs Git flow vs GitHub flow; short-lived branches; feature flags to decouple deploy from release · [notes](notes/trunk-based-development-and-feature-flags.md) · [Trunk Based Development](https://trunkbaseddevelopment.com/) · [Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)
- [ ] 1.2 Pull requests that get reviewed: small, focused, with context; stacked changes; Conventional Commits and generated changelogs · [notes](notes/pull-requests-commits-and-versioning.md) · [Google: Code Review Developer Guide](https://google.github.io/eng-practices/review/) · [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] 1.3 Release versioning: semantic versioning, tags, release notes, release branches when you really need them · [notes](notes/pull-requests-commits-and-versioning.md) · [Semantic Versioning](https://semver.org/)
- [ ] 1.4 Monorepos vs polyrepos; code ownership; `CODEOWNERS` and branch protection · [GitHub: About code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)

### 2. Continuous integration and delivery

- [ ] 2.1 CI principles: every commit builds and tests, fast feedback, deterministic builds, dependency caching · [notes](notes/ci-pipeline-for-a-maven-project.md) · [Fowler: Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html)
- [ ] 2.2 Pipelines as code: GitHub Actions, GitLab CI, Jenkins; stages, artifacts, environments, secrets, matrix builds · [notes](notes/ci-pipeline-for-a-maven-project.md) · [GitHub Actions documentation](https://docs.github.com/en/actions) · [Jenkins User Documentation](https://www.jenkins.io/doc/)
- [ ] 2.3 A Maven pipeline: compile, unit tests, integration tests with Testcontainers, static analysis, dependency scan, image build and push · [notes](notes/ci-pipeline-for-a-maven-project.md) · [GitHub Actions: Building and testing Java with Maven](https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-java-with-maven)
- [ ] 2.4 Continuous delivery vs continuous deployment; deployment pipelines; promotion between environments; approvals · [notes](notes/continuous-delivery-pipelines-and-promotion.md) · [Continuous Delivery](https://continuousdelivery.com/) · [DORA](https://dora.dev/)
- [ ] 2.5 Artifact and image registries; provenance and signing with Sigstore; reproducible builds · [notes](notes/supply-chain-security-sboms-and-signing.md) · [Sigstore](https://www.sigstore.dev/)
- [ ] 2.6 Supply-chain hygiene: pinned dependencies and lockfiles, Dependabot or Renovate, SCA scanning, SBOMs · [notes](notes/supply-chain-security-sboms-and-signing.md) · [Renovate](https://docs.renovatebot.com/) · [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/) · [CycloneDX](https://cyclonedx.org/)

### 3. Docker and containers

- [ ] 3.1 What a container is: namespaces, cgroups, union filesystems; images vs containers; layers and build caching · [notes](notes/docker-fundamentals-for-spring-boot.md) · [Docker: Get started](https://docs.docker.com/get-started/) · [Julia Evans: What even is a container](https://jvns.ca/blog/2016/10/10/what-even-is-a-container/)
- [ ] 3.2 Writing good Dockerfiles: multi-stage builds, layer ordering, `.dockerignore`, non-root users, pinned base images · [notes](notes/docker-fundamentals-for-spring-boot.md) · [Docker: Building best practices](https://docs.docker.com/build/building/best-practices/)
- [ ] 3.3 Containerising Spring Boot: layered JARs, Cloud Native Buildpacks, Temurin and distroless base images, CDS and AOT for startup · [notes](notes/docker-fundamentals-for-spring-boot.md) · [Spring Boot: Efficient container images](https://docs.spring.io/spring-boot/reference/packaging/container-images/efficient-images.html) · [Docker: Java language-specific guide](https://docs.docker.com/guides/java/)
- [ ] 3.4 The JVM in a container: container awareness, `MaxRAMPercentage`, CPU quotas and `availableProcessors`, GC thread counts, OOM-killed vs `OutOfMemoryError` · [notes](notes/the-jvm-in-a-container.md) · [Microsoft: Containerize your Java applications](https://learn.microsoft.com/en-us/azure/developer/java/containers/overview)
- [ ] 3.5 Networking, volumes, environment and secrets; Docker Compose for local stacks (app, PostgreSQL, Redis) · [notes](notes/docker-compose-for-local-stacks.md) · [Docker Compose](https://docs.docker.com/compose/)
- [ ] 3.6 Image security: scanning with Trivy, minimal images, non-root, read-only filesystems · [notes](notes/supply-chain-security-sboms-and-signing.md) · [Trivy](https://trivy.dev/)

### 4. Kubernetes essentials

- [ ] 4.1 Architecture: control plane, nodes, kubelet, the API server and reconciliation loops; `kubectl` basics · [notes](notes/kubernetes-essentials.md) · [Kubernetes: Concepts](https://kubernetes.io/docs/concepts/) · [Kubernetes Basics tutorial](https://kubernetes.io/docs/tutorials/kubernetes-basics/)
- [ ] 4.2 Workloads: Pods, Deployments and ReplicaSets, StatefulSets, DaemonSets, Jobs and CronJobs · [notes](notes/kubernetes-essentials.md) · [Kubernetes: Workloads](https://kubernetes.io/docs/concepts/workloads/)
- [ ] 4.3 Networking: Services (ClusterIP, NodePort, LoadBalancer), Ingress and the Gateway API, cluster DNS, network policies · [notes](notes/kubernetes-essentials.md) · [Kubernetes: Services, Load Balancing, and Networking](https://kubernetes.io/docs/concepts/services-networking/)
- [ ] 4.4 Configuration: ConfigMaps, Secrets (and why they are not secret), environment vs mounted files, external secrets operators · [notes](notes/kubernetes-essentials.md) · [Kubernetes: Configuration](https://kubernetes.io/docs/concepts/configuration/) · [External Secrets Operator](https://external-secrets.io/)
- [ ] 4.5 Health and resources: liveness, readiness and startup probes; requests and limits; QoS classes; `OOMKilled`; the Horizontal Pod Autoscaler · [notes](notes/probes-resources-and-autoscaling-in-kubernetes.md) · [Kubernetes: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) · [Kubernetes: Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [ ] 4.6 Rollouts: rolling update parameters, `kubectl rollout`, PodDisruptionBudgets, graceful termination and `preStop` hooks · [notes](notes/probes-resources-and-autoscaling-in-kubernetes.md) · [Kubernetes: Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [ ] 4.7 Packaging and GitOps: Helm charts, Kustomize, Argo CD or Flux · [notes](notes/helm-kustomize-and-gitops.md) · [Helm](https://helm.sh/docs/) · [Argo CD](https://argo-cd.readthedocs.io/)
- [ ] 4.8 Debugging: `describe`, `logs`, `exec`, events; `CrashLoopBackOff`, `ImagePullBackOff`, pending pods · [notes](notes/debugging-a-crashlooping-pod.md) · [Kubernetes: Debug Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-pods/)
- [ ] 4.9 Kubernetes the Hard Way, once, to understand what managed clusters hide · [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way)

### 5. Observability

- [ ] 5.1 The three signals and the question each answers; structured logging with correlation IDs; log levels and sampling · [notes](notes/observability-logs-metrics-traces.md) · [OpenTelemetry: Observability primer](https://opentelemetry.io/docs/concepts/observability-primer/)
- [ ] 5.2 Metrics: counters, gauges, histograms; the RED and USE methods; Prometheus and PromQL basics; cardinality · [notes](notes/observability-logs-metrics-traces.md) · [Prometheus: Overview](https://prometheus.io/docs/introduction/overview/) · [Brendan Gregg: The USE Method](https://www.brendangregg.com/usemethod.html) · [Grafana: The RED Method](https://grafana.com/blog/2018/08/02/the-red-method-how-to-instrument-your-services/)
- [ ] 5.3 Distributed tracing: spans, context propagation, sampling; the OpenTelemetry SDK and Collector; Jaeger and Tempo · [notes](notes/observability-logs-metrics-traces.md) · [OpenTelemetry: Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [ ] 5.4 Dashboards and alerts: Grafana; alert on symptoms and SLOs, not causes; runbooks; on-call hygiene · [notes](notes/slos-and-alerting.md) · [Grafana tutorials](https://grafana.com/tutorials/) · [Google SRE Book: Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/)
- [ ] 5.5 SLIs, SLOs and error budgets; burn-rate alerting · [notes](notes/slos-and-alerting.md) · [SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/)
- [ ] 5.6 Log aggregation choices: Elasticsearch/OpenSearch, Loki, cloud-native services; the cost of retention · [Grafana Loki](https://grafana.com/docs/loki/latest/)

### 6. Deployment strategies and database changes

- [ ] 6.1 Rolling, blue/green, canary and shadow deployments; progressive delivery with Argo Rollouts or Flagger · [notes](notes/zero-downtime-deployments-and-expand-contract.md) · [Fowler: Blue Green Deployment](https://martinfowler.com/bliki/BlueGreenDeployment.html) · [Fowler: Canary Release](https://martinfowler.com/bliki/CanaryRelease.html)
- [ ] 6.2 Zero-downtime database changes: expand-contract, backwards-compatible migrations, dual writes and backfills, lock-safe DDL · [notes](notes/zero-downtime-deployments-and-expand-contract.md) · [Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html) · [Flyway documentation](https://documentation.red-gate.com/flyway)
- [ ] 6.3 Configuration and secrets across environments; feature-flag platforms · [The Twelve-Factor App: Config](https://12factor.net/config)
- [ ] 6.4 Rollbacks vs forward fixes; immutable artifacts; database rollbacks are rarely possible · [notes](notes/continuous-delivery-pipelines-and-promotion.md) · [Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html)

### 7. Linux operations and troubleshooting

- [ ] 7.1 Performance triage in 60 seconds: `uptime`, `dmesg`, `vmstat`, `mpstat`, `pidstat`, `iostat`, `free`, `sar`, `top` · [notes](notes/linux-performance-triage.md) · [Netflix: Linux Performance Analysis in 60,000 Milliseconds](https://netflixtechblog.com/linux-performance-analysis-in-60-000-milliseconds-accc10403c55) · [Brendan Gregg: Linux Performance](https://www.brendangregg.com/linuxperf.html)
- [ ] 7.2 Network and file-descriptor triage: `ss`, `lsof`, `tcpdump`, `curl -v`, `dig`; "too many open files"; ephemeral port exhaustion · [notes](notes/linux-performance-triage.md) · [Julia Evans: tcpdump is amazing](https://jvns.ca/blog/2016/03/16/tcpdump-is-amazing/)
- [ ] 7.3 systemd services, journald, log rotation, cron and timers · [notes](notes/systemd-and-journald-essentials.md) · [Arch Wiki: systemd](https://wiki.archlinux.org/title/Systemd)
- [ ] 7.4 Disk and memory: `df`, `du`, inodes, the page cache and "free" memory, swap, OOM-killer logs · [notes](notes/linux-performance-triage.md) · [Linux ate my RAM](https://www.linuxatemyram.com/)
- [ ] 7.5 Automation with shell scripts and safety rails; Makefiles or `just` as task runners · [BashGuide](https://mywiki.wooledge.org/BashGuide) · [just](https://just.systems/)

### 8. Incident response and reliability culture

- [ ] 8.1 Incident roles, severity levels, communication cadence, status pages · [notes](notes/incident-response-and-postmortems.md) · [PagerDuty Incident Response](https://response.pagerduty.com/)
- [ ] 8.2 Blameless postmortems: timeline, contributing factors, action items that get done · [notes](notes/incident-response-and-postmortems.md) · [Google SRE Book: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [ ] 8.3 Toil, automation, error budgets and the SRE mindset inside a product team · [notes](notes/dora-metrics-and-the-sre-mindset.md) · [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [ ] 8.4 DORA metrics and what elite delivery performance looks like · [notes](notes/dora-metrics-and-the-sre-mindset.md) · [DORA](https://dora.dev/) · [Accelerate](https://itrevolution.com/product/accelerate/)

## Resources

### Start here

- [Docker: Get started](https://docs.docker.com/get-started/) and [Docker: Building best practices](https://docs.docker.com/build/building/best-practices/) · the official guides are the right first read.
- [Kubernetes Basics](https://kubernetes.io/docs/tutorials/kubernetes-basics/) · the interactive tutorial, then the Concepts section.
- [Site Reliability Engineering](https://sre.google/sre-book/table-of-contents/) · free; chapters on SLOs, monitoring, release engineering and postmortems.
- [The Missing Semester of Your CS Education](https://missing.csail.mit.edu/) · shell, Git, and debugging tools.
- [Martin Fowler: Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) · the principles behind every pipeline.

### Books

- [Site Reliability Engineering](https://sre.google/books/) and [The Site Reliability Workbook](https://sre.google/workbook/table-of-contents/) · Google; free online.
- [Continuous Delivery](https://www.oreilly.com/library/view/continuous-delivery-reliable/9780321670250/) · Jez Humble and David Farley (paid).
- [Accelerate](https://itrevolution.com/product/accelerate/) · Forsgren, Humble and Kim; the research behind DORA (paid).
- [Kubernetes in Action, 2nd edition](https://www.manning.com/books/kubernetes-in-action-second-edition) · Marko Lukša (paid).
- [Systems Performance, 2nd edition](https://www.brendangregg.com/systems-performance-2nd-edition-book.html) · Brendan Gregg (paid).
- [Observability Engineering](https://info.honeycomb.io/observability-engineering-oreilly-book-2022) · Majors, Fong-Jones and Miranda; free from Honeycomb.

### Courses and videos

- [TechWorld with Nana](https://www.youtube.com/@TechWorldwithNana) · clear Docker, Kubernetes and CI/CD tutorials.
- [KodeKloud](https://kodekloud.com/) · hands-on Kubernetes and DevOps labs (paid).
- [Kubernetes The Hard Way](https://github.com/kelseyhightower/kubernetes-the-hard-way) · Kelsey Hightower's manual cluster build.
- [Grafana tutorials](https://grafana.com/tutorials/) · Prometheus, Loki, Tempo and dashboards hands-on.

### References

- [kubectl Quick Reference](https://kubernetes.io/docs/reference/kubectl/quick-reference/) · the cheat sheet.
- [OpenTelemetry documentation](https://opentelemetry.io/docs/) and [Prometheus documentation](https://prometheus.io/docs/introduction/overview/) · the primary sources for observability.
- [The Twelve-Factor App](https://12factor.net/) · still the baseline for deployable services.
- [DORA](https://dora.dev/) · research and the four key metrics.
- [roadmap.sh: DevOps](https://roadmap.sh/devops), [Docker](https://roadmap.sh/docker), [Kubernetes](https://roadmap.sh/kubernetes) · visual overviews.
