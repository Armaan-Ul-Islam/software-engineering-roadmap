# The TLS handshake and certificates in practice

> **In one sentence:** TLS gives you an encrypted, tamper-proof channel to a server that has proven, via a certificate chain ending in a root your client already trusts, that it owns the name you asked for; almost every TLS incident is a chain, name, or expiry problem, and `openssl s_client` shows you which.

**Why it matters:** "Works in Chrome, fails in Java" (a missing intermediate certificate), a certificate that expired on a Saturday, a load balancer serving the wrong certificate because the client did not send SNI: these are routine production incidents, and each takes thirty seconds to diagnose once you can read a handshake. TLS 1.3 also changed the cost model, which matters for latency budgets.

## The idea

**What TLS guarantees.** Confidentiality (nobody in the middle can read the bytes), integrity (nobody can alter them undetected), and server authentication (you are talking to someone holding the private key for a certificate that names the host you asked for and that was issued by a certificate authority your client trusts). Client authentication is optional (mutual TLS). TLS does not hide who you are talking to: the IP address and, without Encrypted Client Hello, the hostname in SNI travel in clear text.

**The TLS 1.3 handshake** takes one round trip:

1. Client sends `ClientHello`: supported versions and cipher suites, a key share (usually X25519), the **SNI** extension with the hostname, and the **ALPN** extension listing the application protocols it speaks (`h2`, `http/1.1`).
2. Server answers `ServerHello` with its own key share. From this point both sides have the shared secret, and everything that follows is encrypted: `EncryptedExtensions` (including the chosen ALPN protocol), `Certificate` (the chain), `CertificateVerify` (a signature with the private key, proving possession), `Finished`.
3. Client verifies the chain and the signature, sends `Finished`, and can send the HTTP request immediately.

TLS 1.2 needed two round trips and sent the certificate in clear. TLS 1.3 also removed RSA key exchange and the weak cipher suites, so forward secrecy is no longer optional. **Session resumption**: after the handshake the server sends one or more `NewSessionTicket` messages; a later connection presents the ticket and skips certificate verification, and may send **0-RTT** early data with its first flight (only safe for idempotent requests, because early data can be replayed).

**Certificate chains.** The server's own certificate (the leaf) is signed by an intermediate CA, which is signed by a root CA. The root is in your trust store (the OS store, the browser's own store for Firefox, `$JAVA_HOME/lib/security/cacerts` for the JVM); nothing else needs to be. The server must send the leaf *and the intermediates*. Browsers often repair a missing intermediate by fetching it from the URL embedded in the leaf; `curl`, Java, Go and Python do not, so the same site works in a browser and fails everywhere else.

**SNI** lets one IP address host many certificates: the client names the host in `ClientHello`, and the server picks the matching certificate. **ALPN** avoids an extra round trip to negotiate HTTP/2: the protocol is agreed inside the handshake.

**Certificates in practice.** A certificate binds names (the `subjectAltName` list; the `CN` field is ignored by modern clients) to a public key for a validity period. Let's Encrypt issues free 90-day certificates through **ACME**: your client proves control of the name by serving a token at `http://<name>/.well-known/acme-challenge/<token>` (`http-01`) or publishing a `TXT` record (`dns-01`, required for wildcards), then renews automatically. A wildcard `*.example.com` matches exactly one label (`api.example.com`, not `example.com` and not `a.b.example.com`), which is why most certificates list several SANs instead. Short lifetimes are a feature only if renewal is automated and monitored.

## Example: reading `openssl s_client`

```bash
openssl s_client -connect example.com:443 -servername example.com -alpn h2,http/1.1 </dev/null
```

Trimmed output, annotated:

```text
depth=3 C=US, O=SSL Corporation, CN=SSL.com TLS ECC Root CA 2022      <- root, found in the local trust store
verify return:1
depth=1 C=US, O=SSL Corporation, CN=Cloudflare TLS Issuing ECC CA 3   <- intermediate
verify return:1
depth=0 CN=example.com                                                 <- leaf; verify return:1 at every depth = chain OK
---
Certificate chain
 0 s:CN=example.com
   i:C=US, O=SSL Corporation, CN=Cloudflare TLS Issuing ECC CA 3
   v:NotBefore: Sep 26 22:49:11 2026 GMT; NotAfter: Dec 25 22:56:35 2026 GMT
 1 s:C=US, O=SSL Corporation, CN=Cloudflare TLS Issuing ECC CA 3
   i:C=US, O=SSL Corporation, CN=SSL.com TLS Transit ECC CA R2
---
Verification: OK
---
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Protocol: TLSv1.3
ALPN protocol: h2                                                      <- HTTP/2 agreed inside the handshake
Verify return code: 0 (ok)
```

Each `s:` line is a subject and the `i:` below it the issuer; entry 1's subject must equal entry 0's issuer, and so on up. The leaf here is valid for 90 days. To print the dates and names your code will check against:

```bash
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -ext subjectAltName
```

```text
notBefore=Sep 26 22:49:11 2026 GMT
notAfter=Dec 25 22:56:35 2026 GMT
X509v3 Subject Alternative Name:
    DNS:example.com, DNS:*.example.com
```

## Example: spotting a missing intermediate

`badssl.com` hosts deliberately broken endpoints. This one sends only the leaf:

```bash
openssl s_client -connect incomplete-chain.badssl.com:443 -servername incomplete-chain.badssl.com </dev/null
```

```text
depth=0 CN=*.badssl.com
verify error:num=20:unable to get local issuer certificate
verify error:num=21:unable to verify the first certificate
---
Certificate chain
 0 s:CN=*.badssl.com
   i:C=US, O=Let's Encrypt, CN=YR1
---
Verification error: unable to verify the first certificate
```

Two tells. The chain has a single entry whose issuer (a Let's Encrypt intermediate) appears nowhere else, and the errors say "unable to get local issuer": the client has the roots but was never given the intermediate that links this leaf to one. A browser may show this site as fine; Java will throw `SSLHandshakeException: PKIX path building failed ... unable to find valid certification path to requested target`. Compare `expired.badssl.com`, where the chain is complete and the error is `num=10:certificate has expired`. The fix for a missing intermediate is always on the server: configure the full chain file (`fullchain.pem` from ACME clients, not `cert.pem`). Importing the intermediate into every client's `cacerts` with `keytool -importcert -cacerts` is the fix only for a private CA.

Two more quick experiments. Omit SNI and a shared host cannot pick a certificate:

```text
$ openssl s_client -connect example.com:443 -noservername </dev/null
error:0A000410:SSL routines::ssl/tls alert handshake failure
```

And save a session ticket, then present it:

```text
$ printf 'GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n' \
    | openssl s_client -connect example.com:443 -servername example.com -sess_out session.pem -ign_eof 2>/dev/null \
    | grep -E '^New,|Ticket arrived'
New, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
Post-Handshake New Session Ticket arrived:
$ openssl s_client -connect example.com:443 -servername example.com -sess_in session.pem </dev/null 2>/dev/null | grep '^Reused'
Reused, TLSv1.3, Cipher is TLS_AES_256_GCM_SHA384
```

## Pitfalls

- Serving `cert.pem` instead of `fullchain.pem`. The symptom is the "browsers fine, everything else broken" pattern above.
- Letting certificates expire. 90-day certificates need automated renewal plus an alert when `notAfter` is under, say, 14 days away; the renewal job failing silently for two months is the usual story.
- Fixing a chain problem on the client. Adding a public intermediate to `cacerts` hides the server's misconfiguration until the intermediate rotates, then everything breaks at once.
- Assuming a wildcard covers the apex or two levels. `*.example.com` does not match `example.com` or `a.b.example.com`; add SANs.
- Health checks and internal clients without SNI. `curl --resolve` and most libraries send SNI; a hand-rolled check that connects by IP and sends no hostname gets the default certificate, or a handshake failure as shown above.
- 0-RTT for non-idempotent requests. Early data can be replayed by an attacker; servers should reject `POST` in early data or terminate TLS somewhere that does.
- Trusting the `CN`. Modern clients only check `subjectAltName`; a certificate with the name only in `CN` fails in Chrome, Java 11+ and Go.

## Check yourself

1. A new Spring service fails with `PKIX path building failed` calling a partner API that opens fine in your browser. Which `openssl s_client` lines would confirm your suspicion, and where is the correct fix?
2. Why is TLS 1.3 one round trip faster than TLS 1.2, and why does a resumed connection skip even more work?
3. Your load balancer hosts `api.example.com` and `admin.example.com` on one IP. What in the handshake lets it pick the right certificate, and what happens when a client does not send it?
4. Why should a server refuse to execute a `POST` carried in 0-RTT early data?

## Go deeper

- [Cloudflare: What happens in a TLS handshake?](https://www.cloudflare.com/learning/ssl/what-happens-in-a-tls-handshake/) · the handshake step by step, 1.2 and 1.3 side by side.
- [HPBN: Transport Layer Security](https://hpbn.co/transport-layer-security-tls/) · the performance view: round trips, resumption, OCSP stapling, record sizes.
- [Let's Encrypt: How it works](https://letsencrypt.org/how-it-works/) and [Challenge types](https://letsencrypt.org/docs/challenge-types/) · ACME, and when you need `dns-01`.
- [badssl.com](https://badssl.com/) · every broken-TLS scenario as a live hostname; test your client against each.
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446.html) · section 2 is a readable overview of the handshake; the rest when you need it.

---

Part of [Web & HTTP](../README.md) · items 3.2, 3.3
