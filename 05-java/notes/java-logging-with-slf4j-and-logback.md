# Logging with SLF4J and Logback

> **In one sentence:** Code logs through the SLF4J API (`LoggerFactory.getLogger`, `{}` placeholders, the exception as the last argument, MDC for request context) and one binding, usually Logback, decides at run time what is written where and at which level; every other logging API on the classpath is bridged into SLF4J so that one configuration file governs everything.

**Why it matters:** Logs are the first and often only evidence in an incident, and they are also a well-known way to make a service slow (string concatenation at `DEBUG` in a hot loop, synchronous file appenders under load) or useless (stack traces lost because the exception was passed as a placeholder, three libraries each logging through a different framework with its own config). The whole subject fits in one note because the rules are few; the mistakes are just common.

## The idea

**The split.** SLF4J (Simple Logging Facade for Java) is an API with no output of its own: `Logger`, `LoggerFactory`, `MDC`, `Marker`. A *provider* (SLF4J 2.x looks it up with `ServiceLoader`; 1.x used a static binder class) implements it: Logback is the native one, written by the same author; `slf4j-simple` prints to stderr; `log4j-slf4j2-impl` routes to Log4j 2; `slf4j-jdk14` routes to `java.util.logging`. Exactly one provider belongs on the classpath. With two, SLF4J 2.x prints `Class path contains multiple SLF4J providers` and picks one; with none, `No SLF4J providers were found` and everything is discarded.

**Bridges** make the other APIs flow into SLF4J: `jul-to-slf4j` (plus `SLF4JBridgeHandler.install()` in code or Logback's `LevelChangePropagator` so that disabled JUL levels cost nothing), `jcl-over-slf4j` for Commons Logging, `log4j-over-slf4j` for Log4j 1, and `log4j-to-slf4j` for the Log4j 2 API. Spring Boot's `spring-boot-starter-logging` is exactly this set with Logback, which is why a Boot application has one `logback-spring.xml` and no per-library configuration.

**Using the API.**

```java
private static final Logger LOGGER = LoggerFactory.getLogger(OrderService.class);

LOGGER.info("order placed id={} items={}", order.id(), order.items());
LOGGER.error("charge failed for {}", order.id(), exception);
```

Placeholders are filled only if the level is enabled, so no string is built for a disabled `DEBUG` line; but the *arguments* are still evaluated, so `LOGGER.debug("{}", expensive())` calls `expensive()` regardless. Guard with `isDebugEnabled()` or, in SLF4J 2.x, pass a `Supplier` through the fluent API: `LOGGER.atDebug().addArgument(() -> expensive()).log("{}")`. An exception passed as the last argument, beyond the placeholders, is logged with its stack trace. The fluent API also carries structured key-value pairs: `LOGGER.atInfo().addKeyValue("orderId", id).log("charging")`.

**MDC** (mapped diagnostic context) is a per-thread map that appenders can print on every line: put `requestId`, `userId` or `orderId` in once, at the edge (a servlet filter, a message listener), and every log line from that thread carries it. It is a `ThreadLocal`, so it does not follow work to another thread or executor; copy it with `MDC.getCopyOfContextMap()` and `setContextMap` in the task, or use a framework that does (Micrometer's context propagation, Spring's `TaskDecorator`). Remove what you put, or use `MDC.putCloseable` in try-with-resources, because pooled threads keep their map otherwise.

**Logback configuration.** `logback.xml` on the classpath (`logback-test.xml` wins if present, which is how tests get their own levels). Loggers form a hierarchy by name: `demo.PaymentGateway` inherits the level and appenders of `demo`, which inherits from `root`, unless `additivity="false"`. Levels are `TRACE < DEBUG < INFO < WARN < ERROR`. Appenders: `ConsoleAppender`, `RollingFileAppender` with `SizeAndTimeBasedRollingPolicy`, and `AsyncAppender`, which wraps another appender with a queue so the logging thread does not wait on disk (it drops `TRACE`, `DEBUG` and `INFO` events when the queue is 80% full unless `discardingThreshold` is 0, and blocks when full unless `neverBlock` is true). In containers, log to the console in JSON and let the platform ship it; `logstash-logback-encoder` is the usual encoder, and Spring Boot 3.4 and later can emit ECS or Logstash JSON with `logging.structured.format.console`.

## Example

```xml
<configuration>
  <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
    <encoder>
      <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] %logger{36} %X{orderId} %kvp - %msg%n</pattern>
    </encoder>
  </appender>
  <logger name="demo.PaymentGateway" level="DEBUG"/>
  <root level="INFO">
    <appender-ref ref="CONSOLE"/>
  </root>
</configuration>
```

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public class LoggingDemo {

    private static final Logger LOGGER = LoggerFactory.getLogger(LoggingDemo.class);
    private static final Logger GATEWAY_LOGGER = LoggerFactory.getLogger("demo.PaymentGateway");

    record Order(String id, int items) {}

    static String expensiveSummary() {
        LOGGER.warn("expensiveSummary() was evaluated");
        return "summary";
    }

    public static void main(String[] arguments) {
        Order order = new Order("o-42", 3);
        LOGGER.info("order placed id={} items={}", order.id(), order.items());
        LOGGER.debug("not shown: root is INFO, summary={}", expensiveSummary());
        LOGGER.debug("not shown either, but the argument is still built: " + expensiveSummary());
        GATEWAY_LOGGER.debug("shown: this logger is DEBUG");

        try (MDC.MDCCloseable ignored = MDC.putCloseable("orderId", order.id())) {
            LOGGER.info("charging card");
            try {
                throw new IllegalStateException("gateway timeout");
            } catch (IllegalStateException exception) {
                LOGGER.error("charge failed for {}", order.id(), exception);
                LOGGER.error("charge failed for {} {}", order.id(), exception);
            }
        }
        LOGGER.info("after MDC scope");
        LOGGER.atInfo().addKeyValue("orderId", order.id()).addKeyValue("items", order.items()).log("fluent api");
    }
}
```

With `slf4j-api` 2.0 and `logback-classic` 1.5 on the classpath (the class is in package `demo`):

```text
11:50:01.329 INFO  [main] demo.LoggingDemo   - order placed id=o-42 items=3
11:50:01.330 WARN  [main] demo.LoggingDemo   - expensiveSummary() was evaluated
11:50:01.330 WARN  [main] demo.LoggingDemo   - expensiveSummary() was evaluated
11:50:01.330 DEBUG [main] demo.PaymentGateway   - shown: this logger is DEBUG
11:50:01.331 INFO  [main] demo.LoggingDemo o-42  - charging card
11:50:01.331 ERROR [main] demo.LoggingDemo o-42  - charge failed for o-42
java.lang.IllegalStateException: gateway timeout
	at demo.LoggingDemo.main(LoggingDemo.java:29)
11:50:01.331 ERROR [main] demo.LoggingDemo o-42  - charge failed for o-42 {}
java.lang.IllegalStateException: gateway timeout
	at demo.LoggingDemo.main(LoggingDemo.java:29)
11:50:01.332 INFO  [main] demo.LoggingDemo   - after MDC scope
11:50:01.333 INFO  [main] demo.LoggingDemo  orderId="o-42" items="3" - fluent api
```

Reading it: the two `WARN` lines prove that both `debug` calls evaluated `expensiveSummary()` even though neither was printed; the placeholder form saved only the string concatenation. The `orderId` column appears for exactly the lines inside the MDC scope. The second `error` call had one placeholder too many: SLF4J still treated the trailing exception as the throwable and left the `{}` in the message, which is lenient of it, but a `{}` in a log line is a sign of a call site to fix. The fluent key-value pairs are rendered by `%kvp`, and by a JSON encoder as fields, which is the point of them.

## Pitfalls

- String concatenation in the message. `LOGGER.debug("order " + order)` builds the string (and calls `order.toString()`, which may load lazy collections) whether or not `DEBUG` is on. Use placeholders; guard genuinely expensive arguments.
- The exception as a placeholder argument. `LOGGER.error("failed: {}", exception)` prints only `exception.toString()`, no stack trace. Pass it as the extra last argument, with a message that says what was being attempted.
- Logging and rethrowing. The same failure is logged at every layer, five stack traces for one error. Log where the exception is handled, or where it leaves your code; add context by wrapping, not by logging (see item 1.8).
- Two providers, or none. Look at the first lines of start-up output; `mvn dependency:tree` shows which transitive dependency dragged in the second one (commonly `logback-classic` plus `log4j-slf4j2-impl` via a client library). Exclude it (see item 6.2).
- `DEBUG` on the root logger in production. Hibernate, Netty and the HTTP client will log every statement and every frame. Raise levels per logger name, and change them at run time (Spring Boot's `/actuator/loggers`) rather than redeploying.
- MDC leaking between requests. A pooled thread keeps its MDC; the next request logs the previous user's id. Clear in a `finally`, or use `putCloseable`.
- MDC not following async work. `CompletableFuture.supplyAsync`, `@Async` and executor tasks start with an empty MDC. Copy the map into the task or use the framework's propagation support. With virtual threads the map is per virtual thread and the same copying applies.
- Synchronous file appenders under load. Every log call waits for the disk; a slow disk makes the service slow. `AsyncAppender`, or console output collected by the platform.
- Logging secrets and personal data. Tokens in `Authorization` headers, card numbers in request bodies, e-mail addresses in `toString`. Mask at the source, and treat `toString` of request objects as a liability.
- `System.out.println` and `printStackTrace()`. They bypass levels, appenders and JSON encoding, and under a container runtime they interleave with real log lines. Route them through SLF4J or delete them.

## Check yourself

1. `LOGGER.debug("state={}", computeState())` is called a million times at `INFO` level. What work is done, what is skipped, and what are two ways to skip the rest?
2. The log shows `charge failed: java.net.SocketTimeoutException` with no stack trace. What does the call site look like, and what is the one-token fix?
3. Requests in a thread pool sometimes log the wrong `userId`. Explain the mechanism and two fixes.
4. Start-up prints `Class path contains multiple SLF4J providers`. How do you find which dependency brought the second one, and what is the risk of leaving it?

## Go deeper

- [SLF4J manual](https://www.slf4j.org/manual.html) · short, and covers placeholders, the fluent API, MDC and the binding mechanism from the author.
- [Logback manual](https://logback.qos.ch/manual/index.html) · configuration, appenders, encoders, `AsyncAppender` and the pattern layout; chapter 3 is the one to read.
- [Spring Boot: Logging](https://docs.spring.io/spring-boot/reference/features/logging.html) · the starter's defaults, `logback-spring.xml`, structured logging and run-time level changes.

---

Part of [Java](../README.md) · item 3.6
