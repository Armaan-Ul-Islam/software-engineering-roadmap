# Cross-site request forgery

> **In one sentence:** CSRF is an attacker's page making the victim's browser send a request to your application with the victim's cookies attached automatically; the defence is to require something the attacker's page cannot produce, which in practice is a `SameSite` cookie policy plus a token the browser does not send on its own.

**Why it matters:** Any state-changing endpoint protected only by a session cookie can be triggered by a page the user merely visits: a transfer, an email change, a "delete account" call. Spring Security turns the protection on by default, so the practical questions are why the token is needed at all, how to make it work with a single-page application, and when disabling it is correct rather than reckless. Those are also the questions interviewers ask.

## The idea

Browsers attach cookies based on the request's destination, not on who initiated it. If `bank.example` set a session cookie, a request to `bank.example` carries that cookie whether it was sent by a page on `bank.example` or by a page on `evil.example`. Cookies are **ambient authority**: the server sees a well-formed request with a valid session and has no way, from the cookie alone, to know which page sent it.

The attack therefore needs no code injection and no stolen secret. The attacker's page contains a form whose `action` points at your endpoint with the fields pre-filled, and a script that submits it on load. The victim is logged in to your application in another tab, opens the attacker's page, and the browser sends `POST /transfers` with the victim's cookie. The response goes to the attacker's page, which cannot read it because of the same-origin policy, but the transfer already happened. A `GET` that changes state is even easier: `<img src="https://bank.example/transfers?to=...">` is enough.

Three defences, and a well-built application uses the first two together:

1. **`SameSite` cookies.** The attribute tells the browser when to attach the cookie to cross-site requests. `Strict` never does. `Lax` attaches it only on top-level navigations with safe methods (clicking a link), so a cross-site `POST` arrives without the cookie and the attack fails. `None` always attaches it and requires `Secure`. Modern Chromium treats cookies without the attribute as `Lax`, with a two-minute exception after the cookie is set that does not apply when you set `Lax` explicitly. "Site" means registrable domain, so `app.example.com` and `blog.example.com` are the same site: a cross-site scripting hole in the blog defeats `SameSite` on the app.
2. **A token the attacker cannot obtain.** The **synchroniser token** pattern generates a random value per session, renders it into each form as a hidden field (or exposes it for scripts to send in a header), and rejects state-changing requests whose token does not match the one stored server-side. The attacker's page cannot read it because of the same-origin policy. The **double-submit cookie** variant stores the token in a cookie instead of the session and requires the same value in a header or field: the attacker's page can neither read that cookie nor set cookies for your domain, so the two values match only for your own pages. It is stateless, which suits a cluster without shared sessions, but weaker when a sibling subdomain can set cookies, which is why a signed variant exists.
3. **Not using cookies for authentication.** An API that reads a bearer token from the `Authorization` header is immune: browsers never add that header on their own, the attacker's page cannot read the token out of another origin's storage, and a cross-origin `fetch` carrying it needs a CORS preflight that your API will not approve for `evil.example`. Immune, that is, until somebody puts the token in a cookie for convenience.

Spring Security applies the synchroniser token to every request whose method is not `GET`, `HEAD`, `OPTIONS` or `TRACE`. By default the token lives in the HTTP session (`HttpSessionCsrfTokenRepository`) and is expected in the `_csrf` form parameter or the `X-CSRF-TOKEN` header. Thymeleaf with the Spring Security dialect adds the hidden field to every `th:action` form, and since Spring Security 6 the value rendered into the page is masked per request to defeat the BREACH compression attack. `CookieCsrfTokenRepository` switches to the double-submit style, with an `XSRF-TOKEN` cookie that Angular and axios read and return as `X-XSRF-TOKEN` without any code of yours.

## Example: the attack page, then two correct configurations

The attack, in prose. The attacker hosts `https://evil.example/cute-cats.html`. The page shows cats and also contains an invisible form with `action="https://bank.example/transfers"`, `method="post"` and hidden inputs `to=attacker-iban` and `amount=1000`, plus a script that calls `form.submit()` on load. The victim, logged in to `bank.example` with a session cookie that lacks `SameSite` on a site without CSRF tokens, opens the link from a chat message. The browser posts the form with the session cookie attached. The bank sees an authenticated `POST` with valid fields and moves the money. With `SameSite=Lax` the cookie is left off this cross-site `POST` and the request arrives anonymous; with a synchroniser token the request arrives without a token and Spring returns `403`. Either stops it; both is the standard.

Configuration one: a session-based single-page application that logs in with a cookie and calls the API from JavaScript. The token is exposed in a readable cookie so the front end can echo it in a header:

```java
@Bean
SecurityFilterChain sessionBasedSinglePageApplication(HttpSecurity http) throws Exception {
    http
        .csrf(csrf -> csrf
            .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
            .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler()))
        .addFilterAfter(new CsrfCookieFilter(), BasicAuthenticationFilter.class)
        .authorizeHttpRequests(requests -> requests.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}

final class CsrfCookieFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        CsrfToken csrfToken = (CsrfToken) request.getAttribute(CsrfToken.class.getName());
        csrfToken.getToken();
        filterChain.doFilter(request, response);
    }
}
```

Two details explain the two unusual lines. Spring Security 6 loads the token lazily, so the cookie is only written when something reads the token; the filter's `getToken()` call forces that on every request, so the first `POST` from the front end finds the cookie in place. And the default request handler masks the token, which is right for values rendered into HTML but wrong for a value the browser copies verbatim from a cookie into a header; the plain `CsrfTokenRequestAttributeHandler` compares the raw value. The reference documentation shows a combined handler that keeps the masking for server-rendered forms as well; use it if you mix both styles.

Configuration two: a stateless API that authenticates every request with a bearer token and never issues a session cookie:

```java
@Bean
SecurityFilterChain statelessApi(HttpSecurity http) throws Exception {
    http
        .csrf(csrf -> csrf.disable())
        .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(requests -> requests.anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
    return http.build();
}
```

Disabling is correct here for one reason only: nothing in this chain authenticates by cookie, so there is no ambient authority to forge. The moment the same application also accepts a session or a JWT stored in a cookie, the first configuration applies to it.

Whatever the style, set the attributes on the session cookie itself:

```properties
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
```

## Pitfalls

- Disabling CSRF "because we have an API". Only true for the chain that has no cookie authentication. A `/api/**` chain with `csrf.disable()` next to a cookie-login chain for the same endpoints is the classic hole.
- State changes on `GET`. `SameSite=Lax` and Spring's protection both treat `GET` as safe, so `GET /orders/42/cancel` is unprotected by design. Use `POST`, `PUT` or `DELETE`.
- Relying on `SameSite` alone. Subdomains are the same site, old clients ignore the attribute, and third-party integrations sometimes force `SameSite=None`. Keep the token.
- Putting a bearer token in a cookie and keeping the "stateless, no CSRF" configuration. The token is ambient authority again.
- "Fixing" the readable `XSRF-TOKEN` cookie by making it `HttpOnly` after a scanner flags it. The cookie is meant to be read by your JavaScript; the attacker's origin still cannot read it. `HttpOnly` breaks the scheme and protects nothing.
- Logout by `GET`. Spring Security requires `POST /logout` when CSRF is enabled precisely because a forced logout is also a forgery.
- Excluding `/login` from protection. Login CSRF logs the victim into the attacker's account so that later actions land there; the token on the login form prevents it.

## Check yourself

1. Explain, in terms of what the browser attaches and what the attacker's page can read, why a session cookie is forgeable and an `Authorization` header is not.
2. Your front end stores a JWT in a cookie because `localStorage` felt unsafe. Which configuration above now applies, and why?
3. `SameSite=Lax` is set on the session cookie. Describe a request that still succeeds as a forgery.
4. A colleague makes the `XSRF-TOKEN` cookie `HttpOnly`. What breaks, and what did the scanner misunderstand?

## Go deeper

- [PortSwigger: CSRF](https://portswigger.net/web-security/csrf) · the attack with labs, including the token-validation bypasses to watch for.
- [OWASP: CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) · synchroniser tokens, signed double-submit cookies and `SameSite`, with the trade-offs.
- [Spring Security: Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html) · how the attack and the defences work, written by the framework's authors.
- [Spring Security: CSRF for servlet applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) · the configuration reference, including the single-page application section the first example is based on.

---

Part of [Security](../README.md) · item 2.11
