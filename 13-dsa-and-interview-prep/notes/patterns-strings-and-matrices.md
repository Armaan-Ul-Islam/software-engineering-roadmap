# Patterns: strings and matrices

> **In one sentence:** String problems are solved by choosing the right representation up front (a `char[]`, a 26-slot count array, a `StringBuilder`, a length-prefixed encoding) so that each character is touched once, and matrix problems are solved by naming the four boundaries or the two transformations (transpose, reverse) instead of reasoning about individual indices.

**Why it matters:** Parsing identifiers and tokens, building responses efficiently, serialising a list of strings over the wire, rotating or walking a grid: these are daily backend tasks and the easy-looking interview questions that candidates still get wrong under time pressure. Encode and Decode Strings, Valid Anagram, Rotate Image and Spiral Matrix are all asked constantly, and each has one trap.

## The idea

### Strings

**Recognising the pattern.** Anagram, palindrome, permutation of letters, "build the output", "parse this format", "serialise and deserialise", "compress". Palindromes and reversals use two pointers (item 2.2); substrings with a constraint use a sliding window (item 2.3); grouping by anagram uses a canonical key (item 2.1). This note covers the remaining tools.

**Representation first.** Java strings are immutable, so `result += letter` in a loop copies the whole string every time and is O(n²). Convert once: `toCharArray()` for in-place work, a `StringBuilder` for building output, an `int[26]` for letter counts when the alphabet is lowercase ASCII (state that assumption), a `HashMap<Character, Integer>` otherwise.

**Counting.** An anagram check is one pass that increments for the first string and decrements for the second, then checks that every slot is zero. The same count array drives "first unique character", "can construct from letters" and "minimum window" problems.

**Building.** `StringBuilder.append` is amortised O(1); `insert(0, ...)` is O(n). When output must be built from the back (adding binary numbers, big-number addition), append and `reverse()` at the end.

**Parsing.** Walk with an index, not `split`, when the format has lengths or nested delimiters. Read a number as `number = number * 10 + (character - '0')`, and use `long` or check against `Integer.MAX_VALUE / 10` before multiplying when the input can overflow (String to Integer).

**Encodings.** To serialise a list of strings into one string that can be decoded unambiguously, prefix each string with its length and a separator: `5#hello`. Escaping a delimiter is the other option, but length prefixing needs no escaping and handles empty strings and strings that contain the separator. This is also how many binary protocols frame messages.

**Complexity.** Every operation above is O(n) time; the point of the pattern is to avoid the accidental O(n²) from immutable concatenation or `substring` in a loop (item 6.2).

### Matrices and grids

**Recognising the pattern.** A `int[][]` or `char[][]`, and a question about traversal order, rotation, searching, or marking cells. If the question is about reachability or distance between cells, it is a graph (item 4.1); this note covers the geometric ones.

**Traversal with boundaries.** Spiral order keeps four variables `top`, `bottom`, `left`, `right` and shrinks one after each side. The two inner sides are guarded by `if (top <= bottom)` and `if (left <= right)` so that a single leftover row or column is not emitted twice.

**Rotation as composition.** Rotating a square matrix 90° clockwise is transpose (swap `matrix[row][column]` with `matrix[column][row]` above the diagonal) followed by reversing each row. Anticlockwise is transpose then reverse each column. Reasoning this way avoids the four-way cell swap and its index arithmetic.

**Searching.** A matrix with sorted rows and sorted columns is searched from the top-right corner: move left when the value is too large, down when too small, O(rows + columns). A fully sorted matrix (each row continues the previous) is one binary search over `rows × columns` virtual indices (item 2.5).

**Marking in place.** Set Matrix Zeroes uses the first row and column as the marker arrays, with two booleans for the first row and column themselves, giving O(1) extra space.

**Complexity.** Spiral and rotation are O(rows × columns) time; rotation and in-place marking are O(1) extra space.

## Example: Encode and Decode Strings (271) and Valid Anagram (242)

```java
import java.util.ArrayList;
import java.util.List;

public final class StringCodec {

    public String encode(List<String> words) {
        StringBuilder encoded = new StringBuilder();
        for (String word : words) {
            encoded.append(word.length()).append('#').append(word);
        }
        return encoded.toString();
    }

    public List<String> decode(String encoded) {
        List<String> words = new ArrayList<>();
        int position = 0;
        while (position < encoded.length()) {
            int separator = encoded.indexOf('#', position);
            int length = Integer.parseInt(encoded.substring(position, separator));
            int wordStart = separator + 1;
            words.add(encoded.substring(wordStart, wordStart + length));
            position = wordStart + length;
        }
        return words;
    }

    public boolean isAnagram(String first, String second) {
        if (first.length() != second.length()) {
            return false;
        }
        int[] letterBalance = new int[26];
        for (int index = 0; index < first.length(); index++) {
            letterBalance[first.charAt(index) - 'a']++;
            letterBalance[second.charAt(index) - 'a']--;
        }
        for (int balance : letterBalance) {
            if (balance != 0) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] arguments) {
        StringCodec codec = new StringCodec();
        List<String> words = List.of("hello", "#world", "", "12#34");
        String encoded = codec.encode(words);
        System.out.println(encoded);
        System.out.println(codec.decode(encoded));
        System.out.println(codec.decode(encoded).equals(words));
        System.out.println(codec.isAnagram("anagram", "nagaram"));
        System.out.println(codec.isAnagram("rat", "car"));
    }
}
```

```text
$ java StringCodec.java
5#hello6##world0#5#12#34
[hello, #world, , 12#34]
true
true
false
```

The test list is chosen to break naive delimiters: a word starting with `#`, an empty word, and a word containing `#`. The decoder never searches for `#` inside a word, because it always jumps `length` characters after reading the prefix. Both methods are O(total characters).

## Example: Rotate Image (48) and Spiral Matrix (54)

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class MatrixTricks {

    public void rotate(int[][] matrix) {
        int size = matrix.length;
        for (int row = 0; row < size; row++) {
            for (int column = row + 1; column < size; column++) {
                int swapped = matrix[row][column];
                matrix[row][column] = matrix[column][row];
                matrix[column][row] = swapped;
            }
        }
        for (int[] row : matrix) {
            for (int left = 0, right = size - 1; left < right; left++, right--) {
                int swapped = row[left];
                row[left] = row[right];
                row[right] = swapped;
            }
        }
    }

    public List<Integer> spiralOrder(int[][] matrix) {
        List<Integer> order = new ArrayList<>();
        int top = 0;
        int bottom = matrix.length - 1;
        int left = 0;
        int right = matrix[0].length - 1;
        while (top <= bottom && left <= right) {
            for (int column = left; column <= right; column++) {
                order.add(matrix[top][column]);
            }
            top++;
            for (int row = top; row <= bottom; row++) {
                order.add(matrix[row][right]);
            }
            right--;
            if (top <= bottom) {
                for (int column = right; column >= left; column--) {
                    order.add(matrix[bottom][column]);
                }
                bottom--;
            }
            if (left <= right) {
                for (int row = bottom; row >= top; row--) {
                    order.add(matrix[row][left]);
                }
                left++;
            }
        }
        return order;
    }

    public static void main(String[] arguments) {
        MatrixTricks tricks = new MatrixTricks();
        int[][] square = {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}};
        tricks.rotate(square);
        System.out.println(Arrays.deepToString(square));
        System.out.println(tricks.spiralOrder(new int[][] {{1, 2, 3, 4}, {5, 6, 7, 8}, {9, 10, 11, 12}}));
        System.out.println(tricks.spiralOrder(new int[][] {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}}));
        System.out.println(tricks.spiralOrder(new int[][] {{1}, {2}, {3}}));
    }
}
```

```text
$ java MatrixTricks.java
[[7, 4, 1], [8, 5, 2], [9, 6, 3]]
[1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7]
[1, 2, 3, 6, 9, 8, 7, 4, 5]
[1, 2, 3]
```

The single-column case `{{1}, {2}, {3}}` is the one that exposes a missing guard: after the first two sides, `right` becomes -1 and `left` is 0, so without `if (left <= right)` the last loop would walk back up the same column and emit `2` a second time. The transpose loop starts `column` at `row + 1` so that each pair is swapped exactly once; starting at 0 would swap every pair twice and leave the matrix unchanged.

## Pitfalls

- String concatenation in a loop. Fine for ten characters, O(n²) for a hundred thousand; the symptom is a time limit on a correct algorithm. Use `StringBuilder`.
- `charAt(index) - 'a'` on input that is not lowercase. State the alphabet assumption or use a map; an `ArrayIndexOutOfBoundsException` on a space or an uppercase letter is a classic mock-interview failure.
- Comparing strings with `==`. Interned literals make it look like it works in tests; use `equals`.
- Delimiter-only encoding. `"a#b"` and `["a", "b"]` collide with `["a#b"]`; either escape or length-prefix.
- `split` on a regular expression you did not intend. `split(".")` splits on any character, `split("|")` on every position; quote with `Pattern.quote` or walk with an index.
- Forgetting the two inner guards in spiral order. Works on square and most rectangular inputs, duplicates on a single row or column.
- Rotating with a fresh matrix when the problem says in place. Correct output, wrong space complexity, and the interviewer will ask.
- Transposing the whole matrix instead of the upper triangle. Each pair is swapped back, the matrix is unchanged, and the test still passes for symmetric inputs.
- `int[][]` rows that are not all the same length. `matrix[0].length` is the column count only for rectangular matrices; say the assumption.

## Check yourself

1. Why does `result += letter` in a loop cost O(n²), and what does `StringBuilder` do differently? Where is the one place in a `StringBuilder` workflow that still costs O(n) per call?
2. The length-prefix encoding uses `#` as a separator. Explain why the decoder is still correct when a word contains `#`, and what would break if the length were written in binary without a separator.
3. Derive the anticlockwise rotation as a composition of transpose and one reversal, and check it on the 3 × 3 example.
4. Spiral Matrix II asks you to fill an n × n matrix in spiral order with 1..n². Which lines of `spiralOrder` change, and do the two inner guards still matter when the matrix is square?

## Go deeper

- [Tech Interview Handbook: String cheatsheet](https://www.techinterviewhandbook.org/algorithms/string/) · representation choices, the count-array trick and the corner cases (empty, one character, Unicode).
- [Tech Interview Handbook: Matrix cheatsheet](https://www.techinterviewhandbook.org/algorithms/matrix/) · creating a copy, transposition, and the traversal templates.
- [NeetCode roadmap](https://neetcode.io/roadmap) · Encode and Decode Strings, Rotate Image and Spiral Matrix with video solutions, under Arrays & Hashing and Math & Geometry.

---

Part of [DSA & Interviews](../README.md) · items 2.7, 2.8
