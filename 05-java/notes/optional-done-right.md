# Optional done right

> **In one sentence:** `Optional` is a return type that makes "there may be no result" visible in the signature and forces the caller to deal with it through `map`, `flatMap`, `filter`, `orElseThrow` and `ifPresentOrElse`; it is not a replacement for `null` in fields, parameters or collections.

**Why it matters:** `Optional` was added for one purpose: library methods that may have no result, where returning `null` was "overwhelmingly likely to cause errors" (Brian Goetz, who led the design). Used that way it removes a class of `NullPointerException`s. Used everywhere else it adds allocation, breaks serialisation and JPA mapping, and produces code like `if (optional.isPresent()) { optional.get() }`, which is a null check with more typing.

## The idea

A `null` return carries no information: is absence expected and fine, or is it a bug? A method declared as `Optional<Customer> findById(String id)` says in its type that absence is a normal outcome, and the compiler will not let the caller touch the `Customer` without first saying what to do when it is not there.

The API is designed to be used as a chain, so that the "present" path reads like straight-line code and the "absent" decision is made exactly once, at the end:

| Method | Use it when |
|---|---|
| `map(function)` | you want to transform the value if present; the function returns a plain value. |
| `flatMap(function)` | the function itself returns an `Optional`, and you do not want `Optional<Optional<T>>`. |
| `filter(predicate)` | a present value that fails a condition should count as absent. |
| `or(supplier)` | you have a second source to try (Java 9). |
| `orElse(value)` | the default is a constant or already computed. |
| `orElseGet(supplier)` | the default is expensive or has side effects; it runs only when absent. |
| `orElseThrow()` / `orElseThrow(supplier)` | absence is an error at this point. The no-argument form (Java 10) throws `NoSuchElementException`; prefer it to `get()`, which does the same thing but reads as if it were safe. |
| `ifPresent(consumer)` / `ifPresentOrElse(consumer, runnable)` | the end of the chain is an action, not a value (Java 9 for the second). |
| `stream()` | you are inside a stream pipeline and want `Stream<Optional<T>>` flattened to `Stream<T>` (Java 9). |
| `isPresent()` / `isEmpty()` | you need a boolean and nothing else (Java 11 for `isEmpty`). |

Where it belongs: return values of lookups, and the results of stream terminal operations (`findFirst`, `max`, `reduce`). Where it does not belong: fields (not `Serializable`, one extra object per field, confuses Jackson and JPA), method parameters (the caller must now pass `Optional.empty()` and you have three states: `null`, empty, present), and collections (return an empty list, never `Optional<List<T>>`). For primitives there are `OptionalInt`, `OptionalLong` and `OptionalDouble`, which avoid boxing but have their own accessor names (`getAsInt`).

## Example: a repository lookup chain

The task: return a customer's billing country code, defaulting to `"NO"` when the customer has no billing address or the code is blank, and failing when the customer does not exist.

```java
record Address(String street, String countryCode) {}

record Customer(String id, Address billingAddress) {

    Optional<Address> optionalBillingAddress() {
        return Optional.ofNullable(billingAddress);
    }
}

final class CustomerRepository {

    private final Map<String, Customer> customers = new HashMap<>();

    Optional<Customer> findById(String customerId) {
        return Optional.ofNullable(customers.get(customerId));
    }
}
```

Before, with nulls:

```java
static String billingCountry(CustomerRepository repository, String customerId) {
    Customer customer = repository.findById(customerId).orElse(null);
    if (customer == null) {
        throw new CustomerNotFoundException(customerId);
    }
    Address address = customer.billingAddress();
    if (address == null || address.countryCode() == null || address.countryCode().isBlank()) {
        return "NO";
    }
    return address.countryCode();
}
```

After, as a chain:

```java
static String billingCountry(CustomerRepository repository, String customerId) {
    return repository.findById(customerId)
        .orElseThrow(() -> new CustomerNotFoundException(customerId))
        .optionalBillingAddress()
        .map(Address::countryCode)
        .filter(countryCode -> !countryCode.isBlank())
        .orElse("NO");
}
```

Both versions return `SE` for a customer with a Swedish address, `NO` for one with no address or a blank code, and throw `CustomerNotFoundException: No customer with id missing` for an unknown id. The chain has no `null` in it, each step handles one concern, and the one place where absence is an error (`orElseThrow`) is explicit. Note that `map(Address::countryCode)` would wrap a `null` country code as an empty `Optional` automatically: `map` applies `Optional.ofNullable` to the function's result.

Had `Customer` exposed `Optional<Address> billingAddress()` directly, the chain would use `.flatMap(Customer::billingAddress)`, because `map` would produce `Optional<Optional<Address>>`.

## Pitfalls

- `isPresent()` followed by `get()`. It is the null check you were trying to remove, and `get()` on an empty `Optional` throws `NoSuchElementException: No value present`. Use `map`, `orElseThrow` or `ifPresent`.
- `orElse(expensiveCall())`. The argument is evaluated before `orElse` runs, present or not. If the default is a database call or has side effects (a counter, a log line), use `orElseGet(() -> expensiveCall())`.
- `Optional.of(value)` with a possibly null value throws `NullPointerException` immediately; `Optional.ofNullable` is the one you want at the boundary with null-returning code.
- Returning `null` from a method whose return type is `Optional`. Now callers get both failure modes.
- `Optional` fields in entities and DTOs. Jackson 2.x needs the `jackson-datatype-jdk8` module to serialise it as the plain value (Spring Boot registers it for you, plain Jackson does not), and JPA cannot map it to a column at all. Keep the field nullable and return an `Optional` from the getter if you want to.
- `Optional` parameters. Overload the method, or accept a nullable parameter annotated with `@Nullable` (see item 1.12).
- `Optional<List<T>>` and `Optional<Optional<T>>`. An empty collection already means "nothing"; nested optionals mean a `map` should have been a `flatMap`.
- Wrapping a local variable in `Optional` just to avoid writing `if (x == null)`. Three lines of `if` are clearer than `Optional.ofNullable(x).map(...).orElse(...)` in the middle of a method.
- `optional.map(Customer::address).orElse(null)` to go back to nulls inside domain code. Acceptable at a framework boundary; a smell anywhere else.

## Check yourself

1. What is the behavioural difference between `orElse(loadDefault())` and `orElseGet(this::loadDefault)`, and when does it matter?
2. A method `Optional<Address> billingAddress()` exists on `Customer`. Why does `customer.map(Customer::billingAddress)` give you the wrong type, and which method fixes it?
3. A colleague adds `Optional<String> filter` as a method parameter. List the three states a caller can pass and propose a better signature.
4. Why is an `Optional` field in a JPA entity a problem, and how do you still offer callers an `Optional` for that column?

## Go deeper

- [Brian Goetz on the intent of Optional](https://stackoverflow.com/a/26328555) · the design rationale from the person who led it, in four paragraphs.
- [Baeldung: Guide to Java Optional](https://www.baeldung.com/java-optional) · every method with a short example.
- [Optional API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Optional.html) · the class comment states the intended use ("primarily intended for use as a method return type") in its first lines.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · item 55, "Return optionals judiciously", including when not to (paid).

---

Part of [Java](../README.md) · item 1.10
