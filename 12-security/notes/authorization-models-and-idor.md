# Authorization models and insecure direct object references

> **In one sentence:** Authorization answers "may this subject do this action on this object?", and the answer has to be computed where the object is known (the service or the query), not merely where the URL is known, because an attacker's favourite exploit is changing `/invoices/41` to `/invoices/42`.

**Why it matters:** Broken access control is number one on the OWASP Top 10, and its most common form is the plainest: an endpoint checks that you are logged in and then returns whatever id you asked for. Multi-tenant systems make it worse, because one missing `WHERE tenant_id = ?` exposes every customer to every other. Interviewers probe this with "where does the ownership check live?" and expect an answer that is not "in the controller".

## The idea

Three models, each answering the question from a different kind of input:

| Model | The decision is based on | Example rule | Fits |
|---|---|---|---|
| RBAC (role-based) | the subject's roles, each a bundle of permissions | "Accountants may approve invoices" | internal tools, admin consoles, any domain with a small fixed set of job functions |
| ABAC (attribute-based) | attributes of subject, object, action and environment | "A user may read a document if its classification is at most the user's clearance and the request comes from the office network" | regulated data, fine-grained rules, rules that change without code changes |
| ReBAC (relationship-based) | relationships between subject and object, traversed as a graph | "A user may edit a document if they own it, or own its folder, or belong to a group granted edit on the folder" | collaboration and sharing products, hierarchies (Google Zanzibar, OpenFGA, SpiceDB) |

Most applications are RBAC for *what kind of thing* a subject may do and ReBAC or ABAC for *which instances*. Keep roles and permissions apart: code checks permissions (`invoice:approve`), roles are collections of permissions assigned to people, and the mapping lives in configuration. Code that checks `hasRole('ADMIN')` ends up with eleven roles that each have to be admin for one feature.

Two rules apply whatever the model. **Deny by default**: every request-matcher chain ends in `anyRequest().authenticated()` or `denyAll()`, every service method needs a positive decision, and the absence of a rule is a refusal. And **function-level** and **object-level** checks are different things. A URL rule such as `/admin/**` requires `ROLE_ADMIN` answers the function-level question well. It cannot answer "may *this* user see invoice 42?", because the matcher only knows that the path fits `/invoices/{id}`, not who owns 42. That gap is the **insecure direct object reference** (IDOR), called **broken object level authorization** (BOLA) in the API Security Top 10: the id is guessable or simply known, and nothing checks that the caller is entitled to the object behind it. Replacing sequential ids with UUIDs helps against guessing and does nothing against a leaked link; the only fix is a check that involves the object.

There are two places for that check, and the second is stronger:

1. **After loading**: fetch the object, then compare its owner or tenant with the caller. Simple, works for single objects, leaks existence (a `403` instead of a `404` confirms the object exists) and does nothing for list endpoints.
2. **In the query**: make the caller's tenant or ownership part of every lookup, so an object the caller may not see is indistinguishable from one that does not exist. Lists and counts are covered automatically.

Multi-tenancy is the query approach taken seriously: the tenant comes from the authenticated principal (a claim in the token, never a parameter or header the client controls) and every repository method takes it. PostgreSQL row-level security enforces the same rule inside the database as a second layer, so a forgotten `WHERE` returns nothing instead of everything.

**Policy as code** moves the rules out of `if` statements into a policy language evaluated by an engine: Open Policy Agent's Rego, AWS's Cedar, or a Zanzibar-style relationship store. The application asks "subject, action, object, context: allowed?" and gets a yes or no. The win is that rules are versioned, tested and reviewable by people who do not read Java, and the same rules serve several services. The cost is a dependency in the request path and the discipline to keep the inputs (attributes, relationships) accurate.

## Example: an ownership check and a tenant-scoped query

Method security is switched on once:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

An ownership check after loading, for a personal resource. The permission check runs before the method; the ownership check runs on the returned object:

```java
@Service
public class NoteService {

    private final NoteRepository noteRepository;

    public NoteService(NoteRepository noteRepository) {
        this.noteRepository = noteRepository;
    }

    @PreAuthorize("hasAuthority('note:read')")
    @PostAuthorize("returnObject.ownerId == authentication.name")
    public Note findNote(long noteId) {
        return noteRepository.findById(noteId).orElseThrow(() -> new NoteNotFoundException(noteId));
    }
}
```

`authentication.name` is the principal's name (the `sub` claim for a JWT, the username for a session) and `returnObject` is the `Note`. A mismatch raises `AccessDeniedException`, which becomes `403`. It is correct, and it is the weaker form: it tells the caller the note exists, and it cannot protect a `findAllNotes()`.

The tenant-scoped query, for a multi-tenant resource. The tenant is read from the token, not from the request, and the repository offers nothing unscoped:

```java
@Component
public class CurrentTenant {

    public String id() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication instanceof JwtAuthenticationToken jwtAuthentication) {
            return jwtAuthentication.getToken().getClaimAsString("tenant_id");
        }
        throw new AccessDeniedException("no tenant in the security context");
    }
}

public interface InvoiceRepository extends Repository<Invoice, Long> {

    Optional<Invoice> findByIdAndTenantId(long id, String tenantId);

    Page<Invoice> findAllByTenantId(String tenantId, Pageable pageable);
}

@Service
public class InvoiceService {

    private final InvoiceRepository invoiceRepository;
    private final CurrentTenant currentTenant;

    public InvoiceService(InvoiceRepository invoiceRepository, CurrentTenant currentTenant) {
        this.invoiceRepository = invoiceRepository;
        this.currentTenant = currentTenant;
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public Invoice findInvoice(long invoiceId) {
        return invoiceRepository.findByIdAndTenantId(invoiceId, currentTenant.id())
                .orElseThrow(() -> new InvoiceNotFoundException(invoiceId));
    }

    @PreAuthorize("hasAuthority('invoice:read')")
    public Page<Invoice> findInvoices(Pageable pageable) {
        return invoiceRepository.findAllByTenantId(currentTenant.id(), pageable);
    }
}
```

Another tenant's invoice id produces the same `404` as a non-existent one, and the list endpoint cannot forget the tenant because there is no method to call that would. Extending Spring Data's `Repository` rather than `JpaRepository` is deliberate: it keeps the unscoped `findById` and `findAll` out of autocomplete.

The second layer, in PostgreSQL, catches the query someone writes next year without the tenant:

```sql
ALTER TABLE invoice ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON invoice
    USING (tenant_id = current_setting('app.tenant_id', true));
```

At the start of each transaction the application runs `SELECT set_config('app.tenant_id', ?, true)` with the tenant bound as a parameter; the `true` makes the setting transaction-local, so pooled connections do not leak it. The application connects as a role that does not own the table, because owners bypass row-level security unless `FORCE ROW LEVEL SECURITY` is set.

For comparison, the same rule as policy code, in Cedar:

```text
permit (principal, action == Action::"readInvoice", resource)
when { resource.tenantId == principal.tenantId };
```

## Pitfalls

- Checking only in the controller or only at the URL. Service methods are called from schedulers, message listeners and other controllers; put the check where the object is.
- Taking the tenant from the request. An `X-Tenant-Id` header or a `tenantId` query parameter chosen by the client is an IDOR with extra steps. It comes from the token or the session.
- Mass assignment. Binding a request body straight onto an entity lets the client set `ownerId`, `tenantId` or `role`. Bind to a request type that has only the fields the client may set.
- `@PostAuthorize` on collections. The expression is evaluated once against the whole list, not per element; use a scoped query (or `@PostFilter`, which is slow and still leaks counts).
- Inherited unscoped methods. `JpaRepository.findById` is one autocomplete away in every service unless the repository does not expose it.
- `hasRole` everywhere. Roles multiply and permissions tangle; check permissions, grant roles.
- UUIDs as the access control. Hard to guess is not the same as authorised; links leak.
- `@PreAuthorize("... #invoiceId ...")` without the `-parameters` compiler flag. Spring Boot's build plugins add it; a hand-written Maven configuration may not, and the expression then fails at runtime.

## Check yourself

1. The URL rule `requestMatchers("/invoices/**").hasAuthority("invoice:read")` is in place. Describe the request that reads another customer's invoice anyway.
2. Why does the tenant-scoped query return `404` for another tenant's object, and why is that preferable to `403`?
3. Where should `tenant_id` come from in a multi-tenant API, and what goes wrong with each alternative?
4. Your product adds "share this document with a colleague". Which model does that push you towards, and what changes in the query approach?

## Go deeper

- [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) · the principles (deny by default, least privilege, object-level checks) with implementation guidance.
- [OWASP API Security: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) · the attack scenarios and the prevention list.
- [OWASP: Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html) · IDOR specifically, including the indirect-reference option and its limits.
- [Spring Security: Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) · `@PreAuthorize`, `@PostAuthorize`, custom authorization managers and the expressions available.
- [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) · the second layer, including who bypasses it.
- [Open Policy Agent](https://www.openpolicyagent.org/) · policy as code with Rego, the engine most teams meet first.

---

Part of [Security](../README.md) · items 4.1, 4.2
