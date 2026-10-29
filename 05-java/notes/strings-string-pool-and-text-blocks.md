# Strings: immutability, the string pool, `StringBuilder`, text blocks and encodings

> **In one sentence:** A `String` is an immutable sequence of UTF-16 code units, so every "modification" allocates a new one, `==` compares references (equal only when both came from the pool), building in a loop needs a `StringBuilder`, and converting to or from bytes is only correct when you name the charset.

**Why it matters:** Strings are most of the heap in a typical service and most of the bugs in its integration layer. `name == "admin"` that works in tests and fails on input read from a request, `Blåbær` arriving as `BlÃ¥bÃ¦r` because somebody called `getBytes()` without a charset on one side and `new String(bytes)` on a server with a different default on the other, and a report builder that takes minutes because of `+=` in a loop are all one-line fixes once you know the model.

## The idea

**Immutability.** A `String` never changes after construction. `toUpperCase`, `trim`, `replace` and `+` all return new strings. This is what makes strings safe to share between threads, safe as `HashMap` keys (the hash is cached after the first call) and safe to put in the pool. Internally, since Java 9 (JEP 254, compact strings), a `String` stores a `byte[]` and a coder flag: one byte per character when every character fits in Latin-1, two bytes per UTF-16 code unit otherwise.

**The string pool.** Every string literal in a class file, and every compile-time constant expression made of literals, is interned: the JVM keeps one shared instance per distinct value in a table on the heap. Strings created at run time (concatenation with a variable, `new String(...)`, `substring`, anything read from I/O) are ordinary objects outside the pool. `intern()` returns the pooled instance for a value, adding it if necessary. Hence `"hel" + "lo" == "hello"` is `true` (folded by `javac`) while `prefix + "lo" == "hello"` is `false`. Compare strings with `equals`, always; `==` on strings is a bug even when it happens to work.

**Concatenation.** `a + b` compiles to an `invokedynamic` call (JEP 280, Java 9) that builds the result in one allocation of the right size; a single expression with several `+` is efficient. The problem is `result += piece` in a loop: each iteration copies everything accumulated so far, which is quadratic. `StringBuilder` grows a buffer in place and copies once at `toString()`. `String.join`, `Collectors.joining` and `String.repeat` cover the common loop shapes without a builder at all.

**Formatting.** `String.format` and the instance form `"...".formatted(...)` use `java.util.Formatter` syntax: `%s`, `%d`, `%.2f`, `%,d`, `%-10s`, `%n`. Formatting of numbers is locale-sensitive; pass `Locale.ROOT` for machine-readable output and the user's locale for display. The same applies to `toLowerCase` and `toUpperCase`: without a locale they use the default, and in a Turkish locale `"TITLE".toLowerCase()` is `tıtle` with a dotless i.

**Text blocks** (JEP 378, Java 15). A `"""` block spans lines, strips the common leading indentation (measured against the closing delimiter and the least-indented line), strips trailing spaces, and keeps a trailing newline when the closing `"""` is on its own line. Two escapes exist only in text blocks: `\` at the end of a line joins it with the next (no newline), and `\s` is a space that survives trailing-space stripping. They are plain strings, so `.formatted(...)` and `.strip()` work on them.

**Encodings.** Characters and bytes are different things; a charset maps between them. UTF-8 is the only sensible interchange encoding. Since Java 18 (JEP 400) the default charset is UTF-8 on every platform, so `getBytes()` and `new String(byte[])` without an argument are no longer a lottery; before that they used the operating system's locale, and on Windows that meant `windows-1252`. Still name the charset explicitly: `StandardCharsets.UTF_8` is free and makes the intent visible, and `Files.readString`, `Files.writeString`, `InputStreamReader` and `HttpResponse.BodyHandlers.ofString` all take one.

## Example

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class Strings {

    public static void main(String[] arguments) {
        String literal = "hello";
        String constantFolded = "hel" + "lo";
        String prefix = "hel";
        String runtimeConcat = prefix + "lo";
        System.out.println("literal == constantFolded : " + (literal == constantFolded));
        System.out.println("literal == runtimeConcat : " + (literal == runtimeConcat));
        System.out.println("literal == runtimeConcat.intern() : " + (literal == runtimeConcat.intern()));

        String json = """
            {
              "name": "Ada",
              "tags": ["a", "b"]
            }
            """;
        System.out.print(json);
        String oneLine = """
            SELECT id, name \
            FROM person \
            WHERE id = %d\
            """.formatted(42);
        System.out.println(oneLine);

        System.out.println(String.format(Locale.ROOT, "%.2f", 1234.5));
        System.out.println(String.format(Locale.GERMANY, "%,.2f", 1234.5));
        System.out.println("TITLE".toLowerCase(Locale.forLanguageTag("tr")));

        String word = "Blåbær";
        System.out.println("default charset : " + Charset.defaultCharset());
        System.out.println("UTF-8 bytes : " + word.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("ISO-8859-1 bytes : " + word.getBytes(StandardCharsets.ISO_8859_1).length);
        byte[] utf8 = word.getBytes(StandardCharsets.UTF_8);
        System.out.println("UTF-8 decoded as Latin-1 : " + new String(utf8, StandardCharsets.ISO_8859_1));
    }
}
```

Output of `java Strings.java` on Java 21 or later:

```text
literal == constantFolded : true
literal == runtimeConcat : false
literal == runtimeConcat.intern() : true
{
  "name": "Ada",
  "tags": ["a", "b"]
}
SELECT id, name FROM person WHERE id = 42
1234.50
1.234,50
tıtle
default charset : UTF-8
UTF-8 bytes : 8
ISO-8859-1 bytes : 6
UTF-8 decoded as Latin-1 : BlÃ¥bÃ¦r
```

The last line is mojibake in its canonical form: each non-ASCII character became two bytes in UTF-8 and each byte was then shown as its own Latin-1 character. When you see `Ã¥` or `Ã¦` in a log, a database or a web page, one side encoded as UTF-8 and the other decoded as Latin-1 or windows-1252.

The `StringBuilder` case, for completeness:

```java
StringBuilder report = new StringBuilder();
for (Line line : lines) {
    report.append(line.sku()).append('\t').append(line.quantity()).append('\n');
}
String text = report.toString();
```

With `report += ...` instead, ten thousand lines means ten thousand copies of an ever-larger string. The builder version is linear.

## Pitfalls

- `==` on strings. Works for literals, fails for anything read at run time. `equals`, or `Objects.equals` when either side may be `null`, and `"admin".equals(role)` to put the constant first if you prefer that style.
- `intern()` as an optimisation. It costs a hash lookup per call and the table is only trimmed by full GC; it pays off only for a bounded set of values repeated millions of times (enum-like codes parsed from a feed). Deduplicate explicitly with a `Map` if you need control.
- Concatenating in a loop. The symptom is a report or CSV export whose time grows with the square of its size. Use `StringBuilder`, `String.join` or `Collectors.joining`.
- `getBytes()` and `new String(bytes)` without a charset. Correct by accident on Java 18 and later, wrong on older runtimes, and unreadable either way. Pass `StandardCharsets.UTF_8`.
- `length()` as "number of characters". It counts UTF-16 code units; emoji and many scripts need two. Use `codePointCount` or `codePoints()` (see item 1.1).
- `String.format` in a hot path. It parses the format string and goes through `Formatter` and locale lookup on every call; it is fine for log lines and error messages, slow for building millions of keys. Concatenation or a builder is an order of magnitude cheaper there.
- Locale-sensitive case conversion. `toLowerCase()` with no argument depends on the server's default locale. Use `Locale.ROOT` for identifiers and protocol tokens, and `equalsIgnoreCase` for comparisons.
- Text block indentation. The closing `"""` sets the left margin. Put it on its own line at the indentation you want stripped; putting it at column zero keeps all the leading spaces.
- Secrets in strings. A password in a `String` stays in the heap, and in heap dumps, until the GC reclaims it. The JDK's own APIs (`Console.readPassword`, `KeyStore`) use `char[]` for that reason, so you can zero it.

## Check yourself

1. `String first = "ab"; String second = "a" + "b"; String third = "a"; third = third + "b";` Which of `first == second` and `first == third` is `true`, and why does `javac` treat the two concatenations differently?
2. A log line shows `Ã¸` where `ø` was expected. On which side (writer or reader) is the mistake, and which two charsets are involved?
3. Why is `report += line` in a loop quadratic when `a + b + c + d` in a single expression is not?
4. You have a text block holding an SQL statement and want it on one line with no trailing newline. Which two text-block-only escapes get you there?

## Go deeper

- [dev.java: Strings](https://dev.java/learn/numbers-strings/strings/) · the official tutorial, including `StringBuilder`, formatting and the text block section.
- [JEP 378: Text Blocks](https://openjdk.org/jeps/378) · the indentation algorithm and the `\` and `\s` escapes, with examples.
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400) · what changed in Java 18 and the `file.encoding=COMPAT` escape hatch for old behaviour.
- [JEP 254: Compact Strings](https://openjdk.org/jeps/254) · why a Latin-1 string takes half the memory it did in Java 8.
- [java.util.Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html) · the complete format-string syntax.

---

Part of [Java](../README.md) · item 1.2
