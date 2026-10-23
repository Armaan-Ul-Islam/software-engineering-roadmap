# Threat modelling with STRIDE in twenty minutes

> **In one sentence:** Threat modelling is drawing where data flows and where trust changes in one feature, asking "what can go wrong here?" for each element with the six STRIDE categories as prompts, and turning the answers into ordinary backlog items before the code exists.

**Why it matters:** The expensive vulnerabilities are design decisions, not typos: a reset link built from the `Host` header, a token that never expires, an export endpoint nobody rate-limited. No scanner finds them, and a penetration test finds them a year late. Twenty minutes with a whiteboard at the start of a feature catches most of them, and senior interviews increasingly ask you to do exactly that out loud.

## The idea

Three words carry the whole method.

- **Asset**: anything worth protecting. Accounts, personal data, money, the ability to send email in your name, and availability itself.
- **Trust boundary**: a line across which the level of trust changes. Browser to server, server to database, your network to a third-party API, one tenant to another. Attacks live at boundaries, because that is where data arrives from somewhere less trusted.
- **Attack surface**: every point where an outsider can put data into the system. Endpoints, headers, cookies, file uploads, webhooks, emails you parse, queue messages you consume.

Three principles decide what a good mitigation looks like: **defence in depth** (no single control stands alone), **least privilege** (each component can do only what its job needs) and **fail secure** (an exception or a timeout ends in denial, never in access).

The method has two tools. The first is a **data-flow diagram** with four element types and dashed lines for trust boundaries:

| Element | Drawn as | Examples |
|---|---|---|
| External entity | box | browser, mobile app, third-party API, another team's service |
| Process | rounded box or circle | your Spring application, a worker, a function |
| Data store | open-ended box or two parallel lines | database table, cache, queue, log files, object storage |
| Data flow | labelled arrow | HTTP request, SQL, SMTP, the message on a topic |

The second is **STRIDE**, six categories that each break one security property. Use them as prompts, not as a form to fill in:

| Letter | Threat | Property broken | The question to ask |
|---|---|---|---|
| S | Spoofing | authentication | Can someone pretend to be another user, service or sender? |
| T | Tampering | integrity | Can data be changed in transit or at rest without detection? |
| R | Repudiation | non-repudiation | Can someone deny an action because we cannot prove it? |
| I | Information disclosure | confidentiality | Who can see data they should not? |
| D | Denial of service | availability | Can someone exhaust or block this element? |
| E | Elevation of privilege | authorization | Can someone do more than their role allows? |

Not every letter applies to every element, which is what makes the exercise fast. Processes get all six. Data stores get tampering, information disclosure and denial of service (and repudiation if they hold logs). Data flows get tampering, information disclosure and denial of service. External entities get spoofing and repudiation.

Prioritise with two questions rather than a scoring scheme: can an unauthenticated user on the internet reach it, and what is the worst outcome (account takeover, data of other tenants, an outage)? Reachable and bad is High. Everything else is Medium or Low. Then write each High as a backlog item with acceptance criteria that a test can check. A threat model that lives only in a document changes nothing; one that produced three tickets did its job.

## Example: a threat model for "password reset by email"

The feature: a user types their email address, receives a link, follows it and sets a new password. Five minutes of drawing gives this:

```text
      internet          :         our platform                    :     third party
                        :                                         :
 +--------------+       :   +-------------------+        +------+ :
 |   Browser    |---1---:-->|                   |---2--->|users | :
 |   (anyone)   |<--4---:---|   Reset service   |        | DB   | :
 +--------------+       :   |   (Spring app)    |---3--->|tokens| :
        ^               :   +-------------------+        +------+ :
        |               :             | 5                         :   +----------------+
        |               :             +---------------------------:-->| Email provider |
        |               :                                         :   +----------------+
        | 6             :                                         :            |
        +<--------------:-----------------------------------------:------------+
        |               :                                         :
        |          7    :   +-------------------+                 :
        +---------------:-->|   Reset service   | 8               :
                        :   +-------------------+                 :
```

The dotted columns are trust boundaries. The flows carry: (1) `POST /password-reset` with the address; (2) look up the account; (3) store a token for it; (4) the response; (5) the email, with the link carrying the token, through the provider's API; (6) the email reaching the inbox; (7) `POST /password-reset/confirm` with the token and the new password; (8) verify the token and set the password.

Ten minutes of STRIDE per element produces a table like this (abridged):

| Element | Threat | What goes wrong | Mitigation | Priority |
|---|---|---|---|---|
| Flow 1 | Spoofing | Anyone can request a reset for any address | Accepted by design: the token only ever goes to the registered address | Low |
| Reset service | Information disclosure | A different message, status code or response time for unknown addresses tells an attacker who has an account | Same response for both cases; send the email from a background job so timing does not differ | Medium |
| Reset service | Denial of service | A script floods a victim's inbox and burns your email quota | Rate limit per address and per IP; queue the sending | Medium |
| Reset service | Tampering | The link is built from the request's `Host` header, so a request with `Host: evil.example` makes the victim receive a link to the attacker's site, which collects the token | Build links from a configured base URL, never from request headers | High |
| Tokens store | Information disclosure | A database dump or a read-only SQL injection yields live tokens | Store only the SHA-256 of the token; generate 32 bytes from `SecureRandom` | High |
| Flow 7 | Elevation of privilege | A token can be reused, never expires, or is not bound to an account | Single use, 15-minute expiry, bound to the account; all outstanding tokens for the account invalidated on success | High |
| Confirm page | Information disclosure | The token sits in the URL and leaks through `Referer` to any third-party script or analytics on the page | No third-party scripts on that page; `Referrer-Policy: no-referrer` | Medium |
| Reset service | Repudiation | A user disputes a password change | Audit log of request and completion with time, IP and account id (never the token); email "your password was changed" | Medium |
| Whole flow | Elevation of privilege | An attacker already inside the account keeps their session after the victim resets | Invalidate every session and refresh token on reset | High |

The last five minutes turn the Highs into tickets. One of them:

```text
Title: Reset tokens are random, hashed at rest, single-use and expire after 15 minutes
Why:   a leaked or guessed token is an account takeover
Acceptance criteria:
  1. The token is 32 bytes from SecureRandom, sent base64url-encoded.
  2. Only the SHA-256 of the token is stored, with account id, created_at and used_at.
  3. Confirm rejects a token older than 15 minutes or one whose used_at is set.
  4. A successful reset marks every outstanding token for the account as used
     and invalidates all of the account's sessions.
  5. Tests cover each rejection path.
```

The agenda that fits in a sprint:

1. Minutes 0 to 5: draw. One process per deployable, one store per database or table group, every external party, every flow labelled with what it carries. Draw the boundaries.
2. Minutes 5 to 15: STRIDE per element. Only the applicable letters; one line per threat; no fixes yet.
3. Minutes 15 to 20: prioritise and write the High tickets. Mediums go to the backlog, Lows stay in the table.
4. Afterwards: store the diagram and the table next to the code (for example `docs/threat-models/password-reset.md`) and revisit them when a flow or a boundary changes.

## Pitfalls

- Modelling the whole system. It never finishes and nobody reads it. One feature, one diagram, one page.
- Forgetting the operator paths. Admin tools, support consoles, CI pipelines and log files are flows and stores too; logs are where tokens and personal data leak most often.
- Trusting the "internal network" boundary. A service that trusts every caller inside the VPC is one server-side request forgery away from compromise (see item 2.9).
- Stopping at "it is behind authentication". Every user is an authenticated attacker against every other user; elevation of privilege between accounts is the common case.
- Spending the meeting on scoring. If two people disagree whether something is High or Medium, make it High and move on.

## Check yourself

1. In the diagram above, which elements get all six STRIDE letters and which get only two? Why does a data store not get Spoofing?
2. Why is "the response reveals whether the address exists" an information disclosure threat even though email addresses are not secret?
3. The team proposes storing reset tokens encrypted instead of hashed. What does hashing give you here that encryption does not?
4. A new requirement adds "reset by SMS". Which parts of the diagram change, and which threats appear that the email version did not have?

## Go deeper

- [OWASP: Threat Modeling](https://owasp.org/www-community/Threat_Modeling) · the four-question framing and the vocabulary used here.
- [OWASP: Threat Modeling Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Threat_Modeling_Cheat_Sheet.html) · the practical checklist, including how to draw the diagram.
- [Microsoft: STRIDE threats](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats) · each category with example threats and mitigations.
- [Threat Modeling Manifesto](https://www.threatmodelingmanifesto.org/) · the values behind the method, one page.
- [OWASP: Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) · compare your table for the example with the reference treatment.
- [OWASP Threat Dragon](https://owasp.org/www-project-threat-dragon/) · a free tool for drawing the diagram and recording STRIDE threats, if a whiteboard photo is not enough.

---

Part of [Security](../README.md) · items 1.1, 1.2
