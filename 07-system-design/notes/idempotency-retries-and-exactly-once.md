# Idempotency, retries and "exactly once"

> **In one sentence:** Because a lost acknowledgement is indistinguishable from a lost request, any reliable system must retry, so every operation that can be retried must be safe to repeat; exactly-once delivery is impossible, but exactly-once *processing* is achievable by making the effect and the record of having done it one atomic step.

**Why it matters:** Double charges, duplicate emails and twice-shipped orders are not exotic failures; they are what at-least-once delivery does by design the first time a network hiccup lands on a payment call. Retries without idempotency create those bugs, and retries without limits turn a brief dependency slowdown into a self-inflicted outage.

## The idea

**Delivery semantics.** A sender that gets no acknowledgement has two choices. Give up: at-most-once, the message may be lost. Send again: at-least-once, the message may be processed twice. There is no third option, because the receiver may have processed the message and the acknowledgement may have been lost, and the sender cannot tell that case apart from the message never arriving. "Exactly-once delivery" over a network is therefore impossible. What systems actually implement is exactly-once processing: deliver at least once, and make the receiver recognise and ignore repeats. Kafka's idempotent producer and transactions do exactly this inside the broker; the moment the effect leaves Kafka (a database row, an HTTP call, an email), the receiver has to do it.

**Idempotency keys for APIs.** The client generates a unique key per logical operation (a UUID is fine) and sends it with the request, conventionally in an `Idempotency-Key` header. The server stores the key with a fingerprint of the request and, once finished, the response; a repeat with the same key returns the stored response without redoing the work. The details decide whether it works:

- Storage: the same database as the effect, so that "the payment row exists" and "the key is marked complete" commit together. A key store in Redis with a TTL is fine for cheap operations but can forget a key before the client stops retrying.
- Scope: unique per client or tenant, not globally; two customers may both send key `1`. Include the endpoint if the same client reuses keys across operations.
- Expiry: longer than the client's longest retry horizon. Stripe keeps keys for 24 hours; a batch job that retries overnight needs more.
- Mismatch: the same key with a different body is a client bug; reject it (the IETF draft suggests 422) rather than returning a response for a request the client did not make.
- Concurrent duplicates: two requests with the same key in flight at once. The first to insert the key row wins; the second sees the row in state `in_progress` and must wait or answer 409 Conflict with a `Retry-After`. Never let both proceed.

**Idempotent consumers.** A message consumer deduplicates the same way: the message carries a stable identifier assigned by the producer (not by the broker on redelivery), and the consumer inserts it into a `processed_message` table in the same transaction as its business writes. A unique-constraint violation means "already done, acknowledge and move on". Alternatives that need no table: operations that are naturally idempotent (`SET status = 'shipped'` rather than `increment shipped_count`), or version checks (ignore an event older than the row's current version). Retention of the deduplication table must outlast the broker's redelivery window.

**Retries done properly.** Retry only what is idempotent or carries a key, only on errors that a retry can fix (timeouts, connection resets, 503, 429 with `Retry-After`), never on 4xx or business failures. Space the attempts with exponential backoff and jitter: with full jitter, `sleep = random(0, min(cap, base × 2^attempt))`, so that a thousand clients that failed at the same moment do not all retry at the same moment. Cap the attempts (three is a common default) and the total time, and make the total fit inside the caller's own deadline.

**Retry storms and budgets.** Retries multiply load exactly when the dependency is struggling. If each of four layers retries three times, one user request can become 81 calls at the bottom, and a dependency that was 20 percent over capacity is now hopelessly over it and cannot recover. Defences: retry at one layer only (usually the one closest to the user that can judge the failure), keep a retry budget (for example, retries may be at most 10 percent of a client's requests over a window; beyond that, failures are returned immediately), and let a circuit breaker stop the retries entirely when the dependency is clearly down (see item 4.2).

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class Backoff {

    public static Duration fullJitter(int attempt, Duration base, Duration cap) {
        long exponential = Math.min(cap.toMillis(), base.toMillis() << Math.min(attempt, 30));
        return Duration.ofMillis(ThreadLocalRandom.current().nextLong(exponential + 1));
    }
}
```

## Example: an idempotency-key flow for a payment endpoint

```sql
CREATE TABLE idempotency_key (
    tenant_id      bigint      NOT NULL,
    key            text        NOT NULL,
    request_hash   bytea       NOT NULL,
    status         text        NOT NULL CHECK (status IN ('in_progress', 'completed')),
    response_code  int,
    response_body  jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, key)
);
```

1. The client generates key `K`, sends `POST /payments` with `Idempotency-Key: K` and the body `{amount: 100, currency: "EUR", source: "card_42"}`, and will resend the identical request on any timeout.
2. The server claims the key in its own short transaction: `INSERT INTO idempotency_key (tenant_id, key, request_hash, status) VALUES ($1, $2, $3, 'in_progress') ON CONFLICT (tenant_id, key) DO NOTHING RETURNING key;`
   2.1. A row comes back: this request owns the key. Continue.
   2.2. No row comes back: load the existing row. A different `request_hash` means 422. Status `completed` means return the stored `response_code` and `response_body`. Status `in_progress` means another request is working; return 409 with `Retry-After: 1`.
3. The server calls the card processor, passing `K` (or a value derived from it) as the processor's own idempotency key, so that a retry of this outbound call cannot charge twice either.
4. In one transaction the server inserts the `payment` row, updates the key row to `completed` with code 201 and the response body, and commits. If this commit fails, nothing is recorded and the client's retry will redo step 3 safely because of the processor-side key.
5. Respond 201. Any later request with `K` hits step 2.2 and gets the same 201 without touching the processor.
6. Crash between steps 3 and 4: the key stays `in_progress` forever and every retry gets 409. Recovery: when a retry finds an `in_progress` row older than a threshold, take it over (`UPDATE ... WHERE status = 'in_progress' AND created_at < ...` returning the row), ask the processor for the outcome of `K`, and finish step 4. This is the "recovery point" idea from the Brandur article: each step after an external call records where it got to.

What the client sees: at most one charge, the same response for every retry, and a 409 only during the seconds when the original is still running.

## Pitfalls

- Generating the idempotency key on the server. The client's retry then arrives with no key, and the server has no way to link it to the first attempt. The key must come from the party that retries.
- Keys derived from the payload. Two legitimate identical orders ("buy one coffee" twice) collide; use a key per attempt of a logical operation, not a hash of its contents.
- Storing the key after the effect, in a different transaction or store. A crash in between leaves an effect with no key, and the retry repeats it.
- Deduplicating on broker message IDs. Redelivery may assign a new ID; deduplicate on an identifier the producer put in the payload.
- Retries at every layer. The client library, the service mesh, the gateway and the application each retry three times, and nobody notices until the 81× day.
- Backoff without jitter. Synchronised retry waves arrive at exactly 1 s, 2 s and 4 s after the failure, each one a new spike.

## Check yourself

1. Why can no protocol guarantee exactly-once delivery, and what exactly does Kafka's exactly-once feature promise instead?
2. In the payment flow, what goes wrong if the key row is written in the same transaction as step 4 and nowhere else?
3. Two requests with the same key arrive 5 ms apart. Walk through what each one experiences at step 2.
4. A dependency is down for 30 seconds. Compare what happens with (a) three retries at each of four layers and no backoff, and (b) one retrying layer with full jitter and a 10 percent retry budget.

## Go deeper

- [You Cannot Have Exactly-Once Delivery](https://bravenewgeek.com/you-cannot-have-exactly-once-delivery/) · the impossibility argument in plain words, and what to do instead.
- [Stripe: Designing robust and predictable APIs with idempotency](https://stripe.com/blog/idempotency) · how a payment API defines keys, retries and error classes.
- [Brandur: Implementing Stripe-like Idempotency Keys in Postgres](https://brandur.org/idempotency-keys) · the full server-side design with recovery points, in SQL.
- [The Idempotency-Key HTTP Header Field (IETF draft)](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/) · the header, the 422 and 409 responses, and the fingerprint rule.
- [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/) · why retries are selfish and how budgets keep them honest.
- [Google SRE Book: Handling Overload](https://sre.google/sre-book/handling-overload/) · the per-client retry budget and why retries must be limited at the client.

---

Part of [System Design](../README.md) · items 3.8, 4.1, 4.4
