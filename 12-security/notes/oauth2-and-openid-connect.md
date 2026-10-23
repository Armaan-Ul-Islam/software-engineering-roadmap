# OAuth 2.0 and OpenID Connect

> **In one sentence:** OAuth 2.0 lets a user grant an application limited access to their resources at another service without sharing a password, by having an authorization server issue the application a scoped access token; OpenID Connect adds a signed ID token so the application also learns, verifiably, who logged in.

**Why it matters:** Every "Log in with Google", every mobile app talking to your API, and every service calling another with a client credential runs on these two protocols. They are also where the subtle authentication bugs live: a missing `state` that lets an attacker log you into their account, a redirect URI matched by prefix, an API that accepts tokens meant for a different API. Drawing the Authorization Code flow with PKCE on a whiteboard and naming every token is a standard senior interview question because it tests whether you understand the trust relationships, not just the library.

## The idea

**Four roles.** The **resource owner** is the user. The **client** is the application that wants access (your web app, a mobile app, a CLI). The **authorization server** authenticates the user, asks for consent and issues tokens (Keycloak, Entra ID, Auth0, Spring Authorization Server). The **resource server** is the API that accepts tokens and serves data. One deployment often plays several roles, which is where the confusion starts.

**Scopes and consent.** A scope is a string naming a permission the client asks for (`orders:read`, `openid`, `profile`). The authorization server shows the user what is requested and records the consent; the token carries the granted scopes and the resource server enforces them. Scopes bound what the client may do on the user's behalf; they do not replace the user's own permissions, which the resource server still has to check (see item 4.2).

**Grant types** are the recipes for obtaining a token:

| Grant | Who is present | Use it for |
|---|---|---|
| Authorization Code with PKCE | a user in a browser | web apps, single-page apps, mobile and desktop apps: everything with a user |
| Client Credentials | no user; the client authenticates as itself | service-to-service calls, batch jobs |
| Device Code | a user, on a device without a browser or keyboard | TVs, consoles, CLIs that show a code to enter on your phone |
| Refresh Token | the client, holding a refresh token | a new access token without bothering the user |

The **Implicit** grant (tokens returned in the URL fragment) and the **Resource Owner Password** grant (the client collects the password) are gone in OAuth 2.1. The first leaked tokens through browser history and `Referer` headers and could not use PKCE; the second defeats the purpose of OAuth and blocks MFA. OAuth 2.1 also requires PKCE for every Authorization Code flow, exact string matching of redirect URIs, no bearer tokens in query strings, and refresh tokens that are either rotated on use or bound to the client.

**PKCE** (Proof Key for Code Exchange) fixes the one weak link in the code flow: the authorization code travels through the browser and can be intercepted. The client invents a random `code_verifier`, sends its SHA-256 hash as `code_challenge` when the flow starts, and sends the verifier itself when redeeming the code. An intercepted code is useless without the verifier, which never left the client.

**Client Credentials** has no browser and no user: the client posts `grant_type=client_credentials` with its own credentials (a secret, a `private_key_jwt` assertion or an mTLS certificate) and receives an access token whose subject is the client itself. **Device Code** has the device fetch a `device_code`, a short `user_code` and a `verification_uri`, show the user the URI and the code, and poll the token endpoint until the user approves on another device.

**Three tokens**, three audiences:

| Token | Meant for | Format | Lifetime | Carries |
|---|---|---|---|---|
| Access token | the resource server; opaque to the client | opaque string or JWT | minutes | scopes, subject, audience, expiry |
| Refresh token | the authorization server only | opaque | hours to months; rotated on use | the right to obtain new access tokens |
| ID token | the client | always a JWT | minutes | who authenticated, when and how, plus the `nonce` |

A resource server validates an access token either locally (a JWT: signature against the issuer's published keys, `iss`, `aud`, `exp`; see item 6.2) or by **introspection** (a `POST` to the authorization server's introspection endpoint, which answers `active: true` and the claims), the only option for opaque tokens and the one that gives immediate revocation.

**OpenID Connect** is a thin identity layer on OAuth 2.0. Request the `openid` scope and the authorization server also returns an ID token with standard claims (`sub`, the stable user identifier; `email` and `email_verified`; `name`; `preferred_username`; `auth_time`; `amr` for how the user authenticated), offers a UserInfo endpoint for more, and publishes its configuration at `https://issuer/.well-known/openid-configuration`: endpoints, signing keys (`jwks_uri`), supported scopes and algorithms. **Discovery** is why Spring Boot needs only an `issuer-uri` to configure a client or a resource server. "Log in with X" is exactly this flow, with the ID token as the proof of login and `sub` (never `email`, which can change or be reassigned) as the key for the local account.

## Example: Authorization Code with PKCE, step by step

A web application with a server side (or a backend-for-frontend) logs a user in and then calls an API with the resulting access token:

```text
 Browser                  Client (web app)                    Authorization server          Resource server (API)
   |                        |                                   |                              |
   |  1. GET /login         |                                   |                              |
   |----------------------->| verifier = 32 random bytes
   |                        | challenge = base64url(sha256(verifier))
   |                        | state = random, nonce = random; keep all three in the session
   |                        |                                   |                              |
   |  2. 302 Location: https://auth.example.com/authorize?response_type=code&client_id=web-app
   |          &redirect_uri=https://app.example.com/callback&scope=openid%20profile%20orders:read
   |          &state=S&nonce=N&code_challenge=C&code_challenge_method=S256
   |<-----------------------|                                   |                              |
   |  3. GET /authorize?...  (the browser follows the redirect)
   |----------------------------------------------------------->|                              |
   |  4. login form, second factor, consent screen (several round trips)
   |<-----------------------------------------------------------|                              |
   |  5. 302 Location: https://app.example.com/callback?code=AC&state=S
   |<-----------------------------------------------------------|                              |
   |  6. GET /callback?code=AC&state=S
   |----------------------->| state == S from the session? otherwise stop
   |                        |  7. POST /token  grant_type=authorization_code&code=AC
   |                        |     &redirect_uri=https://app.example.com/callback&client_id=web-app
   |                        |     &code_verifier=verifier   (plus client_secret for a confidential client)
   |                        |---------------------------------->| base64url(sha256(verifier)) == C?
   |                        |  8. { access_token, id_token, refresh_token, expires_in, scope }
   |                        |<----------------------------------|                              |
   |                        | validate id_token: signature, iss, aud == web-app, nonce == N, exp
   |  9. Set-Cookie: session=...  (local session keyed by sub)
   |<-----------------------|                                   |                              |
   |                        | 10. GET /orders   Authorization: Bearer <access_token>
   |                        |----------------------------------------------------------------->|
   |                        |                                   |                              | validate token, check scope
   |                        |<-----------------------------------------------------------------|
```

What each step protects:

1. Steps 1 and 2: `state` ties the callback to this browser session, `nonce` ties the ID token to this login, and the verifier never leaves the client.
2. Steps 3 to 5: the user authenticates at the authorization server, never at the client, which never sees the password; that is why MFA and passkeys can be added without changing a single client.
3. Step 6: the `state` check stops an attacker from completing the flow in the victim's browser with the attacker's own code (login CSRF) and from injecting a stolen code.
4. Step 7: the verifier proves that whoever redeems the code also started the flow; a confidential client authenticates itself as well, and the repeated `redirect_uri` must match step 2.
5. Steps 8 and 9: the client validates the ID token like any JWT, plus the `nonce`, and only then creates a local session. The ID token's job ends here; it is never sent to the API.
6. Step 10: the access token goes to the resource server, which validates it independently and enforces scope and the user's permissions.

Spring Security's `oauth2Login()` performs steps 1 to 9 from a few properties, generating `state` and `nonce` itself and using PKCE for public clients (for confidential clients, enable it with `OAuth2AuthorizationRequestCustomizers.withPkce()`):

```properties
spring.security.oauth2.client.registration.corp.client-id=web-app
spring.security.oauth2.client.registration.corp.client-secret=${OAUTH_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.corp.scope=openid,profile,orders:read
spring.security.oauth2.client.provider.corp.issuer-uri=https://auth.example.com
```

The mistakes that keep recurring, and what they cost:

| Mistake | What goes wrong | Fix |
|---|---|---|
| Missing or unchecked `state` | Login CSRF: the victim ends up logged into the attacker's account and later saves their data there; stolen codes can be injected | Generate per login, bind to the session, compare on callback |
| Loose `redirect_uri` matching | A prefix or wildcard match lets `https://app.example.com.evil.net/` or an open redirect on your own site receive the code, and the attacker finishes the login as the victim | Register exact URIs; the server compares whole strings |
| Audience confusion | A token issued for `payments-api` is accepted by `orders-api` because both only check signature and issuer | Every resource server checks `aud`; clients request tokens per API |
| Access token as proof of identity | A token the user once granted to a malicious app elsewhere is a valid access token too; it says what the bearer may do, not who is present | Authenticate with the ID token (`aud` is your client id, `nonce` matches), or verify through the issuer that the token was issued to your client |
| Long-lived access tokens | A leaked token works for hours or days and cannot be revoked | Minutes-long access tokens, rotating refresh tokens with reuse detection |
| Tokens in `localStorage` | Any XSS exfiltrates them | A backend-for-frontend holding the tokens behind an `HttpOnly` session cookie (see item 5.5) |

## Pitfalls

- Using `email` as the account key. Providers do not guarantee it is stable or unique; `sub` together with `iss` is the identity.
- Writing your own authorization server for one application. Use Keycloak, Spring Authorization Server or a hosted provider; the protocol surface is large and the mistakes are quiet.
- Shipping a client secret inside a single-page or mobile app. Anything delivered to users is public; those clients use PKCE and no secret.
- Validating the ID token's signature but not its `aud` and `nonce`. An ID token from the same issuer for a different client would pass.

## Check yourself

1. Walk through what the attacker gains if the client does not verify `state`, and why PKCE alone does not prevent it.
2. Why must the resource server check `aud` even when it trusts the issuer, and what does "request tokens per API" mean for a client that calls three APIs?
3. A mobile app sends its access token to your backend as "proof the user is logged in". Describe the attack and the correct alternative.
4. Which grant does a nightly job that copies data between two services use, what is the token's subject, and why is a refresh token pointless there?

## Go deeper

- [OAuth 2.0 Simplified](https://www.oauth.com/) · Aaron Parecki's free book; the clearest end-to-end walk-through of every flow.
- [Aaron Parecki: OAuth 2.0 and OpenID Connect in plain English](https://www.youtube.com/watch?v=996OiexHze0) · an hour that fixes the mental model.
- [OAuth 2.1](https://oauth.net/2.1/) · what changed and why; short.
- [RFC 7636: PKCE](https://www.rfc-editor.org/rfc/rfc7636) · the proof key mechanism in full.
- [OpenID Connect: How it works](https://openid.net/developers/how-connect-works/) · the identity layer and its claims.
- [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700) · the mistakes table in normative form, with the attacks spelled out.
- [PortSwigger: OAuth 2.0 authentication vulnerabilities](https://portswigger.net/web-security/oauth) · labs for the `state`, redirect and implicit-flow mistakes.

---

Part of [Security](../README.md) · items 5.1, 5.2, 5.3, 5.4, 5.6
