# Mutual TLS for service-to-service authentication

> **In one sentence:** Mutual TLS makes the client prove it holds the private key for a certificate your own CA issued, so the server gets a cryptographically verified caller identity before the first byte of HTTP arrives; the work is not the handshake but issuing, rotating and mapping those certificates, which is what service meshes and cert-manager exist to do.

**Why it matters:** "It is on the internal network" has been the cause of enough breaches that the industry now calls the alternative zero trust: every call between services is authenticated, whatever network it arrives from. mTLS is the mechanism with the fewest moving parts at request time, and the one most likely to be handed to you by a platform team as a sidecar. You need to know what it proves, what it does not, and why the application still has to make an authorization decision afterwards.

## The idea

In ordinary TLS the server sends a certificate and proves possession of its key with `CertificateVerify` (item 7.1); the client proves nothing. In mutual TLS the server adds a `CertificateRequest` to its first flight, the client answers with its own `Certificate` and `CertificateVerify`, and the server validates the chain against **its** trust store. That trust store is not the public `cacerts`: it holds your internal CA, so the only clients that can complete the handshake are the ones your CA issued a certificate to. The certificate's subject or subject alternative name is then the caller's identity, available to the application as a verified fact.

What mTLS gives you: caller authentication at the transport layer, no secret that travels in a request, no token endpoint to call, protection of the whole connection including the first request. What it does not give you: authorization (the certificate says *who*, not *what they may do*), the identity of the end user behind the calling service (item 4.3), or anything at all once TLS is terminated by a load balancer in front of the application.

Compared with the alternatives:

| Mechanism | Proves | Where it fails |
|---|---|---|
| Network location | Nothing; any process on the subnet is "internal" | One SSRF or one compromised pod |
| Shared API key | Possession of a string that is in every environment file | Leaks, never rotated, no binding to the connection |
| OAuth client credentials | The client authenticated to the authorization server; the token carries scopes | Needs the token endpoint, token lifetime management, audience checks at every service |
| mTLS | The client holds the private key for a certificate from our CA | Certificate issuance and rotation must be automated; identity still has to be mapped to permissions |

Many systems combine the last two: mTLS between every pair of services, and an OAuth token for the user context riding inside it. RFC 8705 ties them together formally by letting the client authenticate to the token endpoint with its certificate and binding the issued token to that certificate.

**Service meshes.** Istio and Linkerd put a proxy next to every pod, issue each workload a short-lived certificate (hours, not years) whose SAN is a SPIFFE identity such as `spiffe://cluster.local/ns/payments/sa/billing`, and do mTLS between proxies. The application speaks plain HTTP to `localhost` and never sees a key. Authorization policies in the mesh ("only `billing` may call `orders` on `POST /orders/*/charge`") are evaluated on that identity. The trade is operational: a component in every request path, and certificates the platform rotates for you.

**Certificate automation.** Certificates that expire in days or hours replace revocation: a stolen key stops working on its own, and a CRL or OCSP responder nobody checks is no longer needed. That only works when issuance is a machine process. ACME (Let's Encrypt, item 7.2) is the public version. Inside a cluster, cert-manager watches `Certificate` resources, requests certificates from an `Issuer` (its own CA, Vault, a cloud CA, or ACME), stores the key pair in a Kubernetes `Secret`, and renews before expiry. Applications that load certificates from files need to reload them without a restart; Spring Boot's SSL bundles can watch the files for exactly this reason.

## Example: a private CA, a server, a client, and the handshake with and without a certificate

Create the CA and two leaf certificates. The client certificate carries a SPIFFE-style URI SAN, which is how meshes name workloads:

```bash
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout ca.key -out ca.pem -days 365 -subj "/CN=Example Internal CA"
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout server.key -out server.csr -subj "/CN=orders.internal"
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out server.pem -days 90 \
    -extfile <(printf "subjectAltName=DNS:orders.internal,DNS:localhost\nextendedKeyUsage=serverAuth")
openssl req -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
    -keyout client.key -out client.csr -subj "/CN=billing-service"
openssl x509 -req -in client.csr -CA ca.pem -CAkey ca.key -CAcreateserial -out client.pem -days 90 \
    -extfile <(printf "subjectAltName=URI:spiffe://example.internal/billing-service\nextendedKeyUsage=clientAuth")
```

Start a server that requires a client certificate signed by the CA (`-Verify 1` means request and require, depth 1):

```bash
openssl s_server -accept 8443 -cert server.pem -key server.key -CAfile ca.pem -Verify 1 -www
```

A client without a certificate completes the key exchange and is then refused. In TLS 1.3 the refusal arrives as an alert after the client's `Finished`, which is why the output first says the server was verified fine:

```bash
openssl s_client -connect localhost:8443 -CAfile ca.pem </dev/null
```

```text
Acceptable client certificate CA names
CN=Example Internal CA
Protocol: TLSv1.3
Verify return code: 0 (ok)
SSL routines:ssl3_read_bytes:tlsv13 alert certificate required:...:SSL alert number 116
```

The server's log for the same attempt says `peer did not return a certificate`. With the certificate:

```bash
openssl s_client -connect localhost:8443 -CAfile ca.pem -cert client.pem -key client.key </dev/null
```

```text
Protocol: TLSv1.3
Verify return code: 0 (ok)
```

and the server log shows the chain it verified, which is the identity the application will see:

```text
depth=1 CN=Example Internal CA
verify return:1
depth=0 CN=billing-service
verify return:1
```

`curl --cacert ca.pem --cert client.pem --key client.key https://localhost:8443/` works the same way. Note that macOS's `curl` is built against LibreSSL and reports the missing-certificate case as an opaque `SSL_read` error; the `openssl` client names the alert.

## Example: the same thing in Spring Boot and Spring Security

Server side, with PEM files and no `keytool`. `client-auth=need` is `-Verify`; `want` would request a certificate and continue without one, which is right only when some callers authenticate another way:

```properties
spring.ssl.bundle.pem.server.keystore.certificate=file:/etc/certs/server.pem
spring.ssl.bundle.pem.server.keystore.private-key=file:/etc/certs/server.key
spring.ssl.bundle.pem.server.truststore.certificate=file:/etc/certs/ca.pem
spring.ssl.bundle.pem.server.reload-on-update=true
server.ssl.bundle=server
server.ssl.client-auth=need
```

Spring Security turns the verified certificate into an `Authentication`. The subject regex extracts the principal; the `UserDetailsService` is the allow-list that maps known service names to authorities, and an unknown name fails authentication even though its certificate was valid:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.x509(x509 -> x509
                    .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                    .userDetailsService(serviceAccounts()))
            .authorizeHttpRequests(requests -> requests
                    .requestMatchers(HttpMethod.POST, "/orders/*/charge").hasAuthority("orders:charge")
                    .anyRequest().denyAll())
            .sessionManagement(sessions -> sessions.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable());
    return http.build();
}

private UserDetailsService serviceAccounts() {
    UserDetails billing = User.withUsername("billing-service").password("{noop}unused")
            .authorities("orders:charge").build();
    return new InMemoryUserDetailsManager(billing);
}
```

Disabling CSRF is correct here because no browser cookie is involved; a certificate is not attached by the browser on cross-site requests the way a cookie is (item 2.11).

Client side, the bundle holds the client certificate and trusts only the internal CA:

```properties
spring.ssl.bundle.pem.orders.keystore.certificate=file:/etc/certs/client.pem
spring.ssl.bundle.pem.orders.keystore.private-key=file:/etc/certs/client.key
spring.ssl.bundle.pem.orders.truststore.certificate=file:/etc/certs/ca.pem
spring.ssl.bundle.pem.orders.reload-on-update=true
```

```java
@Bean
RestClient ordersClient(RestClient.Builder builder, RestClientSsl restClientSsl) {
    return builder.apply(restClientSsl.fromBundle("orders"))
            .baseUrl("https://orders.internal:8443")
            .build();
}
```

With `reload-on-update`, cert-manager can rewrite the files and the running application picks up the new certificate without a restart.

## Pitfalls

- Terminating TLS at a load balancer and then expecting a client certificate in the application. There is none. Either pass TLS through to the application, or have the proxy verify the client and forward the identity in a header that the application accepts only from that proxy's address.
- Treating a valid certificate as authorization. Every certificate from the CA is valid; the application still needs the allow-list of subjects and what each may do.
- Long-lived client certificates without rotation. A year-long certificate on a laptop image is a year-long credential; issue short ones from a pipeline.
- Private keys in container images or repositories. Mount them at runtime from a secret store or let the mesh inject them.
- `want` where `need` was meant. Requests without a certificate reach the application unauthenticated and the only defence is whether somebody wrote `anyRequest().denyAll()`.
- Identity in the Common Name only. Tooling increasingly expects SANs; put the DNS name or SPIFFE URI in `subjectAltName` and treat the CN as a label.
- Debugging with a system `curl` on macOS. Its LibreSSL error text hides the alert; use `openssl s_client` to see `certificate required` or `unknown ca`.
- Forgetting the intermediate. If your CA has an issuing intermediate, the client must send leaf plus intermediate, and the server's trust store needs the root.

## Check yourself

1. In the TLS 1.3 transcript above, why does the client see `Verify return code: 0 (ok)` and then an alert, rather than a failed handshake?
2. What does a successfully verified client certificate prove, and name two decisions the application still has to make before serving the request.
3. A service mesh gives every pod a certificate valid for 24 hours. Explain why that removes the need for certificate revocation, and what has to be true of issuance for it to work.
4. Your platform team terminates TLS at an ingress controller. What are the two architectures that still give the application a trustworthy caller identity, and what does each depend on?

## Go deeper

- [Cloudflare: What is mTLS?](https://www.cloudflare.com/learning/access-management/what-is-mutual-tls/) · the handshake difference in plain language.
- [Spring Boot: SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html) · SSL bundles, PEM and JKS forms, reloading, and applying a bundle to clients.
- [Spring Security: X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html) · the `x509()` DSL, the principal extractor and the `UserDetailsService` mapping.
- [cert-manager](https://cert-manager.io/) · issuing and renewing certificates inside Kubernetes from your own CA, Vault or ACME.
- [SPIFFE](https://spiffe.io/) · the workload identity format used in the example and by the service meshes.
- [RFC 8705: OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705) · how mTLS and OAuth tokens are combined.
- [OWASP: Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html) · configuration guidance, including the client certificate section.

---

Part of [Security](../README.md) · item 7.4
