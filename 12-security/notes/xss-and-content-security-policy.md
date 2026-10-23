# Cross-site scripting and Content Security Policy

> **In one sentence:** Cross-site scripting (XSS) is your page running an attacker's script because untrusted text reached the browser in a place where it was read as code; encoding output for the exact context it lands in prevents it, and a Content Security Policy limits the damage when an encoding is missed.

**Why it matters:** A script running in your origin can do everything the logged-in user can: read the page, call your API with their session, change their email address and quietly post the results elsewhere. Templating engines and React removed the easy cases, so the XSS that ships today hides in the escape hatches (`th:utext`, `innerHTML`, `dangerouslySetInnerHTML`) and in URL and JavaScript contexts where HTML escaping is the wrong tool.

## The idea

Three variants, one mechanism:

| Variant | Where the payload travels | Typical shape |
|---|---|---|
| Reflected | In the request, echoed straight back in the response | A search page that prints "Results for ..."; delivered as a link the victim clicks |
| Stored | Saved by the server, served to every later viewer | A comment, a profile name, a support ticket; reaches admins through their own console |
| DOM-based | Never reaches the server | Client-side JavaScript copies `location.hash`, `document.referrer` or a `postMessage` payload into `innerHTML` |

The browser has several parsers, and each has its own idea of what a special character is. Text is safe only when it is encoded for the parser that will read it:

| Context | Example sink | Correct handling |
|---|---|---|
| HTML body | `<p>HERE</p>` | HTML entity encoding (`<` to `&lt;`, `&` to `&amp;`, and so on) |
| Quoted attribute | `<input value="HERE">` | Entity encoding including quotes; always quote the attribute |
| URL in an attribute | `<a href="HERE">` | Percent-encode parameters, and validate that the scheme is `http` or `https` |
| JavaScript | `<script>var name = "HERE";</script>` | Avoid. Put the data in a `data-` attribute or a `<script type="application/json">` block and read it from code |
| CSS | `style="color: HERE"` | Avoid; allow-list the values |

Frameworks apply the HTML-body and attribute encodings for you, which is why most modern XSS lives in the exceptions. Thymeleaf's `th:text` and inline `[[...]]` escape; `th:utext` and `[(...)]` do not. React's JSX escapes text and attribute values; `dangerouslySetInnerHTML` does not, and `href={userUrl}` still runs a `javascript:` URL (React logs a warning and renders it). JSP's `${...}` does not escape at all; `<c:out>` does. When you must render HTML written by users (rich-text comments), sanitise it with an allow-list sanitiser such as DOMPurify in the browser or the OWASP Java HTML Sanitizer on the server, never with a regular expression. Outside templates, the OWASP Java Encoder gives you one method per context: `Encode.forHtml`, `Encode.forHtmlAttribute`, `Encode.forJavaScript`, `Encode.forUriComponent`.

Encoding is the fix. **Content Security Policy** (CSP) is the seatbelt: a response header that tells the browser which scripts may run and where the page may send data. With a policy that allows only your own script files, or only scripts carrying a per-response nonce, an injected `<script>` or `onerror=` handler is inert even when an encoding was missed. The policy also refuses `eval` and inline event handlers, which is why retrofitting it onto an old application takes work, and why the header has a **report-only** mode: the browser reports violations to you without blocking anything, so you can fix the inline scripts first and enforce later.

The last line of defence is cookie hygiene. An `HttpOnly` session cookie cannot be read by script, so an XSS cannot copy the session and use it from another machine. It can still make requests as the user from inside the page, which is why `HttpOnly` is damage control, not a fix.

## Example: three sinks and a policy

A DOM-based XSS and its fix. The payload travels in the URL fragment, which the browser never sends to the server:

```javascript
// vulnerable: whatever follows # in the URL becomes HTML
document.getElementById("greeting").innerHTML = "Hello " + decodeURIComponent(location.hash.slice(1));

// fixed: text stays text
document.getElementById("greeting").textContent = "Hello " + decodeURIComponent(location.hash.slice(1));
```

The same comment rendered three ways in Thymeleaf:

```html
<p th:text="${comment.body}">escaped: safe for any text</p>
<p th:utext="${comment.body}">unescaped: only for HTML you sanitised yourself</p>
<a th:href="${comment.website}">escaped as an attribute, yet a javascript: URL still runs when clicked</a>
```

The third line is the one people miss: attribute encoding is applied and still insufficient, because the dangerous part is the URL scheme, not a special character. Validate that `website` starts with `https://` or `http://` when it is saved.

A starting policy for a server-rendered application that serves its own scripts, sent on every HTML response:

```http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-7f3c9a1e2b4d6c8e'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; report-uri /csp-reports
```

| Directive | Value | What it does |
|---|---|---|
| `default-src` | `'self'` | Fallback for every resource type not listed: only our origin |
| `script-src` | `'self' 'nonce-...'` | Scripts may come from our origin or carry this response's nonce. No `'unsafe-inline'`, so injected inline script does not run; no `'unsafe-eval'` |
| `style-src` | `'self'` | Stylesheets from our origin only; inline `style` attributes are blocked (relax with a nonce if you must) |
| `img-src` | `'self' data:` | Images from our origin and data URIs; add your CDN host if you have one |
| `connect-src` | `'self'` | `fetch`, XHR and WebSockets only to our origin, so injected code cannot post data to the attacker |
| `object-src` | `'none'` | No plugins |
| `base-uri` | `'self'` | Stops an injected `<base>` tag from redirecting every relative script URL |
| `form-action` | `'self'` | Forms may submit only to us; stops an injected form from harvesting input |
| `frame-ancestors` | `'none'` | Nobody may frame the page (clickjacking); the modern replacement for `X-Frame-Options` |
| `report-uri` | `/csp-reports` | Where the browser posts a JSON violation report; newer browsers also support `report-to` |

The nonce is 16 random bytes from `SecureRandom`, base64-encoded, generated per response by a filter that both writes the header and exposes the value to the template, so that `<script th:attr="nonce=${cspNonce}" src="/js/app.js"></script>` carries it. Spring Security does not generate nonces, but it writes a static policy for you:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.headers(headers -> headers
            .contentSecurityPolicy(policy -> policy
                    .policyDirectives("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                            + "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
                            + "report-uri /csp-reports")
                    .reportOnly()));
    return http.build();
}
```

With `reportOnly()` the header is `Content-Security-Policy-Report-Only` and nothing is blocked. Roll out in that mode, read the reports for a couple of weeks, move inline scripts into files or give them nonces, then remove `reportOnly()`. Keep the report endpoint afterwards; it is the cheapest XSS detector you will ever run.

Finally, make sure the session cookie carries the right attributes. Spring Boot:

```properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
```

## Pitfalls

- `'unsafe-inline'` in `script-src`. It is the first thing someone adds to make a legacy page work, and it turns the policy into decoration as far as XSS is concerned. Use nonces or hashes instead.
- Encoding for the wrong context. Entity-encoding a value and then placing it in an unquoted attribute (`<div class=HERE>`) still lets `x onmouseover=alert(1)` break out, because a space ends the attribute. Quote every attribute.
- Treating URLs as text. `javascript:` survives HTML encoding; validate the scheme.
- Sanitising with a blacklist. `<img src=x onerror=...>` and `<svg onload=...>` are the classic survivors of "strip `<script>`". Use a real sanitiser with an allow-list.
- Trusting "internal" data. Display names from an identity provider, content entered by admins and payloads from other services are all untrusted at the point of rendering; the admin console is the favourite target of stored XSS.
- Policies without `object-src 'none'` and `base-uri 'self'`. Both are known bypass routes for otherwise strict policies.
- Relying on `HttpOnly`. It protects the cookie, not the user.

## Check yourself

1. A comment body is rendered with `th:text` and the author's website with `th:href="${comment.website}"`. Which is still exploitable, and why does attribute encoding not help?
2. Explain why `script-src 'self' 'nonce-...'` stops an injected `<script>alert(1)</script>` while `script-src 'self' 'unsafe-inline'` does not.
3. The session cookie is `HttpOnly` and an attacker finds a stored XSS. What can they still do, and why is `HttpOnly` nevertheless worth having?
4. Where does a DOM-based payload travel, and why do server-side encoding and a web application firewall never see it?

## Go deeper

- [PortSwigger: Cross-site scripting](https://portswigger.net/web-security/cross-site-scripting) · every variant with labs; do the DOM-based ones.
- [OWASP: XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) · the context table in full, with the rule for each.
- [OWASP: DOM based XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html) · the client-side sinks and how to handle each one.
- [OWASP: Content Security Policy Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html) · directive reference and rollout advice.
- [web.dev: Mitigate cross-site scripting with a strict CSP](https://web.dev/articles/strict-csp) · the nonce-based policy explained by the people who measured it at Google.
- [CSP Evaluator](https://csp-evaluator.withgoogle.com/) · paste your policy and get the bypasses pointed out.
- [OWASP Java Encoder](https://owasp.org/www-project-java-encoder/) · the encoding library for code outside templates.

---

Part of [Security](../README.md) · item 2.10
