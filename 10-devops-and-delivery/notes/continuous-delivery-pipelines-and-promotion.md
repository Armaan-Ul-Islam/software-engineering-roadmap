# Continuous delivery: deployment pipelines, promotion and rollbacks

> **In one sentence:** Continuous delivery means every commit that passes the pipeline produces one immutable artifact that could go to production at the push of a button, continuous deployment removes the button, and promotion means the same artifact moves through environments while only its configuration changes.

**Why it matters:** The expensive failures in delivery are not broken builds but "it worked in staging": a different jar, a different base image or a different flag went to production, so staging proved nothing. The second expensive failure is the rollback that does not exist, because `latest` was overwritten or the database schema already moved. Interviewers ask "what happens after CI goes green" to see whether you know that building and deploying are different problems.

## The idea

**Delivery versus deployment.** In continuous delivery, the pipeline takes every change through build, automated tests and at least one production-like environment, and keeps the software releasable at all times; a human decides when a release goes out. In continuous deployment, there is no human decision: every change that passes goes to production. The difference is one gate. Both require the same pipeline, trunk-based development (item 1.1) and feature flags, because the trunk must always be deployable.

**The deployment pipeline.** Humble and Farley's shape still holds: a commit stage that compiles, runs unit tests and produces the artifact (item 2.3); automated acceptance tests against a deployed instance; optional capacity and exploratory stages; then promotion to production. Each stage gives faster feedback than the next and runs only if the previous one passed. The artifact is built exactly once, in the commit stage, and every later stage deploys that artifact. Rebuilding for production is how "worked in staging" happens.

**Immutable artifacts.** The artifact is the image (or jar) plus its digest. A tag like `sha-000f05c` points at one commit; an image digest `sha256:...` points at one set of bytes, and the digest is what a deployment should pin. `latest` and `1.2` are mutable pointers: the same name means different bytes on different days, which makes "deploy the version from Tuesday" impossible to state. Environments differ only through configuration injected at deploy time (item 6.3): profile, URLs, secrets, resource limits.

**Promotion and approvals.** Promotion is a record, not a rebuild: "digest X is now approved for production". In GitHub Actions the mechanism is an environment with protection rules; a job with `environment: production` waits for the required reviewers and only then receives the environment's secrets. In a GitOps setup (item 4.7) the same promotion is a commit that changes the image digest in the production overlay, and the pull request review is the approval. Either way, the approval should concern the artifact and the moment, not a re-run of the tests.

**Rollback versus forward fix.** A rollback redeploys the previous immutable artifact; it is the fastest mitigation when the cause is the new version and the old one still works against the current state. A forward fix ships a new version with the problem fixed; it is right when the old version cannot run any more (schema changed, a dependency moved, the fault was already in the old version too) or when the fix is small and the pipeline is fast. Decide which you reach for before the incident (item 8.1): a rollback that has never been rehearsed is not a rollback, it is a hope.

**Database rollbacks are rarely possible.** Application code is stateless and replaceable; the database has absorbed writes since the deploy. Reverting a migration means losing those writes or writing a reverse migration that handles data the new version created. That is why schema changes are made backwards compatible and shipped ahead of the code that needs them (expand-contract, item 6.2): the code can roll back one version without touching the schema. Treat "can version N run against the schema of N+1" as a required property of every release.

## Example: a promotion workflow in GitHub Actions

The CI workflow from item 2.3 pushes `ghcr.io/example/orders:sha-<commit>` and records the digest. This second workflow deploys that digest, first to staging automatically, then to production after approval, without rebuilding anything.

```yaml
name: deploy

on:
  workflow_dispatch:
    inputs:
      image_digest:
        description: "Image digest to deploy, as sha256:..."
        required: true

permissions:
  contents: read

concurrency:
  group: deploy
  cancel-in-progress: false

jobs:
  staging:
    runs-on: ubuntu-latest
    environment:
      name: staging
      url: https://orders.staging.example.com
    steps:
      - uses: actions/checkout@v7
      - name: Deploy to staging
        run: ./deploy.sh staging "ghcr.io/example/orders@${{ inputs.image_digest }}"
      - name: Smoke test
        run: curl --fail --silent https://orders.staging.example.com/actuator/health

  production:
    needs: staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://orders.example.com
    steps:
      - uses: actions/checkout@v7
      - name: Deploy to production
        run: ./deploy.sh production "ghcr.io/example/orders@${{ inputs.image_digest }}"
      - name: Smoke test
        run: curl --fail --silent https://orders.example.com/actuator/health
```

1. The input is a digest, so the two jobs cannot deploy different bytes, and the run's log says exactly what went out.
2. `concurrency: deploy` with `cancel-in-progress: false` queues deployments instead of running two at once or cancelling one halfway.
3. The `staging` environment has no reviewers, so the job runs immediately; `production` has required reviewers configured in the repository settings, so the job pauses, notifies them, and continues only after approval. That pause is the "button" of continuous delivery; remove the reviewers and the same workflow is continuous deployment.
4. Each job's secrets (cluster credentials) come from its environment, so the staging job never holds production credentials.
5. `deploy.sh` is whatever your platform needs: a `kubectl set image`, a `helm upgrade --install` with the digest as a value, or a commit to the manifests repository (item 4.7).

A rollback is the same workflow run with the previous digest. Keep the last few deployed digests somewhere obvious (the environment's deployment history on GitHub shows them), and rehearse the rollback in staging once a month. In Kubernetes, `kubectl rollout undo deployment/orders` does the same thing from the Deployment's revision history, but a GitOps controller will revert it unless the manifests change too.

The decision at 02:00, in one table:

| Situation | Reach for | Why |
|---|---|---|
| New version returns 500s, schema unchanged | rollback | fastest known-good state |
| New version applied an additive migration, old code ignores the new column | rollback | expand-contract made the old code compatible |
| New version renamed a column in one step | forward fix | old code would fail against the new schema; the one-step rename was the mistake |
| Fault exists in the old version too (expired certificate, upstream change) | forward fix | rolling back changes nothing |
| Fix is a one-line config change | config change | neither; configuration is deployed separately (item 6.3) |

## Pitfalls

- Rebuilding for production "to be safe". A new build means new timestamps, possibly newer transitive dependencies or a moved base image tag; staging tested something else.
- Deploying `latest` or a moving tag. Nothing says which bytes are running, and the previous version is gone the moment the tag moves. Deploy digests or immutable SHA tags.
- Promotion that re-runs the tests. If the tests take 40 minutes, every production deploy takes 40 minutes longer than it should and the tests are now testing the test environment, not the artifact.
- Approvals that nobody reads. A rule that requires a click produces clicks. Require review of the change, in the pull request, and let the deploy approval be about timing.
- An untested rollback. Old images deleted by a registry retention policy, a Helm chart that cannot go backwards, a `rollout undo` that undoes to a revision with a different ConfigMap. Rehearse it.
- Rolling back the application and forgetting that the schema moved. The old version starts, cannot find a column and crash-loops; now two versions are broken.
- Manual steps "just for production". A `kubectl edit` in production is a change the pipeline does not know about and the next deploy silently reverts.
- Two deploys in flight. Without a concurrency lock, run 42 and run 43 race and the environment ends up with whichever finished last.

## Check yourself

1. Your staging deploy passes but production fails with a `NoSuchMethodError` from a transitive dependency. Which property of the pipeline was violated, and how does deploying by digest prevent it?
2. Explain the one difference between continuous delivery and continuous deployment in terms of the workflow above, and what else must be true of the team before removing it.
3. A release added a `NOT NULL` column with a default and the new code writes it; the old code never reads it. The release is failing for an unrelated reason. Can you roll back? What if the column had been renamed instead?
4. The registry's retention policy deletes images older than 30 days and your last successful deploy was 35 days ago. What does that do to your rollback options, and what would you change?

## Go deeper

- [Continuous Delivery](https://continuousdelivery.com/) · Jez Humble's site; the deployment pipeline, the principles and the evidence in short form.
- [GitHub Actions documentation](https://docs.github.com/en/actions) · environments, required reviewers, `workflow_dispatch` inputs and concurrency groups.
- [DORA](https://dora.dev/) · what delivery performance looks like when this works (item 8.4).
- [Martin Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) · turning a feature off is often the cheapest rollback of all.

---

Part of [DevOps & Delivery](../README.md) · items 2.4, 6.4
