# Unicode and text encodings: code points, code units and graphemes

> **In one sentence:** A Java `String` is a sequence of 16-bit UTF-16 code units, not of characters, so `length()`, `charAt()` and `substring()` count and cut code units, while a user sees grapheme clusters and the network sees UTF-8 bytes: the same text has three different lengths, and only one of them is the one you meant.

**Why it matters:** An emoji truncated to a lone surrogate becomes `?` in the database; a "maximum 10 characters" rule rejects a single family emoji or accepts a 40-byte one; `getBytes()` without a charset turns `é` into `Ã©` on a server with another default; two spellings of `é` compare as different because one is composed and the other is not. Every system that takes text from humans hits one of these.

## The idea

**Code points.** Unicode assigns a number, a code point from U+0000 to U+10FFFF, to every character: `é` is U+00E9, the thumbs-up emoji is U+1F44D. An *encoding* turns code points into bytes. UTF-8 uses one to four bytes per code point, is identical to ASCII for the first 128, has no byte-order problem, and is the default on the web, on Linux and in modern Java. UTF-16 uses two bytes for code points up to U+FFFF and a *surrogate pair* of two 16-bit units for everything above; it is what Java, JavaScript and Windows use in memory.

**Code units in Java.** `char` is a UTF-16 code unit. Every code point above U+FFFF (all emoji, many CJK characters) occupies two `char`s: a high surrogate in D800 to DBFF followed by a low surrogate in DC00 to DFFF. `length()` counts `char`s; `codePointCount`, `codePoints()`, `offsetByCodePoints` and `Character.toChars` work in code points. `charAt(index)` in the middle of a pair returns half a character.

**Grapheme clusters.** What a user perceives as one character is a *grapheme cluster*, defined by Unicode Standard Annex #29: a base character plus combining marks (`e` followed by U+0301, combining acute accent), an emoji plus a skin-tone modifier, several emoji joined by U+200D zero-width joiners (the family), two regional indicators (a flag). Java exposes the boundaries through `BreakIterator.getCharacterInstance()`, which follows the extended grapheme cluster rules on JDK 20 and later, and through the regex `\X`. Older JDKs split some emoji sequences.

**Normalisation.** `é` can be one code point (U+00E9) or two (`e` then U+0301). They look identical, are canonically equivalent, and `equals` says `false`. Normalise text from users, file systems (macOS historically stores decomposed file names) and other systems with `Normalizer.normalize(text, Normalizer.Form.NFC)` before comparing or storing it.

**Bytes.** `String.getBytes()` and `new String(bytes)` without a charset use the platform default. Since JDK 18 (JEP 400) that default is UTF-8 everywhere unless `-Dfile.encoding=COMPAT` is set; before JDK 18 it depended on the operating system and locale, which is where decades of `Ã©` came from. Always name the charset: `getBytes(StandardCharsets.UTF_8)`, `new InputStreamReader(input, StandardCharsets.UTF_8)`, `Files.readString` (UTF-8 by definition). Declare it on the wire too: `Content-Type: text/plain; charset=utf-8`. In databases, know what a length limit counts: PostgreSQL `varchar(10)` counts characters, and MySQL's `utf8` is a three-byte subset that rejects emoji; use `utf8mb4`.

## Example

The source uses Unicode escapes so that it compiles identically on any JDK and under any default charset. The five strings are `héllo` with a precomposed `é`, `héllo` with `e` plus a combining accent, a slightly smiling face, a thumbs-up with a skin-tone modifier, and a family of three joined by zero-width joiners.

```java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.text.BreakIterator;

public final class UnicodeText {

    public static void main(String[] arguments) {
        describe("héllo");
        describe("héllo");
        describe("🙂");
        describe("👍🏽");
        describe("👨‍👩‍👧");

        String thumbsUp = "👍🏽";
        System.out.println("substring(0, 1) is U+" + Integer.toHexString(thumbsUp.substring(0, 1).codePointAt(0)).toUpperCase());
        System.out.println("reversed: " + new StringBuilder(thumbsUp).reverse());
        System.out.println("default charset: " + Charset.defaultCharset());
    }

    static void describe(String text) {
        System.out.printf("length=%d codePoints=%d graphemes=%d utf8=%2d utf16=%2d  %s%n",
                text.length(),
                text.codePointCount(0, text.length()),
                graphemeCount(text),
                text.getBytes(StandardCharsets.UTF_8).length,
                text.getBytes(StandardCharsets.UTF_16BE).length,
                text);
    }

    static int graphemeCount(String text) {
        BreakIterator iterator = BreakIterator.getCharacterInstance();
        iterator.setText(text);
        int count = 0;
        while (iterator.next() != BreakIterator.DONE) {
            count++;
        }
        return count;
    }
}
```

Output on JDK 25:

```text
length=5 codePoints=5 graphemes=5 utf8= 6 utf16=10  héllo
length=6 codePoints=6 graphemes=5 utf8= 7 utf16=12  héllo
length=2 codePoints=1 graphemes=1 utf8= 4 utf16= 4  🙂
length=4 codePoints=2 graphemes=1 utf8= 8 utf16= 8  👍🏽
length=8 codePoints=5 graphemes=1 utf8=18 utf16=16  👨‍👩‍👧
substring(0, 1) is U+D83D
reversed: 🏽👍
default charset: UTF-8
```

The family is one grapheme, five code points, eight `char`s and eighteen UTF-8 bytes; `length()` is the only one of those numbers no human would ever want. `substring(0, 1)` on the thumbs-up returns a lone high surrogate, which becomes `?` or U+FFFD the moment it is encoded. `StringBuilder.reverse()` keeps surrogate pairs intact but puts the skin-tone modifier in front of the hand, a sequence no keyboard can produce. `UTF_16BE` is used for the byte count because `UTF_16` prepends a two-byte byte-order mark.

## Pitfalls

- Validating or truncating with `length()` and `substring()`. A limit meant for humans needs grapheme clusters (`BreakIterator`); a limit for a database column needs that column's unit; a limit for a byte buffer needs `getBytes(UTF_8).length`.
- Looping with `charAt(index)`. Use `codePoints()` or `BreakIterator`, or you will split pairs and clusters.
- `getBytes()`, `new String(bytes)`, `FileReader` and `FileWriter` without a charset. Correct by accident on one machine, mojibake on the next.
- Comparing or deduplicating without normalising. The same name typed on a Mac and on Windows can be two different strings.
- `toUpperCase()` and `toLowerCase()` without a `Locale`. In a Turkish locale `"i".toUpperCase()` is `İ`; use `Locale.ROOT` for identifiers and protocol strings. Case mapping can also change length: `"ß".toUpperCase()` is `"SS"`.
- Assuming one code point is one glyph is one byte. Column widths, cursor positions, `printf` alignment and fixed-width protocols all break on wide and combining characters.
- MySQL `utf8`. It is `utf8mb3`; inserting an emoji fails with "Incorrect string value". The fix is `utf8mb4` on the column, the table and the connection.
- A byte-order mark at the start of a file (U+FEFF, written by some Windows editors). It is invisible, breaks `startsWith`, JSON parsers and shebang lines, and must be stripped explicitly.

## Check yourself

1. The same string has lengths 8, 5 and 1 in the output above. Which API gives each, and which one does a "maximum 10 characters" rule in a user interface want?
2. Why does `"é".equals("é")` return `false`, and what do you do before comparing and before storing?
3. A JDK 11 service on Windows writes `é` with `new FileWriter(path)`; a JDK 21 service on Linux reads the file with `Files.readString`. What happens in the second service, where exactly was the byte sequence misinterpreted, and which side is wrong?
4. Users with emoji in their names fail to register, with a MySQL error. Why, and what must change in the schema and the connection?

## Go deeper

- [The Absolute Minimum Every Software Developer Must Know About Unicode](https://www.joelonsoftware.com/2003/10/08/the-absolute-minimum-every-software-developer-absolutely-positively-must-know-about-unicode-and-character-sets-no-excuses/) · Joel Spolsky's 2003 essay, still the best twenty-minute introduction to code points versus encodings.
- [UTF-8 Everywhere](https://utf8everywhere.org/) · why UTF-8 should be the only encoding at your boundaries, and what counting "characters" even means.
- [Unicode Standard Annex #29: Text Segmentation](https://unicode.org/reports/tr29/) · the definition of grapheme clusters that `BreakIterator` implements.
- [JEP 400: UTF-8 by Default](https://openjdk.org/jeps/400) · what changed in JDK 18, and the `COMPAT` escape hatch.
- [java.lang.Character (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Character.html) · the "Unicode Character Representations" section explains code units, surrogates and the code point API.

---

Part of [Foundations](../README.md) · item 1.5
