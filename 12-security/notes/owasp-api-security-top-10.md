# The OWASP API Security Top 10 and authorization across services

> **In one sentence:** The API Security Top 10 names the ways APIs fail that the web Top 10 only hints at (authorization per object, per property and per function, authentication for machines, and limits on what a caller may consume), and once a request crosses a service boundary every one of those questions has to be answered again, with a token or a certificate rather than a header somebody typed.

**Why it matters:** The browser-facing page is no longer where the data is; the API behind it is, and it is called by mobile apps, partners, scripts and other services that never see your templates or your CSRF tokens. Broken object level authorization is the most common finding in API penetration tests, and mass assignment is the bug that turns a profile update into an admin account. Interviewers ask "how does service B know who the user was when service A calls it?" because most candidates answer "we pass the user id in a header".

## The idea

The 2023 edition has ten entries. Each line below gives the failure, how it looks in a Spring application, and the defence.

| Entry | The failure | In a Spring application | Defence |
|---|---|---|---|
| API1 Broken object level authorization | `GET /invoices/42` returns anyone's invoice | `findById(id)` with no owner or tenant in the query | Ownership or tenant in every query; see item 4.2 |
| API2 Broken authentication | Keys in query strings, no throttling, tokens never validated | A filter that trusts `X-User-Id`; a JWT decoded but not verified | Bearer tokens validated at every service (items 6.2, 6.3); throttles; nothing identifying in URLs |
| API3 Broken object property level authorization | Clients read or write fields they should not | Entity returned straight from the controller; request body bound onto the entity (mass assignment) | Separate request and response types with only the fields the client may see or set |
| API4 Unrestricted resource consumption | No limit on size, count, page size, rate or cost | `findAll()` without a page; 100 MB uploads; an endpoint that sends an SMS per call | Pagination with a maximum, body and multipart limits, timeouts, rate limits per client |
| API5 Broken function level authorization | Regular users reach admin functions | `/admin/**` without a rule; `@PreAuthorize` forgotten on one service method | Deny by default at the URL and the method level |
| API6 Unrestricted access to sensitive business flows | Automation abuses a flow that is fine for humans (buying out stock, scraping, mass sign-up) | A checkout API with no device or velocity checks | Rate limits per account and device, step-up checks, monitoring for machine patterns |
| API7 Server side request forgery | The API fetches a URL the client chose | Webhook registration, avatar-by-URL | Item 2.9 |
| API8 Security misconfiguration | Verbose errors, open CORS, exposed Actuator, missing TLS | `include-stacktrace=always`, `allowedOrigins("*")` with credentials | Item 2.4 |
| API9 Improper inventory management | Old versions and forgotten environments stay reachable | `/v1/` still deployed without the fixes `/v2/` got; a staging host with production data | An inventory of every API and version, retirement dates, the same controls everywhere |
| API10 Unsafe consumption of APIs | Trusting data from third-party APIs as if it were your own | Following redirects from a partner, deserialising their response without limits | Validate and limit responses from other APIs exactly like user input |

Three of these are about authorization, which is why the list exists: a URL rule cannot answer "may this caller see *this* object" (API1), "may this caller set *this* field" (API3), or "may this caller perform *this* operation at all" (API5). The first and third are covered in item 4.2; the second is the one most teams have never heard named.

**Mass assignment** is API3 in its writable form. A framework binds the request body onto an object field by field. If that object is the entity, every column becomes settable: `role`, `emailVerified`, `balance`, `tenantId`. The fix is a request type that lists exactly the fields a client may set, and a response type that lists exactly what it may read. Jackson's default is to reject unknown properties, but Spring Boot turns that off, so an entity bound from JSON silently accepts whatever the client sends.

**Authorization across services** is the same three questions asked again on the next hop. When service A, handling a user's request, calls service B, B has to decide what A may do and on whose behalf. There are three honest ways to carry that identity:

1. **Forward the user's access token.** Simplest, and wrong by default: the token was issued with an audience of A, so B must reject it (item 6.2), and if B accepts it, B cannot tell a request that came through A from one that came directly.
2. **Token exchange (RFC 8693).** A presents the user's token to the authorization server and asks for a new token with audience B, often with narrower scope. The new token names the user as subject and A as the actor (the `act` claim), so B knows both who and via whom. Spring Security's OAuth2 client ships a `TokenExchangeOAuth2AuthorizedClientProvider` for this grant.
3. **Client credentials.** A authenticates as itself (a secret, a `private_key_jwt` assertion, or an mTLS certificate as in RFC 8705) and gets a token with no user in it. B then trusts A's own authorization decision. This fits background jobs and system calls; for user-initiated calls it loses the user, so if B needs the user id it arrives as data, and B must be sure only A can call it.

Mutual TLS (item 7.4) answers "which service is calling" at the transport level and combines with any of the three. What is never acceptable is an `X-User-Id` or `X-Roles` header that any process on the network can write. Identity crosses a boundary only as something B can verify: a signature B checks against the issuer's keys, or a certificate B checks against its own trust store.

## Example: mass assignment, then audience validation

The vulnerable pattern and the fix, run against Jackson with Spring Boot's default of ignoring unknown properties:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;

public final class MassAssignment {

    public static class UserEntity {
        public String name;
        public String email;
        public String role = "USER";
        public boolean emailVerified = false;
    }

    public record UserCreateRequest(String name, String email) {
    }

    public static void main(String[] arguments) throws Exception {
        String body = """
                {"name": "Mallory", "email": "mallory@example.com", "role": "ADMIN", "emailVerified": true}
                """;
        ObjectMapper springBootDefaults = new ObjectMapper()
                .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        UserEntity entity = springBootDefaults.readValue(body, UserEntity.class);
        System.out.println("bound onto the entity:  role=" + entity.role + " emailVerified=" + entity.emailVerified);

        UserCreateRequest request = springBootDefaults.readValue(body, UserCreateRequest.class);
        System.out.println("bound onto the request: " + request);

        ObjectMapper strict = new ObjectMapper();
        try {
            strict.readValue(body, UserCreateRequest.class);
        } catch (UnrecognizedPropertyException exception) {
            System.out.println("strict mapper: " + exception.getOriginalMessage());
        }
    }
}
```

```text
bound onto the entity:  role=ADMIN emailVerified=true
bound onto the request: UserCreateRequest[name=Mallory, email=mallory@example.com]
strict mapper: Unrecognized field "role" (class MassAssignment$UserCreateRequest), not marked as ignorable
```

The record cannot carry `role` because it has no such component; the service sets `role` and `emailVerified` itself. Whether unknown fields should be an error (the strict mapper) or ignored is a product decision; the security property comes from the request type, not from the mapper setting.

For API4, the limits that Spring Boot does not set for you:

```properties
spring.data.web.pageable.max-page-size=200
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
```

Rate limits per client are not in the framework; a token-bucket library in a filter, or the gateway, does that job.

For the hop between services, the resource server side of token exchange is one property. Spring Boot's resource server auto-configuration validates issuer, signature and expiry; the audience check has to be asked for:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.com
spring.security.oauth2.resourceserver.jwt.audiences=billing-api
```

A token issued for `orders-api` and forwarded unchanged is now rejected with `401`, which is what forces the calling service to do the exchange. The exchange request itself, as A sends it to the authorization server:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic b3JkZXJzLWFwaTpjbGllbnQtc2VjcmV0
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=eyJhbGciOiJSUzI1NiIs...
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=billing-api
&scope=invoices:read
```

The response is an ordinary token response. The new token's claims carry `sub` (the user), `aud` (`billing-api`), the reduced scope and `act` with `{"sub": "orders-api"}`, so `billing-api` can log who acted and through what.

## Pitfalls

- Returning entities from controllers. Every new column is exposed the day it is added, and every column becomes writable through the matching `PUT`.
- `@JsonIgnore` on the sensitive fields as the fix for mass assignment. It is a deny-list; the next sensitive field is forgotten. Request types are allow-lists.
- Checking authorization in the gateway only. The gateway knows URLs; it does not know object owners or field names. API1 and API3 are decided in the service.
- A `Pageable` with no maximum. `?size=1000000` is a denial of service that also leaks the whole table.
- Trusting internal headers. If one service in the network is compromised, `X-User-Id` makes every other service compromised too.
- Forwarding user tokens and relaxing the audience check "because it is internal". The check exists so that a token stolen from one service cannot be replayed against all of them.
- Client credentials with a user id in the body for user-initiated calls. The downstream service now authorizes on a claim nobody signed.
- Decommissioning by removing the link, not the deployment. `/v1/` is still answering, without the fix.

## Check yourself

1. A `PUT /users/{id}` binds the JSON body onto the `User` entity and saves it. List three fields an attacker would try, and describe the fix in terms of the request type.
2. Why must a resource server check the `aud` claim, and what breaks if service B accepts tokens whose audience is service A?
3. Service A calls service B on behalf of a logged-in user. Compare forwarding the token, token exchange and client credentials: what does B learn about the user and about A in each case?
4. Which entries in the API Security Top 10 are about authorization, and at which layer (gateway, URL rule, service method, query) is each one decided?

## Go deeper

- [OWASP API Security Project](https://owasp.org/API-Security/) and [the 2023 list](https://owasp.org/API-Security/editions/2023/en/0x11-t10/) · each entry with attack scenarios and prevention.
- [OWASP API Security: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) and [Broken Object Property Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa3-broken-object-property-level-authorization/) · the two authorization entries most often found in practice.
- [OWASP: Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html) · the vulnerability by framework, with the allow-list approaches.
- [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693) · the grant used above, including the `act` claim for delegation.
- [Spring Security: OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) · what the auto-configuration validates and how to add validators.
- [OWASP: Microservices Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Microservices_Security_Cheat_Sheet.html) · identity propagation patterns between services, with their trade-offs.

---

Part of [Security](../README.md) · items 2.12, 4.3
