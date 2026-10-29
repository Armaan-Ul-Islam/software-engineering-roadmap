# Serialisation: why Java serialisation is dangerous, and Jackson done right

> **In one sentence:** Never deserialise Java-serialised bytes you do not fully control (it is remote code execution waiting for a gadget chain); use Jackson for JSON, build one configured `ObjectMapper`, prefer records as DTOs, register `JavaTimeModule` and write dates as ISO-8601 strings, model polymorphism with explicit type names, and decide deliberately what happens with unknown and missing fields.

**Why it matters:** Every API, message consumer and cache in a backend service is a serialisation boundary, and the defaults are wrong in the direction that hurts: a plain `new ObjectMapper()` cannot handle `Instant`, writes dates as fractional epoch seconds once it can, rejects any field the other side added last week, and silently serialises every public `getX()` whether or not it is a field. The same boundary is where the famous security holes live, both in `ObjectInputStream` and in Jackson's default typing.

## The idea

**Java serialisation** (`Serializable`, `ObjectOutputStream`) writes an object graph and, on reading, reconstructs it by instantiating whatever classes the byte stream names and calling their `readObject` methods, before your code sees anything. An attacker who can send bytes to an `ObjectInputStream` picks classes from your classpath whose deserialisation logic chains into `Runtime.exec` (a gadget chain). Commons Collections, Spring and the JDK itself have all shipped such chains. Since Java 9 (JEP 290) you can install an `ObjectInputFilter` that allowlists classes, globally with `-Djdk.serialFilter=...` or per stream, and Java 17 (JEP 415) added context-specific filter factories. The practical rule: do not accept serialised Java objects over the network at all (RMI, old JMS `ObjectMessage`, HTTP invokers, Java-serialised cache values and session stores), and keep `Serializable` only where a framework forces it on you.

**Jackson for JSON.** Three principles cover most of the configuration surface:

1. One `ObjectMapper`, configured once, shared everywhere. It is thread-safe after configuration and expensive to build. Spring Boot does this for you and applies `spring.jackson.*` properties; outside Spring, build it with `JsonMapper.builder()` and keep it in a static or a bean.
2. Records are the right DTO. Jackson 2.12 and later reads and writes records through the canonical constructor and the accessors, no `@JsonCreator` and no setters needed, and immutability means a deserialised object is never half-initialised.
3. Decide the boundary rules explicitly: how dates are written, what unknown properties do, what `null` and absent mean, how a type hierarchy is tagged.

**Property discovery** on a plain class is by convention: public fields, `getX()` and `isX()` (for primitive `boolean`) are serialised, `setX()` or a `@JsonCreator` constructor are used to deserialise, and private fields are ignored unless a getter exists or you change the visibility with `@JsonAutoDetect` or `MapperFeature` settings. A computed `getDisplayName()` becomes a property you never meant to expose. `@JsonProperty` renames or forces inclusion, `@JsonIgnore` excludes.

**Dates.** `java.time` needs the `jackson-datatype-jsr310` module (`JavaTimeModule`). Even then the default writes `Instant` as a decimal epoch second and `LocalDate` as `[2026,11,30]`; disable `SerializationFeature.WRITE_DATES_AS_TIMESTAMPS` to get ISO-8601 strings, which is what every other system expects. Spring Boot registers the module and disables timestamps by default.

**Polymorphism.** To serialise `List<Payment>` where `Payment` is an interface, Jackson needs a type tag. `@JsonTypeInfo(use = Id.NAME, property = "type")` plus `@JsonSubTypes` writes a stable name you chose (`"type":"card"`). `Id.CLASS` writes the fully qualified class name, which couples the wire format to your package layout and, combined with "default typing" that lets the sender name any class, was the root of a long series of remote-code-execution CVEs. Since 2.10 `activateDefaultTyping` requires a `PolymorphicTypeValidator` for that reason; prefer `Id.NAME` with an explicit subtype list and never enable default typing on input you do not trust.

## Example

A sealed hierarchy, dates, unknown properties and a legacy bean, with Jackson 2.x and the `jackson-datatype-jsr310` module on the classpath:

```java
import com.fasterxml.jackson.annotation.JsonSubTypes;
import com.fasterxml.jackson.annotation.JsonTypeInfo;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

public class JacksonDemo {

    record Money(BigDecimal amount, String currency) {}

    @JsonTypeInfo(use = JsonTypeInfo.Id.NAME, property = "type")
    @JsonSubTypes({
        @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
        @JsonSubTypes.Type(value = InvoicePayment.class, name = "invoice")
    })
    sealed interface Payment permits CardPayment, InvoicePayment {}

    record CardPayment(Money amount, String last4) implements Payment {}

    record InvoicePayment(Money amount, LocalDate dueDate) implements Payment {}

    record Order(String id, Instant createdAt, List<Payment> payments) {}

    static class LegacyCustomer {
        private String name;
        private boolean active;

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }
        public boolean isActive() { return active; }
        public void setActive(boolean active) { this.active = active; }
        public String getDisplayName() { return name.toUpperCase(); }
    }

    public static void main(String[] arguments) throws JsonProcessingException {
        Order order = new Order("o-1", Instant.parse("2026-10-29T10:15:30Z"), List.of(
            new CardPayment(new Money(new BigDecimal("10.50"), "NOK"), "4242"),
            new InvoicePayment(new Money(new BigDecimal("99.00"), "NOK"), LocalDate.of(2026, 11, 30))));

        try {
            new ObjectMapper().writeValueAsString(order);
        } catch (JsonProcessingException exception) {
            System.out.println("1 plain mapper: " + exception.getOriginalMessage());
        }

        ObjectMapper timestamps = JsonMapper.builder().addModule(new JavaTimeModule()).build();
        System.out.println("2 module, default dates: " + timestamps.writeValueAsString(
            new Order("o-1", order.createdAt(), List.of())));

        ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();
        String json = mapper.writeValueAsString(order);
        System.out.println("3 configured: " + json);
        System.out.println("4 round trip equal: " + mapper.readValue(json, Order.class).equals(order));

        String withExtraField = """
            {"id":"o-2","createdAt":"2026-10-29T10:15:30Z","payments":[],"source":"mobile"}
            """;
        try {
            mapper.readValue(withExtraField, Order.class);
        } catch (UnrecognizedPropertyException exception) {
            System.out.println("5 unknown property: " + exception.getOriginalMessage().split("\n")[0]);
        }

        String withNulls = """
            {"id":null,"createdAt":"2026-10-29T10:15:30Z","payments":null}
            """;
        System.out.println("6 nulls into record: " + mapper.readValue(withNulls, Order.class));

        LegacyCustomer customer = new LegacyCustomer();
        customer.setName("Ada");
        customer.setActive(true);
        System.out.println("7 bean: " + mapper.writeValueAsString(customer));
    }
}
```

Output (Jackson 2.21):

```text
1 plain mapper: Java 8 date/time type `java.time.Instant` not supported by default: add Module "com.fasterxml.jackson.datatype:jackson-datatype-jsr310" to enable handling (or disable `MapperFeature.REQUIRE_HANDLERS_FOR_JAVA8_TIMES`)
2 module, default dates: {"id":"o-1","createdAt":1793268930.000000000,"payments":[]}
3 configured: {"id":"o-1","createdAt":"2026-10-29T10:15:30Z","payments":[{"type":"card","amount":{"amount":10.50,"currency":"NOK"},"last4":"4242"},{"type":"invoice","amount":{"amount":99.00,"currency":"NOK"},"dueDate":"2026-11-30"}]}
4 round trip equal: true
5 unknown property: Unrecognized field "source" (class JacksonDemo$Order), not marked as ignorable
6 nulls into record: Order[id=null, createdAt=2026-10-29T10:15:30Z, payments=null]
7 bean: {"name":"Ada","active":true,"displayName":"ADA"}
```

Line 5 is the default `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES = true`. For a client consuming someone else's API, disable it (Spring Boot does) so the other side can add fields; for a server validating its own request body, consider keeping it so typos are rejected. Line 6 shows that a record's compact constructor is the place to reject `null` or substitute `List.of()`; Jackson calls it. Line 7 shows the computed getter leaking.

Writing the Java-serialisation filter, for the one place you still need `ObjectInputStream`:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter("com.example.model.*;java.base/*;!*");
try (ObjectInputStream input = new ObjectInputStream(bytes)) {
    input.setObjectInputFilter(filter);
    return input.readObject();
}
```

## Pitfalls

- A new `ObjectMapper` per call. It builds and caches serialisers per type; constructing one per request throws that away and is a common cause of "JSON is slow". One shared, configured instance.
- Forgetting `JavaTimeModule`, or getting epoch seconds. The first fails loudly, the second is discovered by the frontend team. Set `WRITE_DATES_AS_TIMESTAMPS` to `false` and, for `ZonedDateTime`, know that the zone is dropped unless `WRITE_DATES_WITH_ZONE_ID` is on; prefer `Instant` on the wire (see item 3.1).
- `FAIL_ON_UNKNOWN_PROPERTIES` on a client. Any field the provider adds breaks your consumer. Disable it, or annotate the DTO with `@JsonIgnoreProperties(ignoreUnknown = true)`.
- Enabling default typing. `activateDefaultTyping` lets the sender choose which class to instantiate; it was the vector for a long list of CVEs. Use `@JsonTypeInfo(use = Id.NAME)` with `@JsonSubTypes`.
- Public getters that are not properties. `getDisplayName()`, `getTotal()` and `isEmpty()` all serialise. Annotate with `@JsonIgnore` or, better, use records so what you declare is what you send.
- Entities as DTOs. A JPA entity has back-references (infinite recursion, fixed by `@JsonManagedReference` or `@JsonIdentityInfo`, both of which are a smell), lazy proxies that fail outside a session, and columns you did not mean to expose. Map to a record at the boundary.
- `double` for money in JSON. Jackson parses a JSON number into `BigDecimal` exactly when the target type is `BigDecimal`, but into `Double` when the target is `Object` or a `Map<String, Object>`; enable `USE_BIG_DECIMAL_FOR_FLOATS` for untyped parsing, and send money as a string or an integer count of the smallest unit if the other side is JavaScript.
- `Optional` fields. They need the `jackson-datatype-jdk8` module and still serialise an empty optional as `null`; keep the field nullable in the DTO (see item 1.10).
- Ignoring the null-versus-absent distinction. For a PATCH endpoint, `{"name":null}` and `{}` mean different things. Jackson collapses both into `null` on a plain field; model the field as `JsonNullable` (from `jackson-databind-nullable`), use `@JsonInclude` on output, or parse into `JsonNode` and check `has`.

## Check yourself

1. Why is `ObjectInputStream.readObject()` on bytes from the network a remote-code-execution risk even when your own classes are harmless, and what does an `ObjectInputFilter` change?
2. A plain `new ObjectMapper()` serialises your DTO fine in a unit test; in the Spring Boot application the same DTO comes out with different date formats and ignores unknown fields. Which three settings differ?
3. You add `getTotalIncludingVat()` to a response class for a template, and the API clients start receiving a new field. What happened, and what are two fixes?
4. Why is `@JsonTypeInfo(use = Id.CLASS)` worse than `Id.NAME` for both security and API evolution?

## Go deeper

- [Baeldung: Jackson JSON Tutorial](https://www.baeldung.com/jackson) · the index to focused articles on annotations, dates, polymorphism and visibility.
- [JEP 290: Filter Incoming Serialization Data](https://openjdk.org/jeps/290) · the serialisation filter mechanism, with the pattern syntax used above.
- [JEP 415: Context-Specific Deserialization Filters](https://openjdk.org/jeps/415) · filter factories that pick a filter per stream, and the reasoning about why allowlists beat blocklists.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · chapter 12, "Prefer alternatives to Java serialization" (paid).

---

Part of [Java](../README.md) · item 3.5
