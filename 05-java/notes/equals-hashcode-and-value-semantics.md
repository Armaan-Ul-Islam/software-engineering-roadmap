# equals, hashCode and value semantics

> **In one sentence:** Objects that are `equals` must have equal hash codes, `compareTo` should agree with `equals`, and the simplest way to get all of this right for a value type is a record whose compact constructor validates, normalises and defensively copies its components.

**Why it matters:** A class that overrides `equals` but not `hashCode` passes every direct equality assertion and then fails silently as a `HashSet` element or a `HashMap` key: duplicates accumulate, lookups return `null`, caches never hit. Mutable objects used as keys produce the same symptoms later and less predictably. Interviewers ask for the contracts because they are short and because almost everyone has been bitten by them once.

## The idea

**The `equals` contract.** Reflexive (`x.equals(x)`), symmetric (`x.equals(y)` iff `y.equals(x)`), transitive, consistent (same answer while the objects are unchanged), and `x.equals(null)` is `false`.

**The `hashCode` contract.** Consistent within a run as long as the fields used by `equals` do not change; **equal objects must return equal hash codes**; unequal objects may share a hash code (a collision costs performance, never correctness). `HashMap` uses the hash code to pick a bucket and `equals` only within that bucket (see item 2.2). If two equal objects hash differently, the lookup searches the wrong bucket and `equals` is never even called. That is the whole failure mode.

**The `compareTo` contract.** `sgn(x.compareTo(y)) == -sgn(y.compareTo(x))`, transitive, and "strongly recommended" to be *consistent with equals*: `x.compareTo(y) == 0` exactly when `x.equals(y)`. Sorted collections (`TreeSet`, `TreeMap`) use only `compareTo` and ignore `equals` and `hashCode`, so a type that breaks the recommendation behaves differently in a `HashSet` and a `TreeSet`. `BigDecimal` is the standard offender: `2.0` and `2.00` are `compareTo`-equal but not `equals`, because `equals` includes the scale.

**`toString`** has no contract, but it is what you read in logs and in assertion failures. A useful `toString` turns `Money@1b6d3586` into `10.00 NOK`.

**Values and entities.** A *value type* is defined by its components: two `Money(10.00, NOK)` are interchangeable. An *entity* has an identity that survives changes to its state: an `Order` with id 4711 is the same order after its status changes. Compare value types by all components and entities by identifier only; comparing an entity by its mutable fields means its hash code changes while it sits in a set (item 9.4 covers what Lombok does to entities).

**Records make the value case trivial.** `record Money(BigDecimal amount, String currency)` generates `equals`, `hashCode` and `toString` over the components, and is final and shallowly immutable. The compact constructor is where you validate (`requireNonNull`, range checks) and normalise (set a `BigDecimal` scale, trim a string), so that equal values are also represented identically. Shallow means a `List` or array component is still as mutable as what the caller passed in: copy it (`List.copyOf` also rejects `null` elements), and avoid array components altogether, because records compare arrays by reference. For a hand-written class the rules are the same: compare exactly the fields `hashCode` uses, use `Objects.equals` for nullable fields and `Double.compare` for doubles, and make the class `final` so the symmetric-with-subclasses question never arises.

## Example: the broken class a `HashSet` test finds

```java
final class Money {

    private final BigDecimal amount;
    private final String currency;

    Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Money money
            && amount.equals(money.amount)
            && currency.equals(money.currency);
    }

    @Override
    public String toString() {
        return amount + " " + currency;
    }
}
```

```java
@Test
void aPaymentAddedToASetCanBeFoundAgain() {
    Set<Money> paid = new HashSet<>();
    paid.add(new Money(new BigDecimal("10.00"), "NOK"));

    assertThat(paid.contains(new Money(new BigDecimal("10.00"), "NOK"))).isTrue();
}

@Test
void addingAnEqualPaymentTwiceKeepsOneElement() {
    Set<Money> paid = new HashSet<>();
    paid.add(new Money(new BigDecimal("10.00"), "NOK"));
    paid.add(new Money(new BigDecimal("10.00"), "NOK"));

    assertThat(paid).hasSize(1);
}
```

```text
BrokenMoneySetTest.aPaymentAddedToASetCanBeFoundAgain:40
Expecting value to be true but was false
BrokenMoneySetTest.addingAnEqualPaymentTwiceKeepsOneElement:49
Expected size: 1 but was: 2 in:
[10.00 NOK, 10.00 NOK]
```

`Money` inherited `Object.hashCode`, which is identity-based, so the two equal objects landed in different buckets. Note what the tests assert on: `paid.contains(...)` and `hasSize`. AssertJ's `assertThat(paid).contains(...)` passes against this class, because it iterates the set and compares with `equals`, so it never exercises `hashCode`.

The fix, with normalisation so that `10.0` and `10.00` are the same value:

```java
record Money(BigDecimal amount, String currency) {

    Money {
        Objects.requireNonNull(currency, "currency");
        if (amount.signum() < 0) {
            throw new IllegalArgumentException("amount must not be negative: " + amount);
        }
        amount = amount.setScale(2, RoundingMode.HALF_EVEN);
    }
}
```

Both tests pass, `new Money(new BigDecimal("10.0"), "NOK")` prints as `Money[amount=10.00, currency=NOK]`, and it is found by a lookup with `10.00`.

## Example: when `compareTo` disagrees with `equals`

```java
List<BigDecimal> amounts = List.of(new BigDecimal("2.0"), new BigDecimal("2.00"));
System.out.println(new HashSet<>(amounts).size());    // 2
System.out.println(new TreeSet<>(amounts).size());    // 1
```

Same two objects, different answers, and both collections are behaving correctly by their own rules. If you put `BigDecimal` into a `TreeMap` keyed by amount and look it up with a `HashMap` elsewhere, you have written a bug that depends on the scale of the input.

## Example: defensive copies

```java
record TagList(List<String> values) {
    TagList {
        values = List.copyOf(values);
    }
}

List<String> mutable = new ArrayList<>(List.of("a"));
TagList tagList = new TagList(mutable);
mutable.add("b");
System.out.println(tagList);                                          // TagList[values=[a]]

record Tags(String[] values) {}
System.out.println(new Tags(new String[] {"a"}).equals(new Tags(new String[] {"a"})));   // false
```

## Pitfalls

- `equals` without `hashCode`, or the two methods looking at different fields. The compiler does not check; IDE generators and records do it right, hand-written code often does not.
- Mutating a key after insertion. Its hash code changes, it stays in the old bucket, and `get`, `remove` and `contains` all miss it.
- `BigDecimal`, `java.util.Date` subclasses and other types whose `equals` is stricter or looser than you expect inside your own `equals`. Normalise in the constructor or compare with `compareTo` deliberately.
- `compareTo` by subtraction (`return this.amount - other.amount`). Overflows for large values; use `Integer.compare` or `Long.compare`.
- `getClass()` versus `instanceof` in `equals`. `getClass()` breaks with Hibernate proxies and subclasses that add no state; `instanceof` breaks symmetry when a subclass adds fields. Final value classes sidestep the whole debate.
- `Objects.hash(field1, field2)` in a very hot path: it boxes and allocates an array. Fine almost everywhere; hand-roll `31 * result + field` only when a profiler says so.
- Entities in hash-based collections while a transaction changes them. Identifier-based `equals` and `hashCode`, assigned before use, is the safe rule; with database-generated ids, use a stable business key or the identity default.

## Check yourself

1. Why does a missing `hashCode` make `HashSet.contains` return `false` while `ArrayList.contains` with the same objects returns `true`?
2. Two `BigDecimal`s, `2.0` and `2.00`: how many elements in a `HashSet`, how many in a `TreeSet`, and which recommendation in the `Comparable` documentation is violated?
3. A record has a `List<String>` component and the compact constructor does `values = List.copyOf(values)`. Name two different guarantees that single line gives you.
4. A JPA `Customer` entity has `equals` and `hashCode` over all fields. Describe a sequence of ordinary service operations that makes a `HashSet<Customer>` lose the customer.

## Go deeper

- [Baeldung: equals() and hashCode() contracts](https://www.baeldung.com/java-equals-hashcode-contracts) · the contracts with a worked violation of each.
- [dev.java: Using Record to Model Immutable Data](https://dev.java/learn/records/) · compact constructors, generated members and what records cannot do.
- [Object API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html) and [Comparable API documentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Comparable.html) · the contracts in their original wording, including the definition of "consistent with equals".
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · items 10 to 14 (`equals`, `hashCode`, `toString`, `compareTo`) and item 17 (minimise mutability) are the canonical treatment (paid).

---

Part of [Java](../README.md) · items 1.3, 1.5
