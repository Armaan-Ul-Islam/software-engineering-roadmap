# Cryptography for developers: the four jobs and AES-GCM done right

> **In one sentence:** Application cryptography is four jobs (hash for integrity, MAC for authenticity, encrypt for confidentiality, sign for non-repudiation), each with one modern primitive you should reach for, and the skill is choosing the right job and using the primitive exactly as its library intends, inventing nothing.

**Why it matters:** The crypto bugs that reach production are rarely broken algorithms. They are AES in ECB mode, a reused nonce, an unauthenticated ciphertext that an attacker flips bits in, a MAC where a signature was needed, or `java.util.Random` generating a password-reset token. Each is a few characters away from the correct code. Knowing which primitive does which job, and what its parameters mean, is what lets you review such code and answer "how would you encrypt this field?" in an interview.

## The idea

| Job | Question it answers | Key | Use | Do not use |
|---|---|---|---|---|
| Hash | Is this the same data? | none | SHA-256, SHA-3 | MD5, SHA-1; any plain hash for passwords (see item 3.1) |
| MAC | Did someone holding the key produce this, unchanged? | shared secret | HMAC-SHA256 | a hash of secret plus message (length extension) |
| Encrypt | Can only the key holder read it? | shared secret | AES-256-GCM or ChaCha20-Poly1305 (authenticated encryption) | ECB, CBC without a MAC, RC4, hand-built padding |
| Sign | Did this holder of a private key produce it, provably to anyone? | key pair | Ed25519, ECDSA P-256, RSA-PSS | RSA with PKCS#1 v1.5 in new systems |
| Key agreement | How do two parties agree a secret over a public channel? | key pairs | X25519 or ECDH P-256, then HKDF | RSA-encrypting a session key |

Two distinctions trip people up. A **hash** proves nothing about origin: anyone can hash. A **MAC** proves origin to someone who shares the key, so it cannot be shown to a third party as evidence (the verifier could have produced it); a **signature** proves origin to anyone with the public key, which is what non-repudiation means. And **encryption without authentication** is a known failure: an attacker who cannot read a CBC ciphertext can still flip bits in it predictably, and padding-oracle attacks recover plaintext from error messages. **Authenticated encryption with associated data** (AEAD) does both jobs at once and is the only kind to use. The "associated data" is extra input (a record id, a version, a purpose) that is authenticated but not encrypted, so a ciphertext cannot be swapped into another record.

**AES-GCM's rules.** The key is 128 or 256 bits. The **nonce** (IV) is 96 bits and must never repeat for the same key: one repeat leaks the XOR of the two plaintexts and the authentication key, after which forgery is trivial. Random nonces are fine as long as the key is rotated well before 2^32 messages. The **tag** is 128 bits; do not shorten it. The output is nonce, ciphertext and tag, with the nonce stored in the clear, because it is not a secret, only a value that must never be reused. Decryption verifies the tag before returning anything and throws `AEADBadTagException` on any change to nonce, ciphertext, tag or associated data.

**Asymmetric cryptography.** RSA and elliptic curves do the same jobs; curves do them with far smaller keys (a 256-bit curve key is about as strong as 3072-bit RSA) and faster. Prefer **Ed25519** for signatures (deterministic, fast, nothing to configure), ECDSA on P-256 where interoperability demands it (its per-signature random value must be unpredictable; a reused one revealed Sony's PlayStation 3 signing key), and **X25519** or ECDH for key agreement. Nobody encrypts data with public keys directly: **hybrid encryption** agrees or wraps a symmetric key and uses AES-GCM for the data. Where RSA is unavoidable (certificates, JWTs), 2048 bits is the floor and the padding is OAEP for encryption and PSS for signatures.

**Randomness.** Keys, nonces, salts, tokens and session IDs come from `java.security.SecureRandom`; `java.util.Random`, `Math.random()` and `ThreadLocalRandom` are predictable from a few outputs. `new SecureRandom()` is the right constructor; `getInstanceStrong()` can block waiting for entropy and is not safer in practice. A token is 32 random bytes encoded with base64url. A UUID is an identifier, not a secret: versions 1 and 7 embed timestamps, and a version 4 is only as random as whichever system minted it, which the string does not tell you.

**Key management basics.** Keys live in a KMS, HSM or vault, never in code, configuration or the table next to the ciphertext. **Envelope encryption** keeps each data key encrypted under a key-encryption key held in the KMS, so rotation re-wraps small keys instead of re-encrypting terabytes; every ciphertext records which key and scheme produced it, or rotation is impossible (see item 8.5).

**Libraries, and what "don't roll your own" means.** The JCA (`javax.crypto`, `java.security`) ships correct primitives but not a correct composition: modes, nonces, output encoding, key ids and rotation are left to you, and each is a place to go wrong. Google Tink removes those choices (an `Aead` primitive over a keyset that carries key ids and rotation, and no way to pick ECB); Bouncy Castle adds algorithms the JDK lacks, such as Argon2. "Don't roll your own" is not only about inventing ciphers; it is about not inventing the protocol around them. If you are concatenating things and hashing them, you are rolling your own.

## Example: AES-GCM with the JCA, correctly

Compiled and run as written on Java 25:

```java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class AesGcmExample {

    private static final int NONCE_LENGTH_BYTES = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    static SecretKey generateKey() throws GeneralSecurityException {
        KeyGenerator keyGenerator = KeyGenerator.getInstance("AES");
        keyGenerator.init(256);
        return keyGenerator.generateKey();
    }

    static byte[] encrypt(SecretKey key, byte[] plaintext, byte[] associatedData) throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_LENGTH_BYTES];
        SECURE_RANDOM.nextBytes(nonce);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        cipher.updateAAD(associatedData);
        byte[] ciphertextWithTag = cipher.doFinal(plaintext);
        return ByteBuffer.allocate(NONCE_LENGTH_BYTES + ciphertextWithTag.length)
                .put(nonce)
                .put(ciphertextWithTag)
                .array();
    }

    static byte[] decrypt(SecretKey key, byte[] message, byte[] associatedData) throws GeneralSecurityException {
        ByteBuffer buffer = ByteBuffer.wrap(message);
        byte[] nonce = new byte[NONCE_LENGTH_BYTES];
        buffer.get(nonce);
        byte[] ciphertextWithTag = new byte[buffer.remaining()];
        buffer.get(ciphertextWithTag);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, nonce));
        cipher.updateAAD(associatedData);
        return cipher.doFinal(ciphertextWithTag);
    }

    public static void main(String[] arguments) throws GeneralSecurityException {
        SecretKey key = generateKey();
        byte[] associatedData = "customer:42".getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "IBAN NO93 8601 1117 947".getBytes(StandardCharsets.UTF_8);

        byte[] message = encrypt(key, plaintext, associatedData);
        System.out.println("stored bytes: " + message.length + " (12 nonce + " + plaintext.length + " ciphertext + 16 tag)");
        System.out.println("decrypted: " + new String(decrypt(key, message, associatedData), StandardCharsets.UTF_8));

        message[20] ^= 1;
        try {
            decrypt(key, message, associatedData);
        } catch (AEADBadTagException exception) {
            System.out.println("tampering detected: " + exception.getMessage());
        }
    }
}
```

```text
stored bytes: 51 (12 nonce + 23 ciphertext + 16 tag)
decrypted: IBAN NO93 8601 1117 947
tampering detected: Tag mismatch
```

Flipping one bit of the ciphertext makes decryption fail before any plaintext is returned; the same happens if the associated data at decryption time is `customer:43`, which is the point of binding a ciphertext to its record. A fresh `Cipher` per call is deliberate: `Cipher` is not thread-safe, and the SunJCE provider refuses to encrypt twice with the same key and nonce on one instance.

What the example deliberately does **not** do, each of which is its own task:

1. Derive the key from a password. That needs a password-based KDF (Argon2id or PBKDF2) with a salt, and is a different threat model.
2. Store or distribute the key. In production it lives in a KMS or vault and arrives through the secret store (see item 9.1), with envelope encryption wrapping per-record data keys.
3. Record a key id or a format version in the output. Add a small header before the nonce, or keys can never be rotated and the scheme never changed.
4. Handle more than about 2^32 messages per key. Beyond that random nonces risk collision; rotate keys, or use a nonce-misuse-resistant scheme such as AES-GCM-SIV or XChaCha20-Poly1305 from a library that offers it.

With Tink the same operation is `aead.encrypt(plaintext, associatedData)` against a keyset that already carries key ids and rotation, which is why the recommendation for new code is the library that makes this list shorter.

## Pitfalls

- ECB mode. Identical blocks encrypt identically; the "ECB penguin" is structure showing through the ciphertext. If you can see a pattern, so can the attacker.
- Reusing a nonce with the same key, usually through a fixed IV "for determinism" or a counter that resets on restart. One repeat and the key is finished.
- Encrypting without authenticating, or "authenticating" with a hash. `AES/CBC/PKCS5Padding` without an HMAC is malleable and open to padding oracles; a hash of the ciphertext is not a MAC because it has no key.
- Comparing MACs or tokens with `equals`. Timing differences leak the position of the first mismatch; use `MessageDigest.isEqual`.
- `UUID.randomUUID()` or `java.util.Random` as a secret generator. Use `SecureRandom` and 32 bytes.

## Check yourself

1. A webhook receiver checks `sha256(secret + body)` against a header. Why is that not a MAC, and what should it be?
2. Why is the nonce stored in the clear next to the ciphertext, and what property must it have that a secret does not?
3. Two services must prove to a third, auditing service that each produced its own records. MAC or signature, and why?
4. Name three things the AES-GCM example leaves out that a production implementation needs, and say where each would live.

## Go deeper

- [Latacora: Cryptographic Right Answers](https://www.latacora.com/blog/2018/04/03/cryptographic-right-answers/) · one recommendation per job, with reasons; the table above follows it.
- [Crypto 101](https://www.crypto101.io/) · the free book that explains why each primitive is shaped the way it is, including the attacks on the wrong choices.
- [OWASP: Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) · algorithms, key sizes and key management for data at rest.
- [Tink](https://developers.google.com/tink) · the library that turns these recommendations into the only available options.
- [Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-cryptography-architecture-jca-reference-guide.html) · how `Cipher`, `KeyGenerator` and providers fit together.

---

Part of [Security](../README.md) · items 8.1, 8.2, 8.3, 8.4
