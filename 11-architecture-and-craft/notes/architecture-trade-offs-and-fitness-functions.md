# Architecture characteristics, trade-off analysis, and fitness functions

> **In one sentence:** An architecture is chosen by deciding which few characteristics (availability, performance, deployability, testability, and the rest of the "-ilities") matter most for this system, analysing how each option trades them against each other, recording the decision, and then writing fitness functions, automated checks that fail the build or page someone when the architecture drifts from the characteristics it was chosen for.

**Why it matters:** "Should we use microservices?" has no answer; "we need independent deployability for three teams and can accept eventual consistency between orders and billing" does. Richards and Ford's first law of software architecture is that everything is a trade-off, and the second is that *why* matters more than *how*. The engineers who get asked to decide are the ones who can name the trade-off, and the systems that stay healthy are the ones where the chosen characteristics are enforced by a test rather than by a slide.

## The idea

**Architecture characteristics.** The non-functional properties a system must have, separate from the domain requirements. Richards and Ford group them loosely:

| Group | Examples |
|---|---|
| Operational | availability, performance, scalability, elasticity, recoverability, robustness |
| Structural | modularity, testability, deployability, maintainability, configurability, extensibility |
| Cross-cutting | security, privacy, accessibility, legal and regulatory, cost |

Two rules follow. Pick few: every characteristic you optimise for costs you in another, so a list of twelve "critical" ones is a list of none; aim for the three to seven that would make the system fail if missing. And derive them from the domain, not from fashion: "merchants must see an order within a second of its placement" is a performance characteristic with a number; "we want high performance" is not.

**Trade-off analysis.** *Software Architecture: The Hard Parts* is built on one sentence: there are no best practices in architecture, only trade-offs, and the job is to find the least worst option for this context. The method is mechanical:

1. Identify what is entangled: which parts of the system or which characteristics the decision affects (coupling, data ownership, consistency, team boundaries).
2. For each option, list how it affects each characteristic that matters, positively and negatively, in a table.
3. Decide, and write the decision down with its consequences, including what you gave up (item 9.2). "We chose X because it is best" is not a trade-off analysis; "we chose X, accepting slower deployments in exchange for a single consistent transaction" is.

The classic worked case is granularity: splitting a service improves deployability, fault isolation and team autonomy, and worsens data consistency, transactional integrity, performance across the new network hop, and the cost of workflow management. Neither side wins in general; the table for *this* system does.

**Evolutionary architecture.** Ford, Parsons and Kua define it as architecture that supports guided, incremental change across multiple dimensions. "Guided" is the key word: the guide is a set of **fitness functions**, each an objective, often automated, assessment of one characteristic. Categories that help you pick:

- 1.1 **Atomic versus holistic.** An atomic function checks one characteristic in isolation (an ArchUnit rule that the domain does not import Spring). A holistic one checks a combination (a load test under a security scan, to see whether encryption breaks the latency budget).
- 1.2 **Triggered versus continual.** Triggered runs on an event: a unit test, a build step, a deployment gate. Continual runs all the time in production: a monitor on p99 latency, a synthetic transaction, chaos engineering.
- 1.3 **Static versus dynamic.** Static has a fixed pass/fail (no cycles between modules); dynamic depends on context (scalability acceptable if latency stays within budget at the observed load).
- 1.4 **Temporal.** Fires on a date: dependencies older than a year, a toggle past its removal date, a certificate within thirty days of expiry.

The practical set for a Spring Boot service, by characteristic: modularity through ArchUnit or Spring Modulith tests (item 7.3); testability through a mutation-score or coverage floor on core modules (item 5.6); performance through a load test with a budget in the pipeline; deployability through a build-time limit and a check that the service starts in under some number of seconds; maintainability through a limit on file length or cyclomatic complexity; security through dependency vulnerability scanning; and the temporal checks above. Each is a few lines, runs in the pipeline, and turns a value on a slide into something that can fail.

## Example: a trade-off table and two fitness functions

The decision: whether to extract billing from the shop monolith. The characteristics chosen for this system, with the analysis:

| Characteristic (priority) | Keep billing in the monolith | Extract billing as a service |
|---|---|---|
| Deployability (1): billing changes weekly for tax rules, the rest monthly | every tax change redeploys the whole shop | billing deploys alone |
| Data consistency (2): an order and its invoice must never disagree | one transaction | outbox, events, eventual consistency, reconciliation job |
| Performance (3): order placement under 300 ms | in-process call | one network hop, roughly 5 to 20 ms, plus a failure mode |
| Testability (4) | module tests, one database | contract tests per seam (item 5.4) |
| Cost (5) | one deployable | a second runtime, pipeline and on-call rotation |

Decision recorded as an ADR: keep billing in the monolith as a module with enforced boundaries; revisit when tax-rule deployments block two or more releases a month. The table makes the trigger for revisiting explicit, which is what "evolutionary" means in practice.

Fitness function 1, atomic and triggered, guarding the modular boundary that the decision depends on. ArchUnit 1.x:

```java
import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.Test;

class BillingBoundaryFitnessFunction {

    private final JavaClasses productionClasses = new ClassFileImporter()
        .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
        .importPackages("com.example.shop");

    @Test
    void billingInternalsAreReachableOnlyThroughItsApi() {
        noClasses()
            .that().resideOutsideOfPackage("com.example.shop.billing..")
            .should().dependOnClassesThat().resideInAPackage("com.example.shop.billing.internal..")
            .because("extracting billing later requires that nothing else depends on its internals")
            .check(productionClasses);
    }

    @Test
    void theDomainDoesNotDependOnFrameworks() {
        noClasses()
            .that().resideInAPackage("..domain..")
            .should().dependOnClassesThat().resideInAnyPackage("org.springframework..", "jakarta.persistence..")
            .because("domain rules must be testable without a container or a database")
            .check(productionClasses);
    }
}
```

Fitness function 2, atomic, triggered and dependency-free, guarding maintainability. It runs as `java FileLengthFitnessFunction.java src/main/java` in the pipeline and fails the build with a non-zero exit code:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

public class FileLengthFitnessFunction {

    private static final int MAXIMUM_LINES = 60;

    record SourceFile(Path relativePath, int lineCount) {
        boolean isTooLong() {
            return lineCount > MAXIMUM_LINES;
        }
    }

    public static void main(String[] arguments) throws IOException {
        Path sourceRoot = Path.of(arguments[0]);
        List<SourceFile> tooLong;
        try (Stream<Path> files = Files.walk(sourceRoot)) {
            tooLong = files
                .filter(path -> path.toString().endsWith(".java"))
                .map(path -> new SourceFile(sourceRoot.relativize(path), countLines(path)))
                .filter(SourceFile::isTooLong)
                .toList();
        }
        tooLong.forEach(file -> System.out.println("FAIL " + file.relativePath() + " has " + file.lineCount() + " lines"));
        System.out.println(tooLong.isEmpty()
            ? "PASS no source file exceeds " + MAXIMUM_LINES + " lines"
            : "FAIL " + tooLong.size() + " file(s) exceed " + MAXIMUM_LINES + " lines");
        System.exit(tooLong.isEmpty() ? 0 : 1);
    }

    private static int countLines(Path path) {
        try (Stream<String> lines = Files.lines(path)) {
            return (int) lines.count();
        } catch (IOException exception) {
            throw new IllegalStateException("Cannot read " + path, exception);
        }
    }
}
```

Run against a source tree with one 77-line file:

```text
FAIL com/example/shop/orders/ShippingRates.java has 77 lines
FAIL 1 file(s) exceed 60 lines
```

Sixty lines is a deliberately strict number for the example; a real team picks a threshold from its own codebase (the 95th percentile of current files is a common start) and ratchets it down. The value of the function is not the number but that the conversation "this class is getting big" now happens at the pull request where it grew, with a concrete line, instead of in a retrospective.

## Pitfalls

- Characteristics without numbers. "Scalable" cannot fail a test; "handles 500 orders per minute with p99 under 300 ms" can.
- Every characteristic as top priority. The analysis then always produces "it depends" and the decision is made by whoever argues longest.
- Trade-off analysis that lists only the chosen option's benefits. Each cell in the table should have something the option makes worse; if a column has none, you have not found it yet.
- Fitness functions that nobody can fail. A rule with `@Disabled`, a latency budget set at ten times the current value, or a coverage floor at 20 percent is decoration.
- Fitness functions as a replacement for judgement. They catch drift from a decision; they do not make decisions. Thresholds change when the ADR changes, not when a test is inconvenient.
- Holistic functions that run only in a wiki. "We load test before major releases" is a manual, occasional check; the characteristic it guards is unprotected in between.
- Copying another company's characteristics. Netflix's priorities come from Netflix's domain; a tax-reporting system has different ones and no amount of chaos engineering changes that.
- Treating "evolutionary" as "we will refactor later". Without the fitness functions, incremental change is just change.

## Check yourself

1. Your team lists availability, performance, scalability, security, maintainability, testability, deployability and cost as "critical". Describe the exercise that reduces the list, and what question you ask the business about each item.
2. Fill in the trade-off table for "move session state from the application into Redis" against three characteristics of your choosing. Which cell is the one most teams forget?
3. Classify each as atomic or holistic, triggered or continual: an ArchUnit cycle check; a synthetic checkout running every minute in production; a quarterly game day; a nightly dependency vulnerability scan.
4. The file-length function above fails on a generated class that is legitimately 400 lines. What are two correct responses and one wrong one?

## Go deeper

- [Fundamentals of Software Architecture](https://fundamentalsofsoftwarearchitecture.com/) · Richards and Ford; chapters 4 to 6 define, identify and measure architecture characteristics (paid).
- [Software Architecture: The Hard Parts](https://www.oreilly.com/library/view/software-architecture-the/9781492086888/) · the trade-off analysis method applied to granularity, data ownership, and distributed workflows (paid).
- [Building Evolutionary Architectures](https://evolutionaryarchitecture.com/) · the fitness function concept, its categories, and examples per characteristic.
- [ArchUnit](https://www.archunit.org/) · the library for structural fitness functions on the JVM; the user guide lists the full rule syntax.
- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) · where the outcome of a trade-off analysis goes.

---

Part of [Architecture & Craft](../README.md) · items 7.5, 7.6
