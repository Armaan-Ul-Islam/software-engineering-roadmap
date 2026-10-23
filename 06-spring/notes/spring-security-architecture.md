# Spring Security architecture

> **In one sentence:** Spring Security is one servlet filter that delegates to a chain of security filters chosen by request pattern; some filters authenticate (turning credentials into an `Authentication` stored in the `SecurityContextHolder`), the last one authorises, and everything in between is configured by one `SecurityFilterChain` bean per group of URLs.

**Why it matters:** Nearly every Spring Security problem is "which filter ran, in which order, and what did it find in the context". Once the chain is a picture in your head, a 401 versus 403, a CORS preflight that gets rejected, a `@PreAuthorize` that is ignored, or a test that needs `with(jwt())` all explain themselves. The topical guide and the interview question "walk me through what happens when a request hits a secured endpoint" both expect exactly this picture.

## The idea

```text
Tomcat filter chain
  |
  +-- DelegatingFilterProxy ("springSecurityFilterChain")      one servlet filter, registered by Boot
        |
        +-- FilterChainProxy                                    picks the FIRST SecurityFilterChain whose matcher accepts the request
              |
              +-- SecurityFilterChain for /api/**  (stateless)
              |     DisableEncodeUrlFilter
              |     WebAsyncManagerIntegrationFilter
              |     SecurityContextHolderFilter                 loads a SecurityContext (none for stateless)
              |     HeaderWriterFilter                          security headers
              |     CorsFilter                                  answers preflights before anything can reject them
              |     LogoutFilter
              |     BearerTokenAuthenticationFilter             Authorization: Bearer -> AuthenticationManager -> Authentication
              |     RequestCacheAwareFilter
              |     SecurityContextHolderAwareRequestFilter
              |     AnonymousAuthenticationFilter               no authentication yet? insert an anonymous one
              |     ExceptionTranslationFilter                  turns AccessDeniedException into 401 (anonymous) or 403
              |     AuthorizationFilter                         evaluates authorizeHttpRequests rules
              |
              +-- SecurityFilterChain for /**     (browser, sessions)
                    ... CsrfFilter, UsernamePasswordAuthenticationFilter, BasicAuthenticationFilter, ...
  |
  v
DispatcherServlet -> controller (@PreAuthorize is checked here by a method-security proxy)
```

**Only one chain runs per request.** `FilterChainProxy` walks the `SecurityFilterChain` beans in `@Order` and uses the first whose `securityMatcher` matches. A chain with `securityMatcher("/api/**")` must be ordered before the catch-all chain or it is never reached.

**Authentication.** The `SecurityContextHolder` holds, per thread, a `SecurityContext` with one `Authentication`: principal, credentials, granted authorities and an `isAuthenticated` flag. An authentication filter extracts credentials from the request, wraps them in an unauthenticated `Authentication` (for example `UsernamePasswordAuthenticationToken.unauthenticated(username, password)`), and asks the `AuthenticationManager`. The default manager is a `ProviderManager`: a list of `AuthenticationProvider`s, each supporting one token type. `DaoAuthenticationProvider` loads the user through your `UserDetailsService` and checks the password with the `PasswordEncoder` (use `PasswordEncoderFactories.createDelegatingPasswordEncoder()`, which stores hashes as `{bcrypt}...` and can migrate algorithms later). `JwtAuthenticationProvider` validates a bearer token. On success the filter stores the authenticated token in the context; on failure it answers through an `AuthenticationEntryPoint`.

The three styles differ in where the credential lives and what persists between requests:

| Style | Filter | Credential | State between requests | Needs CSRF protection |
|---|---|---|---|---|
| Form login | `UsernamePasswordAuthenticationFilter` on `POST /login` | username and password once | session cookie; the context is saved in the `HttpSession` | yes |
| HTTP Basic | `BasicAuthenticationFilter` | `Authorization: Basic` on every request | none required | no, if sessions are off |
| Bearer token | `BearerTokenAuthenticationFilter` | `Authorization: Bearer` on every request | none; `SessionCreationPolicy.STATELESS` | no |

With sessions, logging in also changes the session id (session fixation protection) and `LogoutFilter` invalidates it. Stateless chains never create a session, so there is nothing to fixate or log out of; the client simply stops sending the token.

**Authorization** happens twice. `AuthorizationFilter`, last in the chain, evaluates the `authorizeHttpRequests` rules top to bottom and stops at the first match, so specific patterns go before `anyRequest()`. `hasRole("ADMIN")` is shorthand for `hasAuthority("ROLE_ADMIN")`; scopes from a JWT arrive as `SCOPE_orders:write`. If the rule fails, `ExceptionTranslationFilter` decides: an anonymous caller gets the entry point (401 with a `WWW-Authenticate` header for Basic and Bearer, a redirect to the login page for form login), an authenticated one gets 403. Method security, enabled with `@EnableMethodSecurity`, adds a second check at the service layer through an AOP proxy: `@PreAuthorize("hasAuthority('SCOPE_orders:write') and #order.ownerId == authentication.name")`. Being a proxy, it has the usual self-invocation blind spot (item 1.4).

## Example: a complete stateless API chain

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .cors(Customizer.withDefaults())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/products/**").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders:write")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(new BearerTokenAuthenticationEntryPoint())
                .accessDeniedHandler(new BearerTokenAccessDeniedHandler()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

Reading the first chain against the diagram: CSRF is off because nothing is cookie-based (item 6.4); `cors` adds the `CorsFilter` early so preflights succeed; `STATELESS` means no `HttpSession` is ever created or consulted; the rules are evaluated in `AuthorizationFilter` in the order written; `oauth2ResourceServer().jwt()` adds `BearerTokenAuthenticationFilter` and a `JwtAuthenticationProvider` that needs a `JwtDecoder` bean, which Boot creates from `spring.security.oauth2.resourceserver.jwt.issuer-uri` (item 6.5); the two handlers, which the resource server configurer also installs as its defaults, make unauthenticated and forbidden calls answer with `WWW-Authenticate` headers instead of a login page redirect; naming them keeps that behaviour explicit when someone later adds `formLogin` to the same chain. `hasRole("ADMIN")` only works if your JWT converter produces `ROLE_ADMIN`; with the default converter you would write `hasAuthority("SCOPE_admin")` instead. The second chain keeps the human-facing part on sessions and form login, with CSRF left on by default.

To see the chain your configuration actually built, set `logging.level.org.springframework.security=DEBUG`: at startup `FilterChainProxy` logs every filter in each chain, and at `TRACE` each request logs `Securing GET /api/orders` followed by `Invoking BearerTokenAuthenticationFilter (7/13)` style lines, which is the fastest way to answer "did my filter run".

## Pitfalls

- Defining no `SecurityFilterChain` at all and wondering about the generated password in the log. Boot's default chain secures every URL with form login and Basic for a single in-memory user; the moment you declare your own chain, that default is gone.
- Ordering. A catch-all chain declared first swallows `/api/**`; `anyRequest()` before a specific matcher makes the specific rule dead. Both fail silently.
- `hasRole("ROLE_ADMIN")`. The prefix is added for you; the result is `ROLE_ROLE_ADMIN`.
- Handling security exceptions in `@ControllerAdvice`. They are thrown in the filter chain, before the `DispatcherServlet`; configure the entry point and access denied handler instead.
- Reading `SecurityContextHolder` on another thread. The default strategy is a `ThreadLocal`; `@Async` methods and `CompletableFuture` callbacks see an empty context unless you propagate it (`DelegatingSecurityContextExecutor` or `SecurityContextHolderStrategy` changes).
- Password checks with `String.equals`, or `NoOpPasswordEncoder`. Use the delegating encoder with bcrypt or Argon2 (item 6.6).
- Adding a custom filter with `addFilterBefore` at the wrong anchor. A filter placed before `SecurityContextHolderFilter` sees no authentication; one placed after `AuthorizationFilter` never runs for denied requests. Pick the anchor from the diagram.

## Check yourself

1. A request to `/api/orders` without a token: which filter notices, which filter produces the response, and why is it 401 rather than 403?
2. Two `SecurityFilterChain` beans, one for `/api/**` and one for everything else. What decides which runs, and what happens to `/api/orders` if the orders are reversed?
3. Where does `@PreAuthorize` run relative to `AuthorizationFilter`, and when would you use both on the same request?
4. Why does HTTP Basic not need CSRF protection when the chain is stateless, but does when a session is created on login?

## Go deeper

- [Spring Security: Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html) · the reference version of the diagram above, with the full filter order list.
- [Spring Security Architecture (topical guide)](https://spring.io/guides/topicals/spring-security-architecture) · authentication and authorisation explained from the interfaces up; the best single read.
- [Spring Security: Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/index.html) · `AuthenticationManager`, providers, `UserDetailsService`, and each login style.
- [Spring Security: Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html) · request matchers, method security, roles versus authorities.
- [Marco Behler: Spring Security](https://www.marcobehler.com/guides/spring-security) · the same architecture built incrementally, which makes the filter order memorable.

---

Part of [Spring](../README.md) · items 6.1, 6.2, 6.3
