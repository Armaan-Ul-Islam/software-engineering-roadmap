# Debugging as a method

> **In one sentence:** Debugging is the scientific method applied to a program: get a reliable reproduction, read the evidence you already have (the stack trace from its first line and its last `Caused by`), form one hypothesis at a time, design the cheapest test that would falsify it, and narrow the search space by halving (bisect) rather than by guessing.

**Why it matters:** The difference between a two-hour and a two-day bug is almost never cleverness. It is whether the engineer reproduced it before changing anything, read the whole stack trace, and changed one thing at a time. Interviewers probe this with "tell me about a hard bug", and what they listen for is the method.

## The idea

Debugging goes wrong in predictable ways: changing code before understanding the failure, trusting a description of the bug instead of observing it, and holding several hypotheses at once so that no experiment is conclusive. The method below is a defence against each.

1. **Reproduce.** Get the failure to happen on demand, as small and as fast as you can: a failing test, a `curl` command, a one-row input file. Until you can reproduce it, you cannot know whether a change fixed it. A bug that "only happens in production" has a difference between production and your machine (data, concurrency, time zone, configuration, versions), and finding that difference is the first sub-problem, not a reason to guess.
2. **Read the evidence.** The stack trace, the log line before the error, the exit code, the HTTP status, the database error code. Most bugs are already explained by evidence nobody read carefully. The two rules for a Java stack trace are below.
3. **One hypothesis, one experiment.** State what you think is wrong in a form that could be false ("the request reaches the service with an empty body"). Design the cheapest observation that would settle it (log the body length). Run it. If the hypothesis survives, narrow it; if it dies, discard it completely and form the next one. Changing two things at once tells you nothing about either.
4. **Bisect.** When the search space is large (which commit, which input row, which of 40 configuration flags), halve it. `git bisect` does this across commits: mark a good and a bad commit, it checks out the middle, you say good or bad, repeat; 1,000 commits take ten steps. The same idea works on data (does the first half of the file reproduce it?) and on code (comment out half the pipeline).
5. **Instrument.** When reading is not enough, make the program tell you what it is doing: a log line with the variables that matter, a debugger breakpoint with a condition, a metric. Add instrumentation around the suspected point, not everywhere. Remove or downgrade it after.
6. **Confirm the fix, then ask why it was possible.** The fix must make the reproduction pass and a reversed fix must make it fail again. Then: which test would have caught this, and what other code has the same shape?

**Reading a Java stack trace.** Two rules. First, the top line of each block is where the exception was *created*, and the frames below it are the call path that got there, innermost first; the first frame in *your* package is where to look. Second, with a chain of `Caused by`, the *last* one is the root cause; the ones above it are wrappers added on the way up. Read the first line of the first block for the symptom, then jump to the last `Caused by` for the cause, then find your own frames in between.

## Example: a failing import and a stack trace read correctly

```java
import java.util.List;
import java.util.Map;

public final class OrderImport {

    public static void main(String[] arguments) {
        List<Map<String, String>> rows = List.of(
                Map.of("id", "1001", "customer", "acme", "total", "199.00"),
                Map.of("id", "1002", "customer", "globex", "total", "1 250,00"));
        for (Map<String, String> row : rows) {
            importRow(row);
        }
    }

    private static void importRow(Map<String, String> row) {
        try {
            OrderTotal total = parseTotal(row);
            System.out.println("imported " + row.get("id") + " total " + total.cents());
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("could not import order " + row.get("id"), exception);
        }
    }

    private static OrderTotal parseTotal(Map<String, String> row) {
        String total = row.get("total");
        try {
            return new OrderTotal(Math.round(Double.parseDouble(total) * 100));
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException("bad total '" + total + "'", exception);
        }
    }

    private record OrderTotal(long cents) {
    }
}
```

```text
$ javac -d out OrderImport.java && java -cp out OrderImport
imported 1001 total 19900
Exception in thread "main" java.lang.IllegalStateException: could not import order 1002
	at OrderImport.importRow(OrderImport.java:20)
	at OrderImport.main(OrderImport.java:11)
Caused by: java.lang.IllegalArgumentException: bad total '1 250,00'
	at OrderImport.parseTotal(OrderImport.java:29)
	at OrderImport.importRow(OrderImport.java:17)
	... 1 more
Caused by: java.lang.NumberFormatException: For input string: "1 250,00"
	at java.base/jdk.internal.math.FloatingDecimal.check(FloatingDecimal.java:2324)
	at java.base/jdk.internal.math.FloatingDecimal.readJavaFormatString(FloatingDecimal.java:1969)
	at java.base/jdk.internal.math.FloatingDecimal.parseDouble(FloatingDecimal.java:110)
	at java.base/java.lang.Double.parseDouble(Double.java:971)
	at OrderImport.parseTotal(OrderImport.java:27)
	... 2 more
```

The `... N more` lines are frames identical to the enclosing trace, elided to save space; the full path is always recoverable from the block above.

Reading it with the two rules: the first line says *which order* failed (1002), useful for the reproduction. The last `Caused by` says *what* failed: `Double.parseDouble` rejected `"1 250,00"`, a Norwegian-formatted number with a space as thousands separator and a comma as decimal mark. The first frame of our own code under it, `OrderImport.parseTotal(OrderImport.java:27)`, is the line to look at. Everything in between is the JDK's parser internals, which are not the bug. A hypothesis that survives this reading: "the export that produces the file uses the locale of the exporting user". The experiment: find a second row from the same exporter and check the format. The fix is at the boundary (parse with a declared format, or reject the row with a message), and the regression test is this one-row input.

An earlier version of this program had a different bug: the row had no `total` key at all. The trace then began with `NullPointerException: Cannot invoke "String.length()" because "in" is null` at the top of `Double.parseDouble`, with *no* `Caused by` chain, because `NullPointerException` is not a `NumberFormatException` and the catch never ran. Reading only the message would have sent you looking for a `length()` call; reading the first own-code frame, again line 27, shows that `total` itself was null, and the helpful NPE message (on by default since JDK 15) names the null variable.

Bisecting a regression, in commands:

```bash
git bisect start
git bisect bad                      # current commit fails
git bisect good v2.2.0              # last known good release
git bisect run ./gradlew test --tests OrderImportTest
```

`git bisect run` repeats the test at each midpoint and stops on the first bad commit. Ten steps cover a thousand commits. If the test is slow, make a faster reproduction first; the method rewards investment in step 1.

## Pitfalls

- Fixing the symptom at the top of the trace. Catching the `IllegalStateException` and continuing hides a data problem that will reappear elsewhere. Find the last `Caused by`.
- Debugging from a description. "The import is broken" is not a reproduction. Get the input, the command and the output before touching code.
- Changing several things, then it works. Nothing was learned, and one of those changes is probably unnecessary and possibly harmful. Revert and reapply one at a time.
- Printing everything. Thousands of log lines hide the one that matters. Instrument at the hypothesis, with the specific values, and delete it afterwards.
- Reading the first own-code frame but ignoring the message. The message often contains the exact value (`"1 250,00"`) that explains the bug without any further experiment.
- Searching the error text before reading it. A web search for `NumberFormatException` returns a million results; the string in the message tells you more than any of them.
- Stopping at "works now". Without a regression test and an answer to "why was this possible", the bug returns in a different file.

## Check yourself

1. A stack trace has three `Caused by` blocks. Which one do you read first for the cause, and which line in the whole trace tells you where in your code to look?
2. A bug appears in production and not locally. Name four categories of difference to investigate, and say which you would check first for a date-formatting bug.
3. You have 2,000 commits between a good and a bad build and a test that takes 3 minutes. How long does `git bisect run` take, roughly, and what would you do first to make it cheaper?
4. In the example, the NPE version of the bug had no `Caused by`. Why, and what does that tell you about catching `IllegalArgumentException` to wrap parse failures?

## Go deeper

- [Debugging: The 9 Indispensable Rules](https://debuggingrules.com/) · the method as nine rules with war stories; "Make it fail" and "Quit thinking and look" are the two most people skip.
- [Pro Git: Debugging with Git](https://git-scm.com/book/en/v2/Git-Tools-Debugging-with-Git) · `git bisect` and `git blame` with examples, including `bisect run`.
- [The Missing Semester: Debugging and Profiling](https://missing.csail.mit.edu/2020/debugging-profiling/) · logging, debuggers, `strace` and profilers, with exercises.
- [Julia Evans' blog](https://jvns.ca/) · dozens of short, concrete debugging stories that show the method in use.

---

Part of [Foundations](../README.md) · item 7.3
