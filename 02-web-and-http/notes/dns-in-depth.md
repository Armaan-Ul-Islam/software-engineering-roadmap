# DNS in depth: resolution, records, TTLs and negative caching

> **In one sentence:** DNS is a distributed, heavily cached tree of delegations; every answer you see is a copy whose remaining lifetime (TTL) depends on who cached it and when, which is why "it works for me but not for you" is the normal failure mode.

**Why it matters:** DNS is behind most migration incidents ("we switched the IP an hour ago and half the users still hit the old server"), a surprising number of Java connectivity bugs (the JVM caches lookups on its own), and the classic trap of querying a record before you create it and caching the negative answer. `dig` shows you exactly which copy you are looking at.

## The idea

**The resolution path.** Your program calls the **stub resolver** in the operating system (`/etc/resolv.conf` on Linux, `scutil --dns` shows it on macOS). The stub forwards to a **recursive resolver** (your ISP, `1.1.1.1`, `8.8.8.8`, or one inside your cloud VPC). If the recursive resolver has no cached answer it walks the tree: a **root server** says who serves `com.`, a **TLD server** says who serves `example.com.`, and the **authoritative server** for `example.com.` gives the final answer. Each step is a delegation expressed with `NS` records, and the TLD includes the IP addresses of the name servers (glue) so the walk does not need another lookup to find them.

**Caching and TTL.** Every record carries a TTL in seconds set by the zone owner. The authoritative server always returns the full TTL; every cache in between returns what is left. Caches exist at every layer: resolver, OS, browser, and application runtime. The JVM is the one backend developers forget: `InetAddress` caches successful lookups for 30 seconds by default and failed ones for 10 seconds (`networkaddress.cache.ttl` and `networkaddress.cache.negative.ttl` in `java.security`). Note also that an open connection pool does not care about DNS at all; it keeps talking to the IP it connected to until the connection closes.

**Record types that matter.**

| Type | Maps a name to | Notes |
|---|---|---|
| `A` / `AAAA` | an IPv4 / IPv6 address | Several of each is normal; clients pick one. |
| `CNAME` | another name | The resolver restarts the query with the target. A name with a `CNAME` may hold no other records. |
| `NS` | the name servers for a zone | This is the delegation itself. |
| `SOA` | the zone's metadata | Serial, refresh/retry/expire for secondaries, and the **minimum** field, which is the negative-cache TTL. |
| `MX` | mail servers, with priority | `MX 0 .` (the null MX) means "this domain receives no mail". |
| `TXT` | free text | SPF, DKIM, DMARC, and the ownership proofs every SaaS asks for. |
| `SRV` | host and port for a service | `_ldap._tcp.example.com`; rare on the web, common in internal infrastructure. |

**Why the apex cannot be a CNAME.** The apex (`example.com` itself) must carry `SOA` and `NS` records, and the rules (RFC 1034 section 3.6.2) say a `CNAME` must be the only record at its name. So `example.com CNAME lb.cloudprovider.net` is illegal, and most servers refuse to load the zone. Providers work around it with `ALIAS`/`ANAME` records or "CNAME flattening": the authoritative server resolves the target itself and returns plain `A` records. `www.example.com` is not the apex, so it can be a `CNAME`.

**Negative caching.** "No such name" (`NXDOMAIN`) and "name exists but has no record of that type" (`NODATA`) are cached too, for `min(SOA TTL, SOA minimum)` (RFC 2308). If you query a record before you create it, every resolver that saw the question remembers the "no" for that long.

## Example: reading `dig`

```bash
dig example.com
```

```text
;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 22077
;; flags: qr rd ra ad; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1

;; QUESTION SECTION:
;example.com.                   IN      A

;; ANSWER SECTION:
example.com.            278     IN      A       172.66.147.243
example.com.            278     IN      A       104.20.23.154

;; Query time: 76 msec
;; SERVER: 8.8.8.8#53(8.8.8.8)
```

Flags: `rd` (recursion desired) and `ra` (recursion available) mean a recursive resolver answered; `aa` (authoritative answer) is absent, so this is a cached copy. `278` is the remaining TTL; the zone's value is 300, as the authoritative server shows below. The same record, at the same moment, from two other caches:

```text
$ dig example.com A @1.1.1.1 +noall +answer
example.com.            158     IN      A       172.66.147.243
$ dig @elliott.ns.cloudflare.com example.com A +noall +answer
example.com.            300     IN      A       104.20.23.154
```

Three resolvers, three TTLs. Change the record now and `1.1.1.1` users see it within 158 seconds, `8.8.8.8` users within 278, and the slowest resolver within 300. "DNS propagation" is just these caches expiring.

## Example: the whole walk with `dig +trace`

`+trace` makes `dig` play recursive resolver: it asks a root server, follows the referral to the TLD, and follows that to the authoritative server. DNSSEC signature lines and most of the thirteen identical `NS` lines are removed here.

```bash
dig +trace example.com @1.1.1.1
```

```text
.                       518400  IN      NS      a.root-servers.net.
;; Received 525 bytes from 1.1.1.1#53(1.1.1.1) in 444 ms

com.                    172800  IN      NS      a.gtld-servers.net.
;; Received 1171 bytes from 2001:7fd::1#53(k.root-servers.net) in 94 ms

example.com.            172800  IN      NS      hera.ns.cloudflare.com.
example.com.            172800  IN      NS      elliott.ns.cloudflare.com.
;; Received 506 bytes from 2001:502:1ca1::30#53(e.gtld-servers.net) in 227 ms

example.com.            300     IN      A       172.66.147.243
example.com.            300     IN      A       104.20.23.154
;; Received 179 bytes from 2606:4700:50::adf5:3aa2#53(hera.ns.cloudflare.com) in 27 ms
```

Four hops, about 800 ms if nothing were cached; the root and TLD referrals carry two-day TTLs (172800), so a busy resolver normally performs only the last hop. Use `+trace` when a record looks right at the authoritative server but wrong through your resolver: it shows whether the delegation (`NS` at the parent) points where you think it does.

## Example: a CNAME chain and a negative answer

```text
$ dig www.github.com +noall +answer
www.github.com.         3144    IN      CNAME   github.com.
github.com.             60      IN      A       20.205.243.166

$ dig @1.1.1.1 doesnotexist-7f3a9.iana.org A
;; ->>HEADER<<- opcode: QUERY, status: NXDOMAIN, id: 28236
;; AUTHORITY SECTION:
iana.org.   3600  IN  SOA  sns.dns.icann.org. noc.dns.icann.org. 2026102201 7200 3600 1209600 3600
```

The `CNAME` answer contains both the alias and the final `A` record, with different TTLs: the alias is cached for 52 minutes, the address it points to for 60 seconds. The `NXDOMAIN` response carries no answer but an `SOA` in the authority section; its last field (3600) and the record's TTL (3600) are both one hour, so the resolver will say "no such name" for an hour without asking again.

## Pitfalls

- Querying before creating. You test `api.example.com`, it does not exist yet, and now your resolver caches `NXDOMAIN` for the SOA minimum (often 1 to 24 hours). Create first, then query, or query the authoritative server directly with `@`.
- Lowering the TTL at the moment of the migration. Caches already hold the old record with the old TTL. Lower it at least one old-TTL before the change, then raise it again afterwards.
- Trusting `dig` to show what your application sees. `dig` talks straight to the resolver in `/etc/resolv.conf`; it ignores `/etc/hosts` and the OS cache. Use `getent hosts example.com` (Linux) or `dscacheutil -q host -a name example.com` (macOS) to go through the same path as your code, and flush with `resolvectl flush-caches` or `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.
- The JVM cache. A failover that updates DNS is invisible to a running JVM for up to 30 seconds, and forever to any connection already in a pool. Design failover around load balancers or health checks, not TTLs of a few seconds.
- Reading `status: NOERROR` with zero answers as success. That is `NODATA`: the name exists but has no record of the type you asked for (a common result when you query `A` for a name that only has `CNAME` or `AAAA`).

## Check yourself

1. The authoritative TTL is 300 seconds, you change the record at 12:00:00, and a user's resolver last fetched it at 11:59:50. At what time does that user see the change, and what else between the resolver and the user could delay it further?
2. Why is `example.com CNAME www.example.com` rejected while `www.example.com CNAME example.com` is fine?
3. A colleague says "I ran `dig` and it returns the new IP, but the Java service still calls the old one". Give two independent explanations.
4. You see `status: NXDOMAIN` with an `SOA` whose minimum field is 86400. What has just happened to every client of that resolver, and how do you check the record without being affected?

## Go deeper

- [How DNS works](https://howdns.works/) · the resolution path as a comic; ten minutes well spent.
- [Cloudflare: DNS records](https://www.cloudflare.com/learning/dns/dns-records/) · one page per record type, accurate and short.
- [Mess with DNS](https://messwithdns.net/) · a real subdomain you can create records in and watch resolvers react; the best way to make TTLs concrete.
- [RFC 2308: Negative Caching of DNS Queries](https://www.rfc-editor.org/rfc/rfc2308.html) · the rule for how long a "no" is cached, in five readable pages.
- [Java 21: InetAddress caching](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/InetAddress.html) · the "InetAddress Caching" section documents the two properties and their defaults.
- [Julia Evans: How DNS works (comics)](https://wizardzines.com/comics/) · the debugging mindset, one panel at a time.

---

Part of [Web & HTTP](../README.md) · items 2.1, 2.2, 2.4
