# Logging safely and GDPR for developers

> **In one sentence:** Logs are a data store with the weakest access control in the company, so nothing that authenticates (passwords, tokens, session IDs) and as little as possible that identifies a person goes into them; and GDPR, for a developer, means knowing which columns hold personal data, why each is there, how long it stays, and being able to export or erase one person's data on request.

**Why it matters:** The breach that costs a company its reputation is rarely a clever exploit; it is a log aggregator with `DEBUG` request dumps and every developer's credentials, or a backup that was never deleted. Regulators fine for exactly these: data kept without purpose, retention nobody defined, erasure requests that could not be honoured. Interviewers ask "what do you log on a failed login?" and "how would you delete a user?" because the answers show whether you have thought about data as a liability rather than only as an asset.

## The idea

**What never goes in a log.** Passwords (including failed attempts; the typo is often the real password), tokens of every kind (`Authorization` headers, cookies, reset and verification links, API keys, signed URLs), card numbers and bank details, full request or response bodies, and personal data that the line does not need. What goes in instead: the event, an opaque identifier (user id, order id), a correlation id, and the outcome. Under GDPR an email address, an IP address and a device identifier are personal data, so even "harmless" context lines carry a retention obligation.

**Application log versus audit log.** They look alike and serve different masters:

| | Application log | Audit log |
|---|---|---|
| Purpose | Debugging and operations | Accountability: who did what, when, to which record |
| Written by | Any code, at any level | Security-relevant events only: login, logout, failed login, permission denied, data exported, record changed by whom |
| Reader | Developers, on-call | Security, compliance, auditors, sometimes the user ("recent activity") |
| Mutability | Rotated, sampled, dropped under load | Append-only, protected from the people it records, never sampled |
| Retention | Days to a few weeks | As long as accountability requires; often years, defined per event type |
| Format | Free text with structured fields | Structured records with a fixed schema |

Keep them apart: a separate logger name and sink for audit events, so retention and access can differ. Item 2.8 covers the Spring Security events to listen for and the line-break stripping that prevents log forging.

**Retention is a decision, not a default.** Every log sink and every table with personal data gets a stated period and a job that enforces it. "Keep for debugging" is not a period. Login events with IP addresses: 90 days, then deleted. Audit records of permission changes: the length your accountability obligations require. Debug logs: a week.

**GDPR, the parts you implement.** The regulation's principles (lawfulness, purpose limitation, data minimisation, accuracy, storage limitation, integrity and confidentiality, accountability) are in Article 5; the six lawful bases for processing (consent, contract, legal obligation, vital interests, public task, legitimate interests) are in Article 6, and consent is the weakest of them because it can be withdrawn. Each translates into a developer task:

1. **Inventory.** A list of every table, column, log field and third-party service that holds personal data, with the purpose and the lawful basis for each. The question "why do we have this column?" must have an answer; if it does not, that is minimisation telling you to drop it.
2. **Purpose limitation.** Data collected for delivery is not used for marketing without a basis of its own. In code: separate tables or explicit flags, not "we have the email anyway".
3. **Retention and deletion.** The periods from the inventory, enforced by scheduled jobs, covering the primary tables, derived data (search indexes, caches, analytics, data warehouses), logs, and backups. Backups are the hard part: document their retention and ensure a restore re-applies deletions, or encrypt per-user data under a key you can destroy (crypto-shredding).
4. **Data subject rights** (Articles 15 to 22): access and portability mean an export of everything about one person in a machine-readable format; rectification means fields are editable; erasure means a deletion that reaches everything in the inventory. Build the export and the erasure as features with tests, not as a script someone writes under a 30-day deadline.
5. **Pseudonymisation** (defined in Article 4): replacing direct identifiers with a key held separately. Pseudonymised data is still personal data, but a leak of one half is far less damaging, and analytics can run on it. Hashing an email with no salt is not pseudonymisation; the hash is trivially reversed from any address list.
6. **Data protection by design and by default** (Article 25) and security of processing (Article 32): the controls in the rest of this roadmap, applied before the feature ships rather than after the audit. Breach notification to the supervisory authority within 72 hours (Article 33) means your logging and monitoring must let you know what happened; see item 10.3.
7. **Processors** (Article 28): every SaaS or cloud service that touches personal data needs a data processing agreement, and your inventory names them.

Legal retention cuts the other way: invoices and accounting records must be kept for the period national bookkeeping law requires, so "erase my account" becomes "anonymise the person, keep the transactions". A deletion that silently breaks a legal obligation is as much a bug as one that fails to delete.

## Example: redaction that runs, and a schema with retention built in

A last-resort redactor for text that reaches the logging framework. It is a safety net, not the design; the design is not to log the value in the first place:

```java
import java.util.List;
import java.util.regex.Pattern;

public final class LogRedactor {

    private record Rule(Pattern pattern, String replacement) {
    }

    private static final List<Rule> RULES = List.of(
            new Rule(Pattern.compile("(?i)(authorization: *bearer +)[A-Za-z0-9._~+/=-]+"), "$1[REDACTED]"),
            new Rule(Pattern.compile("(?i)(password|secret|token)(\"?\\s*[:=]\\s*\"?)[^\\s\",&]+"), "$1$2[REDACTED]"),
            new Rule(Pattern.compile("\\b(\\d{6})\\d{6,9}(\\d{4})\\b"), "$1******$2"),
            new Rule(Pattern.compile("[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\\.[A-Za-z]{2,})"), "***@$1"),
            new Rule(Pattern.compile("[\\r\\n]"), "_"));

    public static String redact(String message) {
        String result = message;
        for (Rule rule : RULES) {
            result = rule.pattern().matcher(result).replaceAll(rule.replacement());
        }
        return result;
    }

    public static void main(String[] arguments) {
        List<String> lines = List.of(
                "request headers: Authorization: Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiI0MiJ9.c2ln",
                "login failed for anna.larsen@example.com password=Winter2026!",
                "payload {\"card\":\"4111111111111111\",\"token\":\"tok_live_8f3a\"}",
                "user submitted name: alice\n2026-10-29 10:00:00 INFO  admin logged in");
        for (String line : lines) {
            System.out.println(redact(line));
        }
    }
}
```

```text
request headers: Authorization: Bearer [REDACTED]
login failed for ***@example.com password=[REDACTED]
payload {"card":"411111******1111","token":"[REDACTED]"}
user submitted name: alice_2026-10-29 10:00:00 INFO  admin logged in
```

The last line shows log forging defeated: the injected newline would otherwise have produced a fake `admin logged in` record. The same rules can live in the Logback pattern, which catches every logger in the process:

```xml
<encoder>
    <pattern>%d{ISO8601} %-5level [%X{correlationId}] %logger{36} - %replace(%msg){'(?i)(authorization: *bearer +)[A-Za-z0-9._~+/=-]+', '$1[REDACTED]'}%n</pattern>
</encoder>
```

Spring Boot 3.4 and later can emit JSON that log platforms index without parsing, which makes "find every line about user 42" and "delete every line about user 42" possible:

```properties
logging.structured.format.console=ecs
```

The schema side. The inventory becomes column comments and a retention job; the erasure becomes an anonymisation because invoices reference the customer:

```sql
CREATE TABLE customer (
    id          bigint PRIMARY KEY,
    email       text NOT NULL,
    full_name   text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    erased_at   timestamptz
);
COMMENT ON COLUMN customer.email IS 'personal data; purpose: contract (order delivery, receipts); retained until erasure request';

CREATE TABLE login_event (
    id          bigserial PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customer (id),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    ip_address  inet NOT NULL,
    user_agent  text
);
COMMENT ON COLUMN login_event.ip_address IS 'personal data; purpose: legitimate interest (account security); retained 90 days';

-- scheduled nightly
DELETE FROM login_event WHERE occurred_at < now() - interval '90 days';

-- erasure request for one customer; invoices keep the id, the person is gone
UPDATE customer
SET email = 'erased-' || id || '@invalid',
    full_name = 'erased',
    erased_at = now()
WHERE id = :customer_id;
DELETE FROM login_event WHERE customer_id = :customer_id;
```

The export for an access request is the mirror image: one query per table in the inventory, joined on the customer id, serialised as JSON. If writing that query is hard, the inventory is incomplete.

## Pitfalls

- `DEBUG` logging of HTTP requests in production. Every header, every body; the log is now the password database.
- Exceptions that carry input. `IllegalArgumentException("invalid token " + token)` puts the token in every stack trace and every error tracker.
- Logging objects with `toString()`. A `User` record prints its email and whatever else it holds, today and after the next field is added.
- Copying production data to development or test. The inventory, retention and access controls do not follow it. Generate test data, or anonymise before copying.
- Deleting from the primary table only. The search index, the cache, the analytics warehouse, the CSV export in someone's inbox and the log platform all still have the person.
- Treating hashing as anonymisation. A SHA-256 of an email is reversed by hashing a mailing list; pseudonymisation needs a secret key or a random surrogate stored separately.
- Consent as the default basis. It must be freely given and withdrawable, and withdrawal must stop the processing; "contract" or "legitimate interest" is usually the honest basis for core functionality.
- Audit logs in the same sink, with the same retention and the same access as application logs. The record of an admin's actions should not be deletable by that admin.

## Check yourself

1. A failed login is logged as `login failed user=anna@example.com password=Winter2026!`. List what is wrong with the line and write the line you would log instead.
2. Why is an audit log kept separate from the application log, and name three properties it needs that the application log does not?
3. A user asks for erasure, but they have three paid invoices. What do you delete, what do you anonymise, what do you keep, and on what basis?
4. Explain why a salted-and-keyed pseudonym is still personal data under GDPR, and what practical difference pseudonymisation makes anyway.

## Go deeper

- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) · what to log, what to exclude, and how to protect the logs themselves.
- [OWASP: Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html) · a fixed set of security event names and fields, which is what an audit log schema should start from.
- [OWASP: User Privacy Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html) · the developer-side privacy controls beyond logging.
- [CNIL: GDPR developer's guide](https://www.cnil.fr/en/gdpr-developers-guide) · the French regulator's checklist for developers; short and practical.
- [Datatilsynet](https://www.datatilsynet.no/en/) · the Norwegian regulator's guidance, including software development and privacy by design.
- [Regulation (EU) 2016/679 on EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679/oj) · the text; Articles 5, 6, 15 to 22, 25, 28, 32 and 33 are the ones cited above.
- [Spring Boot: Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) · structured logging formats and Logback configuration.

---

Part of [Security](../README.md) · items 10.1, 10.2
