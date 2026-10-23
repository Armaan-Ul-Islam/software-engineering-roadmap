# Security

> Application security for people who build backends: the attacker's mindset and threat modelling, the OWASP Top 10 with Java and Spring defences, authentication and sessions, OAuth 2.0 and OpenID Connect, JWT, TLS and certificates, cryptography you can use without being a cryptographer, secrets, supply chain, and privacy basics.

**Prerequisites:** [Web & HTTP](../02-web-and-http/README.md)

**Done when you can:**

- Threat-model a feature in 20 minutes: assets, trust boundaries, STRIDE threats, mitigations.
- Explain each OWASP Top 10 category with an example exploit and the specific defence in a Java/Spring stack.
- Walk through the OAuth 2.0 Authorization Code flow with PKCE on a whiteboard, name every token, and list the common mistakes.
- Validate a JWT correctly, and explain why `alg: none`, a missing audience check and long expiry are failures.
- Explain a TLS handshake and fix a Java "PKIX path building failed" error without disabling verification.
- Choose the right primitive for hashing passwords, signing data and encrypting data at rest, and name the library to use.

## Roadmap

### 1. Mindset and threat modelling

- [ ] 1.1 Thinking like an attacker: assets, trust boundaries, attack surface; defence in depth, least privilege, fail secure · [notes](notes/threat-modelling-with-stride.md) · [OWASP: Threat Modeling](https://owasp.org/www-community/Threat_Modeling) · [OWASP: Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html)
- [ ] 1.2 STRIDE over a data-flow diagram; threat modelling that fits in a sprint · [notes](notes/threat-modelling-with-stride.md) · [Microsoft: STRIDE threats](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats) · [Threat Modeling Manifesto](https://www.threatmodelingmanifesto.org/)
- [ ] 1.3 Security requirements and verification with OWASP ASVS as the checklist · [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/)
- [ ] 1.4 Security in the development lifecycle: design review, code review, SAST/SCA/DAST in CI, penetration tests, disclosure programmes · [OWASP SAMM](https://owaspsamm.org/)

### 2. The OWASP Top 10, with Java and Spring defences

- [ ] 2.1 Broken access control: IDOR/BOLA, missing function-level checks, object-level authorization in the service layer, deny by default · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP Top 10: A01 Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/) · [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [ ] 2.2 Cryptographic failures: plaintext secrets, weak hashing, missing TLS, home-made crypto · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP Top 10: A02 Cryptographic Failures](https://owasp.org/Top10/A02_2021-Cryptographic_Failures/)
- [ ] 2.3 Injection: SQL (prepared statements, JPA parameter binding), OS command, LDAP, template and expression injection · [notes](notes/sql-injection-and-prepared-statements.md) · [PortSwigger: SQL injection](https://portswigger.net/web-security/sql-injection) · [OWASP: SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [ ] 2.4 Insecure design and security misconfiguration: unsafe defaults, verbose errors, exposed actuators and debug endpoints, CORS with wildcard and credentials · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP Top 10: A05 Security Misconfiguration](https://owasp.org/Top10/A05_2021-Security_Misconfiguration/)
- [ ] 2.5 Vulnerable and outdated components; software supply chain failures, with Log4Shell as the case study · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP Top 10: A06 Vulnerable and Outdated Components](https://owasp.org/Top10/A06_2021-Vulnerable_and_Outdated_Components/) · [Log4Shell](https://en.wikipedia.org/wiki/Log4Shell)
- [ ] 2.6 Identification and authentication failures: credential stuffing, weak passwords, missing MFA, session fixation · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [ ] 2.7 Software and data integrity failures: insecure deserialisation (Java serialisation, Jackson polymorphic typing), unsigned artifacts, CI/CD trust · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP: Deserialization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html)
- [ ] 2.8 Logging and monitoring failures; mishandling of exceptional conditions · [notes](notes/owasp-top-10-for-java-developers.md) · [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [ ] 2.9 Server-side request forgery: URL fetchers, webhooks, cloud metadata endpoints · [notes](notes/ssrf-explained.md) · [PortSwigger: SSRF](https://portswigger.net/web-security/ssrf) · [OWASP: SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [ ] 2.10 Cross-site scripting: contexts and output encoding, Content Security Policy, frameworks that escape by default · [notes](notes/xss-and-content-security-policy.md) · [PortSwigger: Cross-site scripting](https://portswigger.net/web-security/cross-site-scripting) · [OWASP: XSS Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)
- [ ] 2.11 Cross-site request forgery: the mechanism, `SameSite` cookies, synchroniser tokens, and why bearer-token APIs are immune · [notes](notes/csrf-explained.md) · [PortSwigger: CSRF](https://portswigger.net/web-security/csrf) · [OWASP: CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [ ] 2.12 The OWASP API Security Top 10: BOLA, broken authentication, unrestricted resource consumption, mass assignment · [OWASP API Security Project](https://owasp.org/API-Security/)

### 3. Authentication and session management

- [ ] 3.1 Password storage: bcrypt, scrypt, Argon2id, work factors, peppers; never plain hashes · [notes](notes/password-storage-and-authentication.md) · [OWASP: Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [ ] 3.2 Password policy done right (NIST 800-63B), breached-password checks, rate limiting and lockout, enumeration-safe messages · [notes](notes/password-storage-and-authentication.md) · [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) · [Have I Been Pwned: Pwned Passwords](https://haveibeenpwned.com/Passwords)
- [ ] 3.3 Multi-factor authentication: TOTP, WebAuthn and passkeys, recovery codes; phishing resistance · [passkeys.dev](https://passkeys.dev/) · [WebAuthn Guide](https://webauthn.guide/)
- [ ] 3.4 Sessions: ID generation, cookie attributes, rotation on login, expiry, server-side invalidation · [notes](notes/password-storage-and-authentication.md) · [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [ ] 3.5 Account lifecycle: registration, email verification, password reset tokens; recovery as the weakest link · [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)

### 4. Authorization

- [ ] 4.1 Models: RBAC, ABAC, ReBAC; roles vs permissions; policy as code (Open Policy Agent, Cedar) · [notes](notes/authorization-models-and-idor.md) · [OWASP: Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) · [Open Policy Agent](https://www.openpolicyagent.org/)
- [ ] 4.2 Object-level and function-level checks; tenant isolation; deny by default in the service layer, not only at the URL · [notes](notes/authorization-models-and-idor.md) · [OWASP API Security: Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [ ] 4.3 Authorization across services: propagating identity, token exchange, service-to-service authentication (client credentials, mTLS) · [RFC 8693: OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)

### 5. OAuth 2.0 and OpenID Connect

- [ ] 5.1 The roles: resource owner, client, authorization server, resource server; scopes and consent · [notes](notes/oauth2-and-openid-connect.md) · [OAuth 2.0 Simplified](https://www.oauth.com/) · [Aaron Parecki: OAuth 2.0 and OpenID Connect in plain English](https://www.youtube.com/watch?v=996OiexHze0)
- [ ] 5.2 Grant types: Authorization Code with PKCE, Client Credentials, Device Code; why Implicit and Password grants are dead · [notes](notes/oauth2-and-openid-connect.md) · [OAuth 2.1](https://oauth.net/2.1/) · [RFC 7636: PKCE](https://www.rfc-editor.org/rfc/rfc7636)
- [ ] 5.3 Tokens: access tokens (opaque vs JWT), refresh tokens and rotation, ID tokens; validation at the resource server; introspection · [notes](notes/oauth2-and-openid-connect.md) · [oauth.net: Access Tokens](https://oauth.net/2/access-tokens/)
- [ ] 5.4 OpenID Connect: the ID token, UserInfo, discovery, standard claims; "log in with" flows · [notes](notes/oauth2-and-openid-connect.md) · [OpenID Connect: How it works](https://openid.net/developers/how-connect-works/)
- [ ] 5.5 Browser-based apps: the backend-for-frontend pattern, token storage, why tokens in JavaScript are risky · [IETF: OAuth 2.0 for Browser-Based Apps](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-browser-based-apps)
- [ ] 5.6 Common mistakes: missing `state`, open redirects, audience confusion, mixing up authentication and authorization, long-lived tokens · [notes](notes/oauth2-and-openid-connect.md) · [RFC 9700: Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [ ] 5.7 Identity providers: Keycloak, Microsoft Entra ID, Auth0/Okta, Spring Authorization Server; what you still own · [Keycloak](https://www.keycloak.org/) · [Spring Authorization Server](https://docs.spring.io/spring-authorization-server/reference/)

### 6. JSON Web Tokens

- [ ] 6.1 Structure: header, claims, signature; JWS vs JWE; the standard claims (`iss`, `sub`, `aud`, `exp`, `nbf`, `iat`, `jti`) · [notes](notes/jwt-validation-and-pitfalls.md) · [RFC 7519: JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519) · [jwt.io: Introduction](https://jwt.io/introduction)
- [ ] 6.2 Validation checklist: algorithm allow-list, signature, issuer, audience, expiry with clock skew, key rotation via JWKS · [notes](notes/jwt-validation-and-pitfalls.md) · [RFC 8725: JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [ ] 6.3 Known attacks: `alg: none`, RS256-to-HS256 confusion, key injection, weak HMAC secrets · [notes](notes/jwt-validation-and-pitfalls.md) · [PortSwigger: JWT attacks](https://portswigger.net/web-security/jwt)
- [ ] 6.4 Design trade-offs: statelessness vs revocation, short expiry plus refresh, what belongs in a token, size and privacy · [notes](notes/jwt-validation-and-pitfalls.md) · [OWASP: JSON Web Token Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html)

### 7. TLS and certificates

- [ ] 7.1 What TLS guarantees and what it does not; the handshake; cipher suites; TLS 1.2 vs 1.3 · [notes](notes/tls-certificates-and-java-trust-stores.md) · [Cloudflare: What happens in a TLS handshake?](https://www.cloudflare.com/learning/ssl/what-happens-in-a-tls-handshake/) · [HPBN: Transport Layer Security](https://hpbn.co/transport-layer-security-tls/)
- [ ] 7.2 Certificates and PKI: certificate authorities, chains, SANs, expiry, revocation (CRL, OCSP), Certificate Transparency · [notes](notes/tls-certificates-and-java-trust-stores.md) · [Let's Encrypt: How it works](https://letsencrypt.org/how-it-works/) · [Cloudflare: What is a certificate authority?](https://www.cloudflare.com/learning/ssl/what-is-a-certificate-authority/)
- [ ] 7.3 Java specifics: the `cacerts` trust store, `keytool`, "PKIX path building failed", custom trust in HTTP clients, never disabling verification · [notes](notes/tls-certificates-and-java-trust-stores.md) · [Baeldung: SSL Handshake Failures](https://www.baeldung.com/java-ssl-handshake-failures) · [keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
- [ ] 7.4 Mutual TLS for service-to-service authentication; service meshes; certificate automation (ACME, cert-manager) · [Cloudflare: What is mTLS?](https://www.cloudflare.com/learning/access-management/what-is-mutual-tls/) · [cert-manager](https://cert-manager.io/)
- [ ] 7.5 HSTS, why certificate pinning is usually wrong, and testing your TLS configuration · [SSL Labs Server Test](https://www.ssllabs.com/ssltest/) · [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/)

### 8. Cryptography for developers

- [ ] 8.1 The four jobs: hashing (integrity), MACs (authenticity), encryption (confidentiality), signatures (non-repudiation); which primitive for which job · [notes](notes/cryptography-for-developers.md) · [Crypto 101](https://www.crypto101.io/) · [Latacora: Cryptographic Right Answers](https://www.latacora.com/blog/2018/04/03/cryptographic-right-answers/)
- [ ] 8.2 Symmetric encryption done right: AES-GCM or ChaCha20-Poly1305, nonces, authenticated encryption, never ECB · [notes](notes/cryptography-for-developers.md) · [OWASP: Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)
- [ ] 8.3 Asymmetric cryptography: RSA vs elliptic curves, key sizes, signatures (Ed25519, ECDSA), key exchange (ECDH), hybrid encryption · [notes](notes/cryptography-for-developers.md) · [Crypto 101](https://www.crypto101.io/)
- [ ] 8.4 Randomness: `SecureRandom`, generating tokens, why UUIDs are not secrets · [notes](notes/cryptography-for-developers.md) · [SecureRandom (Java API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureRandom.html)
- [ ] 8.5 Key management: generation, storage (KMS, HSM), rotation, envelope encryption; keys never in code · [OWASP: Key Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Key_Management_Cheat_Sheet.html)
- [ ] 8.6 Libraries: the JCA, Google Tink, Bouncy Castle; what "don't roll your own" means in practice · [Tink](https://developers.google.com/tink)

### 9. Secrets, dependencies and the pipeline

- [ ] 9.1 Secrets management: nothing in repos or images, vaults, runtime injection, rotation, leak scanning · [notes](notes/secrets-and-supply-chain.md) · [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) · [gitleaks](https://github.com/gitleaks/gitleaks)
- [ ] 9.2 Dependency security: software composition analysis, lockfiles and pinning, SBOMs, typosquatting · [notes](notes/secrets-and-supply-chain.md) · [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/) · [GitHub Advisory Database](https://github.com/advisories)
- [ ] 9.3 Container and infrastructure security: image scanning, non-root, minimal images, network policies, least-privilege IAM · [OWASP: Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [ ] 9.4 Security headers: CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` · [OWASP: HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html) · [securityheaders.com](https://securityheaders.com/)
- [ ] 9.5 Input validation and output encoding as a system: allow-lists, canonicalisation, file-upload safety, size limits · [OWASP: Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) · [OWASP: File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

### 10. Privacy, logging and compliance basics

- [ ] 10.1 Logging safely: no secrets, tokens or personal data in logs; audit logs vs application logs; retention · [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [ ] 10.2 GDPR for developers: lawful basis, data minimisation, purpose limitation, retention and deletion, data subject rights, pseudonymisation · [CNIL: GDPR developer's guide](https://www.cnil.fr/en/gdpr-developers-guide) · [Datatilsynet](https://www.datatilsynet.no/en/)
- [ ] 10.3 Handling security incidents and vulnerability reports: detection, containment, disclosure duties · [OWASP: Vulnerability Disclosure Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Vulnerability_Disclosure_Cheat_Sheet.html)
- [ ] 10.4 Security for AI features: prompt injection, data exfiltration through tools, excessive agency (details in AI Engineering) · [OWASP GenAI Security Project](https://genai.owasp.org/)

## Resources

### Start here

- [PortSwigger Web Security Academy](https://portswigger.net/web-security) · free, hands-on labs for every web vulnerability class; the best way to learn offence in order to build defence.
- [OWASP Cheat Sheet Series](https://cheatsheetseries.owasp.org/) · concise, maintained guidance for every topic in this roadmap.
- [OWASP Top 10](https://owasp.org/www-project-top-ten/) · the vocabulary everyone shares; read the 2021 edition and the latest.
- [OAuth 2.0 Simplified](https://www.oauth.com/) · Aaron Parecki's free book; the clearest explanation of OAuth and OpenID Connect.
- [Crypto 101](https://www.crypto101.io/) · a free introductory cryptography book for programmers.

### Books

- [Alice and Bob Learn Application Security](https://www.wiley.com/en-us/Alice+and+Bob+Learn+Application+Security-p-9781119687351) · Tanya Janca; an approachable overview of secure development (paid).
- [OAuth 2 in Action](https://www.manning.com/books/oauth-2-in-action) · Richer and Sanso (paid).
- [Serious Cryptography, 2nd edition](https://nostarch.com/seriouscrypto) · Jean-Philippe Aumasson; cryptography for engineers (paid).
- [Building Secure and Reliable Systems](https://google.github.io/building-secure-and-reliable-systems/) · Google; free online.
- [Spring Security in Action, 2nd edition](https://www.manning.com/books/spring-security-in-action-second-edition) · Laurențiu Spilcă (paid).

### Courses and videos

- [Stanford CS 253: Web Security](https://web.stanford.edu/class/cs253/) · free lecture videos and slides.
- [Hacksplaining](https://www.hacksplaining.com/lessons) · interactive, visual lessons on the common vulnerabilities.
- [Snyk Learn](https://learn.snyk.io/) · free short lessons with code examples in Java and JavaScript.
- [Computerphile: How NOT to Store Passwords](https://www.youtube.com/watch?v=8ZtInClXe1Q) · Tom Scott's classic; share it with anyone who stores passwords.

### References

- [MDN: Web security](https://developer.mozilla.org/en-US/docs/Web/Security) and [Mozilla Web Security Guidelines](https://infosec.mozilla.org/guidelines/web_security) · browser-side defences, headers and TLS settings.
- [oauth.net](https://oauth.net/2/) and [jwt.io](https://jwt.io/) · specifications, libraries and debugging tools.
- [CWE Top 25](https://cwe.mitre.org/top25/) · the most dangerous software weaknesses, with examples.
- [Troy Hunt's blog](https://www.troyhunt.com/) · breaches explained and what they teach.
- [roadmap.sh: Cyber Security](https://roadmap.sh/cyber-security) · visual overview, broader than application security.
