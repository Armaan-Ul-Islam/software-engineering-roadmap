# CORS and the same-origin policy

> **In one sentence:** The same-origin policy stops a page from *reading* responses from other origins using the user's credentials, CORS is the server's way of relaxing that rule for named origins, and the fix for a CORS error is always on the server, never in the browser or the frontend code.

**Why it matters:** "Blocked by CORS policy" is the most searched error in web development, and the top search results teach the wrong fix (`Access-Control-Allow-Origin: *` everywhere, or reflecting whatever `Origin` arrives). Done wrong, CORS configuration quietly disables the one protection that keeps a malicious tab from reading your users' data out of your API.

## The idea

**An origin** is the triple scheme, host, port. `https://app.example.com`, `https://api.example.com`, `http://app.example.com` and `https://app.example.com:8443` are four different origins. (This is stricter than the "site" that cookies use for `SameSite`; see item 6.1.)

**What the same-origin policy protects.** The browser attaches cookies to every request to a host, regardless of which page started it. Without the policy, `evil.com` could run `fetch('https://bank.example/accounts')` in your tab, the request would carry your bank cookie, and the script could read the response. The policy does not stop the request from being *sent* (forms, images, scripts and simple fetches cross origins freely, which is why CSRF exists); it stops the script from *reading* the response and, for anything beyond a simple request, stops it from being sent at all until the server agrees.

**Simple vs preflighted requests.** A request is simple if it is `GET`, `HEAD` or `POST`, has only safelisted headers, and any `Content-Type` is one of `application/x-www-form-urlencoded`, `multipart/form-data` or `text/plain`. Simple requests are sent immediately with an `Origin` header; the browser then checks the response's `Access-Control-Allow-Origin` before letting the script read it. Anything else (`PUT`, `DELETE`, `PATCH`, a `Content-Type: application/json`, an `Authorization` header) is **preflighted**: the browser first sends `OPTIONS` with `Access-Control-Request-Method` and `Access-Control-Request-Headers`, and only sends the real request if the response allows the method, the headers and the origin. `Access-Control-Max-Age` lets the browser cache that decision (Chrome caps it at 7200 seconds).

**Credentials mode.** By default `fetch` sends no cookies cross-origin. With `credentials: 'include'` it does, and the server must then answer with `Access-Control-Allow-Credentials: true` *and* an explicit origin: `Access-Control-Allow-Origin: *` is rejected in credentialed mode, as are wildcard `Allow-Headers` and `Allow-Methods`. When a server echoes the request's origin it must add `Vary: Origin` so caches keep the answers apart (item 5.2).

**Reading response headers.** Scripts see only a safelist (`Content-Type`, `Cache-Control`, `Content-Length` and a few more) unless the server lists others in `Access-Control-Expose-Headers`, which is why a frontend "cannot see" `ETag`, `Location` or `X-RateLimit-Remaining` until you add it.

**The correct fix** is a server-side allowlist of exact origins, the methods and headers you really use, credentials only if you use cookies, and `Vary: Origin`. The frontend cannot fix CORS: the headers are read from the *response*, and a browser error means the server did not send them. A development proxy or a gateway that serves the frontend and the API from one origin removes CORS from the picture entirely, which is often the best answer.

## Example: a real preflight exchange

A page on `https://app.example.com` runs `fetch('https://api.github.com/user', { headers: { Authorization: 'Bearer ...' } })`. The `Authorization` header forces a preflight. Reproduced with curl (long header lists trimmed):

```http
OPTIONS /user HTTP/1.1
Host: api.github.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization, content-type

```

```http
HTTP/2 204
access-control-allow-origin: *
access-control-allow-methods: GET, POST, PATCH, PUT, DELETE
access-control-allow-headers: Authorization, Content-Type, If-Match, If-None-Match, ...
access-control-expose-headers: ETag, Link, Location, Retry-After, X-RateLimit-Remaining, ...
access-control-max-age: 86400
vary: Accept-Encoding, Accept, X-Requested-With

```

`204` with no body is the canonical preflight answer. GitHub can use `*` because its API is authenticated by the `Authorization` header, which attackers cannot forge from another site, and not by cookies; a cookie-authenticated API must name the origin instead. Only after this does the browser send the real `GET /user`, whose response must again carry `access-control-allow-origin`.

## Example: a minimal correct Spring MVC configuration

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET", "POST", "PUT", "DELETE")
                .allowedHeaders("Authorization", "Content-Type")
                .exposedHeaders("ETag", "Location")
                .allowCredentials(true)
                .maxAge(3600);
    }
}
```

Spring answers the `OPTIONS` preflight itself, adds `Vary: Origin` automatically, and rejects `allowCredentials(true)` combined with `allowedOrigins("*")` with an `IllegalArgumentException` when the configuration is validated. With Spring Security on the classpath, also enable `http.cors(Customizer.withDefaults())` so the CORS filter runs before authentication; otherwise the preflight, which carries no credentials, is rejected with 401 and the browser reports it as a CORS failure.

## Pitfalls

- Reflecting any `Origin` back with `Allow-Credentials: true`. This is equivalent to switching off the same-origin policy for your API: any site can now read your users' data with their cookies. Allowlist exact origins.
- `Access-Control-Allow-Origin: *` on a cookie-authenticated API. Browsers reject it in credentialed mode, so it "does not work" rather than being insecure, but the usual next step is the reflection above.
- Preflight blocked by authentication. The `OPTIONS` request carries no `Authorization` header; if your security filter demands one, the browser sees a 401 and reports CORS. Let `OPTIONS` through, or let the framework's CORS filter run first.
- Adding CORS headers in the frontend or in the request. They are response headers; the browser ignores them anywhere else.
- Missing `Vary: Origin` while echoing origins. A CDN caches the response for origin A and serves it to origin B.
- A CORS error that is really something else. A 500, a redirect (preflights must not redirect), or a proxy that strips headers all surface as "blocked by CORS". Check the network tab for the actual status of the `OPTIONS` response.
- Preflighting every request. A custom header such as `X-Request-Id` on every call doubles your request count; set `Access-Control-Max-Age` and avoid non-safelisted headers on hot paths.
- Confusing CORS with CSRF protection. CORS controls who may *read* responses; it does nothing about a cross-site form `POST`, which is still sent with cookies. That needs `SameSite` and CSRF tokens (item 6.1).

## Check yourself

1. Why is a `POST` with `Content-Type: application/json` preflighted while the same `POST` with `application/x-www-form-urlencoded` is not, and what does the difference tell you about the policy's purpose?
2. A server echoes the `Origin` header and sets `Access-Control-Allow-Credentials: true`. Describe the attack this enables, step by step, from the attacker's page.
3. Your frontend gets "blocked by CORS" but curl shows the API works. Which single response in the network tab tells you where the problem is?
4. A frontend cannot read the `Location` header of a 201 response although the request succeeded. Which header is missing, and why does the browser hide headers by default?

## Go deeper

- [MDN: Same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy) · what the policy covers beyond network requests: DOM access, storage and the exceptions.
- [MDN: CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) · the reference for simple requests, preflights, credentials and every header, with sequence diagrams.
- [Spring Framework: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) and [Spring Security: CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) · the configuration above, and how the two filters are ordered.
- [OWASP: Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) · the attack CORS does not stop, and what does.

---

Part of [Web & HTTP](../README.md) · items 7.1, 7.2
