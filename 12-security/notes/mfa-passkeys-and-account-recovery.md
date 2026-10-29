# Multi-factor authentication, passkeys and account recovery

> **In one sentence:** A second factor only helps if an attacker who has the password cannot also obtain it, which TOTP codes fail (the user types them into whatever page asks) and WebAuthn passkeys achieve (the browser signs a challenge bound to the real origin); and whatever your login requires, the account is only as strong as the easiest way to get back in after losing it.

**Why it matters:** Credential stuffing works because passwords are reused, so every account with money or data in it needs a second factor, and the authentication cheat sheets now say which kind. Real-time phishing kits relay TOTP codes in seconds; passkeys are the first factor ordinary users will adopt that those kits cannot relay. At the same time, "forgot my password" and "lost my phone" flows are where account takeovers actually happen, because teams design them for support convenience rather than as authentication.

## The idea

**Factors.** Something you know (password), something you have (phone, security key), something you are (biometric, which on consumer devices unlocks a key rather than being sent anywhere). A second factor from a different category defeats a leaked password. The categories differ in how they fail:

| Method | How it works | Phishable? | Typical failure |
|---|---|---|---|
| SMS code | Server sends a code to a phone number | Yes | SIM swap, number recycling, SS7 interception; treat as better than nothing |
| TOTP app | Shared secret, HMAC over the current 30-second counter, six digits | Yes | User types the code into a phishing page that relays it within the window |
| Push approval | Server asks the user's app "was this you?" | Yes, by fatigue | Attacker spams prompts until the user taps approve; number matching helps |
| WebAuthn security key or passkey | Public-key challenge-response bound to the origin | No | Lost device without recovery |
| Recovery codes | Pre-generated one-time codes, stored hashed | Yes | Stored in the same password manager as the password; fine, that is the design |

**TOTP (RFC 6238).** Enrollment shares a random secret (encoded base32 in the QR code). Both sides compute `HMAC-SHA1(secret, floor(unix_time / 30))`, take four bytes at an offset given by the last nibble, and reduce to six digits. The server accepts the current step and one on either side for clock drift, and must remember which step it last accepted so a captured code cannot be replayed within the window. The secret is a credential: store it encrypted, never log it, and require the current password (or an existing factor) before enrolling or removing it.

**WebAuthn and passkeys.** At registration the server sends a random challenge and its relying party ID (`rpId`, the site's registrable domain). The authenticator (the platform's secure element or a security key) creates a key pair scoped to that `rpId`, returns the public key and a credential ID, and the server stores both with the user. At login the server sends a fresh challenge; the browser passes it to the authenticator together with the page's origin; the authenticator signs the challenge plus a hash of the `rpId` plus flags saying the user was present and verified; the server checks the origin and challenge in `clientDataJSON`, the `rpId` hash, the flags, and the signature against the stored public key. Phishing resistance follows from two facts: the authenticator will not use a credential for any `rpId` other than the one it was created for, and the browser, not the page, writes the origin into the signed data. A phishing site at `examp1e.com` cannot ask for `example.com`'s credential, and a relayed response would carry the wrong origin. A **passkey** is a WebAuthn credential that is discoverable (the authenticator can find it by `rpId` without the server naming a credential ID first, so login needs no username) and usually synced through the platform's password manager, which solves the lost-device problem for most people. Spring Security 6.4 added passkey registration and login to the servlet DSL; the credential store defaults to memory and persisting it is your job.

**Recovery is the real authentication.** Password reset, "lost my authenticator", and the support desk are all logins with different proofs. If reset by email alone bypasses MFA, the account's security is the mailbox's. Rules that hold up:

1. Email verification before the address can be used for anything: before it appears to other users, before it can receive reset links, before it can be used to log in. Otherwise an attacker registers with the victim's address first and inherits the account when the victim later signs up (account pre-hijacking).
2. Reset tokens are 32 random bytes from `SecureRandom`, stored only as a hash, bound to the account, single use, expired within 15 to 20 minutes, and every outstanding token and session is invalidated when one is used. The link is built from configuration, never from the request's `Host` header. The threat model in item 1.2 goes through this flow line by line.
3. Responses never reveal whether an address or username exists.
4. Losing the second factor must not reduce to "click the email link". Accept a recovery code, or another registered passkey, or an identity check followed by a waiting period during which every channel the user has is notified and any of them can cancel. The waiting period is the control: it turns a silent takeover into a visible one.
5. Support staff follow the same rules as the software. A takeover that starts with "hi, I lost my phone" and a friendly agent is the most common kind at companies with good code.
6. Recovery codes: eight to ten codes of at least 10 random characters each, shown once, stored hashed, each usable once, regenerable only from a logged-in session with a fresh factor.

## Example: TOTP generation and replay-safe verification

A complete implementation, checked against the RFC 6238 test vector (secret `12345678901234567890`, time 59 seconds, SHA-1, which gives `94287082` at eight digits and therefore `287082` at six):

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class Totp {

    private static final int TIME_STEP_SECONDS = 30;
    private static final int DIGITS = 6;

    private final byte[] secret;
    private final Set<Long> usedCounters = new HashSet<>();

    public Totp(byte[] secret) {
        this.secret = secret;
    }

    public String codeFor(long counter) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA1");
        mac.init(new SecretKeySpec(secret, "HmacSHA1"));
        byte[] hash = mac.doFinal(ByteBuffer.allocate(8).putLong(counter).array());
        int offset = hash[hash.length - 1] & 0x0f;
        int binary = ((hash[offset] & 0x7f) << 24)
                | ((hash[offset + 1] & 0xff) << 16)
                | ((hash[offset + 2] & 0xff) << 8)
                | (hash[offset + 3] & 0xff);
        int code = binary % (int) Math.pow(10, DIGITS);
        return String.format("%0" + DIGITS + "d", code);
    }

    public boolean verify(String submittedCode, Instant now) throws Exception {
        long currentCounter = now.getEpochSecond() / TIME_STEP_SECONDS;
        for (long counter = currentCounter - 1; counter <= currentCounter + 1; counter++) {
            if (usedCounters.contains(counter)) {
                continue;
            }
            if (constantTimeEquals(codeFor(counter), submittedCode)) {
                usedCounters.add(counter);
                return true;
            }
        }
        return false;
    }

    private static boolean constantTimeEquals(String expected, String actual) {
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII), actual.getBytes(StandardCharsets.US_ASCII));
    }

    public static void main(String[] arguments) throws Exception {
        byte[] rfcTestSecret = "12345678901234567890".getBytes(StandardCharsets.US_ASCII);
        Totp totp = new Totp(rfcTestSecret);
        System.out.println("code at t=59s: " + totp.codeFor(59 / TIME_STEP_SECONDS));

        Instant now = Instant.ofEpochSecond(1_700_000_000L);
        String code = totp.codeFor(now.getEpochSecond() / TIME_STEP_SECONDS);
        System.out.println("first use:     " + totp.verify(code, now));
        System.out.println("replay:        " + totp.verify(code, now));
        System.out.println("20s later:     " + totp.verify(code, now.plusSeconds(20)));
        System.out.println("wrong code:    " + totp.verify("000000", now));
    }
}
```

```text
code at t=59s: 287082
first use:     true
replay:        false
20s later:     false
wrong code:    false
```

In production the `usedCounters` set is a column on the user's MFA record (the last accepted counter is enough), the comparison stays constant-time, and failed attempts count towards the same throttles as passwords (item 3.2). Notice what the code cannot do: it has no idea which page the user typed the code into. That is the phishing gap, and no amount of server-side care closes it.

## Example: passkey login in Spring Security

The relying party is three values; everything else (challenge generation, the registration and assertion endpoints, origin and `rpId` checks, signature verification) is in the framework:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(requests -> requests.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .webAuthn(webAuthn -> webAuthn
                    .rpName("Example Shop")
                    .rpId("example.com")
                    .allowedOrigins("https://example.com"));
    return http.build();
}
```

`rpId` must be the site's registrable domain or a suffix of the origin's host; a credential registered for `example.com` works on `shop.example.com`, and a credential registered for `shop.example.com` works nowhere else. `allowedOrigins` is the list of exact origins the server will accept in `clientDataJSON`. Both are what make the flow phishing resistant, so neither is a wildcard.

## Pitfalls

- MFA that is bypassed by the reset flow. Check it explicitly: can a user with no second factor in hand get in by email alone? If yes, the second factor is decoration.
- Accepting a TOTP code more than once in its window. The server must record the last accepted step.
- Enrolling a second factor without re-authentication. An attacker with a hijacked session adds their own authenticator and keeps the account after the password changes.
- SMS as the recovery path for an account protected by a passkey. The strongest factor is irrelevant when the weakest one resets it.
- Storing recovery codes in plain text, or showing them again later. Hash them like passwords; regenerate rather than redisplay.
- Building reset links from `Host`. The classic takeover, see item 1.2.
- A single registered passkey with no second one and no recovery codes. Prompt for a backup method at enrollment; synced passkeys reduce the problem but device-bound keys do not.
- Treating "verified" biometrics as data you receive. The biometric never leaves the device; what you receive is a signature, and the user-verified flag is the authenticator's claim.

## Check yourself

1. Explain, in terms of what is signed and by whom, why a phishing site that relays a WebAuthn challenge in real time still cannot log in, while the same relay works for a TOTP code.
2. Why does the server need to remember the last accepted TOTP step, and what attack does the one-step window on either side open if it does not?
3. A product owner wants "if the user loses their phone, support can disable MFA after checking their date of birth". What is the account's effective authentication strength afterwards, and what would you propose instead?
4. Describe account pre-hijacking and the single rule in the registration flow that prevents it.

## Go deeper

- [WebAuthn Guide](https://webauthn.guide/) · the registration and authentication ceremonies with annotated JavaScript; read before touching any library.
- [passkeys.dev](https://passkeys.dev/) · what passkeys are, platform support, and the user-experience guidance that decides adoption.
- [OWASP: Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html) · the factor types compared, when to require MFA, and how to handle failed and lost factors.
- [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) · the reset flow step by step, including the token rules above.
- [RFC 6238: TOTP](https://www.rfc-editor.org/rfc/rfc6238) · short, with the test vectors the example reproduces.
- [Web Authentication: Level 3](https://www.w3.org/TR/webauthn-3/) · the specification; section 7 is the server's verification procedure.
- [Spring Security: Passkeys](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html) · the configuration above, the endpoints it adds, and the persistence you need to supply.

---

Part of [Security](../README.md) · items 3.3, 3.5
