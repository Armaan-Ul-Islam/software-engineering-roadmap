# Autoboxing, the `Integer` cache and numeric pitfalls

> **In one sentence:** A primitive is a value and a wrapper is an object, so `==` on wrappers compares identity (which the `Integer` cache makes true only for small values), `null` wrappers unbox into `NullPointerException`, and primitive arithmetic silently wraps on overflow, truncates on narrowing, and promotes to `int` before you expect it.

**Why it matters:** `if (order.getQuantity() == other.getQuantity())` on two `Integer` fields passes every test with small numbers and fails in production at 128. A `Map<String, Integer>` lookup assigned to an `int` throws on a missing key. A duration computed with `int` literals overflows after 24 days. These are the oldest bugs in Java and still the most common ones in code review, and interviewers like them because the answer reveals whether you know what the compiler inserts for you.

## The idea

Java has eight primitive types (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`) and a wrapper class for each. A primitive holds a value directly; a wrapper is a heap object holding one. Generics, collections and `Optional` only work with objects, so the compiler converts between the two for you: **boxing** turns `int` into `Integer` by calling `Integer.valueOf(int)`, and **unboxing** calls `intValue()`.

`Integer.valueOf` does not always allocate. It keeps a cache of `Integer` objects for the values -128 to 127 and returns the shared instance for those. `Long`, `Short` and `Byte` cache the same range, `Character` caches 0 to 127, and `Boolean` has two constants. Only the upper bound of the `Integer` cache can be raised (`-XX:AutoBoxCacheMax=<size>`); the others are fixed. That is why `==` on two `Integer` objects is `true` for 127 and `false` for 128: the cache made the first pair the same object and the second pair two objects. The result for 128 is not undefined; it is reliably the identity comparison you asked for.

Unboxing happens wherever the compiler needs a primitive: arithmetic, comparisons with `<`, `if` conditions, assignment to a primitive variable, and `switch`. If the wrapper is `null`, the inserted `intValue()` call throws `NullPointerException`.

Primitive arithmetic has three rules that catch people:

1. Binary numeric promotion. Operands narrower than `int` (`byte`, `short`, `char`) become `int` before any arithmetic. `int` with `long` becomes `long`; anything with `double` becomes `double`. So `'A' + 1` is an `int`, and `365 * 24 * 60 * 60 * 1000` is computed entirely in `int` even when assigned to a `long`.
2. Overflow wraps silently. `Integer.MAX_VALUE + 1` is `Integer.MIN_VALUE`; there is no exception. `Math.addExact`, `multiplyExact` and friends throw `ArithmeticException` instead.
3. Narrowing casts truncate. `(int) 3.99` is `3`; `(byte) 200` is `-56`, because only the low eight bits are kept.

`char` is a 16-bit UTF-16 code unit, not a character. Any code point above U+FFFF (most emoji, many CJK characters) occupies two `char`s, so `String.length()` counts code units and `codePointCount` counts characters.

## Example

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class Boxing {

    public static void main(String[] arguments) {
        Integer small1 = 127;
        Integer small2 = 127;
        Integer big1 = 128;
        Integer big2 = 128;
        System.out.println("127 == 127 : " + (small1 == small2));
        System.out.println("128 == 128 : " + (big1 == big2));
        System.out.println("128 equals 128 : " + big1.equals(big2));

        Long oneLong = 1L;
        Integer oneInteger = 1;
        System.out.println("Long(1).equals(Integer 1) : " + oneLong.equals(oneInteger));

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        numbers.remove(1);
        System.out.println("after remove(1) : " + numbers);
        numbers.remove(Integer.valueOf(30));
        System.out.println("after remove(Integer.valueOf(30)) : " + numbers);

        Map<String, Integer> counts = new HashMap<>();
        try {
            int missing = counts.get("absent");
        } catch (NullPointerException exception) {
            System.out.println("NPE: " + exception.getMessage());
        }

        System.out.println("MAX_VALUE + 1 : " + (Integer.MAX_VALUE + 1));
        System.out.println("Math.abs(MIN_VALUE) : " + Math.abs(Integer.MIN_VALUE));
        long millisPerYear = 365 * 24 * 60 * 60 * 1000;
        long millisPerYearCorrect = 365L * 24 * 60 * 60 * 1000;
        System.out.println("int arithmetic widened too late : " + millisPerYear);
        System.out.println("long arithmetic : " + millisPerYearCorrect);

        System.out.println("(byte) 200 : " + (byte) 200);
        System.out.println("5 / 2 : " + (5 / 2) + ", 5 / 2.0 : " + (5 / 2.0));
        System.out.println("-7 % 3 : " + (-7 % 3) + ", floorMod : " + Math.floorMod(-7, 3));
        System.out.println("0.1 + 0.2 == 0.3 : " + (0.1 + 0.2 == 0.3));

        String smile = "😀";
        System.out.println("length of one emoji : " + smile.length());
        System.out.println("code points : " + smile.codePointCount(0, smile.length()));
        System.out.println("'A' + 1 : " + ('A' + 1));
    }
}
```

Run it with `java Boxing.java`:

```text
127 == 127 : true
128 == 128 : false
128 equals 128 : true
Long(1).equals(Integer 1) : false
after remove(1) : [10, 30]
after remove(Integer.valueOf(30)) : [10]
NPE: Cannot invoke "java.lang.Integer.intValue()" because the return value of "java.util.Map.get(Object)" is null
MAX_VALUE + 1 : -2147483648
Math.abs(MIN_VALUE) : -2147483648
int arithmetic widened too late : 1471228928
long arithmetic : 31536000000
(byte) 200 : -56
5 / 2 : 2, 5 / 2.0 : 2.5
-7 % 3 : -1, floorMod : 2
0.1 + 0.2 == 0.3 : false
length of one emoji : 2
code points : 1
'A' + 1 : 66
```

Three lines deserve a second look. `Long(1).equals(Integer 1)` is `false` because `equals` on wrappers checks the class first; a `Map<Long, X>` queried with an `int` key never finds anything. `list.remove(1)` chose the `remove(int index)` overload over `remove(Object)` because an exact primitive match beats boxing in overload resolution. And `Math.abs(Integer.MIN_VALUE)` is still negative, because `2147483648` does not fit in an `int`; the helpful NPE message (Java 14 and later) is the other thing to notice.

## Pitfalls

- `==` on wrappers. It compiles, works for small values, and fails at 128. Compare wrappers with `equals` or unbox to primitives first. Error Prone and most IDEs flag this (`BoxedPrimitiveEquality`).
- Unboxing `null`. `int quantity = map.get(key)`, `if (entity.getActive())` on a `Boolean` field, or a ternary `condition ? integerField : 0` (the ternary unboxes to `int` because one branch is primitive) all throw `NullPointerException`. Use `getOrDefault`, `Objects.requireNonNullElse`, or keep the value primitive in the first place.
- Wrapper fields in hot loops. `Integer total = 0; for (...) total += value;` allocates a new `Integer` on every iteration above 127. Use `int` or `long` for accumulators, and primitive streams (`mapToInt`, `IntStream`) instead of `Stream<Integer>`.
- `int` literals in `long` arithmetic. `24 * 60 * 60 * 1000 * 30` overflows before the assignment to `long` widens it. Put an `L` on the first literal, or better, use `Duration.ofDays(30).toMillis()`.
- `Math.abs` and `-` on `MIN_VALUE`. Both return `MIN_VALUE`. Use `Math.absExact` (Java 15 and later) when the input might be the minimum.
- `double` for money. `0.1 + 0.2 != 0.3`. Use `BigDecimal` with an explicit scale, or a `long` count of the smallest unit (see item 3.3).
- `char` arithmetic. `'A' + 1` is an `int` 66, not `'B'`; `char letter = 'A'; letter += 1;` is `'B'` because compound assignment casts back. Neither handles characters outside the Basic Multilingual Plane; use code points (`String.codePoints()`) for anything user-facing.
- Integer division and remainder of negatives. `5 / 2` is `2`, `-7 % 3` is `-1`. For a non-negative remainder (hash buckets, ring indexes) use `Math.floorMod`.

## Check yourself

1. `Integer first = 1000; Integer second = 1000; first == second` is `false`, but `first <= second && first >= second` is `true`. Explain both results in terms of what the compiler inserts.
2. `Map<Long, Account> accounts = ...; accounts.get(42)` compiles and always returns `null`. Why, and what does `accounts.get(42L)` do differently?
3. A method returns `Integer` and the caller writes `int value = service.count();`. Under what condition does this throw, and what does the stack trace say on Java 21?
4. `long timeoutMillis = 1000 * 60 * 60 * 24 * 30;` produces a negative number. Where exactly does the overflow happen, and what are two correct ways to write it?

## Go deeper

- [dev.java: Numbers and Strings](https://dev.java/learn/numbers-strings/) · the official tutorial on the wrapper classes, formatting and conversions.
- [JLS 5.1.7: Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.7) · the paragraph that guarantees the -128 to 127 cache, and nothing beyond it.
- [JLS 5.6: Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6) · the promotion rules behind `'A' + 1` and `byte + byte`.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · item 61, "Prefer primitive types to boxed primitives" (paid).

---

Part of [Java](../README.md) · item 1.1
