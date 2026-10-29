# Patterns: bit manipulation and math

> **In one sentence:** A handful of identities (XOR cancels pairs, `n & (n - 1)` clears the lowest set bit, squaring halves an exponent, Euclid's remainder loop finds the gcd) solve every bit and math problem that interviews actually ask, and knowing them lets you give an O(1)-space answer where others reach for a hash map.

**Why it matters:** Bit tricks appear in permission flags, Bloom filters, hash functions, compact sets and feature toggles; modular arithmetic and fast exponentiation appear in hashing, sharding, cryptography and any "answer modulo 10^9 + 7" question. In interviews they are short problems with a single trick each, so they are where a prepared candidate saves ten minutes and an unprepared one loses them.

## The idea

**Recognising the pattern.** "Without extra memory", "every element appears twice except one", "count the 1 bits", "power of two", "reverse the bits", "answer modulo 10^9 + 7", "gcd", "x to the power n with n huge". A bit problem is also sometimes hidden as a set problem over at most 32 or 64 items (a bitmask is a `boolean[]` that fits in a register).

**The identities that matter.**

| Expression | Effect | Used for |
|---|---|---|
| `a ^ a == 0`, `a ^ 0 == a`, XOR is commutative | pairs cancel, order does not matter | Single Number, Missing Number, swapping without a temporary |
| `n & (n - 1)` | clears the lowest set bit | counting bits, power-of-two check (`n > 0 && (n & (n - 1)) == 0`) |
| `n & -n` | isolates the lowest set bit | Fenwick trees, iterating set bits |
| `n >> 1`, `n << 1` | divide or multiply by 2 for non-negative `n` | halving exponents, building masks |
| `n >>> 1` | logical shift, fills with 0 | loops over all 32 bits of a possibly negative `int` |
| `mask \| (1 << position)`, `mask & ~(1 << position)`, `(mask >> position) & 1` | set, clear, test bit `position` | bitmask sets, visited sets over at most 64 items |
| `Integer.bitCount`, `Integer.highestOneBit`, `Integer.numberOfTrailingZeros` | library intrinsics | say the name, then show you know the loop too |

Counting Bits in O(n) follows from the second row: `bits[n] = bits[n & (n - 1)] + 1`, because clearing one bit leaves a smaller number whose count is already known.

**Modular arithmetic.** `(a + b) mod m = ((a mod m) + (b mod m)) mod m`, and the same for multiplication. Division does not distribute; dividing by `b` modulo a prime `m` is multiplying by `b^(m - 2) mod m` (Fermat's little theorem). Java's `%` keeps the sign of the dividend, so `-7 % 3` is `-1`; use `Math.floorMod(-7, 3)` to get `2`. Multiply in `long`: two values below 10^9 + 7 multiply to about 10^18, which fits in `long` but not in `int`.

**Fast exponentiation.** `base^exponent` in O(log exponent) multiplications: look at the exponent's bits from the lowest; keep squaring `base`; multiply the result by `base` whenever the current bit is 1. Reduce modulo `m` after every multiplication.

**Euclid.** `gcd(a, b) = gcd(b, a mod b)` until `b` is 0. O(log min(a, b)) steps. `lcm(a, b) = a / gcd(a, b) * b`, in that order to avoid overflow.

**Complexity.** Everything here is O(1) or O(32) per operation, O(log n) for exponentiation and gcd, and O(1) extra space, which is the whole reason the interviewer asked.

## Example: Single Number (136), Counting Bits (338), Number of 1 Bits (191), Reverse Bits (190), Missing Number (268)

```java
import java.util.Arrays;

public final class BitTricks {

    public int singleNumber(int[] numbers) {
        int accumulator = 0;
        for (int number : numbers) {
            accumulator ^= number;
        }
        return accumulator;
    }

    public int[] countBits(int limit) {
        int[] bitCounts = new int[limit + 1];
        for (int number = 1; number <= limit; number++) {
            bitCounts[number] = bitCounts[number & (number - 1)] + 1;
        }
        return bitCounts;
    }

    public int hammingWeight(int number) {
        int count = 0;
        while (number != 0) {
            number &= number - 1;
            count++;
        }
        return count;
    }

    public int reverseBits(int number) {
        int reversed = 0;
        for (int position = 0; position < 32; position++) {
            reversed = (reversed << 1) | (number & 1);
            number >>>= 1;
        }
        return reversed;
    }

    public int missingNumber(int[] numbers) {
        int missing = numbers.length;
        for (int index = 0; index < numbers.length; index++) {
            missing ^= index ^ numbers[index];
        }
        return missing;
    }

    public static void main(String[] arguments) {
        BitTricks tricks = new BitTricks();
        System.out.println(tricks.singleNumber(new int[] {4, 1, 2, 1, 2}));
        System.out.println(Arrays.toString(tricks.countBits(8)));
        System.out.println(tricks.hammingWeight(0b1011));
        System.out.println(tricks.hammingWeight(-1));
        System.out.println(Integer.toBinaryString(tricks.reverseBits(0b1011)));
        System.out.println(tricks.missingNumber(new int[] {3, 0, 1}));
    }
}
```

```text
$ java BitTricks.java
4
[0, 1, 1, 2, 1, 2, 2, 3, 1]
3
32
11010000000000000000000000000000
2
```

`hammingWeight(-1)` is 32 because `-1` is all ones in two's complement, and the `n & (n - 1)` loop works on negative numbers because it uses `!= 0`, not `> 0`. `reverseBits` must use `>>>=`: an arithmetic shift of a negative number would keep feeding ones in from the left and the loop would never see zeros. In Missing Number, every index in `0..n-1` and the value `n` are XORed together with every array value; each present number appears twice and cancels, the missing one appears once.

## Example: gcd, fast exponentiation and a modular inverse

```java
public final class ModularMath {

    private static final long MODULUS = 1_000_000_007L;

    public long gcd(long first, long second) {
        while (second != 0) {
            long remainder = first % second;
            first = second;
            second = remainder;
        }
        return first;
    }

    public long modularPower(long base, long exponent, long modulus) {
        long result = 1;
        base %= modulus;
        while (exponent > 0) {
            if ((exponent & 1) == 1) {
                result = result * base % modulus;
            }
            base = base * base % modulus;
            exponent >>= 1;
        }
        return result;
    }

    public long modularInverse(long value, long primeModulus) {
        return modularPower(value, primeModulus - 2, primeModulus);
    }

    public static void main(String[] arguments) {
        ModularMath math = new ModularMath();
        System.out.println(math.gcd(1071, 462));
        System.out.println(math.modularPower(2, 10, MODULUS));
        System.out.println(math.modularPower(3, 200, MODULUS));
        System.out.println(math.modularInverse(3, MODULUS));
        System.out.println(3 * math.modularInverse(3, MODULUS) % MODULUS);
        System.out.println(Math.floorMod(-7, 3) + " " + (-7 % 3));
    }
}
```

```text
$ java ModularMath.java
21
1024
136318165
333333336
1
2 -1
```

`3^200` has 96 decimal digits; the loop performs 8 squarings and never holds a value above `modulus²`. The inverse of 3 is 333333336 because 3 × 333333336 = 1000000008 = 1 × (10^9 + 7) + 1. Pow(x, n) (50) is the same loop over `double` with a negative exponent handled by inverting `x` first; take care that `-Integer.MIN_VALUE` overflows, so convert the exponent to `long` before negating.

## Pitfalls

- `>>` on negative numbers in a bit-by-bit loop. The loop never terminates or produces garbage; use `>>>` or iterate a fixed 32 times.
- `n & (n - 1) == 0` without parentheses. `==` binds tighter than `&` in Java, so this compares `n - 1` with 0 first and then ANDs the boolean, which does not compile; write `(n & (n - 1)) == 0`.
- Power-of-two check without `n > 0`. Zero and `Integer.MIN_VALUE` both pass `(n & (n - 1)) == 0`.
- Multiplying two `int` values below the modulus. 10^9 × 10^9 overflows `int` long before the `%`; do the arithmetic in `long`.
- Applying `%` once at the end. Intermediate products overflow even `long`; reduce after every multiplication.
- Negative remainders. `(a - b) % m` can be negative in Java; add `m` or use `Math.floorMod`.
- `1 << 32` or `1 << 64`. Shift counts are taken modulo the width (32 for `int`, 64 for `long`), so `1 << 32` is `1`, not 0. Use `1L << position` for positions above 30.
- Dividing modulo a non-prime. The Fermat inverse exists only when the modulus is prime and the value is not a multiple of it; for a composite modulus use the extended Euclidean algorithm, or restructure to avoid division.
- Recomputing XOR tricks as "magic". Be ready to say *why* pairs cancel (XOR is its own inverse and is commutative), because the follow-up is usually "and if every element appears three times?" (count bits per position modulo 3).

## Check yourself

1. Explain, using only the three XOR properties in the table, why `missingNumber` returns the missing value. What changes if the array may contain one duplicate instead of one missing number?
2. Why is `bits[n] = bits[n & (n - 1)] + 1` a valid recurrence, and in what order must the table be filled for it to work?
3. Trace `modularPower(3, 13, 1000)` by hand: list the exponent's bits, the base after each squaring, and when `result` is multiplied.
4. A colleague writes `(a * b) % MODULUS` with `int a` and `int b`, both below `MODULUS`, and stores the result in a `long`. Why is the result still wrong, and what is the minimal fix?

## Go deeper

- [Tech Interview Handbook: Binary cheatsheet](https://www.techinterviewhandbook.org/algorithms/binary/) · the identities above with the problems they unlock.
- [Tech Interview Handbook: Math cheatsheet](https://www.techinterviewhandbook.org/algorithms/math/) · overflow, modular arithmetic, and the "corner cases" list interviewers probe.
- [JLS 15.19: Shift Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.19) · the rule that shift counts are masked to 5 or 6 bits, and the difference between `>>` and `>>>`.

---

Part of [DSA & Interviews](../README.md) · item 5.6
