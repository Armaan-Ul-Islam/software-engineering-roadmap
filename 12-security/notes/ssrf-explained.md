# Server-side request forgery

> **In one sentence:** SSRF is tricking your server into making an HTTP request to an address of the attacker's choosing, and because your server sits inside the network and often next to a cloud metadata endpoint, "an address of the attacker's choosing" usually means "something only your server can reach".

**Why it matters:** Every webhook, URL importer, link previewer, PDF renderer and "fetch my avatar from this URL" feature is an outbound HTTP client fed by user input. In a cloud account, one such feature pointed at `169.254.169.254` hands over the instance's credentials; the 2019 Capital One breach was exactly this. SSRF has had its own OWASP Top 10 category since 2021, and it is the vulnerability that turns "internal, so not exposed" into an empty promise.

## The idea

The server is trusted by things the user is not: the private network, the database's admin interface, the Kubernetes API, Redis, Elasticsearch, and the cloud provider's metadata service that every instance can reach at a well-known link-local address without any credentials. When the server fetches a URL supplied by a user, the user borrows that trust. The response may be returned to them (full SSRF), or they may only learn whether the request succeeded or how long it took (blind SSRF), which is still enough to map the network and trigger side effects.

| Target | Why it matters |
|---|---|
| Cloud metadata endpoint (`169.254.169.254` on AWS and Azure, `metadata.google.internal` on GCP) | Returns temporary credentials for the instance's role: the keys to whatever the server may do in the cloud account |
| Internal admin interfaces | Databases, brokers, dashboards and actuator endpoints that trust the network and have no authentication |
| `localhost` | The application's own management port, or sibling containers in the pod |

What makes the defence hard is that "is this URL internal?" is a harder question than it looks:

- The **hostname** is not the address. `attacker.example` can resolve to `10.0.0.5`. You have to resolve it and check every address returned.
- **DNS rebinding** separates the check from the use. The attacker's DNS answers with a public address when you validate (with a very short TTL) and with an internal one when the HTTP client resolves again a moment later. The connection must use the addresses you validated.
- **Redirects** do the same with HTTP. The validated URL returns `302 Location: http://169.254.169.254/...`, and a client that follows redirects automatically fetches it for you. Redirects must be disabled, or every hop validated.
- **Address spelling** is flexible. `127.0.0.1` is also `2130706433`, `0x7f000001`, `127.1` and `[::ffff:127.0.0.1]`. Parse with `java.net.URI`, resolve with `InetAddress`, and classify the resulting bytes rather than matching strings.
- **The URL grammar** has traps: in `https://trusted.example@169.254.169.254/` the trusted name is the user-info part, not the host.

So the defence is layered:

1. **Allow-list where you can.** A payment provider's callback or a fixed set of partner domains needs no general-purpose fetcher. Compare the parsed host against the list.
2. **Validate the resolved addresses** when the destination is genuinely user-chosen, rejecting loopback, link-local, private, unique-local, multicast and the unspecified address. Then **pin the connection** to those addresses: HTTP clients that let you supply the resolver (OkHttp's `Dns`, Apache HttpClient's `DnsResolver`) connect to what you validated, which closes the rebinding window.
3. **Disable automatic redirects** and treat a redirect as a new URL to validate, with a small hop limit.
4. **Harden the metadata service.** On AWS, require IMDSv2: the client must first `PUT` for a session token and send it in a header on every read, and the token response has a hop limit of one by default, so it does not survive the extra network hop of a bridged container. Azure requires a `Metadata: true` header and GCP a `Metadata-Flavor: Google` header, which defeats SSRF primitives that only control the URL. Give workloads narrow identities so that leaked credentials can do little.
5. **Control egress at the network.** Run URL fetchers and webhook senders in their own egress-restricted segment or behind a forward proxy that enforces the allow-list, block the metadata address from application subnets, and apply Kubernetes `NetworkPolicy` so a pod reaches only what it needs. This layer does not depend on your code being right.

## Example: what a webhook delivery service must check

A customer registers `https://hooks.customer.example/orders` and your service posts events there. The URL is user input, the sender runs inside your network, and the customer can change the URL or its DNS at any time, so validation happens at registration **and** at every delivery:

```java
import java.net.InetAddress;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.UnknownHostException;
import java.util.List;

public final class WebhookUrlValidator {

    public static List<InetAddress> validate(String rawUrl) throws UnknownHostException {
        URI uri;
        try {
            uri = new URI(rawUrl);
        } catch (URISyntaxException exception) {
            throw new IllegalArgumentException("malformed url");
        }
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("scheme must be https");
        }
        if (uri.getRawUserInfo() != null) {
            throw new IllegalArgumentException("credentials in the url are not allowed");
        }
        String host = uri.getHost();
        if (host == null) {
            throw new IllegalArgumentException("url has no parseable host");
        }
        if (uri.getPort() != -1 && uri.getPort() != 443) {
            throw new IllegalArgumentException("only port 443 is allowed");
        }
        List<InetAddress> addresses = List.of(InetAddress.getAllByName(host));
        for (InetAddress address : addresses) {
            if (!isPublic(address)) {
                throw new IllegalArgumentException(host + " resolves to a non-public address " + address.getHostAddress());
            }
        }
        return addresses;
    }

    static boolean isPublic(InetAddress address) {
        if (address.isAnyLocalAddress() || address.isLoopbackAddress() || address.isLinkLocalAddress()
                || address.isSiteLocalAddress() || address.isMulticastAddress()) {
            return false;
        }
        byte[] bytes = address.getAddress();
        boolean uniqueLocalIpv6 = bytes.length == 16 && (bytes[0] & 0xfe) == 0xfc;
        boolean carrierGradeNat = bytes.length == 4 && (bytes[0] & 0xff) == 100 && (bytes[1] & 0xc0) == 64;
        return !uniqueLocalIpv6 && !carrierGradeNat;
    }
}
```

Run against a few candidates (Java 25, abridged):

```text
REJECT  https://169.254.169.254/latest/meta-data/   resolves to a non-public address 169.254.169.254
REJECT  https://[::ffff:169.254.169.254]/           resolves to a non-public address 169.254.169.254
REJECT  https://2130706433/                         resolves to a non-public address 127.0.0.1
REJECT  https://[fd12::1]/                          resolves to a non-public address fd12:0:0:0:0:0:0:1
REJECT  https://user@example.com/                   credentials in the url are not allowed
REJECT  http://example.com/                         scheme must be https
OK      https://example.com/hooks                   [example.com/104.20.23.154, example.com/172.66.147.243, ...]
```

Note the third line: Java resolves the decimal form to `127.0.0.1` without complaint, which is why the check classifies resolved addresses instead of matching strings. `isSiteLocalAddress()` covers the three IPv4 private ranges; the two extra checks add IPv6 unique-local addresses and the carrier-grade NAT range, which Java does not classify. Extend the list for your environment (the ranges your VPN or service mesh uses, for instance).

The validator returns the addresses so the sender can pin them, and the sender itself is configured not to follow redirects and to give up quickly:

```java
HttpClient webhookClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

A `3xx` response is a failed delivery to log, not a location to follow. The JDK client cannot be pinned to pre-resolved addresses, so either deliver through an egress proxy that re-validates, or use a client with a pluggable resolver as described above. Finally, the delivery service runs with a network policy that allows outbound `443` to the internet and nothing to the VPC or the metadata address, so a validation bug stays a bug.

## Pitfalls

- Validating only at registration. The customer changes DNS afterwards, or the stored URL was never validated because it arrived through an import. Validate on every use.
- String matching the hostname. `localhost`, `127.0.0.1` and `169.254.169.254` are three of hundreds of spellings. Resolve and classify.
- Letting the HTTP client follow redirects. The validated URL is innocent; its `Location` header is not.
- Checking only the first resolved address. A name with one public and one private record passes a naive check, and the client may use either.
- Accepting any scheme. Libraries that handle `file:`, `ftp:` or `gopher:` turn an HTTP fetcher into a file reader or a raw socket. Allow `https` only (plus `http` if you must).
- Trusting the metadata service's defaults. IMDSv1 answers any `GET` from the instance; requiring IMDSv2 is an instance or account setting that someone has to switch on.
- Exposing Spring Boot Actuator on the application port without authentication. SSRF to `localhost:8080/actuator/env` or `/actuator/heapdump` from inside your own application is a classic chain.

## Check yourself

1. Why does validating a URL and then handing it to an ordinary HTTP client leave a window, and what are the two ways to close it?
2. What does IMDSv2 require that a plain `GET`-based SSRF cannot supply, and why does the hop limit matter for containers?
3. A link-preview feature only ever shows the user the page title. Argue whether it still needs the full defence.
4. Your validator rejects the string `169.254.169.254`. Write down three URLs that bypass it.

## Go deeper

- [PortSwigger: SSRF](https://portswigger.net/web-security/ssrf) · the attack variants with labs, including blind SSRF and bypasses of naive filters.
- [OWASP: SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) · the two cases (known destinations versus user-chosen) and the defence for each.
- [OWASP Top 10: A10 Server-Side Request Forgery](https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/) · the category description with the incident pattern.
- [AWS: Configure the Instance Metadata Service options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html) · how to require IMDSv2 and set the hop limit.

---

Part of [Security](../README.md) · item 2.9
