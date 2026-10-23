# CSRF and CORS in Spring Security

> **In one sentence:** CSRF protection is needed exactly when the browser attaches the credential by itself (session or any other cookie) and is pointless when JavaScript attaches a bearer token, while CORS is a browser rule about which origins may read responses, and in Spring Security it must be answered by a `CorsFilter` placed before authentication or preflights get rejected as unauthenticated.

**Why it matters:** The two are confused constantly because both fail with opaque browser errors on cross-origin requests. Teams disable CSRF on a session-based application "to make the SPA work", or add `@CrossOrigin` on a controller and wonder why the preflight still returns 401. Knowing which mechanism applies to which authentication style is the difference between a secure configuration and one that looks secure.

## The idea

**CSRF.** The browser sends cookies for a site with every request to that site, regardless of which page triggered the request. So a form on `evil.example` that posts to `bank.example/transfer` arrives at the bank with the victim's session cookie, and the bank cannot tell it from a legitimate request. The defence is a secret the attacker's page cannot read: a CSRF token tied to the session, sent as a form field or a request header on every state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`). `CsrfFilter` checks it and answers 403 when it is missing or wrong. `SameSite=Lax` cookies reduce the attack surface and Spring Security still recommends the token, because `Lax` leaves gaps (top-level navigations, older browsers, subdomain takeovers).

The rule follows directly: if authentication rides on a cookie (form login session, remember-me, a JWT stored in a cookie), CSRF protection is required. If the client sends `Authorization: Bearer ...` from JavaScript, the browser never adds it on its own, the attacker's page cannot produce it, and CSRF protection has nothing to protect; disable it on that chain. Mixed applications get two `SecurityFilterChain` beans, one per style (item 6.1).

**The SPA setup** for a cookie-based session: the server writes the token into a readable cookie (`XSRF-TOKEN`), the JavaScript client reads it and sends it back in the `X-XSRF-TOKEN` header, which Angular, axios and most fetch wrappers do automatically. Since Spring Security 6 two details changed. The token is loaded lazily, so a request that never touches it gets no cookie; and the default `XorCsrfTokenRequestAttributeHandler` masks the token on every response to defeat the BREACH attack, which means the raw value from the cookie must be accepted when it arrives in a header. The reference documentation's `SpaCsrfTokenRequestHandler` handles both.

**CORS.** A page from `https://app.example.com` calling `https://api.example.com` is a cross-origin request. The browser allows it only if the API answers with `Access-Control-Allow-Origin` for that origin, and for anything beyond a simple `GET` or form post it first sends a preflight: `OPTIONS` with `Origin` and `Access-Control-Request-Method`, carrying no cookies and no `Authorization` header. If that preflight reaches an authentication filter, it is rejected as anonymous, the browser never sees a CORS header, and the console says "blocked by CORS policy" even though the real problem is a 401. Spring Security therefore places `CorsFilter` near the start of the chain, before `CsrfFilter` and every authentication filter, when you call `http.cors(Customizer.withDefaults())`.

That call needs a configuration. `CorsConfigurer` looks for a bean named `corsConfigurationSource` of type `CorsConfigurationSource`; if none exists and Spring MVC is present, it falls back to the MVC CORS mappings (`@CrossOrigin`, `addCorsMappings`). Declaring the bean is the reliable choice: the filter runs before the `DispatcherServlet` and must know the rules on its own, one bean gives the filter and MVC the same answer, and the name is checked, so a `@Bean` method called `corsConfigurationSource()` is the whole trick. `@CrossOrigin` alone does nothing for secured endpoints because it is evaluated inside MVC, after the chain has already rejected the preflight.

Credentials make the last difference. A cookie-based SPA on another origin must set `allowCredentials(true)` and list explicit origins, because browsers refuse `Access-Control-Allow-Origin: *` together with credentials. A bearer-token SPA needs no credentials flag; it needs `Authorization` in the allowed headers.

## Example: the two configurations side by side

Cookie session with a SPA on another origin, CSRF on:

```java
@Configuration
@EnableWebSecurity
public class BrowserSecurityConfiguration {

    @Bean
    SecurityFilterChain browserSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/csrf").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        configuration.setAllowedHeaders(List.of("Content-Type", "X-XSRF-TOKEN"));
        configuration.setAllowCredentials(true);
        configuration.setMaxAge(Duration.ofHours(1));
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration);
        return source;
    }
}

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plainHandler = new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xorHandler = new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response, Supplier<CsrfToken> csrfToken) {
        xorHandler.handle(request, response, csrfToken);
        csrfToken.get();   // resolves the deferred token so the XSRF-TOKEN cookie is written on this response
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request, CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        return (StringUtils.hasText(headerValue) ? plainHandler : xorHandler).resolveCsrfTokenValue(request, csrfToken);
    }
}
```

The handler uses the masking handler for anything rendered into a page and the plain one when the token arrives in the header, exactly as the reference documentation describes. The browser receives `Set-Cookie: XSRF-TOKEN=...; Path=/` (not `HttpOnly`, so the script can read it) and sends `X-XSRF-TOKEN` back; `CsrfFilter` compares it with the cookie's value.

Stateless API with bearer tokens, CSRF off:

```java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration configuration = new CorsConfiguration();
        configuration.setAllowedOrigins(List.of("https://app.example.com"));
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        configuration.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        configuration.setMaxAge(Duration.ofHours(1));
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", configuration);
        return source;
    }
}
```

Differences worth noticing: no CSRF because no cookie; `Authorization` instead of `X-XSRF-TOKEN` in the allowed headers; no `allowCredentials`, because a header set by script is not a credential in the CORS sense; and `STATELESS`, which guarantees that even a stray cookie cannot authenticate a request.

## Pitfalls

- Disabling CSRF on a session-based application because `POST` returned 403. The 403 is the protection working; wire the token through instead.
- Keeping CSRF on for a bearer-token API. Harmless to security but every `POST` from a client without the token fails, and the usual "fix" is a global disable that then also covers the session chain.
- `@CrossOrigin` on controllers with Spring Security in front and no `http.cors()`. Preflights never reach the controller.
- `allowedOrigins("*")` with `allowCredentials(true)`. The browser rejects the combination; use `setAllowedOriginPatterns` with explicit patterns if you must be flexible.
- A `CorsConfigurationSource` bean with another name and no explicit `cors(cors -> cors.configurationSource(source))`. Spring Security does not find it and silently falls back to the MVC mappings, which are probably empty.
- Storing a JWT in `localStorage` to avoid CSRF, then exposing it to every script on the page. Cookies plus CSRF token, or in-memory tokens with a BFF, are the two defensible patterns; pick one knowingly.
- Treating the preflight 401 as an authentication bug and opening `OPTIONS` to `permitAll()` everywhere. It works by accident; the real fix is `CorsFilter` ahead of authentication, which `http.cors()` already gives you.

## Check yourself

1. A SPA uses a session cookie and calls the API from the same origin. Is CSRF protection needed? And if the API moves to a different subdomain?
2. Why does a preflight request fail with 401 when CORS is configured only through `@CrossOrigin`, and which filter order fixes it?
3. In the cookie-based configuration, why must the `XSRF-TOKEN` cookie not be `HttpOnly`, and why does that not defeat the protection?
4. Explain why `allowCredentials(true)` is required in the first configuration and absent in the second.

## Go deeper

- [Spring Security: CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) · the threat model, when to disable, and the SPA recipe this note's handler comes from.
- [Spring Security: CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) · why the filter is placed before authentication and how the bean is discovered.
- [Spring: CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html) · the MVC side: `@CrossOrigin`, global mappings and `CorsFilter`.

---

Part of [Spring](../README.md) · item 6.4
