# Security headers, HSTS and testing your TLS configuration

> **In one sentence:** A handful of response headers tell the browser to refuse behaviours that attackers rely on (downgrading to HTTP, sniffing content types, framing your page, leaking URLs in `Referer`, running scripts from anywhere), Spring Security sends the basic set by default, and the rest is five lines of configuration plus a scanner to prove it stuck.

**Why it matters:** These headers are the cheapest defence-in-depth you will ever ship: no code changes, one configuration block, and they blunt whole classes of attack (SSL stripping, clickjacking, MIME confusion, token leakage through referrers) that your application code cannot otherwise see. They are also the first thing an external scanner or a penetration tester reports, so knowing which ones matter, which are obsolete, and why the HSTS one needs care keeps the findings list short.

## The idea

| Header | Value to send | What it stops |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | The browser upgrades every future `http://` request to this host to `https://` and refuses to click through certificate errors, so an attacker on the network cannot downgrade the connection |
| `Content-Security-Policy` | At least `default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'` | Where scripts, styles, frames and connections may come from; the XSS seatbelt of item 2.10 and the replacement for `X-Frame-Options` |
| `X-Content-Type-Options` | `nosniff` | The browser guessing a content type: a user upload served as `text/plain` can otherwise be interpreted as HTML or script |
| `X-Frame-Options` | `DENY` | Clickjacking in browsers too old for `frame-ancestors`; harmless to send both |
| `Referrer-Policy` | `strict-origin-when-cross-origin` (or `no-referrer` on pages whose URLs carry tokens) | The full URL, with query string and path, reaching third parties through the `Referer` header |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=(), payment=()` | Your page, or a script injected into it, or an iframe inside it, using browser features you never meant to use |
| `Cross-Origin-Opener-Policy` | `same-origin` | Other origins keeping a handle on your window after opening it; also isolates the process against speculative side-channel attacks |
| `Cross-Origin-Resource-Policy` | `same-origin` or `same-site` | Other origins embedding your responses as `<img>`, `<script>` or `<audio>` and measuring them |
| `Cache-Control` | `no-store` on authenticated responses | A shared cache or the back button serving one user's page to another |
| `Server`, `X-Powered-By` | Remove | Nothing important; version strings make scanning marginally easier |

Two headers you may still meet are obsolete. `X-XSS-Protection` controlled a browser filter that was removed because it caused its own vulnerabilities; the only sensible value is `0`, which Spring Security sends. `Public-Key-Pins` (HPKP) was removed from every browser; see pinning below.

**HSTS in detail.** The header is only honoured when received over a valid HTTPS connection (browsers ignore it on HTTP, so a plain-HTTP site cannot accidentally lock itself out), and it protects only visits after the first. The first visit is the gap: a user who types `example.com` and is intercepted before the redirect never sees the header. The **preload list** closes it: submit the domain at hstspreload.org, and browsers ship with it already marked HTTPS-only. Preload requires `max-age` of at least one year, `includeSubDomains`, the `preload` directive, a redirect from HTTP to HTTPS on the same host, and every subdomain serving HTTPS. That last condition is the one to check first: `includeSubDomains` applies to `intranet.example.com` and `legacy.example.com` too, and removal from the preload list takes months. Start with a short `max-age` (a day), confirm nothing breaks, then raise it to a year.

**Why certificate pinning is usually wrong.** Pinning means the client accepts only a specific key or certificate, not anything the trust store would allow. It protects against a compromised or coerced CA, which is rare, and it fails the moment the key rotates unexpectedly, which is common: an incident, a provider change, a CA deprecation. HPKP was withdrawn because a wrong pin, or an attacker who set one, locked users out of a site for the duration of `max-age`. Mobile apps that pin leaf certificates brick themselves at renewal. Certificate Transparency (item 7.2) and short-lived certificates deliver most of the benefit without the fragility. Pin only when you control both ends, pin the CA or the SPKI hash rather than the leaf, keep a backup pin, and have a tested way to ship an update before the backup runs out.

**Testing.** For headers: `curl -sI` and read, then securityheaders.com for a grade and a list. For TLS: SSL Labs for a public host; the Mozilla configuration generator for the server profile you should be running (modern, intermediate, old); `openssl s_client` to prove a protocol version is refused.

## Example: what good looks like, and configuring it in Spring Security

Real headers from two sites that take this seriously (`curl -sI`, abridged):

```text
$ curl -sI https://github.com | grep -iE "^(strict|x-content|x-frame|referrer|content-security|x-xss)"
strict-transport-security: max-age=31536000; includeSubdomains; preload
x-frame-options: deny
x-content-type-options: nosniff
x-xss-protection: 0
referrer-policy: origin-when-cross-origin, strict-origin-when-cross-origin
content-security-policy: default-src 'none'; base-uri 'self'; ... frame-ancestors 'none'; ... upgrade-insecure-requests; ...

$ curl -sI https://developer.mozilla.org/en-US/ | grep -iE "^(strict|x-content|x-frame|referrer|content-security)"
strict-transport-security: max-age=63072000
x-content-type-options: nosniff
content-security-policy: default-src 'self'; script-src 'report-sample' 'self' ... 'sha256-...'; object-src 'none'; base-uri 'self'; ...
referrer-policy: strict-origin-when-cross-origin
x-frame-options: DENY
```

Spring Security 6 sends, without configuration: `Cache-Control: no-cache, no-store, max-age=0, must-revalidate` (with `Pragma` and `Expires`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`, and `Strict-Transport-Security` with a one-year `max-age` and `includeSubDomains` on requests it sees as secure. The additions that bring an application to the table above:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.headers(headers -> headers
            .httpStrictTransportSecurity(hsts -> hsts
                    .maxAgeInSeconds(31_536_000)
                    .includeSubDomains(true)
                    .preload(true))
            .contentSecurityPolicy(policy -> policy
                    .policyDirectives("default-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'"))
            .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicyHeaderWriter.ReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN))
            .crossOriginOpenerPolicy(opener -> opener
                    .policy(CrossOriginOpenerPolicyHeaderWriter.CrossOriginOpenerPolicy.SAME_ORIGIN))
            .permissionsPolicy(permissions -> permissions
                    .policy("camera=(), microphone=(), geolocation=(), payment=()")));
    return http.build();
}
```

One deployment detail decides whether HSTS is sent at all. Spring Security writes it only when `request.isSecure()` is true. Behind a load balancer that terminates TLS, the request arrives over plain HTTP and the header is silently omitted. Tell the framework to trust the proxy's `X-Forwarded-Proto`:

```properties
server.forward-headers-strategy=framework
```

and confirm with `curl -sI` through the load balancer, not against the pod. For responses that must never sit in a cache or a back-button history (account pages, downloads of personal data), the framework default already says `no-store`; for public, cacheable pages, override `Cache-Control` per response rather than disabling the default.

Proving a TLS version is refused. Modern OpenSSL builds will not even offer TLS 1.1 unless told to lower their security level, which is itself a sign of where the floor is:

```bash
openssl s_client -connect github.com:443 -servername github.com -tls1_1 -cipher 'DEFAULT:@SECLEVEL=0' </dev/null
```

```text
SSL routines:ssl3_read_bytes:tlsv1 alert protocol version:...:SSL alert number 70
```

Alert 70 is the server saying no. The same command with `-tls1_2` negotiates `ECDHE-ECDSA-AES128-GCM-SHA256`, and without a version flag it negotiates TLS 1.3. A server whose intermediate profile still has to support TLS 1.2 should refuse everything older and offer only the ECDHE, AEAD suites the Mozilla generator lists.

## Pitfalls

- `includeSubDomains` before auditing the subdomains. The intranet host that only speaks HTTP stops working for everyone who visited the main site, and preload makes that permanent for months.
- Setting a CSP with `'unsafe-inline'` in `script-src` to make it "pass". The scanner is happy and the policy does nothing against XSS; use nonces or hashes (item 2.10).
- Testing headers against the application directly. The load balancer, CDN or gateway may strip, add or override them; test the URL users hit.
- HSTS missing behind the proxy because `isSecure()` is false. Set the forward-headers strategy, or send the header from the proxy.
- `Referrer-Policy: no-referrer` everywhere. It breaks legitimate analytics and some CSRF defences that compare `Origin`/`Referer`; `strict-origin-when-cross-origin` is the default for a reason, and `no-referrer` belongs on the pages whose URLs carry secrets.
- Pinning the leaf certificate in a mobile app. The next renewal is an outage you can only fix with an app store release.
- Treating an A+ as done. Headers are the browser's side of the defence; the server still has to encode output, check authorization and validate input.

## Check yourself

1. A site sends `Strict-Transport-Security` only over HTTPS and redirects HTTP to HTTPS. Which visit is still vulnerable to SSL stripping, and what closes the gap?
2. Why does `X-Content-Type-Options: nosniff` matter specifically for an endpoint that serves user-uploaded files?
3. Your application sends HSTS in tests but `curl -sI` through the production load balancer shows no such header. What is the most likely cause and the fix?
4. When is certificate pinning the right choice, and what three things must be in place before you ship it?

## Go deeper

- [OWASP: HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) · every header above with recommended values and the ones to remove.
- [Spring Security: Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) · the defaults and the DSL used in the example.
- [MDN: Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Strict-Transport-Security) and [hstspreload.org](https://hstspreload.org/) · the directive semantics and the preload submission requirements.
- [MDN: Permissions-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy) and [Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy) · the full list of features and policy values.
- [securityheaders.com](https://securityheaders.com/) · paste a URL, read the report, fix the red lines.
- [SSL Labs Server Test](https://www.ssllabs.com/ssltest/) and [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/) · test the TLS side, then generate the configuration for your server from the profile you need.
- [OWASP: Pinning Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Pinning_Cheat_Sheet.html) · when pinning is appropriate and how to do it without bricking clients.

---

Part of [Security](../README.md) · items 9.4, 7.5
