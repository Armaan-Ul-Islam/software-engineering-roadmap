# Securing a REST API as an OAuth2 resource server

> **In one sentence:** A resource server accepts a bearer JWT on every request, checks its signature against the issuer's published keys and its `iss`, `exp` and `aud` claims, turns the scopes and roles inside it into authorities, and then applies ordinary request and method authorisation; no session, no password, no call to the authorisation server per request.

**Why it matters:** This is the default way to protect an API behind Keycloak, Entra ID, Auth0 or Spring Authorization Server, and the configuration is three lines, which is exactly why it is misconfigured so often: tokens issued for another API are accepted because nobody validated the audience, roles are missing because the claim has a different name, and the tests pass because they bypass the real decoder without anyone noticing what the real one would do.

## The idea

With `spring-boot-starter-oauth2-resource-server` on the classpath and this property:

```properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.com/realms/shop
```

Boot builds a `JwtDecoder` (a `NimbusJwtDecoder`). On first use it fetches `https://auth.example.com/realms/shop/.well-known/openid-configuration`, reads the `jwks_uri`, and downloads the public keys. For every request with `Authorization: Bearer <token>`, `BearerTokenAuthenticationFilter` hands the token to `JwtAuthenticationProvider`, which asks the decoder to:

1. Parse the compact JWT and look up the signing key by the `kid` header; unknown `kid` values trigger a refetch of the key set, which is how key rotation works without restarts.
2. Verify the signature with that key.
3. Validate the standard claims: `exp` and `nbf` with a 60-second clock skew allowance, and `iss` equal to the configured issuer, byte for byte.
4. Run any additional validators, such as audience.

The resolution is lazy, so the application starts even when the issuer is unreachable, and fails on the first request instead. If you configure `jwk-set-uri` instead of `issuer-uri`, no discovery happens and the `iss` claim is not checked unless you add the validator yourself.

**Audience.** A token minted for the billing API must not open the orders API, even though both trust the same issuer. The `aud` claim says which resource the token is for; validate it:

```properties
spring.security.oauth2.resourceserver.jwt.audiences=shop-api
```

Boot adds a `JwtClaimValidator` for `aud`. The programmatic equivalent, when you need custom logic, is a `JwtDecoder` bean created with `JwtDecoders.fromIssuerLocation(issuer)` and `setJwtValidator(new DelegatingOAuth2TokenValidator<>(JwtValidators.createDefaultWithIssuer(issuer), audienceValidator))`.

**Claims to authorities.** The default `JwtAuthenticationConverter` reads the `scope` (or `scp`) claim, splits it on spaces and prefixes each value with `SCOPE_`, so a token with `"scope": "orders:read orders:write"` yields `SCOPE_orders:read` and `SCOPE_orders:write`. Roles live under provider-specific claim names (`roles`, Keycloak's nested `realm_access.roles`, Entra ID's `roles`), and you map them with a `JwtGrantedAuthoritiesConverter` configured for that claim and the `ROLE_` prefix. The principal name defaults to `sub`; `setPrincipalClaimName("preferred_username")` makes `authentication.getName()` readable in logs and audit trails.

**Authorisation** then works as everywhere else (item 6.3): `hasAuthority("SCOPE_orders:write")` in `authorizeHttpRequests`, `@PreAuthorize("hasAuthority('SCOPE_orders:write')")` on service methods, and `@AuthenticationPrincipal Jwt jwt` as a controller parameter when you need claims such as `jwt.getSubject()` or `jwt.getClaimAsString("email")`.

## Example: configuration and a test

```java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/orders/**").hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders").hasAuthority("SCOPE_orders:write")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopeConverter = new JwtGrantedAuthoritiesConverter();

        JwtGrantedAuthoritiesConverter roleConverter = new JwtGrantedAuthoritiesConverter();
        roleConverter.setAuthoritiesClaimName("roles");
        roleConverter.setAuthorityPrefix("ROLE_");

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> Stream
                .concat(scopeConverter.convert(jwt).stream(), roleConverter.convert(jwt).stream())
                .toList());
        converter.setPrincipalClaimName("preferred_username");
        return converter;
    }
}
```

A `JwtAuthenticationConverter` bean is picked up by `jwt(Customizer.withDefaults())`; you can also pass it explicitly with `jwt.jwtAuthenticationConverter(converter)`. A token carrying `"scope": "orders:write"` and `"roles": ["ADMIN"]` now produces `SCOPE_orders:write` and `ROLE_ADMIN`, so both `hasAuthority` and `hasRole("ADMIN")` work.

The test uses `spring-security-test`. The `jwt()` post-processor puts a ready-made `JwtAuthenticationToken` into the security context, so the decoder is never called; the chain still needs a `JwtDecoder` bean to start, hence the mock:

```java
@WebMvcTest(OrderController.class)
@Import(ApiSecurityConfiguration.class)
class OrderControllerSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @Test
    void placesOrderWithWriteScope() throws Exception {
        when(orderService.place(any())).thenReturn(new OrderResponse(7L, OrderStatus.NEW));

        mockMvc.perform(post("/api/orders")
                .with(jwt()
                        .jwt(jwt -> jwt.subject("alice").claim("preferred_username", "alice"))
                        .authorities(new SimpleGrantedAuthority("SCOPE_orders:write")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"productId": 42, "quantity": 1}
                        """))
            .andExpect(status().isCreated());
    }

    @Test
    void rejectsReadOnlyToken() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(jwt().authorities(new SimpleGrantedAuthority("SCOPE_orders:read")))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectsAnonymousCall() throws Exception {
        mockMvc.perform(post("/api/orders"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string("WWW-Authenticate", "Bearer"));
    }
}
```

`@MockitoBean` is Spring Framework 6.2 and Boot 3.4; on older 3.x use `@MockBean`. The second test sends an empty body that would fail validation with 400, but authorisation runs in the filter chain before the controller, so 403 wins; that ordering is a useful thing to assert. Because `jwt()` bypasses the decoder, add one test against the real decoder somewhere (a `@SpringBootTest` with a token signed by a test key, or an end-to-end test against a dev realm) so that audience and issuer validation are exercised at least once.

## Pitfalls

- No audience validation. Every token from the shared issuer is accepted, including tokens issued to other applications. Set `audiences` on day one.
- `issuer-uri` that differs from the token's `iss` by a trailing slash, a port, or an internal versus external hostname. Behind a proxy the authorisation server may issue tokens with its public URL while the resource server is configured with the cluster-internal one; the decoder rejects every token with "The iss claim is not valid".
- `hasRole("orders:write")` for a scope. Scopes are authorities with the `SCOPE_` prefix; roles are `ROLE_`. Mixing them produces 403 for valid tokens.
- Trusting roles in a claim the converter does not read. The default converter looks only at `scope` and `scp`; with Keycloak's nested `realm_access.roles` you need a custom converter that walks the map.
- Treating `jwt()` tests as security tests. They prove your rules, not your decoder. Signature, expiry, issuer and audience checks need at least one test with a real token.
- Caching a JWT and its authorities in a server-side session. The token already is the credential; adding a session reintroduces CSRF and fixation concerns for nothing.
- Logging the token. It is a bearer credential; whoever reads the log can replay it until it expires.

## Check yourself

1. The issuer is reachable only as `http://keycloak:8080` from the cluster but issues tokens with `iss` of `https://auth.example.com`. What fails, and what are two ways to fix it?
2. Which claims does the default decoder validate, and which important one does it not validate unless you configure it?
3. Why does the `rejectsReadOnlyToken` test return 403 rather than 400, even though the body is invalid?
4. A `@WebMvcTest` with `jwt()` passes. What would still break in production if the authorisation server rotated its signing key? What if it changed the `aud` it issues?

## Go deeper

- [Spring Security: OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html) · the reference, including JWT decoding, validators, authority mapping and opaque tokens.
- [Spring Security: Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html) · the `jwt()` and `opaqueToken()` request post-processors and what they do and do not exercise.
- [Spring Security: OAuth2](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html) · how the resource server relates to OAuth2 login and client support.
- [Spring Authorization Server](https://docs.spring.io/spring-authorization-server/reference/) · run your own issuer for local development and end-to-end tests.

---

Part of [Spring](../README.md) · item 6.5
