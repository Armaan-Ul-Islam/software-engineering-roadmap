# JWT validation and its pitfalls

> **In one sentence:** A JWT is a signed (not encrypted) set of claims that a resource server can verify locally, and its security rests entirely on the verifier checking the right things in the right order: an allow-listed algorithm, the signature against the expected key, issuer, audience, the time window, and only then the claims it actually uses.

**Why it matters:** JWTs are the access-token format most APIs receive, and most JWT breaches were not broken cryptography but skipped checks: a library that honoured `alg: none`, a server that accepted a token issued for a different API, a secret short enough to brute-force offline. "Validate a JWT correctly, and explain why `alg: none`, a missing audience check and long expiry are failures" is in this roadmap's exit criteria because interviewers ask exactly that.

## The idea

**Structure.** A signed JWT (JWS) is three base64url segments separated by dots: `header.payload.signature`. The header names the algorithm (`alg`), the type (`typ`) and usually the key id (`kid`). The payload is a JSON object of **claims**. The signature covers the first two segments. Decoding needs no key, which is the first thing to internalise: anyone holding a token can read it, so **a JWT hides nothing**. Encryption is a separate format, JWE (five segments), rarely used for access tokens; the normal protection is TLS in transit and not putting secrets in the payload.

| Claim | Meaning | Verifier's job |
|---|---|---|
| `iss` | who issued the token | must equal the issuer you trust |
| `sub` | the subject (user or client) | identity for authorization decisions |
| `aud` | who the token is for | must contain this service's identifier |
| `exp` | expiry (seconds since the epoch) | reject after this time, with small skew |
| `nbf` | not before | reject before this time, with small skew |
| `iat` | issued at | sanity check; some verifiers cap the age |
| `jti` | unique token id | needed for replay detection or deny-lists |

Access tokens from modern authorization servers also carry `scope`, `client_id` and `typ: at+jwt` (RFC 9068), which lets a verifier refuse an ID token presented as an access token.

**Signing versus encryption, and which algorithm.** HMAC algorithms (`HS256`) use one shared secret: whoever can verify can also mint, so they only make sense when issuer and verifier are the same deployment. Asymmetric algorithms (`RS256`, `PS256`, `ES256`, `EdDSA`) let the issuer keep the private key and publish the public key, which is what every multi-service setup needs. Public keys are published as a **JWK Set** at the `jwks_uri` named in the issuer's discovery document; each key has a `kid`, so the issuer **rotates** keys by publishing the new one, signing with it, and removing the old one once its tokens have expired. The verifier caches the set and refetches when it sees an unknown `kid`, with a rate limit, or an attacker can make it fetch forever.

**The validation checklist**, in order:

1. Parse. Exactly three segments, valid base64url, header and payload are JSON. Reject anything else without looking further.
2. Algorithm allow-list. Decide the acceptable algorithm (usually one) from your configuration, never from the token's header. The header's `alg` is attacker-controlled input; it may be compared, never obeyed.
3. Signature. Select the key by `kid` from your cached JWKS for the expected issuer and verify the signature over `header.payload`. Ignore any `jwk`, `jku` or `x5u` header offering you a key; a token that carries its own verification key proves nothing.
4. `iss` equals the configured issuer.
5. `aud` contains this service's identifier. A token for `payments-api` must not open `orders-api`.
6. `exp` is in the future and `nbf` in the past, allowing a skew of at most a minute for clock drift between servers.
7. `typ` is what you expect, if the issuer sets it.
8. Only now read `sub`, `scope` and the rest, and make authorization decisions.

**The classic attacks**, explained enough to defend against:

- `alg: none`. The specification defines an "unsecured JWT" with an empty signature. Early libraries accepted a token whose header said `none` as valid. Defence: step 2; `none` is never in the allow-list.
- RS256-to-HS256 confusion. The verifier holds an RSA public key; the attacker changes `alg` to `HS256` and signs with HMAC using the public key bytes as the secret. A library that picks the algorithm from the header and feeds it whatever key it was given accepts the token. Defence: step 2 again, plus a key type bound to its algorithm.
- Weak HMAC secrets. `HS256` with a human-chosen secret is brute-forceable offline from a single captured token. A secret needs at least 256 bits from a cryptographic random source.
- Key injection. `jwk` or `jku` headers pointing at the attacker's key, or a `kid` crafted for path traversal or SQL injection when the server looks the key up. Defence: keys come only from your configuration and the trusted JWKS; `kid` is an untrusted lookup string.

**Design trade-offs.** A JWT is validated without a round trip, which is the point and the problem: nothing happens at the issuer when a token is used, so **revocation** cannot be immediate. The standard compromise is short expiry (five to fifteen minutes) with a refresh token the client exchanges at the authorization server, where revocation and rotation are enforced; the damage window is the access token's lifetime. If that is too long for your threat model, keep a small deny-list of `jti` values until their `exp`, or a "session version" claim checked against a cache, accepting that you have reintroduced a lookup. **What belongs in a token**: identifiers, scopes, audience and the claims the resource server needs for authorization; nothing that must stay confidential or changes faster than the token expires. Tokens travel in a header on every request, so keep them small.

## Example: a decoded token and the checklist applied

A resource server for `orders-api` receives this token at 2026-10-24 00:04:00 UTC (epoch 1792800240). Decoded header and payload:

```json
{"alg":"RS256","typ":"at+jwt","kid":"2026-10-a"}
```

```json
{
  "iss": "https://auth.example.com",
  "sub": "4f3c2a1e-9b7d-4c0e-8a6f-1d2e3f4a5b6c",
  "aud": "orders-api",
  "exp": 1792800600,
  "iat": 1792800000,
  "nbf": 1792800000,
  "jti": "0b7e9a2c-5d1f-4e8a-9c3b-7f6e5d4c3b2a",
  "client_id": "web-bff",
  "scope": "orders:read orders:write"
}
```

| Step | Check | Result |
|---|---|---|
| 1 | Three segments, valid JSON | pass |
| 2 | `RS256` is the one configured algorithm | pass; a header saying `HS256` or `none` fails here, before any key is touched |
| 3 | Key `2026-10-a` is in the cached JWKS of `https://auth.example.com`; the signature verifies | pass |
| 4 | `iss` equals `https://auth.example.com` | pass |
| 5 | `aud` contains `orders-api` | pass; a token with `aud: payments-api` fails here even with a valid signature |
| 6 | `exp` 1792800600 is 360 seconds ahead; `nbf` 1792800000 is 240 seconds behind | pass; the lifetime is ten minutes |
| 7 | `typ` is `at+jwt` | pass; an ID token would say `JWT` and name the client in `aud` |
| 8 | `scope` contains `orders:read`; `sub` identifies the user for object-level checks | authorize |

Spring Security's resource server performs steps 1 to 4 and 6 from one property (`spring.security.oauth2.resourceserver.jwt.issuer-uri`, which also fetches the discovery document); the audience check is the one you must add yourself:

```java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    String jwkSetUri = "https://auth.example.com/oauth2/jwks";
    NimbusJwtDecoder jwtDecoder = NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();
    OAuth2TokenValidator<Jwt> audienceValidator = new JwtClaimValidator<Collection<String>>(
            JwtClaimNames.AUD, audiences -> audiences != null && audiences.contains("orders-api"));
    jwtDecoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer), audienceValidator));
    return jwtDecoder;
}
```

`jwsAlgorithm` is the allow-list of step 2; `createDefaultWithIssuer` supplies the issuer check and the timestamp check with a 60-second skew; the `JwtClaimValidator` is step 5. The JWKS URI comes from the issuer's discovery document, so copy it from there rather than guessing the path.

## Pitfalls

- Decoding instead of verifying. Decode-only calls return the claims without checking the signature. Use the verifying call and give it the key.
- Picking the algorithm from the header. Any code shaped like "if `alg` is X, verify with X" is the confusion bug; the algorithm is configuration.
- Skipping the audience check because the issuer is "ours". One issuer usually serves several APIs; a token for one unlocks the others.
- Long-lived access tokens because refresh was inconvenient. A 24-hour token copied from a log is a 24-hour account takeover with no way to stop it.
- Using the ID token as an API credential. It is addressed to the client (`aud` is the client id), so a correct resource server rejects it; one that accepts it has skipped step 5.

## Check yourself

1. Why is the algorithm in a JWT header an input to be compared rather than an instruction to be followed? Describe the attack that exploits the difference.
2. The token above arrives at `payments-api`, which shares the issuer. Which single check fails, and what would happen if that check were missing?
3. Your product needs "log out everywhere" to take effect within a second. What are your options with JWT access tokens, and what does each cost?
4. An `HS256` token is signed with the secret `orders-service-2026`. What can an attacker who captures one token do, and roughly how hard is it?

## Go deeper

- [RFC 7519: JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519) · the claims and the structure; short.
- [RFC 8725: JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) · the checklist above in normative form, including algorithm and key-management guidance.
- [PortSwigger: JWT attacks](https://portswigger.net/web-security/jwt) · `alg: none`, algorithm confusion, `jwk` and `kid` injection, with labs.
- [OWASP: JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html) · revocation strategies and token storage.
- [Spring Security: OAuth 2.0 Resource Server, JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) · what the default decoder validates and how to add validators.
- [jwt.io: Introduction](https://jwt.io/introduction) · decode tokens while reading this, remembering that decoding is not verifying.

---

Part of [Security](../README.md) · items 6.1, 6.2, 6.3, 6.4
