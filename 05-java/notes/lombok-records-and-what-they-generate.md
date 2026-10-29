# Lombok and records: what they generate, where Lombok bites, and when a record replaces it

> **In one sentence:** Lombok writes getters, setters, constructors, builders, `equals`/`hashCode`/`toString` and loggers into your class at compile time by editing `javac`'s syntax tree, which is convenient until the generated `equals` breaks a JPA entity's identity or a builder meets inheritance; a record gives you the immutable half of that as a language feature, with no plugin and no surprises.

**Why it matters:** Most Java code bases carry Lombok, and most of the bugs it causes are silent: a `@Data` entity whose hash code changes after `save()` and disappears from a `HashSet`, a `toString` that triggers lazy loading of half the database, a `@Builder` that quietly drops a field's default value. Knowing exactly what each annotation expands to (run `delombok` once; it is sobering) is what lets you decide, per class, between a Lombok annotation, a record, or writing the method yourself.

## The idea

**How Lombok works.** It registers as an annotation processor, but a standard processor can only generate new files. Lombok instead uses that entry point to obtain `javac`'s internal AST and adds members to your class before code generation. Your source file does not change; the class file does. That is why IDEs need a plugin to know the methods exist, why `javac` on JDK 23 and later no longer picks it up automatically (`-proc:full`, or `annotationProcessorPaths` in `maven-compiler-plugin`, is required), and why a new JDK can break it until Lombok releases an update (see item 3.4).

**What the common annotations generate.**

| Annotation | Generates |
|---|---|
| `@Getter` / `@Setter` | `getX()` (`isX()` for primitive `boolean`) and `setX(...)` per field, or for one field |
| `@ToString` | `ClassName(field=value, ...)` over all non-static fields, including associations |
| `@EqualsAndHashCode` | both methods over all non-static, non-transient fields; `callSuper = false` by default, with a warning when there is a superclass |
| `@RequiredArgsConstructor` | a constructor for `final` and `@NonNull` fields |
| `@AllArgsConstructor` / `@NoArgsConstructor` | what the names say |
| `@Data` | `@Getter @Setter @RequiredArgsConstructor @ToString @EqualsAndHashCode` |
| `@Value` | the immutable version: all fields `private final`, class `final`, `@AllArgsConstructor`, getters, `@ToString`, `@EqualsAndHashCode` |
| `@Builder` | a static nested `XBuilder` with a fluent setter per field, `builder()`, `build()`, and a package-private all-args constructor if the class has none; `toBuilder = true` adds a copy-builder |
| `@NonNull` | a null check throwing `NullPointerException("x is marked non-null but is null")` in constructors, setters and builder methods |
| `@Slf4j` | `private static final org.slf4j.Logger log = LoggerFactory.getLogger(X.class);` |
| `@With` | `withX(value)` returning a copy with one field changed |
| `@SneakyThrows` | rethrows a checked exception without declaring it, by exploiting erasure |

**Records** (Java 16) are a language feature: `record Money(BigDecimal amount, String currency)` gets a canonical constructor, accessors (`amount()`, not `getAmount()`), `equals`, `hashCode` and `toString`, all specified by the language, visible to every tool, and immutable by construction. A record is what `@Value` was approximating. It cannot have mutable fields, cannot extend a class, and has no builder; a compact constructor handles validation and defensive copies (see item 1.6).

**The decision.** For immutable data carriers (DTOs, events, value objects, configuration), use a record; add a hand-written static factory or a small builder only if there are more than five or six components with sensible defaults. For JPA entities, Lombok's `@Getter` and `@Setter` are fine and `@Data` is not. For everything else, ask whether the class should exist as a bag of fields at all.

## Example: what `@Data @Builder` really produces

```java
import java.util.List;
import lombok.Builder;
import lombok.Data;
import lombok.NonNull;

@Data
@Builder(toBuilder = true)
public class Customer {
    private Long id;
    @NonNull
    private String name;
    private List<String> tags;
}
```

`java -jar lombok.jar delombok Customer.java -p` prints the expansion. Trimmed to the parts that matter:

```java
public class Customer {
    private Long id;
    @NonNull
    private String name;
    private List<String> tags;

    Customer(final Long id, @NonNull final String name, final List<String> tags) {
        if (name == null) {
            throw new java.lang.NullPointerException("name is marked non-null but is null");
        }
        this.id = id;
        this.name = name;
        this.tags = tags;
    }

    public static class CustomerBuilder {
        private Long id;
        private String name;
        private List<String> tags;

        public Customer.CustomerBuilder name(@NonNull final String name) {
            if (name == null) {
                throw new java.lang.NullPointerException("name is marked non-null but is null");
            }
            this.name = name;
            return this;
        }

        public Customer build() {
            return new Customer(this.id, this.name, this.tags);
        }
    }

    public static Customer.CustomerBuilder builder() {
        return new Customer.CustomerBuilder();
    }

    public Customer.CustomerBuilder toBuilder() {
        return new Customer.CustomerBuilder().id(this.id).name(this.name).tags(this.tags);
    }

    public Long getId() { return this.id; }
    public void setId(final Long id) { this.id = id; }

    public boolean equals(final Object other) {
        // instanceof check, canEqual, then field-by-field comparison of id, name and tags
    }

    public int hashCode() {
        // 59 * result + hash of each of id, name, tags
    }

    public String toString() {
        return "Customer(id=" + this.getId() + ", name=" + this.getName() + ", tags=" + this.getTags() + ")";
    }
}
```

Every generated method carries `@lombok.Generated`, which JaCoCo and most static analysers skip. Now use the class the way an entity gets used:

```java
Customer customer = Customer.builder().name("Ada").tags(List.of("vip")).build();
Set<Customer> customers = new HashSet<>();
customers.add(customer);
customer.setId(42L);
System.out.println("contains after setId : " + customers.contains(customer));
System.out.println(customer);
Customer.builder().build();
```

```text
contains after setId : false
Customer(id=42, name=Ada, tags=[vip])
Exception: java.lang.NullPointerException: name is marked non-null but is null
```

The first line is the entity bug in miniature: `hashCode` covered `id`, `id` changed (in real life, when JPA assigned it on `persist`), and the object is now in the wrong bucket of the set it was added to. The same class as a record:

```java
public record Customer(Long id, String name, List<String> tags) {
    public Customer {
        Objects.requireNonNull(name, "name");
        tags = List.copyOf(tags);
    }
}
```

No builder, no setter, no plugin; `equals` and `hashCode` are stable because nothing can change. Where a builder is genuinely wanted for a record, Lombok's `@Builder` works on records too, and generates only the builder.

## Pitfalls

- `@Data` or `@EqualsAndHashCode` on a JPA entity. Hash over a generated `id` changes after persist; hash over mutable fields changes on every update; either way the entity vanishes from sets and maps. Use `@EqualsAndHashCode(onlyExplicitlyIncluded = true)` with a business key marked `@EqualsAndHashCode.Include`, or write `equals` on the identifier with a `null`-safe rule, or do not override them at all (see item 1.3).
- `@ToString` on an entity. It walks every association, which triggers lazy loading inside a session and `LazyInitializationException` outside one, and recurses forever on a bidirectional mapping. `@ToString.Exclude` on associations, or `@ToString(onlyExplicitlyIncluded = true)`.
- `@Builder` and field initialisers. `private List<String> tags = new ArrayList<>();` is ignored by the builder (the all-args constructor overwrites it with `null`). Lombok warns; the fix is `@Builder.Default`, and then the initialiser is used only through the builder, not through a `@NoArgsConstructor`.
- `@Builder` with inheritance. The generated builder knows only the annotated class's fields; a subclass needs `@SuperBuilder` on every level of the hierarchy, and mixing the two does not compile. Records avoid the question by not supporting inheritance.
- `callSuper` defaults. `@EqualsAndHashCode` ignores superclass fields unless `callSuper = true`; `@ToString` likewise. Two subclasses that differ only in inherited state compare equal.
- `@NonNull` as validation. It throws `NullPointerException` from the constructor, which a web layer reports as a 500, not a 400. Validate input at the boundary and keep `@NonNull` for programming errors.
- `@SneakyThrows`. The checked exception crosses a method that does not declare it, so callers cannot catch it by type without a compiler warning. Acceptable in a lambda that must call a checked API; a smell anywhere else.
- `@Setter` everywhere. A class with a setter for every field has no invariants; `@Data` makes that the default shape. Prefer `@Getter` plus explicit methods that change state, or a record.
- Lombok on JDK upgrades. Each new JDK has broken a Lombok release at some point because of the internal API it uses; upgrade Lombok first, and on JDK 23 and later configure the processor explicitly or compilation silently produces classes without the generated members.
- Generated code in the IDE only. Without the plugin the IDE shows errors that `javac` does not; without `delombok` nobody has ever read the generated `equals`. Run `delombok` on one class per code base, once, so the team knows.

## Check yourself

1. A `@Data` entity is added to a `HashSet`, saved with JPA, and `set.contains(entity)` is then `false`. Walk through exactly which generated method caused it and name two fixes.
2. Which of these does a record give you and which does it not: getters, setters, `equals`, a builder, a no-args constructor, immutability of a `List` component?
3. `@Builder` on a class with `private boolean active = true;` produces objects with `active == false`. Why, and what annotation fixes it?
4. Why can an ordinary annotation processor such as MapStruct not do what Lombok does, and what does that imply for IDE support of each?

## Go deeper

- [Project Lombok features](https://projectlombok.org/features/) · each annotation's page shows the exact generated code and the configuration keys.
- [dev.java: Using Record to Model Immutable Data](https://dev.java/learn/records/) · the record tutorial, including compact constructors and the limits.
- [Vlad Mihalcea: The best way to implement equals, hashCode, and toString with JPA and Hibernate](https://vladmihalcea.com/the-best-way-to-implement-equals-hashcode-and-tostring-with-jpa-and-hibernate/) · the entity-identity problem with the test that proves a fix works.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · items 2 (builders) and 10 to 12 (`equals`, `hashCode`, `toString`), which are what Lombok is automating (paid).

---

Part of [Java](../README.md) · item 9.4
