# Exceptions done right

> **In one sentence:** Throw unchecked exceptions for failures the caller cannot fix, reserve checked exceptions for conditions every caller must decide about, close resources with try-with-resources, translate low-level exceptions at layer boundaries with the cause attached and the identifiers in the message, and never swallow an exception or use one for control flow.

**Why it matters:** Exception handling is where a codebase quietly rots. An empty `catch` hides the real failure, `throw new RuntimeException(exception.getMessage())` throws away the stack trace, and a `finally` that closes a resource can replace the exception you needed with one you did not. The difference between a well-formed exception and a bad one is often an hour of production debugging, and "checked versus unchecked" is still a standard interview question.

## The idea

**The hierarchy.** `Throwable` splits into `Error` (JVM trouble such as `OutOfMemoryError` and `StackOverflowError`; do not catch these) and `Exception`. Every `Exception` is **checked** unless it extends `RuntimeException`: the compiler forces callers to catch it or declare it.

**Checked or unchecked.** Use a checked exception when the condition is a normal, foreseeable outcome that *every* caller must handle and can realistically do something about. Use an unchecked exception for programming errors (`IllegalArgumentException`, `IllegalStateException`) and for failures the caller can only report (`DataAccessException` in Spring, `UncheckedIOException`). Checked exceptions do not compose with lambdas (`Function` cannot throw one) or with layered architectures (every layer must declare them), which is why Spring, Hibernate and most modern libraries use unchecked exceptions with a documented hierarchy. When "no result" or "rejected" is an expected outcome rather than a failure, do not throw at all: return an `Optional` (see item 1.10) or a sealed result type (see item 1.6).

**try-with-resources.** Any `AutoCloseable` declared in the parentheses is closed automatically, in reverse order of declaration. If the body throws and `close()` also throws, the body's exception wins and the `close()` exception is attached to it as a **suppressed** exception, retrievable with `getSuppressed()` and printed as `Suppressed:` in the stack trace. Before Java 7, the hand-written `finally { resource.close(); }` pattern silently replaced the original exception with the one from `close()`.

**Translation at boundaries.** The repository layer catches `SQLException` and throws a domain or infrastructure exception; the HTTP layer maps domain exceptions to status codes. Always pass the original as the cause (`new OrderRepositoryException(message, exception)`), and translate once per boundary, not once per method, or you get four nested exceptions with the same message.

**Messages.** Include what is needed to reproduce: the order id, the file path, the rejected value. "Could not load order 4711" beats "Database error". Never include secrets or whole request bodies.

**Cost.** Creating an exception calls `fillInStackTrace()`, which walks the entire call stack; in a Spring application that can be hundreds of frames, which makes a thrown exception thousands of times more expensive than a returned value. Using `NumberFormatException` to test whether a string is numeric, or `NoSuchElementException` to end a loop, is therefore slow as well as unclear. HotSpot adds a twist: for implicit exceptions it throws very frequently (`NullPointerException`, `ArithmeticException`, `ArrayIndexOutOfBoundsException`, `ClassCastException`), the JIT eventually switches to preallocated instances with no stack trace at all. That is the famous `NullPointerException` with an empty stack trace in production logs; `-XX:-OmitStackTraceInFastThrow` turns the optimisation off while you investigate. If you really need a cheap exception for an expected condition, the `Throwable(String, Throwable, boolean enableSuppression, boolean writableStackTrace)` constructor lets a subclass skip the stack trace.

## Example: a repository method, before and after

Before:

```java
Order load(long orderId) {
    Connection connection = null;
    try {
        connection = dataSource.getConnection();
        PreparedStatement statement = connection.prepareStatement("SELECT id, customer_id, total FROM orders WHERE id = ?");
        statement.setLong(1, orderId);
        ResultSet resultSet = statement.executeQuery();
        resultSet.next();
        return mapRow(resultSet);
    } catch (SQLException exception) {
        throw new RuntimeException(exception.getMessage());
    } finally {
        try {
            if (connection != null) {
                connection.close();
            }
        } catch (SQLException ignored) {
        }
    }
}
```

Four problems. The statement and result set are never closed, so cursors leak until the connection is closed. `new RuntimeException(exception.getMessage())` drops the cause, the SQL state and the stack trace, and the message does not say which order failed. `resultSet.next()` is not checked, so a missing row surfaces as an obscure "ResultSet not positioned" error from `mapRow`. And an exception from `close()` is thrown away.

After:

```java
public final class OrderRepositoryException extends RuntimeException {

    public OrderRepositoryException(String message, Throwable cause) {
        super(message, cause);
    }
}

Order load(long orderId) {
    String sql = "SELECT id, customer_id, total FROM orders WHERE id = ?";
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, orderId);
        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                throw new OrderNotFoundException(orderId);
            }
            return mapRow(resultSet);
        }
    } catch (SQLException exception) {
        throw new OrderRepositoryException("Could not load order " + orderId, exception);
    }
}
```

Everything is closed in the right order, the not-found case is an explicit domain exception, and a driver failure arrives one layer up as a single exception with a useful message and the full cause chain.

## Example: suppressed exceptions

```java
import java.io.IOException;

final class Door implements AutoCloseable {

    private final String name;

    Door(String name) {
        this.name = name;
    }

    @Override
    public void close() throws IOException {
        throw new IOException("close failed for " + name);
    }
}

public class Suppressed {
    public static void main(String[] arguments) {
        try (Door front = new Door("front"); Door back = new Door("back")) {
            throw new IOException("body failed");
        } catch (IOException exception) {
            exception.printStackTrace(System.out);
        }
    }
}
```

Output:

```text
java.io.IOException: body failed
	at Suppressed.main(Suppressed.java:20)
	Suppressed: java.io.IOException: close failed for back
		at Door.close(Suppressed.java:13)
		at Suppressed.main(Suppressed.java:19)
	Suppressed: java.io.IOException: close failed for front
		at Door.close(Suppressed.java:13)
		at Suppressed.main(Suppressed.java:19)
```

The body's exception is primary, `back` is closed before `front`, and nothing is lost.

## Pitfalls

- The empty or logging-only `catch`. `catch (Exception exception) { log.error("failed"); }` without passing `exception` to the logger loses the stack trace; `return null` in a `catch` turns one failure into a later `NullPointerException`. Either handle it, rethrow it, or let it propagate.
- `catch (Exception)` around a whole method "to be safe". It also catches `NullPointerException` and `IllegalStateException`, which are bugs you wanted to see.
- Wrapping without a cause. `new ServiceException("Import failed")` thrown from a `catch` block hides the real reason. Always use the `(message, cause)` constructor.
- Catching `InterruptedException` and doing nothing. Either rethrow it or call `Thread.currentThread().interrupt()` so the interruption is not lost.
- Throwing from `finally` or returning from it. Both discard the exception that was in flight.
- Using exceptions in a hot path for expected outcomes. If a validation fails for ten percent of requests, model it as a return value.
- Checked exceptions on `@Transactional` methods. By default Spring commits on checked exceptions and rolls back only on unchecked ones (see the Spring domain); use unchecked exceptions for failures.
- Logging and rethrowing at every layer. The same stack trace appears five times in the log. Log once, where the exception is finally handled.

## Check yourself

1. Your `close()` throws and so does the body of the try-with-resources block. Which exception does the caller receive, and where did the other one go?
2. A colleague proposes a checked `OrderNotFoundException`. For which callers is that a good idea, and what breaks when the lookup is used inside a stream pipeline?
3. Why does a `NullPointerException` in a six-month-old production log sometimes have no stack trace, and what flag restores it?
4. A repository catches `SQLException` and throws `RepositoryException(message, cause)`; the service catches that and throws `ServiceException(message, cause)`; the controller catches that and throws `ApiException(message, cause)`. What is wrong with this chain and how many translations should there be?

## Go deeper

- [dev.java: Exceptions](https://dev.java/learn/exceptions/) · the official tutorial, including try-with-resources and the chained exception facility.
- [JLS 14.20.3: try-with-resources](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20.3) · the exact closing and suppression semantics, including the order resources are closed in.
- [Throwable API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html) · `addSuppressed`, `getSuppressed` and the constructor that disables stack traces.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · chapter 10 (items 69 to 77): checked versus unchecked, failure atomicity, and why you should never ignore an exception (paid).

---

Part of [Java](../README.md) · item 1.8
