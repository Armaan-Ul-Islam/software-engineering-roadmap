# Webhooks done right

> **In one sentence:** A webhook is an HTTP request your system receives when something happened elsewhere, delivered at least once and in no guaranteed order by a sender you must authenticate, so a correct receiver verifies an HMAC signature over the raw body and a timestamp, deduplicates by event ID, acknowledges within milliseconds and does the real work asynchronously.

**Why it matters:** Payment providers, source-code hosts and every SaaS product deliver webhooks, and most receivers are written in an afternoon as "parse JSON, update the database, return 200". Those receivers double-ship when a delivery is retried, accept forged events when the signature check is missing or compares strings with `equals`, lose events when the handler throws, and time out when processing takes longer than the sender's patience. Every one of these failures is silent until money is involved.

## The idea

**Delivery guarantees.** The sender `POST`s to your URL and waits a few seconds for a 2xx (GitHub gives you 10 seconds). Anything else (timeout, 5xx, connection error) is a failure, and the sender retries with exponential backoff over hours or days (Stripe retries for up to three days in live mode). So delivery is **at least once**: retries produce duplicates, and because a retry of an old event can land after a newer event, there is **no ordering**. You will also receive event types you did not subscribe to yet, because senders add them.

**Idempotent receivers.** Every delivery carries a unique ID (`webhook-id` in Standard Webhooks, `X-GitHub-Delivery` at GitHub, the event's `id` at Stripe). Store it before doing anything else, with a unique constraint; if the insert finds the ID already there, this is a duplicate: answer 200 and stop. Then make the handler idempotent anyway, because the dedupe store protects the first step, not a crash halfway through the second: "mark invoice paid" can run twice, "add 100 to the balance" cannot.

**Authenticity.** Anyone who learns the URL can post to it, so the sender signs each delivery with a shared secret: `HMAC-SHA256(secret, signed content)`, where the signed content includes a timestamp and the raw body. Stripe sends `Stripe-Signature: t=<unix seconds>,v1=<hex>` over `t.body`; Standard Webhooks sends `webhook-id`, `webhook-timestamp` and `webhook-signature: v1,<base64>` over `id.timestamp.body`; GitHub sends `X-Hub-Signature-256: sha256=<hex>` over the body alone. The receiver recomputes the HMAC over the **exact bytes received** (not over a parsed and re-serialised body, whose whitespace, key order or number formatting may differ), compares with a **constant-time** comparison such as `MessageDigest.isEqual`, and rejects deliveries whose timestamp is outside a tolerance window (five minutes is the convention) to limit replay. Several signatures may be present at once so that the secret can be rotated without downtime. Webhooks must use HTTPS, because the payload itself is often confidential.

**Replay windows.** The timestamp check bounds how long a captured delivery stays valid; the dedupe store catches replays inside that window. Keep stored IDs for at least the sender's retry horizon (days), so that a legitimate late retry is recognised as a duplicate rather than processed again.

**Ordering.** Never assume it. Either treat the event as a trigger and fetch the object's current state from the sender's API before acting (Stripe's own recommendation), or carry a version or `updated_at` in the payload and ignore anything older than what you already applied, or design handlers that commute.

**Respond fast, process asynchronously.** On the request thread: verify, dedupe-insert, persist the raw event (an outbox table or a queue), return 200. Milliseconds. Workers then process events with their own retries; after N failures an event is marked **dead** with its raw payload kept, an alert fires, and someone can inspect and replay it. Returning 200 only after the event is durably stored is what makes "we never lose events" true; returning 200 after processing is what makes the sender time out and retry while you are still working.

**Observability.** Log the event ID, type, sender timestamp, verification result and outcome for every delivery. Count received, duplicate, invalid-signature (an alert: an attack, or a secret rotation gone wrong), processing lag and dead events. Keep the sender's delivery dashboard bookmarked for reconciliation, and run a periodic job that lists recent events from the sender's API and finds any you never received: webhooks are notifications, the API is the truth.

**If you are the sender.** Write the event to an outbox in the same transaction as the business change and let a worker deliver it. Sign as above, with the timestamp inside the signed content. Retry with exponential backoff and jitter, cap the attempts, disable the endpoint after sustained failure and tell its owner, and offer manual redelivery and an events API. Validate receiver URLs (HTTPS only, no private address ranges) to prevent server-side request forgery, do not follow redirects, and use timeouts of a few seconds.

## Example: HMAC verification in Java (Standard Webhooks format)

```java
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class WebhookSignatureVerifier {

    private static final Duration TOLERANCE = Duration.ofMinutes(5);
    private static final String SECRET_PREFIX = "whsec_";

    private final byte[] secret;

    public WebhookSignatureVerifier(String secretWithPrefix) {
        String secretBase64 = secretWithPrefix.startsWith(SECRET_PREFIX)
                ? secretWithPrefix.substring(SECRET_PREFIX.length())
                : secretWithPrefix;
        this.secret = Base64.getDecoder().decode(secretBase64);
    }

    public boolean isValid(String webhookId, String webhookTimestamp, String webhookSignature, byte[] rawBody, Instant now) {
        long epochSeconds;
        try {
            epochSeconds = Long.parseLong(webhookTimestamp);
        } catch (NumberFormatException exception) {
            return false;
        }
        if (Duration.between(Instant.ofEpochSecond(epochSeconds), now).abs().compareTo(TOLERANCE) > 0) {
            return false;
        }
        byte[] expected = hmacSha256(webhookId + "." + webhookTimestamp + ".", rawBody);
        for (String candidate : webhookSignature.split(" ")) {
            String[] versionAndValue = candidate.split(",", 2);
            if (versionAndValue.length == 2 && versionAndValue[0].equals("v1")) {
                byte[] provided;
                try {
                    provided = Base64.getDecoder().decode(versionAndValue[1]);
                } catch (IllegalArgumentException exception) {
                    continue;
                }
                if (MessageDigest.isEqual(expected, provided)) {
                    return true;
                }
            }
        }
        return false;
    }

    private byte[] hmacSha256(String signedContentPrefix, byte[] rawBody) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            mac.update(signedContentPrefix.getBytes(StandardCharsets.UTF_8));
            return mac.doFinal(rawBody);
        } catch (NoSuchAlgorithmException | InvalidKeyException exception) {
            throw new IllegalStateException("HmacSHA256 is mandatory in every JDK", exception);
        }
    }
}
```

Three details carry the security. The signed content is `id.timestamp.body`, so neither the body nor the timestamp can be swapped without invalidating the signature; `MessageDigest.isEqual` takes the same time whether the first or the last byte differs, so an attacker cannot forge a signature byte by byte from response times; and the body is `byte[]` straight from the request, never a re-serialised object. The loop over space-separated `v1,...` entries is what allows two secrets to be live during a rotation. Tested with a locally signed payload: the genuine delivery verifies, a one-character change to the body fails, a timestamp ten minutes old fails, and malformed timestamp or base64 values fail without an exception.

## Example: the receiver's processing flow

```text
sender --POST /webhooks/payments--> verify signature and timestamp
                                        |  invalid -> 400, nothing stored
                                        v
                               INSERT event id ... ON CONFLICT DO NOTHING
                                        |  duplicate -> 200, nothing else
                                        v
                               stored as 'received' -> 200 within milliseconds
                                        |
                           worker: claim, fetch current object from the sender's API,
                                   apply idempotently, mark 'processed'
                                        |  after N failures -> 'dead', alert, manual replay
```

The request handler in Spring MVC takes the raw bytes and does nothing slow:

```java
import java.time.Instant;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PaymentWebhookController {

    private final WebhookSignatureVerifier verifier;
    private final WebhookEventRepository webhookEventRepository;

    public PaymentWebhookController(WebhookSignatureVerifier verifier, WebhookEventRepository webhookEventRepository) {
        this.verifier = verifier;
        this.webhookEventRepository = webhookEventRepository;
    }

    @PostMapping(path = "/webhooks/payments", consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
            @RequestHeader("webhook-id") String webhookId,
            @RequestHeader("webhook-timestamp") String webhookTimestamp,
            @RequestHeader("webhook-signature") String webhookSignature,
            @RequestBody byte[] rawBody) {
        if (!verifier.isValid(webhookId, webhookTimestamp, webhookSignature, rawBody, Instant.now())) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST).build();
        }
        webhookEventRepository.insertIfAbsent(webhookId, rawBody);
        return ResponseEntity.ok().build();
    }
}
```

`insertIfAbsent` is one statement, and the worker claims rows without blocking other workers:

```sql
INSERT INTO webhook_event (id, received_at, payload, status)
VALUES (?, now(), ?, 'received')
ON CONFLICT (id) DO NOTHING;

SELECT id, payload FROM webhook_event
WHERE status = 'received'
ORDER BY received_at
FOR UPDATE SKIP LOCKED
LIMIT 10;
```

Each claimed event is processed in its own transaction that also updates `status` and `attempts`; a row that reaches the attempt limit becomes `dead` and stays, payload and all, until a human replays it by setting it back to `received`.

## Pitfalls

- Verifying over a re-serialised body. `@RequestBody Map` followed by `objectMapper.writeValueAsBytes(...)` changes key order, whitespace, unicode escapes or number formatting, and the signature fails for some events only. Take `byte[]` or read the servlet input stream.
- `String.equals` or `Arrays.equals` on signatures. Both return at the first differing byte; use `MessageDigest.isEqual`.
- No timestamp check, or a tolerance of hours. A captured delivery can be replayed for as long as the window allows. Five minutes, and clocks synchronised with NTP.
- Processing on the request thread. The sender times out at ten seconds, retries, and your logs show two successes for one event.
- Deduplicating in memory or after processing. Restarts and multiple instances let duplicates through; the unique constraint has to come before the work.
- Trusting payload state and order. A `payment.succeeded` that arrives after `payment.refunded` flips the state back. Fetch the current object, or compare versions.
- Swallowing exceptions to always return 200 without a dead-letter store. The sender never retries, and the event is gone.
- Rotating the secret by replacing it. Every in-flight delivery fails; accept both secrets during the rotation, which the multi-signature header exists for.
- Leaving the endpoint behind session-based security. CSRF protection and login redirects break it; the signature is its authentication, so exempt the path from both and require nothing else.
- On the sending side: calling user-supplied URLs without SSRF protection, following redirects, or waiting without a timeout.

## Check yourself

1. Why must the signature be computed over the raw request bytes, and name two ways a framework can change those bytes before your code sees them.
2. The sender retries after a timeout and you ship the same order twice. Which two layers should have stopped it, and in which order do they run?
3. `invoice.paid` and `invoice.voided` for the same invoice arrive in reverse order. Describe two designs that still end in the right state.
4. Where does an event go after its fifth failed processing attempt, who finds out, and how is it replayed?

## Go deeper

- [Stripe docs: Webhooks](https://docs.stripe.com/webhooks) · the best-practices section covers idempotency, ordering, quick responses and signature verification from a sender that has seen every receiver mistake.
- [Standard Webhooks](https://www.standardwebhooks.com/) and [the specification](https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md) · the header format implemented above, with reference libraries in several languages.
- [GitHub: Validating webhook deliveries](https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries) and [Best practices for using webhooks](https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks) · the `X-Hub-Signature-256` scheme and the ten-second rule.
- [RFC 2104: HMAC](https://www.rfc-editor.org/rfc/rfc2104.html) · what you are computing, in four pages.
- [Java: `MessageDigest.isEqual`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html) · the constant-time comparison and why it exists.
- [OWASP: Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) · for the sending side, where receivers choose the URL.

---

Part of [Web & HTTP](../README.md) · item 9.6
