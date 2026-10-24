# URLs, URIs and percent-encoding

> **In one sentence:** A URL is five components (scheme, authority, path, query, fragment) that each allow a different set of characters, so "encoding a URL" is not one operation but one per component, and almost every URL bug is a string encoded with the wrong component's rules, the wrong number of times, or not at all.

**Why it matters:** A customer name with an ampersand that silently truncates a query, a `+` that is a space in one service and a plus in the next, a `%2F` in a path segment that Tomcat rejects with 400, and a `%2520` that turns into a 404 only in production: each costs an afternoon, and each is the same mistake, treating a URL as a string instead of a structure. The cure is one mental model and one habit: encode each piece with the rules of the component it goes into, before you concatenate, and never again afterwards.

## The idea

**Anatomy** (RFC 3986):

```text
https://api.example.com:8443/customers/42/orders?status=paid&sort=-createdAt#summary
\___/   \__________________/\___________________/ \_______________________/ \_____/
scheme        authority              path                    query          fragment
```

- Scheme and host are case-insensitive. The authority is `[userinfo@]host[:port]`; the port is omitted when it is the scheme's default (443 for `https`). IPv6 literals go in brackets: `https://[::1]:8443/`.
- The path is hierarchical: segments separated by `/`, with `.` and `..` segments resolved before the request is sent.
- The query is everything between `?` and `#`. The `key=value&key=value` shape comes from HTML forms, not from the URI grammar; the server decides how to read it.
- The fragment is never sent to the server. Browsers keep it for in-page anchors and client-side routing.
- URI versus URL: a URI identifies, a URL also locates (scheme plus authority). `urn:isbn:0-486-27557-4` is a URI that is not a URL. In Java the type to use is `java.net.URI` either way; `java.net.URL` has a problem you will meet below.

**Reserved and unreserved characters.** Unreserved characters (`A-Z a-z 0-9 - . _ ~`) are safe everywhere; encoding them is allowed but pointless. Reserved characters (`: / ? # [ ] @` and `! $ & ' ( ) * + , ; =`) have structural meaning in *some* component: `/` separates path segments, `?` starts the query, `#` the fragment, and `&` and `=` are the form convention inside the query. A reserved character is written as itself when it plays that role and percent-encoded when it is data in a component where it would be misread. Everything else (space, `"`, `<`, `>`, `\`, `{`, `|`, `}` and every non-ASCII character) is always encoded.

**Percent-encoding** writes each byte of the UTF-8 form as `%` plus two hex digits: `ø` is the bytes `C3 B8`, so `%C3%B8`; a space is `%20`. Hex case does not matter (`%c3` equals `%C3`). UTF-8 is the only sensible choice today (the WHATWG URL Standard uses it throughout); URLs encoded with a legacy charset are where mojibake in links comes from.

**Three different "encode" operations.** This is the part people miss:

| Operation | Space | `/` | `&` `=` `+` | Used for | Java |
|---|---|---|---|---|---|
| Path segment | `%20` | `%2F` | kept, they are legal in a segment | one segment between slashes | Spring `UriUtils.encodePathSegment`; JDK: `URLEncoder`, then `+` to `%20` |
| Query parameter (RFC 3986) | `%20` | kept | `%26` `%3D` `%2B` | one value in `key=value` | Spring `UriUtils.encodeQueryParam` |
| Form encoding (`application/x-www-form-urlencoded`) | `+` | `%2F` | `%26` `%3D` `%2B` | HTML form bodies, and by convention query strings | `java.net.URLEncoder` |

`URLEncoder`'s own documentation says it implements form encoding. That is why it produces `+` for a space, and why it also leaves `*` alone and encodes `~` as `%7E` (a 1990s quirk; harmless, but a sign that it is not RFC 3986). Servlet containers decode `+` as a space in *query parameters* because of the form convention; in a *path* a `+` is a literal plus. Decoders disagree the same way: `URLDecoder.decode("a+b")` gives `a b`, while `URI.getQuery()` on `?q=a+b` returns `q=a+b` untouched. Two services reading the same URL with different classes get different values.

**Normalisation** (RFC 3986 section 6) decides when two URLs name the same resource: lowercase the scheme and host, uppercase the hex digits of escapes, decode escaped unreserved characters (`%7E` to `~`), drop the default port, resolve dot segments. Beyond that it is application-specific: whether a trailing slash or the order of query parameters matters is your decision. `java.net.URI.normalize()` only resolves dot segments, and `URI.equals` ignores case in the scheme, host and escape hex digits but does not decode anything. Cache keys and allow-lists must normalise explicitly.

**Browsers parse differently from Java.** Browsers implement the WHATWG URL Standard, which accepts and repairs what users type. `java.net.URI` follows the older RFC 2396 strictly: it rejects spaces, `<`, `{` and non-ASCII hostnames (encode those first with `java.net.IDN.toASCII`, which turns `bücher.example` into `xn--bcher-kva.example`). "It works when I paste it into the browser" proves nothing about your client.

## Example: Java `URI` and `URLEncoder`, with output

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;

public class UrlEncodingDemo {

    static String pathSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    public static void main(String[] arguments) throws URISyntaxException {
        String customerName = "Smith & Sons/Oslo";
        String searchText = "price<100 øre";

        System.out.println(URLEncoder.encode(customerName, StandardCharsets.UTF_8));
        System.out.println(URLEncoder.encode(searchText, StandardCharsets.UTF_8));

        String concatenated = "https://api.example.com/customers/" + customerName + "/orders?q=" + searchText;
        try {
            URI.create(concatenated);
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        URI perComponent = new URI("https", "api.example.com", "/customers/" + customerName + "/orders", "q=" + searchText, null);
        System.out.println(perComponent.toASCIIString());

        URI correct = URI.create("https://api.example.com/customers/" + pathSegment(customerName)
                + "/orders?q=" + URLEncoder.encode(searchText, StandardCharsets.UTF_8));
        System.out.println(correct);
        System.out.println(correct.getRawPath() + "   " + correct.getPath());
        System.out.println(URLEncoder.encode(pathSegment(customerName), StandardCharsets.UTF_8));
        System.out.println(URI.create("HTTPS://Example.COM:443/a/./b/../c").normalize());
        System.out.println(URI.create("https://api.example.com/v1/orders").resolve("items"));
    }
}
```

Output (Java 21 and later; the exception message is trimmed), annotated:

```text
Smith+%26+Sons%2FOslo                                 form encoding: + for the space, / and & encoded
price%3C100+%C3%B8re                                  fine for a query value, wrong for a path
Illegal character in path at index 39: https://...    concatenation: URI.create rejects the space
https://api.example.com/customers/Smith%20&%20Sons/Oslo/orders?q=price%3C100%20%C3%B8re
https://api.example.com/customers/Smith%20%26%20Sons%2FOslo/orders?q=price%3C100+%C3%B8re
/customers/Smith%20%26%20Sons%2FOslo/orders   /customers/Smith & Sons/Oslo/orders
Smith%2520%2526%2520Sons%252FOslo                     double encoding: the % itself became %25
HTTPS://Example.COM:443/a/c                           normalize() resolved the dots and nothing else
https://api.example.com/v1/items                      resolve() replaced the last segment
```

Read line four carefully. The multi-argument constructor encodes per component, which looks right, but it cannot know that the `/` inside the customer name is data: `Smith & Sons/Oslo` became two path segments, and the `&` stayed raw because `&` is legal in a path. Line five is the correct URL: the segment was encoded *as a segment* (`%2F`, `%20`) before concatenation, and the query value with the form rule the server will apply to a query. `getRawPath()` shows the wire form and `getPath()` the decoded one. A `URI` built from components can still print unencoded non-ASCII from `toString()`, which is why the example prints `toASCIIString()`.

With Spring the same result needs no helper:

```java
URI uri = UriComponentsBuilder.fromUriString("https://api.example.com")
        .pathSegment("customers", customerName, "orders")
        .queryParam("q", searchText)
        .build()
        .encode()
        .toUri();
```

This yields `https://api.example.com/customers/Smith%20&%20Sons%2FOslo/orders?q=price%3C100%20%C3%B8re`: `&` kept because it is legal in a segment, `/` encoded because it would split the segment, and the space in the query as `%20` because Spring follows RFC 3986 rather than the form rule. `build().encode()` encodes only what is illegal in each component; `build(true)` declares the input already encoded and leaves it alone.

One thing the example cannot show: Tomcat answers `400 Bad Request` to any path containing `%2F` by default (the connector attribute `encodedSolidusHandling`, default `reject`, because a decoded slash defeats path-based security checks), and Spring Security's `StrictHttpFirewall` rejects it as well unless `setAllowUrlEncodedSlash(true)` is called. So the practical rule is stronger than "encode correctly": free text does not belong in a path segment at all. Put opaque identifiers in the path and free text in query parameters.

## Pitfalls

- Building URLs by concatenation. The lucky outcome is `IllegalArgumentException: Illegal character`; the unlucky one is a URL that parses but means something else, such as `?company=Smith%20&%20Sons` arriving as `company=Smith ` plus a second parameter named ` Sons`.
- Encoding the whole query string in one call. `?q%3D1%26page%3D2` is a single parameter named `q=1&page=2`. Encode the values, then join them with `=` and `&`.
- Double encoding. A value encoded once by you and once by a framework (or passed pre-encoded to the `URI` multi-argument constructor) becomes `%2520`; the symptom is 404s only for names with spaces. Encode exactly once, at the point where the string becomes a URL.
- `+` versus `%20`. Safe in a query value, because servers decode `+` as a space there; wrong in a path, where it stays a plus. When in doubt use `%20`, which every decoder reads as a space.
- Decoding before splitting. Decode the path and then split on `/`, and the `%2F` in `report%2F2026.pdf` becomes a separator while `%2e%2e%2f` becomes `../`. Split the raw path first, then decode each segment. This is also why Tomcat rejects `%2F`.
- Comparing or caching by raw string. `HTTPS://EXAMPLE.COM/` and `https://example.com/` are one resource; `%7e` and `~` are one character. Normalise scheme and host case and unreserved escapes yourself; `URI.normalize()` will not.
- `java.net.URL` as a map key or in `equals`. Its `equals` and `hashCode` resolve both hostnames through DNS, so they block, differ by network and fail offline. Use `URI`.
- Relative resolution. `URI.create("https://h/v1/orders").resolve("items")` drops `orders`; with a trailing slash on the base it keeps it. Base URLs for clients should end in `/`.

## Check yourself

1. `URLEncoder.encode` turns a space into `+`. In which component is that correct, in which is it wrong, and what does a servlet container do with `a+b` in a query parameter versus in a path?
2. Your code receives `/files/report%2F2026.pdf`, decodes the path, then splits on `/`. What goes wrong, in what order must the two steps happen, and why does Tomcat refuse the request before your code runs at all?
3. A URL produced by your service ends in `%2520`. Explain how it got there and name two ways to prevent it when using `UriComponentsBuilder`.
4. Two URLs differ only in `HTTPS://API.Example.COM` versus `https://api.example.com` and `%7e` versus `~`. Do they name the same resource? Which of those normalisations does `java.net.URI` apply for you, and which are yours to do?

## Go deeper

- [MDN: URIs](https://developer.mozilla.org/en-US/docs/Web/URI) · the components, one page per part, and a readable treatment of percent-encoding.
- [RFC 3986: Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986.html) · the grammar, the reserved sets (section 2) and normalisation (section 6).
- [WHATWG URL Standard](https://url.spec.whatwg.org/) · what browsers actually implement, including how malformed input is repaired.
- [Java: `java.net.URI`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URI.html) · the sections on identities and on escaping, quotation, encoding and decoding explain every line of the output above.
- [Java: `java.net.URLEncoder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLEncoder.html) · the first sentence says "form"; the rest lists the exact character rules.
- [Spring Framework: URI Links](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html) · `UriComponentsBuilder`, the encoding modes and `build(true)`.
- [Tomcat: HTTP Connector](https://tomcat.apache.org/tomcat-10.1-doc/config/http.html) · `encodedSolidusHandling` and the other path-decoding attributes.

---

Part of [Web & HTTP](../README.md) · item 1.3
