# Patterns: stack and monotonic stack

> **In one sentence:** A stack answers "what is the most recent thing still waiting to be matched?", which solves bracket matching and parsing directly, and a stack kept in sorted order (a monotonic stack) answers "for each element, where is the next greater or smaller one?" in O(n), because every element is pushed once and popped at most once.

**Why it matters:** Parsing nested structure (brackets, expressions, paths, nested JSON by hand) comes up in both interviews and real code, and the stack is the whole trick. The monotonic stack is the non-obvious half: it replaces the O(n^2) "scan right until you find something bigger" with a linear pass, and interviewers use Daily Temperatures and Largest Rectangle in Histogram to see whether you know it.

## The idea

**Recognising the pattern.** Matching: "valid parentheses", "balanced", "nested", "evaluate the expression", "decode the string", "simplify the path", "undo". Monotonic: "next greater element", "previous smaller element", "days until a warmer temperature", "stock span", "largest rectangle", "trapping rain water", "remove k digits to make the smallest number". The tell is a question asked for *every* element about the nearest element to one side that beats it.

**Matching template.** Push every opener. On a closer, the stack must be non-empty and its top must be the matching opener; pop it. At the end the stack must be empty. Use `ArrayDeque`, not `java.util.Stack` (item 6.1).

**Monotonic stack template (next greater element to the right).** Walk left to right keeping a stack of indices whose values are decreasing from bottom to top. Each new element pops every smaller top, and the element that popped it is its answer.

```java
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;

public final class NextGreaterElement {

    static int[] nextGreaterIndex(int[] values) {
        int[] answer = new int[values.length];
        Arrays.fill(answer, -1);
        Deque<Integer> unresolved = new ArrayDeque<>();
        for (int index = 0; index < values.length; index++) {
            while (!unresolved.isEmpty() && values[unresolved.peek()] < values[index]) {
                answer[unresolved.pop()] = index;
            }
            unresolved.push(index);
        }
        return answer;
    }
}
```

The variants are one comparison away: pop while the top is *greater* for "next smaller"; after popping, the new top is the *previous* greater (or smaller) element, so one pass can produce both neighbours; use `<=` to treat equal values as "beaten" when the problem wants greater-or-equal. Store indices, not values, because distances and widths need positions.

**Complexity.** O(n) time for all three problems below, because each index enters and leaves the stack at most once, so the nested `while` executes at most `n` times in total. O(n) space for the stack.

## Example: Valid Parentheses (20)

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

public final class ValidParentheses {

    private static final Map<Character, Character> OPENER_FOR_CLOSER = Map.of(')', '(', ']', '[', '}', '{');

    public boolean isValid(String input) {
        Deque<Character> openers = new ArrayDeque<>();
        for (char character : input.toCharArray()) {
            Character expectedOpener = OPENER_FOR_CLOSER.get(character);
            if (expectedOpener == null) {
                openers.push(character);
            } else if (openers.isEmpty() || !expectedOpener.equals(openers.pop())) {
                return false;
            }
        }
        return openers.isEmpty();
    }
}
```

`"([]{})"` is valid, `"(]"` fails at the `]`, `"(("` fails at the end because two openers are still waiting, and `")"` fails because there is nothing to pop. The `isEmpty` check before `pop` matters: `ArrayDeque.pop()` throws `NoSuchElementException` on an empty deque.

## Example: Daily Temperatures (739)

For each day, how many days until a warmer one (0 if none). This is "next greater element" with the answer expressed as a distance.

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class DailyTemperatures {

    public int[] dailyTemperatures(int[] temperatures) {
        int[] daysToWait = new int[temperatures.length];
        Deque<Integer> unresolvedDays = new ArrayDeque<>();
        for (int day = 0; day < temperatures.length; day++) {
            while (!unresolvedDays.isEmpty() && temperatures[unresolvedDays.peek()] < temperatures[day]) {
                int resolvedDay = unresolvedDays.pop();
                daysToWait[resolvedDay] = day - resolvedDay;
            }
            unresolvedDays.push(day);
        }
        return daysToWait;
    }
}
```

Trace for `[73, 74, 75, 71, 69, 72, 76, 73]`; the stack is shown bottom to top as indices:

| day | temperature | popped (answer) | stack after |
|---|---|---|---|
| 0 | 73 | | 0 |
| 1 | 74 | 0 (1) | 1 |
| 2 | 75 | 1 (1) | 2 |
| 3 | 71 | | 2, 3 |
| 4 | 69 | | 2, 3, 4 |
| 5 | 72 | 4 (1), 3 (2) | 2, 5 |
| 6 | 76 | 5 (1), 2 (4) | 6 |
| 7 | 73 | | 6, 7 |

Days 6 and 7 are never popped and keep the default 0. Result: `[1, 1, 4, 2, 1, 1, 0, 0]`. Note the stack is always decreasing in temperature from bottom to top; that is the invariant that makes the top the right thing to compare against.

## Example: Largest Rectangle in Histogram (84)

The rectangle of height `heights[index]` extends left to the previous shorter bar and right to the next shorter bar. A stack that is *increasing* from bottom to top gives both at once: when a lower bar arrives, the popped bar's right boundary is the current index and its left boundary is the new top. A sentinel height of 0 at the end flushes the stack.

```java
import java.util.ArrayDeque;
import java.util.Deque;

public final class LargestRectangleInHistogram {

    public int largestRectangleArea(int[] heights) {
        Deque<Integer> risingBars = new ArrayDeque<>();
        int best = 0;
        for (int index = 0; index <= heights.length; index++) {
            int currentHeight = index == heights.length ? 0 : heights[index];
            while (!risingBars.isEmpty() && heights[risingBars.peek()] > currentHeight) {
                int height = heights[risingBars.pop()];
                int leftBoundary = risingBars.isEmpty() ? -1 : risingBars.peek();
                int width = index - leftBoundary - 1;
                best = Math.max(best, height * width);
            }
            risingBars.push(index);
        }
        return best;
    }
}
```

For `[2, 1, 5, 6, 2, 3]` the answer is 10: when the 2 at index 4 arrives, the 6 pops with width 1 (area 6) and then the 5 pops with left boundary index 1 and width `4 - 1 - 1 = 2` (area 10). Equal heights are handled by the strict `>`: the earlier of two equal bars stays on the stack and gets the full width when the sentinel flushes it. The maximum area, 10^4 height times 10^5 width, fits in an `int`.

## Pitfalls

- `java.util.Stack`. It is synchronised, extends `Vector`, and iterates bottom to top, which surprises anyone who prints it. Use `Deque<T> stack = new ArrayDeque<>()` with `push`, `pop`, `peek`.
- `peek()` and `poll()` return `null` on an empty `ArrayDeque`, while `pop()` and `remove()` throw. Unboxing a `null` `Integer` from `peek()` gives a `NullPointerException` far from the cause; check `isEmpty()` first.
- Storing values instead of indices. You cannot compute "days to wait" or a rectangle width from values.
- The wrong strictness in the pop condition. `<` versus `<=` decides how equal elements are treated; decide from the problem statement, then test with a repeated value.
- Forgetting to flush. Elements still on the stack at the end either keep a default (Daily Temperatures) or need a sentinel pass (Largest Rectangle). Leaving them unprocessed is a wrong answer only on inputs that end high.
- Comparing boxed characters or integers with `==`. `Character` values are cached for ASCII, so `!=` on brackets happens to work; the same code with `Integer` above 127 does not. Use `equals` or unbox.
- Calling the nested `while` O(n^2). Each index is popped at most once; say "amortised O(n)".
- `ArrayDeque` rejects `null`. Pushing a `null` sentinel throws; use a sentinel index such as -1 or a sentinel value instead.

## Check yourself

1. In Daily Temperatures, state the invariant the stack maintains and explain why comparing only against the top is enough to find the next warmer day for every popped index.
2. Change `nextGreaterIndex` so it returns, for each element, the index of the previous smaller element. What is the pop condition, and where does the answer come from?
3. Why does Largest Rectangle need the sentinel iteration `index == heights.length`, and what inputs would give a wrong answer without it?
4. Using the monotonic stack idea, how would you remove `k` digits from a number string to make it as small as possible (Remove K Digits, 402)? What do you pop, and what do you do with the leftover `k` at the end?

## Go deeper

- [Tech Interview Handbook: Stack cheatsheet](https://www.techinterviewhandbook.org/algorithms/stack/) · the stack problems that come up most and the corner cases to mention.
- [ArrayDeque (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ArrayDeque.html) · which methods throw and which return `null`, and the table mapping stack and queue operations to deque methods.
- [Baeldung: Guide to the Java ArrayDeque](https://www.baeldung.com/java-array-deque) · how `ArrayDeque` works as both stack and queue, and why it replaces `Stack` and `LinkedList`.

---

Part of [DSA & Interviews](../README.md) · item 2.4
