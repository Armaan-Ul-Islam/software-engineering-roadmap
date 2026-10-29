# Project spec: an authentication service you can explain filter by filter

> **In one sentence:** Build an authentication service with Spring Security that offers session login with Argon2id password storage, TOTP as a second factor, rate limiting and lockout, an audit log, and a separate OAuth2 resource-server chain for the API, then document every filter in both chains and check the result against OWASP ASVS level 1.

**Why it matters:** Authentication is where a vague understanding of Spring Security turns into a breach: a filter in the wrong order, a password hashed with the wrong algorithm, a login form that tells attackers which emails exist. Listing the filter chain from memory and saying what each filter does is a reliable senior-interview signal, and the only way to get there is to build the thing and read the debug output.

## The idea

One Spring Boot service, `authn`, with two `SecurityFilterChain` beans: a browser chain (form login, server-side sessions, CSRF on) and an API chain under `/api/**` (stateless, bearer JWTs validated against an issuer you run locally, CSRF off). Keycloak in Docker Compose plays the authorization server; the service is only a resource server. The README's centrepiece is a table of every filter in each chain, in order, with one sentence on what it does and why it is there.

Scope:

- 1.1 Registration with email verification, login, logout, password change; passwords stored with Argon2id.
- 1.2 TOTP enrolment (secret shown as an `otpauth://` URI) and verification as a second login step, with recovery codes.
- 1.3 Rate limiting per source IP and per account, account lockout after repeated failures, and enumeration-safe responses.
- 1.4 An append-only audit log of security events, with no secrets in it.
- 1.5 `/api/**` protected as an OAuth2 resource server; scopes mapped to authorities.

Concepts exercised: Web & HTTP 6.1, 6.2; Spring 3.4, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6; Security 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.3, 6.2, 8.4, 10.1; System Design 2.11.

## Example: the data model, the two chains and the TOTP check

```sql
CREATE TABLE users (
    id              uuid PRIMARY KEY,
    email           text        NOT NULL UNIQUE,
    password_hash   text        NOT NULL,
    totp_secret     bytea,
    locked_until    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE login_attempts (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email           text        NOT NULL,
    source_ip       inet        NOT NULL,
    succeeded       boolean     NOT NULL,
    attempted_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX login_attempts_email_attempted_at_idx ON login_attempts (email, attempted_at);

CREATE TABLE audit_log (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    actor_user_id   uuid,
    event_type      text        NOT NULL,
    source_ip       inet,
    details         jsonb       NOT NULL DEFAULT '{}'::jsonb
);
```

The two chains, compiled against Spring Security 7.0 (the same API exists in 6.x). Order matters: the API chain must be matched first, or the browser chain's `anyRequest()` swallows `/api/**`.

```java
@Bean
@Order(1)
SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize.anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer -> resourceServer.jwt(Customizer.withDefaults()))
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/register", "/actuator/health").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}

@Bean
PasswordEncoder passwordEncoder() {
    return Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8();
}
```

The TOTP computation (RFC 6238 with HMAC-SHA1, 30-second steps, six digits), compiled and checked against the RFC's test vectors: the secret `12345678901234567890` at time 59 gives `287082`, at time 1111111109 gives `81804`.

```java
static int codeAt(byte[] secret, long unixSeconds) throws GeneralSecurityException {
    long counter = unixSeconds / 30;
    Mac mac = Mac.getInstance("HmacSHA1");
    mac.init(new SecretKeySpec(secret, "HmacSHA1"));
    byte[] hash = mac.doFinal(ByteBuffer.allocate(Long.BYTES).putLong(counter).array());
    int offset = hash[hash.length - 1] & 0x0f;
    int truncated = ((hash[offset] & 0x7f) << 24)
        | ((hash[offset + 1] & 0xff) << 16)
        | ((hash[offset + 2] & 0xff) << 8)
        | (hash[offset + 3] & 0xff);
    return truncated % 1_000_000;
}
```

Milestones, each ending in a committed test:

1. **Session login with Argon2id.** Registration, login, logout. Test (MockMvc with the real filter chain): the stored hash starts with `$argon2id$`; the session cookie is `HttpOnly` and `Secure`; the session ID before and after login differ (fixation protection); logout invalidates the session so a replayed cookie gets `302` to `/login`.
2. **TOTP.** Secret from `SecureRandom`, enrolment confirmed by one valid code, verification at login with a window of one step either side, the last accepted counter stored so a code cannot be replayed. Test: the RFC 6238 vectors above; a code accepted once is rejected the second time; a code from two steps ago is rejected.
3. **Rate limiting, lockout and enumeration safety.** A `OncePerRequestFilter` with a token bucket per source IP answering `429` with `Retry-After`; lockout after five failures in fifteen minutes from `login_attempts`; the same message, status and a comparable response time for unknown email, wrong password and locked account (hash a dummy password when the user does not exist). Test: the response bodies for the three failure cases are byte-identical; the sixth attempt is refused even with the correct password; the 101st request from one IP in a minute gets `429`.
4. **Audit log.** Listen for `AuthenticationSuccessEvent` and `AbstractAuthenticationFailureEvent` and for your own events (TOTP enrolled, password changed, lockout). Test: a failed login writes exactly one row, and the `details` column contains neither the password nor the hash; the log is append-only (no `UPDATE` or `DELETE` grant for the application role).
5. **Resource server.** Keycloak in Compose as issuer, `spring.security.oauth2.resourceserver.jwt.issuer-uri` pointing at it, a `JwtAuthenticationConverter` mapping `scope` claims to authorities. Test: `SecurityMockMvcRequestPostProcessors.jwt()` for unit tests of authorisation rules; one integration test that obtains a real token from Keycloak and calls `/api/me`; an expired token and a token with the wrong audience both get `401`.
6. **The filter table.** Start with `@EnableWebSecurity(debug = true)`, copy the printed filter list for each chain into the README, and write one line per filter. Then walk the Authentication chapter of ASVS level 1 (state which ASVS version) and record pass, fail or not applicable per requirement with the test or code that proves it.

Definition of done:

- 2.1 Every filter in the security chain is listed and explained in the README, and the OWASP ASVS level 1 authentication checks pass.
- 2.2 `docker compose up` starts the service, PostgreSQL and Keycloak; a `curl` script registers, logs in, enrols TOTP and calls `/api/me` with a bearer token.
- 2.3 No password, hash, TOTP secret or token appears in any log line, proven by a test that captures log output during a full login.

Stretch goals:

- 3.1 Passkeys (WebAuthn) as an alternative second factor, and a comparison of phishing resistance with TOTP.
- 3.2 Breached-password checks against the Have I Been Pwned range API at registration and password change.
- 3.3 Replace Keycloak with Spring Authorization Server and issue your own tokens; list what you now own that Keycloak used to.

## Pitfalls

- One chain for everything. The browser chain's CSRF protection and redirect-to-login behaviour are wrong for an API, and the API chain's `401` is wrong for a browser; two chains with `securityMatcher` and explicit `@Order`.
- Hashing with bcrypt "because it is the default" without a work factor decision, or with Argon2 parameters pulled from a blog. Use the encoder's `defaultsForSpringSecurity_v5_8()` and record the measured hash time on your hardware in the README.
- Telling the user which part failed. "Unknown email" versus "wrong password" is enumeration; so is a lockout message that only appears for existing accounts, and so is a response time that differs by one Argon2 hash.
- A TOTP window wider than one step, or no replay protection. Both turn a six-digit code into something an attacker can reuse within the window.
- Rate limiting by IP alone. Credential stuffing comes from many IPs against one account; limit per account too, and prefer lockout with a time window over permanent lockout (which becomes a denial-of-service tool).
- Trusting any JWT that validates. Check issuer, audience and expiry; a token from the right issuer for a different API is still the wrong token.

## Check yourself

1. Name the filter that stores the `SecurityContext` in the session and the one that reads it back on the next request, and explain what breaks if the API chain includes them.
2. Why must the service hash a dummy password when the email does not exist, and what would a timing attack look like without it?
3. A user's TOTP code is accepted at second 29 of a step. For how long could the same code be replayed if you store nothing, and what do you store to prevent it?
4. Your resource server validates signatures with the issuer's JWKS. What happens when the issuer rotates keys, and why does the resource server need no restart?

## Go deeper

- [Spring Security Reference: Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html) · the filter chain you are documenting.
- [Spring Security Reference: Password storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html) · `DelegatingPasswordEncoder` and the Argon2 encoder.
- [Spring Security Reference: OAuth2 resource server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) · JWT validation and authority mapping for milestone 5.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) · the checklist behind milestone 3.
- [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) · the level 1 requirements for the definition of done.

---

Part of [Projects](../README.md) · item 2.3
