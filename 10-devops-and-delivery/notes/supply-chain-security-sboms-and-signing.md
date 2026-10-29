# Supply-chain security: pinning, SBOMs, scanning and signing

> **In one sentence:** Everything that ends up in your image came from somewhere else, so you pin what you take (versions, digests, action SHAs), write down what you took (an SBOM), check it against known vulnerabilities (SCA and image scanning), and sign what you produced so that the cluster can refuse anything that was not built by your pipeline.

**Why it matters:** When Log4Shell was disclosed, teams with an inventory of what each deployed image contained could list the affected services in minutes; the rest searched jars by hand for days. Compromised build tools and typosquatted packages are now a routine attack, and the question auditors and customers ask is "prove that this image was built from this commit by your pipeline". Interviewers ask about SBOMs and signing because the answer shows whether you think of the pipeline as part of the product's security boundary.

## The idea

**Pin inputs.** Maven resolves fixed versions from the POM, so a Maven build is already pinned at the direct-dependency level; the Enforcer plugin's `requireUpperBoundDeps` and `dependencyConvergence` rules catch transitive drift. Base images are pinned by digest (`eclipse-temurin:21-jre-jammy@sha256:...`), not by tag. GitHub Actions are pinned by commit SHA with the version in a comment (`uses: actions/checkout@<sha> # v7.0.0`), because a tag like `v7` can be moved by whoever controls the action's repository. Pinning freezes the problem; a bot such as Dependabot or Renovate thaws it on your schedule by opening a pull request per upgrade, which CI tests like any other change.

**Reproducible builds.** The same source and the same inputs should give the same bytes. Maven does this when `project.build.outputTimestamp` is set in the POM, so jar entries get a fixed timestamp and the jar's hash is stable; BuildKit records the base image digest and build arguments in provenance. Reproducibility is what lets a third party rebuild and confirm that the published artifact matches the source.

**SBOM.** A software bill of materials lists every component in an artifact with its version, package URL (`pkg:maven/...`), hash and licence, in a machine-readable format: CycloneDX or SPDX. Generate it from the build (the CycloneDX Maven plugin reads the resolved dependency tree) or from the image (Syft or Trivy inspect installed packages and jars). Store it next to the artifact, ideally attached to the image as an attestation, so "which services ship `jackson-databind` 2.17.2" is a query, not an investigation.

**Scanning.** Software composition analysis compares the dependency list with vulnerability databases: OWASP Dependency-Check at build time (item 2.3), Trivy on the image, or Trivy on the SBOM itself (`trivy sbom bom.json`), which is faster and needs no image pull. Scan the final image, because the base image's OS packages matter as much as your jars. Fail the build on fixable critical and high findings, keep an explicit, dated ignore list for the rest, and rescan deployed images on a schedule, because new CVEs apply to old images.

**Provenance and signing with Sigstore.** `cosign` signs an image digest. In keyless mode the pipeline's OIDC identity (for GitHub Actions, the workflow in a repository) gets a short-lived certificate from Fulcio, the signature is recorded in the Rekor transparency log, and nobody has a private key to leak. The verifier checks the signature against the expected identity and issuer. A build can additionally attach attestations: SLSA provenance (which workflow, which commit, which inputs) and the SBOM. An admission controller (Kyverno or Sigstore's policy-controller) can then refuse any image in the cluster that lacks a valid signature from your pipeline.

**Image hygiene (item 3.6).** The attack surface is what is in the image and what the process may do. Minimal base images (a JRE image, or distroless such as `gcr.io/distroless/java21-debian12`) contain fewer packages to patch and no shell to use after a break-in. Run as a non-root `USER`, set `readOnlyRootFilesystem: true` with a writable `emptyDir` on `/tmp` (the JVM writes `hsperfdata` there), `allowPrivilegeEscalation: false`, and drop all capabilities. Scanning finds known problems; these settings limit unknown ones.

## Example: a real SBOM, then a pipeline that signs and attests

A POM with one dependency, `jackson-databind` 2.17.2, and the CycloneDX plugin:

```bash
$ mvn -B -ntp -q org.cyclonedx:cyclonedx-maven-plugin:2.9.1:makeBom -DoutputFormat=json
$ ls target/
bom.json
```

The result is CycloneDX 1.6 with three components, because the plugin walks the resolved tree. One component entry, trimmed to the fields that matter:

```json
{
  "type": "library",
  "group": "com.fasterxml.jackson.core",
  "name": "jackson-core",
  "version": "2.17.2",
  "purl": "pkg:maven/com.fasterxml.jackson.core/jackson-core@2.17.2?type=jar",
  "hashes": [
    {
      "alg": "SHA-256",
      "content": "721a189241dab0525d9e858e5cb604d3ecc0ede081e2de77d6f34fa5779a5b46"
    }
  ],
  "licenses": [
    {
      "license": {
        "id": "Apache-2.0"
      }
    }
  ]
}
```

The `dependencies` section records that `orders@2.0.0` depends on `jackson-databind`, which depends on `jackson-core` and `jackson-annotations`. A scanner matches the `purl` and version against its database; the hash lets you confirm that the jar in the image is the one listed.

The image job from item 2.3, extended with SBOM, signing and attestation. Only the new parts are shown:

```yaml
  image:
    needs: verify
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-buildx-action@v4
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - id: build
        uses: docker/build-push-action@v7
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:sha-${{ github.sha }}
          provenance: true
          sbom: true
      - uses: sigstore/cosign-installer@v3
      - name: Sign the image by digest
        run: cosign sign --yes "ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}"
      - name: Attach the Maven SBOM as an attestation
        run: |
          ./mvnw -B -ntp -q org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom -DoutputFormat=json
          cosign attest --yes --type cyclonedx --predicate target/bom.json \
            "ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}"
      - uses: aquasecurity/trivy-action@v0.36.0
        with:
          image-ref: ghcr.io/${{ github.repository }}@${{ steps.build.outputs.digest }}
          severity: CRITICAL,HIGH
          ignore-unfixed: true
          exit-code: "1"
```

1. `id-token: write` lets the job obtain an OIDC token; that token is the identity Fulcio certifies. No signing key is stored anywhere.
2. `provenance: true` and `sbom: true` make BuildKit attach its own provenance and an SBOM of the image contents; the Maven SBOM attested afterwards is more precise about Java dependencies than an image scan, so keep both.
3. Everything after the build uses the digest from `steps.build.outputs.digest`, never the tag: a signature over a tag would be meaningless the moment the tag moved.
4. `cosign attest` wraps the SBOM in a signed in-toto statement and stores it in the registry next to the image.

Verifying on a laptop or in an admission policy, naming the identity you expect:

```bash
cosign verify \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  --certificate-identity-regexp '^https://github.com/example/orders/\.github/workflows/ci\.yaml@refs/heads/main$' \
  ghcr.io/example/orders@sha256:<digest>
```

Without the identity flags, any Sigstore signature by anyone would pass; the two flags are the whole point.

The bot that keeps the pins fresh, `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: maven
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: docker
    directory: /
    schedule:
      interval: weekly
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
```

## Pitfalls

- Pinning without a bot. Frozen dependencies rot; within a year the service runs a library with a dozen known CVEs because nobody wanted to open the upgrade pull request.
- A bot without CI discipline. Fifty open upgrade pull requests that nobody merges are the same as no bot. Group minor updates, auto-merge patch updates that pass the full pipeline, and review majors.
- Scanning only the jar, or only the image. The jar scan misses `libssl` in the base image; the image scan misses shaded or nested dependencies that Maven knows about. Do both, and scan the SBOM on a schedule for images already in production.
- `--ignore-unfixed` forever. It keeps the build green for findings without a patch, which is right for the gate but must not become invisible; list them somewhere people read.
- Verifying a signature without an identity. `cosign verify` with no `--certificate-identity` constraint accepts a signature from any GitHub account in the world.
- Signing the tag instead of the digest. The signature is over a digest internally, but a policy that resolves a tag at verification time can be pointed at different bytes between verification and pull. Deploy by digest (item 6.4).
- Building the SBOM from the source tree instead of the shipped artifact. Test-scoped dependencies pollute it, and the build plugins that actually ran are missing. The CycloneDX plugin uses the resolved runtime scope; confirm what yours includes.
- A read-only root filesystem with no writable `/tmp`. The JVM fails to start or logs warnings about `hsperfdata`; mount an `emptyDir` or set `-XX:-UsePerfData` and `-Djava.io.tmpdir` to a writable path.

## Check yourself

1. A critical CVE in a transitive dependency is announced. With an SBOM per deployed image, write the steps to find every affected service in under an hour; without one, what would you do instead?
2. Why does keyless signing need `id-token: write`, and what would an attacker who stole the `GITHUB_TOKEN` of a pull request from a fork be able to sign?
3. Explain what `--certificate-identity-regexp` and `--certificate-oidc-issuer` constrain, and what a verification without them actually proves.
4. Which of these is caught by Dependency-Check in the build, by Trivy on the image, both, or neither: a vulnerable `snakeyaml` from Spring Boot's starter; a vulnerable `zlib` in the base image; a malicious Maven plugin that runs at build time?

## Go deeper

- [Sigstore](https://www.sigstore.dev/) · cosign, Fulcio and Rekor; the documentation covers keyless signing, attestations and policy enforcement.
- [CycloneDX](https://cyclonedx.org/) · the SBOM specification and the list of generators, including the Maven plugin used above.
- [Trivy](https://trivy.dev/) · image, filesystem and SBOM scanning; the `--ignore-unfixed` and severity options.
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/) · SCA in the Maven build, with the NVD API key setup.
- [Renovate](https://docs.renovatebot.com/) · grouping, scheduling and auto-merge rules for upgrade pull requests, and digest pinning for images and actions.

---

Part of [DevOps & Delivery](../README.md) · items 2.5, 2.6, 3.6
