# Security in the development lifecycle: ASVS and the pipeline

> **In one sentence:** Security becomes an engineering property, rather than a yearly scare, when requirements come from a checklist (OWASP ASVS), design gets a threat model, every pull request is scanned for vulnerable code, dependencies and secrets, the deployed application is probed from outside, and people who find holes have a published way to tell you.

**Why it matters:** A penetration test that finds twelve issues a week before launch is not a security programme; it is a bill. The expensive findings (missing authorization, weak recovery flows, no rate limiting) are design decisions that were cheap to fix as acceptance criteria and are expensive to fix as findings. Teams that put the checks where the work happens (the backlog, the pull request, the pipeline) ship with fewer surprises, and senior engineers are expected to know which tool catches which class of problem and which classes no tool catches.

## The idea

**ASVS as the requirements list.** The OWASP Application Security Verification Standard is a numbered list of verifiable requirements for web applications and APIs, grouped by topic: authentication, session management, access control, input handling and encoding, cryptography, logging and error handling, data protection, communication, file handling, API and web services, configuration, and (in version 5.0) OAuth and OpenID Connect and self-contained tokens. Each requirement is written to be checked ("verify that..."), not aspired to. Three levels:

| Level | Intended for | Rough meaning |
|---|---|---|
| L1 | Every application | The minimum; largely testable from outside without source access |
| L2 | Applications handling sensitive data, which is most of them | The recommended target; needs source and design access to verify |
| L3 | Critical applications: health, finance, safety | Everything, including architecture and deep defence-in-depth requirements |

Requirement identifiers are chapter, section, number. They were renumbered between version 4.0 and version 5.0, so a ticket that cites one must name the version. The way to use the standard is not to read it cover to cover but to pick a level, import the requirements relevant to each feature as acceptance criteria when the story is written, and record for each how it will be verified: a unit test, a configuration review, a scanner rule, or a manual test. That record is also your answer to the auditor.

**The lifecycle, and what belongs at each stage.**

1. **Requirements.** The ASVS items for the feature. "Password reset" pulls in the authentication and session requirements; "export to CSV" pulls in access control and data protection.
2. **Design.** The twenty-minute threat model (item 1.2). Its High tickets go into the same sprint as the feature.
3. **Implementation.** Secure defaults from the framework, a short review checklist for the reviewer (authorization at the object level, no secrets, parameterised queries, validation at the boundary, no new dependency without a reason), and automated checks on every pull request.
4. **Verification.** Scanners against the running application, a penetration test when the attack surface changes substantially, and the findings handled as ordinary bugs with severity-based deadlines.
5. **Operations.** Monitoring and alerting on security events (item 10.1), a vulnerability disclosure channel, and an incident process (item 10.3).

**The tools, and what each one can and cannot find.**

| Class | Examples | Finds | Misses |
|---|---|---|---|
| SAST (static analysis) | CodeQL, Semgrep, SonarQube, SpotBugs with Find Security Bugs | Code patterns: concatenated SQL, `Runtime.exec` with strings, weak crypto, taint flows from request to sink | Missing authorization, business logic, anything the pattern author did not write a rule for; many false positives until tuned |
| SCA (software composition analysis) | OWASP Dependency-Check, Trivy, Snyk, Dependabot, Renovate | Dependencies with published CVEs, by comparing your lockfile to advisory databases | Whether the vulnerable code path is reachable; unpublished vulnerabilities; your own code |
| Secret scanning | gitleaks, GitHub push protection | Credentials committed to the repository, by pattern and entropy | Secrets that do not look like secrets; secrets in images and logs |
| DAST (dynamic analysis) | OWASP ZAP | Missing headers, verbose errors, reflected injection, some authentication misconfiguration, against a deployed instance | Anything behind a login it cannot complete, authorization between users, logic |
| Penetration test | People, scoped and time-boxed | Authorization gaps, chained findings, business logic, the things above combined | Whatever is outside scope, and everything that changes after the report |

The pattern across the rows: tools find what tools can describe, and the top finding in every list, broken access control, is not one of them. That is what the review checklist and the threat model are for.

**Running scanners without stopping the team.** Fail the build on new high-severity findings only, baseline the existing ones with a date to fix them, tune rules that produce noise rather than ignoring the whole tool, and run the slow scans on a schedule instead of on every push. A scanner that everybody has learned to skip is worse than none, because it provides the feeling of coverage.

**Disclosure and maturity.** A `security.txt` file (RFC 9116) at `/.well-known/security.txt` tells a researcher where to report, and a published policy tells them they will not be sued for doing so. Respond within days, fix by severity, credit the reporter. OWASP SAMM is the model for measuring the whole programme: five business functions (governance, design, implementation, verification, operations), three practices under each, three maturity levels per practice; useful as a yearly self-assessment, not as a project plan.

## Example: a pipeline, a build gate and a security test

A GitHub Actions workflow that runs secret scanning and static analysis on every pull request and the dependency check on a schedule as well, so a CVE published on Tuesday is known on Monday:

```yaml
name: security
on:
  pull_request:
  schedule:
    - cron: "0 3 * * 1"

jobs:
  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  static-analysis:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v3
        with:
          languages: java-kotlin
      - uses: github/codeql-action/autobuild@v3
      - uses: github/codeql-action/analyze@v3

  dependencies:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
      - run: ./mvnw --batch-mode org.owasp:dependency-check-maven:check -DfailBuildOnCVSS=7
```

The dependency job fails the build when any dependency has a known vulnerability scored 7 or higher; a suppression file with an expiry date handles the false positives. A dynamic scan against a deployed staging environment is one command, run after each deployment there:

```bash
docker run --rm ghcr.io/zaproxy/zaproxy:stable zap-baseline.py -t https://staging.example.com
```

Requirements that no scanner checks become tests. Two that cover "deny by default" and "security headers present" for a Spring application, so a new controller cannot silently open an endpoint:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityBaselineTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void endpointsThatNobodyConfiguredRequireAuthentication() throws Exception {
        mockMvc.perform(get("/internal/added-last-week"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void everyResponseCarriesTheHeaderBaseline() throws Exception {
        mockMvc.perform(get("/"))
                .andExpect(header().string("X-Content-Type-Options", "nosniff"))
                .andExpect(header().exists("Content-Security-Policy"))
                .andExpect(header().string("Cache-Control", "no-cache, no-store, max-age=0, must-revalidate"));
    }
}
```

And the disclosure file, served at `/.well-known/security.txt`:

```text
Contact: mailto:security@example.com
Expires: 2027-10-29T00:00:00.000Z
Preferred-Languages: en, no
Policy: https://example.com/security/disclosure-policy
Canonical: https://example.com/.well-known/security.txt
```

`Contact` and `Expires` are the required fields; an expired file tells researchers the address may be dead.

## Pitfalls

- Buying the pentest instead of the backlog. Findings that are design flaws recur in the next feature unless the requirement enters the definition of done.
- ASVS as a 300-item audit done once. Pick the level, pull the relevant items per feature, and stop; a standard nobody can finish is a standard nobody starts.
- Scanners that block everything. The team disables them within a month. Gate on new high findings; schedule the rest.
- SCA without a lockfile or a BOM. The scan reports what it resolved today, which may not be what production runs (item 9.2).
- Trusting a green SAST run. It found no patterns it knows; it did not check that invoice 42 belongs to the caller.
- Secret scanning only on the main branch. The secret was pushed to a feature branch, is in the history forever, and must be rotated (item 9.1).
- No `security.txt`, no policy. The researcher emails `info@`, waits, and publishes.
- Treating SAMM levels as targets for their own sake. Maturity is the by-product of the practices; measure to find the weakest, not to collect a score.

## Check yourself

1. Which ASVS level would you pick for an internal HR application that stores salaries, and what changes in how you can verify it compared with L1?
2. For each of SAST, SCA, DAST and a penetration test, name one bug class it reliably finds and one it structurally cannot.
3. A new `GET /reports/{id}` endpoint ships without an ownership check. Which stage of the lifecycle should have caught it, which tool would not, and what automated test could have?
4. Why does the dependency check run on a schedule as well as on pull requests, and what has to exist for `failBuildOnCVSS` not to block the team on false positives?

## Go deeper

- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) · the standard; download the current version and the mapping to the previous numbering.
- [OWASP SAMM](https://owaspsamm.org/) · the maturity model with a free self-assessment toolkit.
- [OWASP Web Security Testing Guide](https://owasp.org/www-project-web-security-testing-guide/) · what a penetration tester actually does, test by test; read it to know what to expect and to test yourself first.
- [OWASP Code Review Guide](https://owasp.org/www-project-code-review-guide/) · the reviewer's checklist in long form.
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/) · the Maven plugin used above, suppression files and CVSS thresholds.
- [OWASP ZAP](https://www.zaproxy.org/) · the baseline scan and how to run authenticated scans.
- [CodeQL](https://codeql.github.com/) and [Semgrep](https://semgrep.dev/) · the two static analysers most teams start with; both have free tiers and Java rule sets.
- [RFC 9116: security.txt](https://www.rfc-editor.org/rfc/rfc9116) and [securitytxt.org](https://securitytxt.org/) · the file format and a generator.
- [OWASP: Vulnerability Disclosure Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html) · how to receive and handle reports.

---

Part of [Security](../README.md) · items 1.3, 1.4
