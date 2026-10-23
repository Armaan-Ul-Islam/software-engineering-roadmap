# Parse, don't validate: value objects and illegal states you cannot construct

> **In one sentence:** Check untrusted input once, at the boundary, by turning it into a type that can only hold valid values; from then on the type carries the proof, no deeper method needs to re-check, and whole classes of bugs ("can this be null?", "what if the currency is missing?") stop being possible.

**Why it matters:** Much of the defensive code in a typical Spring service (null checks, `isBlank`, the same email regex in three layers) exists because validation returns a boolean and throws away what it learned. The bugs that result (a `NullPointerException` three layers from its cause, a negative amount reaching the database) pass unit tests and reach production. When an interviewer asks "where do you validate?", the strong answer is "once, by parsing into a type".

## The idea

**Validation versus parsing.** `boolean isValidEmail(String)` inspects a value and forgets. `new EmailAddress(String)` inspects a value and remembers, by returning a value whose type says "this has been checked". Alexis King's phrase for the difference is *parse, don't validate*: a parser consumes a less structured input and produces a more structured output, or fails. Once `EmailAddress` exists, every method that needs an address asks for `EmailAddress`, and the compiler rejects an unparsed `String`. The check has moved from "everywhere, hopefully" to "exactly once, provably".

**Illegal states unrepresentable.** The same move applies to combinations. `BigDecimal amount` and `String currency` passed separately can be `(10.00, null)`. A `boolean success` next to `String errorCode` and `String transactionId` has eight combinations, six of them meaningless. Design the type so its set of possible values equals the set of valid states: `record Money(BigDecimal amount, Currency currency)` for the first, a sealed interface with one record per outcome for the second.

**Value objects.** Fowler's definition (item 1.5): equality by value rather than identity, immutable, small, validated at construction. Java records are the natural fit. Components are final, `equals`, `hashCode` and `toString` are generated, and the compact constructor is where validation and normalisation live. Where the type's validity depends on a rule, the rule lives in exactly one place.

**Where to parse.** At every boundary where data enters: the controller's request DTO, the message consumer, configuration at startup, a database row being loaded. Bean Validation annotations on the DTO are fine for shape (`@NotBlank`, `@Size`) but they do not produce a type, so they do not stop the next developer from building a domain object with an unchecked string. The conversion into domain types is what carries the proof.

**`Optional` versus `null`.** The JDK's own guidance: `Optional` is a return type for results that may legitimately be absent. Use `orElseThrow()`, `map`, `ifPresent`; never `get()` without a check. Do not use it for fields (it is not `Serializable` and JPA cannot map it), for method parameters (callers end up writing `Optional.of(value)` and you still have to guard against a null `Optional`), or for collections (return an empty collection). Within your own code, `null` should be rare enough that every nullable value is either wrapped in `Optional` at the point it is returned or documented as nullable at an API boundary.

**Exceptions versus result types.** Throw for failures the caller cannot sensibly handle at the call site: bugs, broken invariants, infrastructure gone. Parse failures at a boundary are also exceptions, because the only sensible handling is "reject the request", and a single `@ExceptionHandler` turns them into a 400 (item 8.2). Model *expected business outcomes* that the caller must branch on (payment declined, email already taken) as a sealed result type: an exhaustive `switch` then forces every caller to handle every case, and the compiler, not a code reviewer, catches the forgotten one. Checked exceptions were designed for the same purpose but compose badly with lambdas and streams.

**Fail fast.** Detect the problem at the earliest point and stop: `Objects.requireNonNull` in constructors, configuration validated at startup, invariants checked when an object is created rather than when it is used. The alternative is an object that is half-valid for a while and explodes later, far from the cause. Helpful `NullPointerException` messages (on by default since JDK 15) tell you which variable was null, but only where it exploded; failing fast moves the explosion to the source.

## Example: `EmailAddress` and `Money`

```java
import java.util.Objects;
import java.util.regex.Pattern;

public record EmailAddress(String value) {

    private static final Pattern SHAPE = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");

    public EmailAddress {
        Objects.requireNonNull(value, "value");
        value = value.strip();
        if (!SHAPE.matcher(value).matches()) {
            throw new IllegalArgumentException("Not an email address: '" + value + "'");
        }
    }
}
```

Assigning to the parameter inside a compact constructor is allowed and is how normalisation works: the stripped value is what gets stored. Lower-casing the domain part would belong here too, so that equality means what the business means.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
        int fractionDigits = currency.getDefaultFractionDigits();
        if (amount.scale() > fractionDigits) {
            throw new IllegalArgumentException(amount + " has more decimals than " + currency + " allows");
        }
        amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
    }

    public static Money of(String amount, String currencyCode) {
        return new Money(new BigDecimal(amount), Currency.getInstance(currencyCode));
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money times(int quantity) {
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }

    private void requireSameCurrency(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Cannot add " + other.currency + " to " + currency);
        }
    }
}
```

Observed behaviour:

```java
Money.of("2.5", "EUR").equals(Money.of("2.50", "EUR"));    // true
new BigDecimal("2.5").equals(new BigDecimal("2.50"));      // false, which is why the constructor normalises scale
Money.of("2.505", "EUR");                                    // IllegalArgumentException
Money.of("10.00", "EUR").plus(Money.of("1.00", "USD"));     // IllegalArgumentException
```

The second line is the trap `Money` exists to close: `BigDecimal.equals` compares scale as well as value, so a record holding a raw `BigDecimal` would say two equal amounts differ. The constructor fixes it once, for every `Money` that will ever exist.

## Example: a service signature, before and after

Before, the service re-checks everything because its parameters prove nothing:

```java
public Customer register(String email, String name, BigDecimal deposit, String currency) {
    if (email == null || !email.contains("@")) {
        throw new IllegalArgumentException("bad email");
    }
    if (deposit == null || deposit.signum() < 0) {
        throw new IllegalArgumentException("bad deposit");
    }
    Currency parsedCurrency = Currency.getInstance(currency);
    // ... and the repository and the mailer check the same things again
}
```

After, the controller parses once and the service trusts its types:

```java
@PostMapping("/customers")
public ResponseEntity<?> register(@RequestBody RegisterCustomerRequest request) {
    RegistrationResult result = customerService.register(
        new EmailAddress(request.email()),
        new CustomerName(request.name()),
        Money.of(request.initialDeposit(), request.currency()));
    return switch (result) {
        case RegistrationResult.Registered registered ->
            ResponseEntity.created(locationOf(registered.customerId())).build();
        case RegistrationResult.EmailAlreadyTaken taken ->
            ResponseEntity.status(HttpStatus.CONFLICT).body(problemFor(taken));
    };
}
```

```java
public sealed interface RegistrationResult {
    record Registered(CustomerId customerId) implements RegistrationResult {}
    record EmailAlreadyTaken(EmailAddress email) implements RegistrationResult {}
}

public RegistrationResult register(EmailAddress email, CustomerName name, Money initialDeposit)
```

A malformed email throws `IllegalArgumentException` inside `new EmailAddress(...)`, before the service is reached; one `@RestControllerAdvice` method maps it to a 400 with a Problem Details body. "Email already taken" is not an error in the request, it is a business outcome, so it is a result case and the `switch` is exhaustive: add a third case to the sealed interface and this controller stops compiling until it handles it.

## Pitfalls

- Validating in every layer "to be safe". It is the symptom of types that carry no proof; fix the types and delete the checks.
- A record with a mutable component. `List<OrderLine> lines` must be copied in the compact constructor (`lines = List.copyOf(lines)`), otherwise the caller can mutate your "immutable" value afterwards.
- Converting a parse failure into `null` with a try-catch. You have validated and then thrown the result away, which is the original problem with extra steps.
- `Optional.get()`, `Optional` fields, `Optional` parameters, and `orElse(expensiveCall())` (evaluated eagerly; use `orElseGet`).
- Primitive obsession: `String currency`, `String countryCode`, `long amountInCents` travelling separately through five signatures. Each is a value object waiting to be written.
- Using `IllegalArgumentException` for both user input and programming errors, then mapping all of them to 400. A dedicated exception type for boundary parsing keeps genuine bugs visible as 500s.
- `Currency.getDefaultFractionDigits()` returns -1 for pseudo-currencies such as `XAU`; if you accept those, the `Money` constructor above needs a branch.
- Mapping value objects to JPA. Recent Hibernate versions can map a record as an `@Embeddable`; otherwise an `AttributeConverter` does it. Do not let the mapping push you back to raw strings in the domain.

## Check yourself

1. After `boolean isValidEmail(String)` returns `true`, what does the rest of the program know? After `new EmailAddress(String)` returns, what does it know, and who enforces it?
2. Why does `Money.of("2.5", "EUR").equals(Money.of("2.50", "EUR"))` require code in the constructor to be true, and what would break if that code were removed?
3. A colleague proposes `Optional<EmailAddress>` as a method parameter so callers "can pass nothing". What do you propose instead, and why?
4. A payment can be approved, declined by the issuer, or fail because the gateway is down. Which outcomes belong in a sealed result type and which should be an exception? Defend the split.

## Go deeper

- [Alexis King: Parse, don't validate](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/) · the essay that named the idea; Haskell examples, but the argument is language-neutral.
- [Scott Wlaschin: Making illegal states unrepresentable](https://fsharpforfunandprofit.com/posts/designing-with-types-making-illegal-states-unrepresentable/) · the type-design walkthrough that sealed interfaces and records now let you do in Java.
- [Martin Fowler: Value Object](https://martinfowler.com/bliki/ValueObject.html) · the definition, with the equality and immutability rules.
- [Brian Goetz: Data Oriented Programming in Java](https://www.infoq.com/articles/data-oriented-programming-java/) · records, sealed types and pattern matching as a modelling toolkit, by the language architect.
- [java.util.Optional (Java 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html) · the API note at the top is the official position on where `Optional` belongs.
- [Jim Shore: Fail Fast](https://www.martinfowler.com/ieeeSoftware/failFast.pdf) · four pages on why a loud early failure is cheaper than a quiet late one.
- [Tony Hoare: Null References, The Billion Dollar Mistake](https://www.infoq.com/presentations/Null-References-The-Billion-Dollar-Mistake-Tony-Hoare/) · the inventor of `null` on why it was a mistake.

---

Part of [Architecture & Craft](../README.md) · items 1.4, 1.5
