# Floating point, integer overflow and how to represent money

> **In one sentence:** A `double` holds a binary fraction with 53 significant bits, so most decimal amounts (0.1 included) are stored as the nearest approximation, and money must live in a `BigDecimal` with an explicit scale and `RoundingMode`, or as whole minor units in a `long`, never in a `double`.

**Why it matters:** Invoice totals one cent off the sum of their lines, a `0.1 + 0.2 == 0.3` check that fails, IDs above 2^53 silently changing on their way through JavaScript, an `int` counter going negative after two billion events. All of these have shipped to production, and "how would you store money" is an early question in most backend interviews.

## The idea

**What a double is.** IEEE 754 double precision stores a sign bit, an 11-bit exponent and a 52-bit fraction with an implied leading 1, so 53 bits of precision, about 15.9 decimal digits. The value is a binary fraction times a power of two. A decimal fraction can only be stored exactly if its denominator is a power of two: 0.5, 0.25 and 0.75 are exact; 0.1 is `0.000110011001100...` repeating in binary, cut off after 53 bits, so the stored value is 0.1000000000000000055511151231257827... `0.2` and `0.3` are approximations too, and the sum of the first two approximations rounds to a different double than the approximation of `0.3`. Java prints the shortest decimal string that uniquely identifies a double, which is why `0.1` prints as `0.1` but the sum prints as `0.30000000000000004`.

**Precision is relative, not absolute.** The gap between adjacent doubles grows with magnitude. Every integer up to 2^53 (9,007,199,254,740,992) is exact; above that, doubles skip integers. A `float` has 24 bits of precision and stops being exact at 16,777,216. `NaN` is not equal to anything, including itself, and dividing by zero gives an infinity, not an exception.

**Integers wrap silently.** `int` is 32-bit two's complement, from −2,147,483,648 to 2,147,483,647; `long` is 64-bit. Overflow is not an error in Java: the JLS defines the result as the low-order bits of the true result, so `Integer.MAX_VALUE + 1` is `Integer.MIN_VALUE`. `Math.addExact`, `multiplyExact`, `incrementExact` and `toIntExact` throw `ArithmeticException` instead. Classic victims: `(low + high) / 2` in a binary search, `Math.abs(Integer.MIN_VALUE)` (still negative), event counters, and amounts in `int` cents, which wrap at about 21.4 million units of currency.

**The money rule.** Money is a decimal quantity with a fixed number of fractional digits set by the currency (2 for EUR and NOK, 0 for JPY) and with rules about rounding. Two representations fit:

1. `BigDecimal`, created from a `String` or with `BigDecimal.valueOf(double)`, never with `new BigDecimal(double)`. Every operation that can produce extra digits (`divide`, percentages, currency conversion) must be given a scale and a `RoundingMode`. `equals` compares scale as well as value (`1.10` is not `equals` to `1.1`), so compare with `compareTo` and normalise with `setScale` before using amounts as map keys. Pick the rounding mode your domain requires and write it down: `HALF_UP` is what most people mean by rounding, `HALF_EVEN` (banker's rounding) avoids a systematic bias when many rounded values are summed.
2. Minor units in a `long` (cents, øre): exact and fast for sums and for multiplying by integer quantities. You carry the currency and scale separately, and anything involving division or a rate needs explicit rounding, usually by switching to `BigDecimal` for that step.

In PostgreSQL the column is `numeric(19, 4)` or similar, never `real` or `double precision`. In JSON, send money as a string (`"19.99"`) or as an integer of minor units, because every JavaScript number is a double.

## Example

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class FloatingPointAndMoney {

    public static void main(String[] arguments) {
        System.out.println("0.1 + 0.2            = " + (0.1 + 0.2));
        System.out.println("0.1 + 0.2 == 0.3     : " + (0.1 + 0.2 == 0.3));
        System.out.println("new BigDecimal(0.1)  = " + new BigDecimal(0.1));
        System.out.println("(int) (0.29 * 100)   = " + (int) (0.29 * 100));

        double twoToThe53 = 9_007_199_254_740_992.0;
        System.out.println("2^53 + 1 as double   = " + (long) (twoToThe53 + 1));

        System.out.println("MAX_VALUE + 1        = " + (Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException exception) {
            System.out.println("addExact             : " + exception.getMessage());
        }

        BigDecimal price = new BigDecimal("19.99");
        BigDecimal vatRate = new BigDecimal("0.25");
        BigDecimal vat = price.multiply(vatRate);
        System.out.println("19.99 * 0.25         = " + vat);
        System.out.println("rounded HALF_EVEN    = " + vat.setScale(2, RoundingMode.HALF_EVEN));
        System.out.println("10.00 / 3 (scale 2)  = " + new BigDecimal("10.00").divide(new BigDecimal("3"), 2, RoundingMode.HALF_EVEN));
        System.out.println("1.10 equals 1.1      : " + new BigDecimal("1.10").equals(new BigDecimal("1.1")));
        System.out.println("1.10 compareTo 1.1   : " + new BigDecimal("1.10").compareTo(new BigDecimal("1.1")));
        try {
            new BigDecimal("10").divide(new BigDecimal("3"));
        } catch (ArithmeticException exception) {
            System.out.println("10 / 3 no scale      : " + exception.getMessage());
        }

        long priceInCents = 1_999L;
        long totalCents = priceInCents * 3;
        System.out.printf("3 x 19.99 in cents   = %d (%d.%02d)%n", totalCents, totalCents / 100, totalCents % 100);
    }
}
```

Output:

```text
0.1 + 0.2            = 0.30000000000000004
0.1 + 0.2 == 0.3     : false
new BigDecimal(0.1)  = 0.1000000000000000055511151231257827021181583404541015625
(int) (0.29 * 100)   = 28
2^53 + 1 as double   = 9007199254740992
MAX_VALUE + 1        = -2147483648
addExact             : integer overflow
19.99 * 0.25         = 4.9975
rounded HALF_EVEN    = 5.00
10.00 / 3 (scale 2)  = 3.33
1.10 equals 1.1      : false
1.10 compareTo 1.1   : 0
10 / 3 no scale      : Non-terminating decimal expansion; no exact representable decimal result.
3 x 19.99 in cents   = 5997 (59.97)
```

Three lines deserve a second look. `(int) (0.29 * 100)` is 28 because the product is 28.999999999999996 and the cast truncates; "multiply by 100 to get cents" is a bug, use `new BigDecimal("0.29").movePointRight(2).longValueExact()`. `new BigDecimal(0.1)` shows exactly which number the `double` had been holding all along; the damage happened at the literal, not in `BigDecimal`. And the VAT: three lines rounded separately give 3 × 5.00 = 15.00, while VAT on the total, 59.97 × 0.25 = 14.9925, rounds to 14.99. Neither is wrong arithmetic. Where you round is a business rule, and the invoice must state the one it follows.

## Pitfalls

- `new BigDecimal(0.1)` instead of `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)`. Any amount that has passed through a `double`, including a JSON number parsed as `double`, has already been approximated.
- `BigDecimal.equals` includes the scale, so `HashSet`, `HashMap` keys and `assertEquals` treat `1.10` and `1.1` as different. Use `compareTo`, or normalise with `setScale(2)` or `stripTrailingZeros()`.
- `divide` without a scale. `10 / 3` throws; `divide(divisor, 2, RoundingMode.HALF_EVEN)` does not. Always pass both arguments.
- Rounding at an unspecified point. Per-line and per-total rounding differ by a cent, and whichever the loop happened to implement becomes the de facto rule. Decide, document, and test it.
- `long` identifiers above 2^53 in JSON. JavaScript parses them as doubles and changes the last digits. Serialise large IDs as strings.
- `int` for cents or for counters. 21.4 million units or 2.1 billion events later it wraps. Use `long`, and `Math.addExact` where wrapping must be impossible.
- `==` on doubles. For measured quantities compare with a tolerance; for money do not have doubles at all. Remember `Double.NaN == Double.NaN` is `false`.

## Check yourself

1. Why does `0.1 + 0.2 == 0.3` fail for `double` while `0.1f + 0.2f == 0.3f` happens to be `true` for `float`? What does that tell you about tests that rely on either?
2. A 64-bit ID `9007199254740993` is returned as a JSON number to a browser. What value does the browser see, why, and what is the fix?
3. `new BigDecimal("1.10")` and `new BigDecimal("1.1")` are added to a `HashSet`. What is its size, and what would you do before using amounts as keys?
4. An order has three lines of 19.99 with 25% VAT. Compute the VAT rounding per line and rounding on the total. Do they differ, and who should decide which one the invoice shows?

## Go deeper

- [What Every Computer Scientist Should Know About Floating-Point Arithmetic](https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html) · Goldberg's paper; the first third is enough for everyday work.
- [Float Toy](https://evanw.github.io/float-toy/) · flip the bits of a float or double and watch the value change; the fastest way to feel what 53 bits means.
- [0.30000000000000004.com](https://0.30000000000000004.com/) · the same sum in every language, with the explanation.
- [BigDecimal (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html) · read the class description once; it explains scale, precision and why `equals` behaves as it does.
- [JLS 15.18.2: Additive operators for numeric types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18.2) · the sentence that makes integer overflow silent.

---

Part of [Foundations](../README.md) · item 1.4
