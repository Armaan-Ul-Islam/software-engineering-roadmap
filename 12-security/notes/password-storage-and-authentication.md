# Password storage, login flows and sessions

> **In one sentence:** Store passwords with a deliberately slow, salted, memory-hard hash (Argon2id or bcrypt) behind Spring's `DelegatingPasswordEncoder`, let users choose long passwords without composition rules, check them against breach lists, throttle guessing without handing attackers a lockout weapon, and rotate the session ID the moment someone logs in.

**Why it matters:** Password databases leak; the only question is how much the leak is worth. With MD5 or SHA-256 the answer is "most of the passwords by the weekend", with Argon2id it is "the weakest few, at great expense". The login endpoint is also the most attacked URL you own: credential stuffing with billions of leaked pairs, enumeration to find valid accounts, and lockout abuse to shut out real users. Interviewers ask about salts and work factors because the answers reveal whether you understand who the attacker is.

## The idea

**Why fast hashes fail.** A password hash has one job: make each guess expensive for the attacker while staying cheap enough for one login. General-purpose hashes are built for the opposite. Published benchmarks put a single modern GPU at tens of billions of SHA-256 computations per second, against roughly a thousand bcrypt computations per second at cost 12; that gap of seven orders of magnitude is the whole defence. A **salt** (random, per password, stored next to the hash) stops precomputed tables and makes identical passwords hash differently. Password-hashing functions add a **work factor** you raise as hardware improves: bcrypt's cost (each step doubles the work) or the memory size of scrypt and Argon2, which also defeats GPUs because memory is expensive to parallelise. A **pepper** is a secret mixed into every hash and kept out of the database (in the application's secret store), so a database-only leak yields nothing crackable.

| Algorithm | Parameters (OWASP guidance) | Notes |
|---|---|---|
| Argon2id | 19 MiB memory, 2 iterations, parallelism 1 | The current recommendation; memory-hard; Spring's encoder needs Bouncy Castle on the classpath |
| scrypt | N = 2^17, r = 8, p = 1 | Memory-hard; fine where Argon2 is unavailable |
| bcrypt | cost 10 or more; 12 is comfortable for a login endpoint | Everywhere and safe; silently truncates input at 72 bytes |
| PBKDF2-HMAC-SHA256 | 600,000 iterations | Only where FIPS compliance forces it; not memory-hard |

Spring Security's `DelegatingPasswordEncoder` stores the algorithm id with the hash (`{argon2}$argon2id$v=19$m=19456,t=2,p=1$...`), so verification picks the right encoder per stored value while new hashes use the current default. That is what makes **upgrading on login** possible: the only time you hold the plaintext is when the user types it, so when a user authenticates against an old hash, re-hash with the current encoder and store it. `DaoAuthenticationProvider` does this when a `UserDetailsPasswordService` bean exists.

**Password policy, per NIST SP 800-63B.** Minimum length 8 (the newer revision recommends 15 or more when the password is the only factor), maximum at least 64, all printable characters and Unicode allowed, paste and password managers allowed. No composition rules: "one uppercase, one symbol" produces `Winter2026!` and nothing better. No periodic expiry; force a change only on evidence of compromise. Check new passwords against breached-password lists. Have I Been Pwned offers this with k-anonymity: send the first five hex characters of the SHA-1 of the password to the range API, receive a few hundred hash suffixes, compare locally, and the password never leaves your server. Spring Security 6.3 ships `HaveIBeenPwnedRestApiPasswordChecker` as a `CompromisedPasswordChecker`.

**Rate limiting without creating a denial of service.** A hard lockout after five failures hands an attacker a way to lock any user out by typing their username and garbage. Prefer measures that slow the attacker and not the victim: exponential delays per account and per source IP, a short temporary lockout rather than a permanent one, a CAPTCHA or an MFA challenge after a few failures, and a trusted-device cookie that exempts the user's known browsers. Count failures per account **and** per IP, because credential stuffing spreads a few guesses over millions of accounts. Notify the user of lockouts and of logins from new devices.

**Enumeration-safe responses.** Login returns the same message, status code and roughly the same time whether the username is unknown or the password is wrong; `DaoAuthenticationProvider` hashes a dummy password when the user is not found for exactly this reason. Registration and password reset say "if that address is new / registered, we have sent an email" and do the real work asynchronously.

**Sessions.** The container draws the session ID from a cryptographic random source; your job is the cookie attributes (`Secure`, `HttpOnly`, `SameSite`), the idle and absolute timeouts, and the lifecycle. **Session fixation**: an attacker plants a known session ID in the victim's browser (through a link carrying `;jsessionid=` or a cookie set from a sibling subdomain), the victim logs in, and the attacker now holds an authenticated session. The fix is a fresh session ID at login, which Spring Security does by default (`changeSessionId`). Rotate again when privileges change, and on logout invalidate the session server-side and expire the cookie; a client that only deletes its cookie leaves the session alive until it times out.

## Example: the encoder configuration and a safe login flow

```java
@Configuration
public class PasswordConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> encoders = new HashMap<>();
        encoders.put("argon2", new Argon2PasswordEncoder(16, 32, 1, 19_456, 2));
        encoders.put("bcrypt", new BCryptPasswordEncoder(12));
        return new DelegatingPasswordEncoder("argon2", encoders);
    }
}

@Service
public class AccountUserDetailsService implements UserDetailsService, UserDetailsPasswordService {

    private final AccountRepository accountRepository;

    public AccountUserDetailsService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        Account account = accountRepository.findByUsername(username)
                .orElseThrow(() -> new UsernameNotFoundException(username));
        return User.withUsername(account.username())
                .password(account.passwordHash())
                .authorities(account.authorities())
                .build();
    }

    @Override
    public UserDetails updatePassword(UserDetails user, String newPassword) {
        accountRepository.updatePasswordHash(user.getUsername(), newPassword);
        return User.withUserDetails(user).password(newPassword).build();
    }
}
```

The `Argon2PasswordEncoder` arguments are salt length, hash length, parallelism, memory in kibibytes and iterations. Existing `{bcrypt}` hashes keep verifying; after a successful login against one, Spring calls `updatePassword` with the new `{argon2}` hash (the `newPassword` parameter arrives already encoded, despite its name) and the account is upgraded without anyone noticing. Session fixation protection is on by default; logout is one block of configuration:

```java
http.logout(logout -> logout
        .invalidateHttpSession(true)
        .deleteCookies("JSESSIONID"));
```

A safe login flow, in prose:

1. Receive the username and password over TLS. Normalise the username (trim, lower-case an email address); never normalise the password.
2. Check the throttles: failures for this account and for this IP in the current window. If exceeded, respond with the generic failure after the current delay and record the attempt.
3. Load the account. If it does not exist, still run the encoder against a fixed dummy hash so the response time matches.
4. Verify with `passwordEncoder.matches(rawPassword, storedHash)`.
5. On failure: increment both counters, log the event with account id and IP (never the password), return "invalid username or password" with the same status code as every other failure.
6. On success: reset the counters, run the compromised-password check and flag the account for a forced change if the password is known to be breached, re-hash if `upgradeEncoding` says so, rotate the session ID, set the cookie with `Secure`, `HttpOnly` and `SameSite=Lax`, log the event, and notify the user if the device is new.
7. On logout: invalidate the session server-side, expire the cookie, and revoke any refresh tokens tied to the session.

## Pitfalls

- A single SHA-256 with a salt. Salting fixes rainbow tables; it does nothing about speed. Only a password-hashing function slows the attacker down.
- Choosing a work factor once. Measure the hashing time at login (tens of milliseconds, not microseconds) and raise the factor every couple of years; upgrade-on-login makes that painless.
- Pre-hashing for bcrypt. Working around the 72-byte limit by hashing with SHA-256 first produces binary output that may contain a null byte, which bcrypt implementations treat as the end of the string. Use Argon2id, or base64-encode the pre-hash.
- Hard lockouts. An attacker locks out your whole customer list in a loop. Throttle and step up instead.
- Different messages, status codes or response times for "no such user" and "wrong password". Enumeration follows.
- Session IDs in URLs. `;jsessionid=` rewriting puts the session into logs and `Referer` headers and enables fixation; set `server.servlet.session.tracking-modes=cookie`.

## Check yourself

1. Why does a per-password salt not protect a leaked database of SHA-256 hashes, and what property of bcrypt or Argon2id does?
2. How does a `DelegatingPasswordEncoder` let you migrate ten million bcrypt hashes to Argon2id without a batch job, and when does each account actually migrate?
3. A product owner asks for "lock the account after five wrong attempts". What attack does that enable, and what do you propose instead?
4. Explain session fixation and why a new session ID at login defeats it. Why is rotating at login not enough if the application elevates privileges later?

## Go deeper

- [OWASP: Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) · the algorithm parameters in the table come from here; revisit it yearly.
- [NIST SP 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html) · the digital identity guidelines; section 5.1.1 is the password policy.
- [Have I Been Pwned: Pwned Passwords](https://haveibeenpwned.com/Passwords) · the breached-password corpus and the k-anonymity range API.
- [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) · enumeration-safe messages, throttling and the rest of the login flow.
- [OWASP: Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) · session ID properties, cookie attributes, fixation and expiry.
- [Spring Security: Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html) · `DelegatingPasswordEncoder`, the encoders and upgrade-on-login.

---

Part of [Security](../README.md) · items 3.1, 3.2, 3.4
