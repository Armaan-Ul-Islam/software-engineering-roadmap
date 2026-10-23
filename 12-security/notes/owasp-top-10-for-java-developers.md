# The OWASP Top 10 for Java and Spring developers

> **In one sentence:** The OWASP Top 10 is the shared vocabulary for the ways web applications get broken, and for each category a Spring application has a specific, mostly unglamorous defence that you should be able to name, configure and verify.

**Why it matters:** "Explain each category with an example and the defence in our stack" is both an interview staple and the checklist a reviewer runs through on every pull request. The 2021 edition is the one most people quote; a 2025 edition exists and reshuffles the list (supply chain failures become a category of their own, SSRF folds into broken access control, and "mishandling of exceptional conditions" is new), but the underlying failures and their defences are the same. This note takes the 2021 list and, for each entry, says what it is, how it shows up in a Spring application and what fixes it.

## The idea

### A01 Broken access control

The application checks who you are and forgets to check what you may touch: `GET /invoices/42` returns another customer's invoice, an `/admin` URL is reachable because nobody wrote the rule, a `role` field in a request body gets bound onto the user entity. The defence has three layers: `authorizeHttpRequests` ending in `anyRequest().authenticated()` (deny by default at the URL), `@EnableMethodSecurity` with `@PreAuthorize` on service methods (function-level), and queries that include the owner or tenant (object-level), with request types that have only the fields a client may set. The full treatment is item 4.2.

### A02 Cryptographic failures

Data that should have been protected was not, or was protected badly: passwords hashed with MD5 or SHA-256, secrets in `application.properties`, a database field "encrypted" with AES in ECB mode, plain HTTP between services because "it is internal". Defences: `DelegatingPasswordEncoder` with Argon2id or bcrypt (item 3.1); AES-GCM through the JCA or Tink with keys in a KMS (item 8.2); TLS everywhere, including inside the cluster, with HSTS (which Spring Security sends by default on HTTPS); and no home-made schemes.

### A03 Injection

Untrusted data becomes code. SQL through concatenated queries (item 2.3), but also OS commands (`Runtime.exec` with a shell string instead of `ProcessBuilder` with an argument list), LDAP filters (Spring LDAP's `LdapQueryBuilder` binds `{0}` placeholders), SpEL (never evaluate user input as an expression; several Spring projects have had remote-code-execution CVEs from exactly that), template injection (never render user input as a template) and cross-site scripting (item 2.10). The pattern is the same everywhere: parameterised APIs for the data, allow-lists for the structure, and Bean Validation (`@Valid` with `@Size`, `@Pattern`, `@Email`) at the boundary so garbage never travels far.

### A04 Insecure design and A05 Security misconfiguration

Design flaws cannot be patched: a password recovery built on security questions, a coupon redemption without limits, a price taken from the client. The defence is up front: threat modelling per feature (item 1.2), abuse cases, ASVS as the requirements list. Misconfiguration is the same failure at deployment time, and Spring Boot has well-known examples: Actuator endpoints exposed on the application port (`/actuator/env` and `/actuator/heapdump` leak secrets and memory), stack traces in error responses, Swagger UI or the H2 console in production, default credentials in a bundled identity provider, and CORS with a wildcard or a reflected `Origin` together with credentials. Spring Boot's defaults are good (only `health` is exposed, `include-stacktrace=never`, Spring Security's header set); the job is not to undo them, and to put management endpoints on a separate port behind authentication.

### A06 Vulnerable and outdated components

The library you did not know you had. Log4Shell is the case study: a transitive dependency, exploitable through any logged string, in services whose owners could not say whether they ran it. Defences: an SBOM so you know, SCA (Dependency-Check, Trivy, Dependabot) in CI so you are told, a BOM so versions are pinned, and routine update pull requests so an emergency bump is small (item 9.2).

### A07 Identification and authentication failures

Credential stuffing against a login with no rate limit, passwords stored with a fast hash, no MFA on admin accounts, session fixation, sessions that never expire. Spring Security provides the password encoder, session fixation protection (`changeSessionId` by default), a compromised-password check and the events you need for throttling; you add the breach check, the throttles per account and per IP, the enumeration-safe messages and MFA for anything privileged (items 3.1 to 3.4).

### A08 Software and data integrity failures

Code or data accepted without checking where it came from. In Java this is first of all **insecure deserialisation**: `ObjectInputStream.readObject()` on untrusted bytes instantiates whatever classes the stream names, and gadget chains in common libraries turn that into remote code execution. Never deserialise untrusted Java serialisation; where a legacy protocol forces it, set a `jdk.serialFilter` allow-list (JEP 290). Jackson's version is **polymorphic typing**: `activateDefaultTyping` (or the old `enableDefaultTyping`) and `@JsonTypeInfo(use = Id.CLASS)` let the JSON choose the class to instantiate. Use `Id.NAME` with explicit `@JsonSubTypes`, and if default typing is unavoidable, a `BasicPolymorphicTypeValidator` that allows only your own packages. The category also covers unsigned artifacts and pipelines that trust tags instead of hashes (item 9.2).

### A09 Security logging and monitoring failures

Breaches that last months do so because nobody saw them. Log authentication successes and failures, access denied, validation failures and administrative actions, with user id, source IP and correlation id, in a structured format something can alert on. Never log passwords, tokens, session IDs or personal data, and strip line breaks from user-controlled values so an attacker cannot forge log lines. Spring Security publishes `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent`; one `@EventListener` turns them into audit records. The 2025 edition adds **mishandling of exceptional conditions**: a catch block that logs and continues past a failed authorization check, a `finally` that swallows an error, a fallback that serves cached data to a user who was just denied. Fail closed: an exception inside a security decision ends in a refusal.

### A10 Server-side request forgery

The server fetches a URL the user chose and reaches the cloud metadata endpoint or an internal admin interface. Allow-lists, resolved-address validation, no automatic redirects, IMDSv2 and egress rules (item 2.9).

## Example: the map from category to defence, and three configurations

| Category | How it appears in Spring | The defence |
|---|---|---|
| A01 Broken access control | `findById(id)` with no owner check; a missing URL rule | `anyRequest().authenticated()`, `@PreAuthorize`, tenant-scoped queries, request DTOs |
| A02 Cryptographic failures | MD5 passwords, ECB, secrets in properties, plain HTTP | `DelegatingPasswordEncoder`, AES-GCM via JCA or Tink, KMS, TLS and HSTS |
| A03 Injection | concatenated SQL, shell strings, SpEL on input | `PreparedStatement` and `:params`, `ProcessBuilder`, Bean Validation, no expression evaluation of input |
| A04 Insecure design | recovery by security question, unlimited coupon use | threat model per feature, abuse cases, ASVS |
| A05 Security misconfiguration | exposed Actuator, stack traces, wildcard CORS with credentials | keep the Boot defaults, separate management port, explicit CORS origins |
| A06 Vulnerable components | Log4j through a transitive dependency | SBOM, Dependency-Check or Trivy in CI, BOM pinning, Renovate |
| A07 Authentication failures | no throttling, fast hashes, fixation | Argon2id or bcrypt, throttles, compromised-password check, MFA, `changeSessionId` |
| A08 Integrity failures | `readObject` on input, Jackson default typing | no Java serialisation of input, `jdk.serialFilter`, `Id.NAME` with `@JsonSubTypes`, `BasicPolymorphicTypeValidator` |
| A09 Logging failures | no login audit, tokens in logs, swallowed exceptions | security event listeners, structured logs, line-break stripping, fail closed |
| A10 SSRF | a webhook sender fetching `169.254.169.254` | allow-lists, address validation, no redirects, IMDSv2, egress rules |

Misconfiguration, made explicit so a reviewer can see it:

```properties
management.server.port=9090
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.show-details=when-authorized
server.error.include-stacktrace=never
server.error.include-message=never
```

Safe polymorphic JSON: the type name is chosen from a closed list, never a class name from the wire:

```java
@JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
@JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = InvoicePayment.class, name = "invoice")
})
public sealed interface Payment permits CardPayment, InvoicePayment {
}
```

Audit logging from Spring Security's events, with user-controlled values forced onto one line:

```java
@Component
public class AuthenticationAuditLogger {

    private static final Logger log = LoggerFactory.getLogger(AuthenticationAuditLogger.class);

    @EventListener
    public void onFailure(AbstractAuthenticationFailureEvent event) {
        log.warn("authentication failed user={} reason={}",
                singleLine(event.getAuthentication().getName()), event.getException().getClass().getSimpleName());
    }

    @EventListener
    public void onSuccess(AuthenticationSuccessEvent event) {
        log.info("authentication succeeded user={}", singleLine(event.getAuthentication().getName()));
    }

    private static String singleLine(String value) {
        return value == null ? "" : value.replaceAll("[\\r\\n]", "_");
    }
}
```

## Pitfalls

- Reading the list as ten independent bugs. Most incidents chain them: a misconfigured Actuator (A05) leaks a credential (A02) that is used through SSRF (A10) to reach data that access control (A01) never guarded.
- Treating "we use Spring Security" as the defence for A01. The framework secures the URLs you configure and the methods you annotate; the object-level check is still yours.
- Disabling defaults to make something work: `csrf.disable()` on a cookie-authenticated application, `include-stacktrace=always` left on after debugging, `exposure.include=*` in a Helm values file.
- Scanning once. SCA and secret scanning are continuous or they are theatre; a clean build in March says nothing about the CVE published in April.
- Trusting internal callers. Admin consoles, batch jobs and sibling services are inputs too; stored XSS, deserialisation and injection arrive through them as readily as through the public API.
- Logging everything "for security". Request bodies and headers contain passwords, tokens and personal data; the log becomes the breach.

## Check yourself

1. For each of the ten categories, name the single Spring configuration or coding rule you would check first in a code review.
2. Why is Jackson's `@JsonTypeInfo(use = Id.CLASS)` an integrity failure rather than an injection, and what does `Id.NAME` with `@JsonSubTypes` change?
3. An exception handler catches `AccessDeniedException`, logs it, and returns the cached response for the endpoint. Which category is this, and what should happen instead?
4. Describe a realistic chain of three categories that turns an exposed `/actuator/env` into a data breach.

## Go deeper

- [OWASP Top 10](https://owasp.org/www-project-top-ten/) · the project page, with both the 2021 and the 2025 editions.
- [OWASP Top 10: A01 Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/) and [A05 Security Misconfiguration](https://owasp.org/Top10/A05_2021-Security_Misconfiguration/) · the two categories most often found in Spring applications, with their CWE lists.
- [OWASP: Deserialization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html) · Java serialisation and JSON library guidance in detail.
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) · what to log, what never to log, and how to protect the logs.
- [OWASP: Error Handling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Error_Handling_Cheat_Sheet.html) · failing closed and keeping internals out of responses.
- [JEP 290: Filter Incoming Serialization Data](https://openjdk.org/jeps/290) · the `jdk.serialFilter` mechanism.
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/) · one sheet per category above; the index is the fastest way in.

---

Part of [Security](../README.md) · items 2.1, 2.2, 2.4, 2.5, 2.6, 2.7, 2.8
