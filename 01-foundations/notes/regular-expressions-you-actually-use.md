# Regular expressions you actually use, and when not to

> **In one sentence:** A regular expression is a small pattern language for finding, extracting and replacing text; a dozen constructs (character classes, quantifiers, anchors, groups, alternation) cover nearly every real use, and the two things to know beyond the syntax are that a backtracking engine can take exponential or polynomial time on the wrong pattern, and that nested or structured formats (JSON, HTML, dates, email) need a parser, not a regex.

**Why it matters:** Log triage, input validation, `grep` on a server, route matching, `sed` in a migration script, a `CHECK` constraint: regex is the tool you reach for ten times a week. It is also the source of a specific production outage class: a pattern that runs in microseconds on test data and takes seconds, or forever, on a crafted or merely unusual input.

## The idea

The constructs you will use, in Java syntax (the same in JavaScript, PostgreSQL's `~` operator, `grep -E`, and most other engines, with small differences noted below):

| Construct | Meaning | Example |
|---|---|---|
| `.` | any character except newline | `a.c` matches `abc`, `a c` |
| `\d` `\w` `\s` | digit, word character (letters, digits, `_`), whitespace; capitals negate | `\d{4}-\d{2}-\d{2}` |
| `[abc]` `[a-z]` `[^,]` | one character from the set, a range, anything not in the set | `[^\]]+` reads up to the next `]` |
| `*` `+` `?` `{n,m}` | zero or more, one or more, optional, between n and m times | `\d{4,}` four or more digits |
| `^` `$` `\b` | start and end of input (or line with `MULTILINE`), word boundary | `\border-\d+\b` |
| `(…)` `(?<name>…)` `(?:…)` | capturing group, named group, non-capturing group | `(?<level>WARN\|ERROR)` |
| `a\|b` | alternation | `WARN\|ERROR` |
| `*?` `+?` | lazy quantifiers: match as little as possible | `".*?"` one quoted string, not the whole line |
| `\.` `\[` `\\` | escape a character that would otherwise be special | `\.` a literal dot |

Quantifiers are *greedy*: `.*` grabs as much as it can and gives back only what the rest of the pattern needs. Anchors matter more than people expect: a validation pattern without `^` and `$` (`\d{4}`) accepts `abc1234def`. In Java, `matcher.matches()` requires the whole input to match, `find()` searches for the pattern anywhere, and `String.matches` is `matches()` with a compile on every call.

**Engine cost.** Java, JavaScript, Python, PCRE and most engines are *backtracking* engines: when a choice (quantifier, alternation) leads to a dead end, they go back and try the next option. For most patterns this is linear. For a pattern where two or more parts can match the same text in many ways, failing inputs force the engine to try every split: `.*.*=.*` on a string with no `=` tries every way of dividing the string between the two `.*`, which is cubic; nested quantifiers like `(a|aa)+` can be exponential. The JDK memoises some nested-group cases since Java 9, so textbook examples often run fast there, but the `.*.*` shape still scales as badly as the example below shows. RE2, Go's `regexp` and Rust's `regex` are linear-time by construction because they drop backreferences and lookaround; if you accept patterns from users, use one of those or a strict timeout.

**When a regex is the wrong tool.** A regex matches *regular* languages: no counting of nested brackets, no "this tag closes that tag". So: HTML and XML need a parser (`jsoup`, the DOM); JSON needs `Jackson` or `jq`; a date needs `DateTimeFormatter` (a regex cannot know that February has 28 days); an email address is "contains an `@` with something on both sides, then send a confirmation", because the real grammar (RFC 5322) is not worth matching; a URL is `java.net.URI`. And a regex that needs a comment to be understood should be a few lines of code instead.

## Example: triage a log, then watch a pattern go cubic

```java
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class LogRegex {

    private static final Pattern LOG_LINE = Pattern.compile(
            "^(?<time>\\d{2}:\\d{2}:\\d{2}\\.\\d{3}) +(?<level>WARN|ERROR) +\\[(?<thread>[^\\]]+)\\] +(?<message>.*)$");

    private static final Pattern ORDER_ID = Pattern.compile("\\border-(\\d{4,})\\b");

    public static void main(String[] arguments) {
        List<String> lines = List.of(
                "10:42:01.117  INFO [http-nio-8080-exec-3] Accepted order-10421",
                "10:42:01.903  WARN [http-nio-8080-exec-7] Retrying payment for order-10421 (attempt 2)",
                "10:42:02.250 ERROR [scheduler-1] Timeout for order-10422, order-10423; see order-9");
        for (String line : lines) {
            Matcher lineMatcher = LOG_LINE.matcher(line);
            if (!lineMatcher.matches()) {
                continue;
            }
            Matcher orderMatcher = ORDER_ID.matcher(lineMatcher.group("message"));
            StringBuilder orders = new StringBuilder();
            while (orderMatcher.find()) {
                orders.append(orderMatcher.group(1)).append(' ');
            }
            System.out.printf("%s %-5s %-22s orders: %s%n", lineMatcher.group("time"),
                    lineMatcher.group("level"), lineMatcher.group("thread"), orders.toString().trim());
        }
        System.out.println("replace: " + ORDER_ID.matcher("see order-10421 and order-10422").replaceAll("order-***"));
        System.out.println("split:   " + List.of("a, b,c ,  d".split("\\s*,\\s*")));
    }
}
```

```text
$ java LogRegex.java
10:42:01.903 WARN  http-nio-8080-exec-7   orders: 10421
10:42:02.250 ERROR scheduler-1            orders: 10422 10423
replace: see order-*** and order-***
split:   [a, b, c, d]
```

What each piece does: `(?<level>WARN|ERROR)` drops the `INFO` line because `matches()` needs the whole line to fit. `\[(?<thread>[^\]]+)\]` reads the thread name up to the first `]`; `\[(.*)\]` would have worked here but is the greedy mistake waiting to happen on a line with two bracketed fields. `\border-(\d{4,})\b` finds every order with at least four digits and skips `order-9`; the `\b` keeps `order-104210` from matching as `10421`. Patterns are compiled once as constants, because `Pattern.compile` is the expensive part and `Pattern` is thread-safe while `Matcher` is not. Note that the same regex, written in `grep -E` on a server, loses the `\d` shorthand on some platforms (`[0-9]` is portable) and that `\b`, lookaround and named groups vary between tools; `regex101` lets you pick the flavour before you trust a pattern.

The cubic case, which is the shape of the pattern behind the Cloudflare outage of July 2019:

```java
import java.util.regex.Pattern;

public final class Backtracking {

    public static void main(String[] arguments) {
        Pattern greedy = Pattern.compile(".*.*=.*");
        for (int length : new int[] {1000, 2000, 4000}) {
            String input = "x".repeat(length);
            long start = System.nanoTime();
            boolean found = greedy.matcher(input).find();
            long elapsedMillis = (System.nanoTime() - start) / 1_000_000;
            System.out.printf("length %4d  found %-5s  %6d ms%n", length, found, elapsedMillis);
        }
    }
}
```

```text
$ java Backtracking.java
length 1000  found false     362 ms
length 2000  found false    2541 ms
length 4000  found false   20777 ms
```

Doubling the input multiplies the time by about eight: cubic. On matching inputs (one that contains `=`) the same pattern returns in microseconds, which is why it passes every test. A 4 KB request header without an `=` would hold a request thread for 20 seconds; a few hundred of them is the outage. The fix is to say what you mean: `[^=]*=` reads up to the first `=` with no ambiguity, and runs in linear time.

## Pitfalls

- Validation without anchors. `\d{4}` accepts `12345` and `x1234`. Use `^…$` or `matches()`.
- Greedy `.*` across delimiters. `"(.*)"` on `"a" and "b"` captures `a" and "b`. Use `"([^"]*)"` or a lazy `.*?`.
- `String.matches`, `split` and `replaceAll` in a hot loop. Each call compiles the pattern. Keep a `static final Pattern`.
- Sharing a `Matcher` between threads. `Pattern` is immutable; `Matcher` carries state. Create one per use.
- Ambiguous patterns on untrusted input. Anything with two adjacent unbounded quantifiers (`.*.*`, `\s*\s*`, `(\w+\s?)+`) is a denial-of-service waiting for the input that does not match. Make each part unambiguous (`[^=]*`), bound the input length, or use a linear-time engine.
- Parsing structured formats. HTML, JSON, CSV with quoted commas, and dates all have parsers that know the rules a regex cannot express. The regex works on the examples you tried and fails on the first real file.
- Different flavours. `\d` in Java matches only ASCII digits unless `UNICODE_CHARACTER_CLASS` is set; in PostgreSQL `~` is case-sensitive and `~*` is not; `sed` on macOS uses basic syntax where `+` is a literal. Test the pattern in the engine that will run it.
- Writing a regex that needs a comment. Split it into named groups, use `Pattern.COMMENTS` with whitespace and `#` comments, or write a small parser.

## Check yourself

1. The pattern `\d{4}-\d{2}-\d{2}` is used to validate dates. Give an input that passes it and is not a date, and say what the right tool is.
2. Why does `.*.*=.*` take 20 seconds on 4,000 characters without an `=` and microseconds on 4,000 characters with one? Rewrite it so both cases are fast.
3. A log line has two bracketed fields: `[main] [order-service]`. What does `\[(.*)\]` capture, and what should it be?
4. A colleague proposes a regex to extract all `<a href>` targets from arbitrary HTML pages. Name two inputs where it breaks and the alternative.

## Go deeper

- [RegexOne](https://regexone.com/) · an hour of interactive lessons that cover the table above with exercises.
- [regex101](https://regex101.com/) · test a pattern against sample input with an explanation of every piece and a choice of engine flavour; keep it open.
- [java.util.regex.Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html) · the full Java syntax, flags and the differences from other engines.
- [Russ Cox: Regular Expression Matching Can Be Simple And Fast](https://swtch.com/~rsc/regexp/regexp1.html) · why backtracking engines blow up and how linear-time engines avoid it.
- [Cloudflare: Details of the Cloudflare outage on July 2, 2019](https://blog.cloudflare.com/details-of-the-cloudflare-outage-on-july-2-2019/) · the `.*.*=.*` backtracking explained step by step by the people it bit.

---

Part of [Foundations](../README.md) · item 7.4
