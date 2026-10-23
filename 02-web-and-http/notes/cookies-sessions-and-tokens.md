# Cookies, sessions and tokens

> **In one sentence:** A cookie is the browser's only credential that is sent automatically, so its attributes decide who can read it and when it is attached; whether the value is an opaque session ID or a self-contained token decides how you scale, revoke and debug authentication.

**Why it matters:** Every web login ends in one of two designs, and the wrong attribute on one `Set-Cookie` header turns either into an account-takeover path. "Where do we keep the JWT in the browser" is the question every frontend team asks on week one, and the honest answer depends on which attack you fear more.

## The idea

**Cookie attributes.** A server sets a cookie with `Set-Cookie`; the browser sends it back as `Cookie: name=value` on every matching request, without the page's JavaScript doing anything. The attributes limit "matching":

| Attribute | What it prevents |
|---|---|
| `Secure` | Sending over plain `http://`, where a network attacker could read it. |
| `HttpOnly` | Reading it from `document.cookie`, so an XSS payload cannot exfiltrate it (it can still make requests from the page). |
| `SameSite=Strict` | Sending it on any request that originates from another site, including a user clicking a link to you. |
| `SameSite=Lax` | Sending it on cross-site `POST`s, iframes and subresources; still sent on top-level `GET` navigations. The sensible default for a session cookie. |
| `SameSite=None` | Nothing; required for cookies that must work in a third-party context, and only allowed together with `Secure`. |
| `Domain=example.com` | Nothing; it *widens* the cookie to all subdomains. Omit it and the cookie is host-only. |
| `Path=/api` | Sending it to other paths; a convenience, not a security boundary, since any page on the origin can still reach `/api`. |
| `Max-Age` / `Expires` | Surviving the browser session. Omit both and the cookie is a session cookie; `Max-Age` wins if both are present and does not depend on the client's clock. |

Two prefixes let the browser enforce the attributes for you: a cookie named `__Host-session` is rejected unless it has `Secure`, `Path=/` and no `Domain`; `__Secure-` requires only `Secure`. "Site" in `SameSite` means registrable domain plus scheme, not origin: `app.example.com` and `api.example.com` are the same site, so `SameSite=Strict` cookies flow between them even though CORS (item 7.2) treats them as different origins.

**Server-side sessions.** The cookie holds a random, opaque ID; everything else (user, roles, expiry) lives in a server-side store. Revocation is immediate (delete the row), the cookie is small, and nothing sensitive leaves the server. The cost is state: every instance must reach the store (Redis, the database) or you need sticky sessions at the load balancer (item 11.3). Rotate the ID on login to defeat session fixation; Spring Security does this by default.

**Stateless tokens.** The credential is a signed document (a JWT) that any instance can verify with a key, no lookup required. Horizontal scaling is trivial and a token can be handed to other services. The costs: you cannot revoke one before it expires, so lifetimes must be short (minutes) and paired with a refresh token that *is* revocable server-side; the token is larger and carries claims in clear text (signed, not encrypted); key rotation needs a `kid` and a published key set. In practice "stateless" systems end up with a token store for refresh tokens and denylists, so the difference is smaller than the brochure says.

**Where the browser should keep a token.** The options, and the attack each one is weak against:

1. `localStorage`: readable by any script on the origin, so a single XSS steals a reusable credential. Not sent automatically, so immune to CSRF. OWASP advises against it for session tokens.
2. JavaScript memory: lost on reload, so it needs a silent refresh (usually a `HttpOnly` cookie carrying a refresh token), at which point you have cookies anyway.
3. A `Secure; HttpOnly; SameSite=Lax` cookie: XSS cannot read it, though it can still make requests while the page is open; cross-site `POST`s are blocked by `SameSite`; the server adds a CSRF token for any case `SameSite` does not cover.
4. A backend-for-frontend: the browser holds only a session cookie; the backend holds the access and refresh tokens for the APIs. This is where the OAuth working group's guidance for browser apps has landed.

The debate is "contested" because XSS defeats every option to some degree. The cookie options keep the credential itself from leaving the browser, which limits the damage to the duration of the attack rather than the lifetime of the token.

## Example: Set-Cookie headers, one attribute at a time

Observed on `curl -sI https://github.com/` (values redacted):

```http
set-cookie: _gh_sess=<redacted>; path=/; HttpOnly; secure; SameSite=Lax
set-cookie: _octo=<redacted>; expires=Sat, 23 Oct 2027 18:31:01 GMT; domain=.github.com; path=/; secure; SameSite=Lax
```

The first is a server-side session: no `Domain` (host-only, so `gist.github.com` never sees it), no expiry (dies with the browser), `HttpOnly` (scripts cannot read it), `Lax` (not attached to cross-site `POST`s). The second is an analytics identifier: one-year lifetime, `domain=.github.com` so every subdomain receives it, and readable by JavaScript because there is no `HttpOnly`. Same site, two deliberately different policies.

A session cookie as you should set it today, and what each piece buys:

```http
Set-Cookie: __Host-session=9f3b2c7e4d1a; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=28800
```

- `__Host-` makes the browser reject the cookie if `Secure`, `Path=/` or the absence of `Domain` is ever lost in a refactor.
- `Secure` and `HttpOnly` close the network-sniffing and script-theft paths.
- `SameSite=Lax` blocks the classic CSRF `POST` from another site while keeping "click a link to the dashboard" working.
- `Max-Age=28800` gives eight hours and lets the server-side session expire at the same time.

A cookie that must work inside a third-party iframe (an embedded widget) has no choice but to drop the cross-site protection:

```http
Set-Cookie: widget_session=4a7c; Path=/; Secure; HttpOnly; SameSite=None
```

Without `Secure`, browsers discard a `SameSite=None` cookie outright, which is the most common reason "the embedded login stopped working".

In Spring Boot the session cookie's attributes are properties, so they can be reviewed in one place:

```properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

## Pitfalls

- `Domain=example.com` on the session cookie. Every subdomain, including the one that hosts user-uploaded content or a forgotten marketing site, now receives it. Omit `Domain` unless cross-subdomain login is a requirement.
- Relying on the browser's default `SameSite`. Chrome treats a missing attribute as `Lax`; other browsers differ. Set it explicitly.
- `SameSite=None` without `Secure`, or a `SameSite=Strict` session cookie on a site users reach from links in email. The first is silently dropped; the second logs people out on every arrival.
- A JWT in a cookie that grows past 4 KB. Browsers are only required to keep 4096 bytes per cookie; the header gets truncated or the request is rejected with 431 by the proxy.
- Logout that only deletes the cookie. With server-side sessions, delete the session too; with JWTs, revoke the refresh token and accept that the access token lives until expiry.
- Treating `HttpOnly` as XSS protection. It protects the cookie value, not the user: injected script can still call your API with the cookie attached. Content Security Policy (item 7.3) is the actual XSS defence.
- Long-lived access tokens "to avoid refresh complexity". The whole stateless trade-off rests on short lifetimes; a 24-hour unrevocable token is a 24-hour breach.

## Check yourself

1. A support engineer must be able to terminate a compromised user's access within seconds. Which design do you pick, and what would the stateless design need to add to meet the requirement?
2. Why can `app.example.com` send a `SameSite=Strict` cookie to `api.example.com`, while `partner.com` cannot send its cookie to either?
3. Rank `localStorage`, an `HttpOnly` cookie and a backend-for-frontend by what an XSS payload can steal, and by what a CSRF attack can do.
4. A `Set-Cookie` with `SameSite=None` is being ignored by the browser. What is missing, and why does the browser enforce it?

## Go deeper

- [MDN: Using HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies) and [Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) · every attribute, with current browser behaviour.
- [web.dev: SameSite cookies explained](https://web.dev/articles/samesite-cookies-explained) · the clearest explanation of `Lax`, `Strict` and `None`, with the cases each one covers.
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) · ID entropy, rotation, expiry and cookie attributes as a checklist.
- [OWASP: HTML5 Security Cheat Sheet, local storage](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html#local-storage) · the case against tokens in `localStorage`, from the source.
- [OAuth 2.0 for Browser-Based Applications](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps) · the IETF's architecture comparison, including the backend-for-frontend pattern.
- [RFC 6265: HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265.html) · the cookie specification, for the exact matching rules.

---

Part of [Web & HTTP](../README.md) · items 6.1, 6.2, 6.3
