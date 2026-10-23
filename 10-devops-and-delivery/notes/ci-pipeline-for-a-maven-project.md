# A CI pipeline for a Maven project with GitHub Actions

> **In one sentence:** Continuous integration means every push is built and tested the same way by a machine within minutes, and a pipeline written as code makes that build reproducible: check out, set up a JDK with a dependency cache, run `mvn verify` including Testcontainers, scan, and build and push an image only from the main branch.

**Why it matters:** A slow or flaky pipeline quietly changes how a team works: people batch changes, skip tests and merge on green-ish. Knowing what each stage does also lets you debug the classic "passes locally, fails in CI" in minutes. Interviewers ask you to sketch a pipeline to see whether you separate integration (every commit) from delivery (promotion to environments).

## The idea

**CI principles.** One integration branch; everyone merges to it at least daily (item 1.1). Every commit triggers an automated build that is *self-testing*: it fails if any test fails. Feedback arrives in under ten minutes, a red build is the team's first priority, and the build is *deterministic*: the same commit produces the same result because tool versions, plugin versions and dependencies are pinned and nothing is resolved as `LATEST`. Caching speeds up dependency downloads; it must never cache results.

**Pipeline anatomy (GitHub Actions vocabulary).** A workflow file has triggers (`on`), jobs (parallel unless connected with `needs`), and steps (reusable actions or shell `run` commands) executed on runners. Artifacts move files between jobs; environments hold secrets and approval rules; a matrix runs the same job across versions; `permissions` limits what the automatic `GITHUB_TOKEN` can do; `concurrency` cancels superseded runs.

**Mapping to Maven.** `mvn -B verify` is the whole validation in one command: compile, unit tests (Surefire in the `test` phase), package, integration tests (Failsafe runs `*IT` classes in `integration-test` and fails the build in `verify`), and any plugin bound to `verify` in the POM: SpotBugs (`spotbugs:check`), Checkstyle (`checkstyle:check`), OWASP Dependency-Check. Binding them in the POM means CI and your laptop run exactly the same checks. Testcontainers needs a Docker daemon; GitHub-hosted Ubuntu runners have one, so `@Testcontainers` tests run with no extra configuration.

**Where delivery starts.** The image is built once, from a commit that passed verification, tagged with that commit's SHA (never a mutable `latest`) and pushed to a registry. Deployment is a separate job gated by an environment with required reviewers, or a GitOps commit that a controller applies (items 2.4 and 4.7).

## Example: `.github/workflows/ci.yaml`, annotated

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - name: Compile, test, integration-test and analyse
        run: ./mvnw -B -ntp verify
      - name: Dependency vulnerability scan
        run: ./mvnw -B -ntp org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=7 -DnvdApiKey=${{ secrets.NVD_API_KEY }}
      - uses: actions/upload-artifact@v7
        if: always()
        with:
          name: test-reports
          path: |
            target/surefire-reports/
            target/failsafe-reports/
          if-no-files-found: ignore

  image:
    needs: verify
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      tag: ${{ steps.meta.outputs.tags }}
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: meta
        uses: docker/metadata-action@v6
        with:
          images: ghcr.io/${{ github.repository }}
          tags: type=sha,format=long
      - uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ${{ steps.meta.outputs.tags }}
          severity: CRITICAL,HIGH
          ignore-unfixed: true
          exit-code: "1"

  deploy:
    needs: image
    runs-on: ubuntu-latest
    environment: production
    steps:
      - run: echo "deploy ${{ needs.image.outputs.tag }} by updating the image tag in the manifests repository"
```

1. `on` runs the workflow for every pull request and for pushes to `main`. `concurrency` cancels an older run of the same pull request when a new commit arrives, but never cancels a `main` build.
2. `permissions: contents: read` at the top gives the token the minimum; only the `image` job adds `packages: write` for the registry.
3. `actions/setup-java` with `cache: maven` restores `~/.m2/repository` keyed on the hashes of the POM files, so dependencies are downloaded only when they change. It never caches `target/`.
4. `./mvnw -B -ntp verify`: batch mode and no transfer progress keep the log readable. Static analysis runs here because the plugins are bound to `verify` in the POM, not as separate CI steps.
5. The OWASP step scans the dependency tree against the NVD and fails on CVSS 7 or higher. The plugin version is declared in the POM's `pluginManagement`; `NVD_API_KEY` is a repository secret, because the unauthenticated NVD API is rate limited to the point of timeouts.
6. `upload-artifact` with `if: always()` keeps the Surefire and Failsafe reports when tests fail, which is exactly when you want them.
7. The `image` job runs only for pushes to `main`. Pull requests from forks have no access to secrets, and an image per pull request is wasted registry space.
8. `metadata-action` produces `ghcr.io/<owner>/<repo>:sha-<full commit sha>` and OCI labels, and lowercases the name, which GHCR requires. One tag per build keeps `steps.meta.outputs.tags` a single value that Trivy and the deploy job can reuse.
9. `build-push-action` builds with BuildKit, pushes, and stores layer cache in the GitHub Actions cache. Note that `type=gha` caches image layers but not the contents of `RUN --mount=type=cache` directories, so a Dockerfile that runs Maven inside (item 3.2) downloads dependencies again. If that is too slow, build the jar in `verify`, pass it as an artifact, and use a Dockerfile that only extracts and copies it.
10. Trivy scans the pushed image, OS packages and Java libraries alike, and fails the job on fixable critical or high findings.
11. `environment: production` pauses the `deploy` job until the environment's required reviewers approve, and exposes that environment's secrets. The step itself depends on your platform: a `kubectl set image` with cluster credentials, or a commit to a manifests repository that Argo CD or Flux applies.

## Pitfalls

- Caching the wrong thing. A cache key that does not include the POM hashes serves stale dependencies; caching `target/` makes incremental compilation hide broken builds.
- `mvn install` in CI. It writes to the local repository for no reader; `verify` runs everything that matters.
- Unpinned actions. `uses: some/action@main` executes whatever that branch contains tomorrow. Pin to a major tag, or to a commit SHA with the version in a comment for supply-chain hardening (item 2.6).
- Building images on pull requests from forks. The job fails on the missing registry secret, and a build that pushes anything from an unreviewed branch is a security problem.
- Tolerating flaky tests with `rerunFailingTestsCount`. The pipeline goes green and the race condition goes to production.
- "Works locally." Runners run in UTC with a fresh Docker daemon and no `~/.m2/settings.xml`. Tests that depend on your time zone, a local file or a mirror configuration fail only in CI.
- A single 25-minute job. Unit tests, integration tests and analysis can run as parallel jobs on separate runners; only the image build must wait for them.
- Deploying `latest`. Nobody can tell which commit is running, and a rollback has nothing to roll back to. Deploy the SHA tag (item 6.4).

## Check yourself

1. Why does the `image` job run only on pushes to `main`, and what exactly would fail or be dangerous if it also ran on pull requests from forks?
2. `mvn verify` passes on your laptop but Testcontainers fails in CI with "Could not find a valid Docker environment". List three differences between the two environments that could explain it.
3. Which parts of this workflow make the build non-deterministic even though it is "pipelines as code"? Name at least three and say how you would pin each.
4. The pipeline takes 25 minutes. Which jobs could run in parallel, what must stay sequential, and what would you measure first before splitting?

## Go deeper

- [Martin Fowler: Continuous Integration](https://martinfowler.com/articles/continuousIntegration.html) · the principles every pipeline is trying to implement.
- [GitHub Actions: Building and testing Java with Maven](https://docs.github.com/en/actions/use-cases-and-examples/building-and-testing/building-and-testing-java-with-maven) · the official starter this workflow extends.
- [GitHub Actions documentation](https://docs.github.com/en/actions) · workflow syntax, environments, permissions, concurrency, caching.
- [docker/build-push-action](https://github.com/docker/build-push-action) · the inputs used above and the `type=gha` cache.
- [Renovate](https://docs.renovatebot.com/) · keeps the action versions, base images and dependencies in this pipeline pinned yet current.

---

Part of [DevOps & Delivery](../README.md) · items 2.1, 2.2, 2.3
