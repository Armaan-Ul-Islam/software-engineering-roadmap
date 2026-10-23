# TLS, certificates and Java trust stores

> **In one sentence:** TLS gives you confidentiality, integrity and proof that you are talking to the holder of a certificate that a trusted authority issued for that hostname; Java checks that proof against its `cacerts` trust store, and "PKIX path building failed" means the chain the server sent does not lead to anything in that store.

**Why it matters:** Every developer meets `PKIX path building failed` eventually: a corporate proxy, an internal service with a private CA, a staging environment with a self-signed certificate. The wrong fix (a trust-all `TrustManager`) is on every Q&A site and ends up in production, where it turns TLS into plaintext with extra steps. Knowing what the error means and fixing it correctly in ten minutes is a basic competence; explaining the handshake is a basic interview question.

## The idea

**What TLS guarantees.** Confidentiality (nobody on the path can read the bytes), integrity (nobody can modify them undetected) and server authentication (the server proved it holds the private key for a certificate that a CA your client trusts issued for the name you connected to). Optionally the client authenticates the same way (mutual TLS, item 7.4). What it does not guarantee: that the server is honest or the one you meant (a phishing site has a perfectly valid certificate), that the data is safe once it arrives, or that metadata is hidden (the server's IP, the hostname in the SNI extension unless Encrypted Client Hello is used, and the traffic pattern are visible).

**The TLS 1.3 handshake** takes one round trip. Braces mark messages that are already encrypted:

```text
Client                                                        Server
  |  ClientHello: supported versions, cipher suites, key_share,    |
  |  server_name (SNI), ALPN (h2, http/1.1)                        |
  |--------------------------------------------------------------->|
  |  ServerHello: chosen suite, key_share                          |
  |  {EncryptedExtensions} {Certificate} {CertificateVerify}       |
  |  {Finished}                                                    |
  |<---------------------------------------------------------------|
  |  {Finished}                                                    |
  |--------------------------------------------------------------->|
  |  {application data}                                            |
  |<-------------------------------------------------------------->|
```

Both sides derive the session keys from the two `key_share` values (ephemeral Diffie-Hellman, so a private key stolen later does not decrypt recorded traffic), which is why even the certificate travels encrypted. `CertificateVerify` is the actual proof of ownership: a signature over the handshake so far, made with the certificate's private key. TLS 1.3 removed RSA key exchange and every non-authenticated cipher mode; its three suites (`TLS_AES_128_GCM_SHA256`, `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`) are all authenticated encryption. TLS 1.2 needs two round trips and still permits weak options, which is why configuration guides exist for it and not for 1.3.

**Certificates and chains.** A certificate binds a public key to names (the Subject Alternative Names; the Common Name is ignored by browsers and should be by you), with a validity window and the issuer's signature. The client builds a **chain**: the server's leaf certificate, signed by an intermediate CA, signed by a root CA whose certificate sits in the client's **trust store**. Roots are the **trust anchors**: nobody vouches for them, they are simply present. The server must send the leaf and every intermediate; it need not send the root. Publicly trusted certificates are limited to 200 days as of 2026, and the industry has agreed to shorten that in steps to 47 days by 2029, which makes automation through ACME (the protocol behind Let's Encrypt and cert-manager) the only sane way to manage them. Let's Encrypt issues 90-day certificates for free once you prove control of the name with an HTTP or DNS challenge.

**Java specifics.** The JDK ships its own trust store, `$JAVA_HOME/lib/security/cacerts`, with the public roots; the password is `changeit` and `keytool` is the tool for looking inside. A Java client that cannot build a chain throws:

```text
javax.net.ssl.SSLHandshakeException: PKIX path building failed:
  sun.security.provider.certpath.SunCertPathBuilderException:
  unable to find valid certification path to requested target
```

Recent JDKs prefix the message with the TLS alert name, `(certificate_unknown)`. It means exactly one thing: the chain the server presented does not end at a certificate in the trust store this JVM is using. Two causes cover nearly every case: the server uses a private CA that this JVM has never heard of, or the server forgot to send its intermediate and the JVM cannot bridge the gap. Other errors mean other things: `No subject alternative DNS name matching ... found` is a hostname mismatch and `validity check failed` is expiry. Fix the cause the error names.

## Example: diagnose with openssl, fix with keytool

Step one is to look at what the server actually sends. Against a test server whose certificate was issued by a private "Example Corp Root CA":

```bash
openssl s_client -connect internal.example.com:443 -servername internal.example.com -showcerts </dev/null
```

```text
Certificate chain
 0 s:CN=internal.example.com
   i:CN=Example Corp Root CA
Verify return code: 21 (unable to verify the first certificate)
```

Return code 21 (or 19, `self-signed certificate in certificate chain`, when the server also sends the root) says that the client has no trust anchor for this chain. The `s:` and `i:` lines show the subject and issuer of each certificate the server sent, so a missing intermediate is visible at a glance. Add `-CAfile example-corp-root.pem` and the code becomes `0 (ok)`, which proves the server is fine and the problem is purely the client's trust store. `keytool -printcert -sslserver internal.example.com:443` shows the same chain the way Java sees it, including the SAN list and validity dates.

Step two is to give the JVM the root. Three places to put it, from quick to right. The JDK's own store (lost at every JDK upgrade or image rebuild unless the import is in the Dockerfile):

```bash
keytool -importcert -cacerts -storepass changeit -noprompt \
    -alias example-corp-root -file example-corp-root.pem
```

A dedicated trust store for the whole JVM. The copy step matters: `javax.net.ssl.trustStore` **replaces** the default store rather than adding to it, so a store with only the private root makes every public site fail:

```bash
keytool -importkeystore -srckeystore "$JAVA_HOME/lib/security/cacerts" -srcstorepass changeit \
    -destkeystore truststore.p12 -deststoretype PKCS12 -deststorepass changeit
keytool -importcert -keystore truststore.p12 -storepass changeit -noprompt \
    -alias example-corp-root -file example-corp-root.pem
keytool -list -keystore truststore.p12 -storepass changeit | grep example-corp-root
java -Djavax.net.ssl.trustStore=/etc/app/truststore.p12 -Djavax.net.ssl.trustStorePassword=changeit -jar app.jar
```

```text
example-corp-root, Oct 24, 2026, trustedCertEntry,
```

Or custom trust for one HTTP client, leaving the rest of the JVM untouched:

```java
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(Path.of("/etc/app/truststore.p12"))) {
    trustStore.load(input, "changeit".toCharArray());
}
TrustManagerFactory trustManagerFactory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
trustManagerFactory.init(trustStore);
SSLContext sslContext = SSLContext.getInstance("TLS");
sslContext.init(null, trustManagerFactory.getTrustManagers(), null);

HttpClient httpClient = HttpClient.newBuilder().sslContext(sslContext).build();
```

Spring Boot wraps the same idea in SSL bundles, with the certificate in PEM and no `keytool` at all: `spring.ssl.bundle.pem.corp.truststore.certificate=classpath:example-corp-root.pem`, then `RestClient.builder().apply(restClientSsl.fromBundle("corp"))`. That client trusts the corporate CA and nothing else, which is right for an internal client.

Whichever place you choose, import the **root** (or the issuing CA), never the leaf: trusting the leaf works until it is renewed. And get the root from the CA's owner, not from the server's handshake; a trust anchor only means something if it arrives through a different channel than the connection it is meant to verify.

**Why disabling verification is never the fix.** A `TrustManager` whose `checkServerTrusted` is empty, or a `HostnameVerifier` that returns `true`, accepts any certificate from anyone. The connection is still encrypted, but to whoever answered: a proxy on the corporate network, an attacker on the Wi-Fi, a poisoned DNS entry. Authentication is what makes the encryption mean something. Supplying the right trust anchor takes the same ten minutes and leaves TLS doing its job.

## Pitfalls

- Trusting the leaf certificate. Works until the next renewal, then fails in production at 3 a.m. Trust the CA.
- Setting `javax.net.ssl.trustStore` to a store containing only your private root. The JVM now distrusts the entire public internet.
- Testing with `curl` and concluding Java is broken. `curl` uses the operating system's trust store; Java uses its own. They disagree whenever a CA was added to one and not the other.
- Blaming the client for a server that does not send its intermediate. Browsers fetch or preload missing intermediates and hide the problem; Java does not. Fix the server's chain.
- Debugging with `-Djavax.net.debug=all`. It drowns you; `-Djavax.net.debug=ssl:handshake` shows what matters.

## Check yourself

1. A colleague says "TLS proves we are talking to the right server". What exactly is proven, and what is the gap a phishing site exploits?
2. Why does `CertificateVerify` exist when the certificate is already signed by the CA?
3. `PKIX path building failed` appears in production after a certificate renewal, although the CA did not change. Name the two most likely causes and the command that distinguishes them.
4. Why does a trust-all `TrustManager` make the connection no better than plaintext against an attacker on the same network, even though the traffic is encrypted?

## Go deeper

- [Cloudflare: What happens in a TLS handshake?](https://www.cloudflare.com/learning/ssl/what-happens-in-a-tls-handshake/) · the handshake in plain language, 1.2 and 1.3 side by side.
- [The Illustrated TLS 1.3 Connection](https://tls13.xargs.org/) · every byte of a real handshake, annotated; the best way to make the diagram above concrete.
- [Let's Encrypt: How it works](https://letsencrypt.org/how-it-works/) · ACME and the challenges, which is how certificates get automated.
- [keytool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html) · the reference for every option used above.
- [Baeldung: SSL Handshake Failures](https://www.baeldung.com/java-ssl-handshake-failures) · the common Java-side errors and their causes.
- [Spring Boot: SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html) · SSL bundles for clients and for the embedded server.

---

Part of [Security](../README.md) · items 7.1, 7.2, 7.3
