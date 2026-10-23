# Generics: invariance, wildcards and erasure

> **In one sentence:** `List<Integer>` is not a `List<Number>`; wildcards (`? extends` for parameters you read from, `? super` for parameters you write to) give method signatures back the flexibility that invariance takes away, and because the compiler erases type arguments before the JVM ever sees them, there is a short list of things generics cannot do.

**Why it matters:** A wrong generic signature either rejects perfectly valid calls ("why can't I pass my `List<Integer>` here?") or pushes callers into unchecked casts that explode later with a `ClassCastException` far from the real mistake. Erasure explains a whole family of confusing compile errors (`generic array creation`, `name clash ... have the same erasure`, `cannot be safely cast`) and a few runtime surprises, such as bridge methods in stack traces and why Jackson needs a `TypeReference`.

## The idea

**Invariance.** If `List<Integer>` were a subtype of `List<Number>`, you could take a `List<Integer>`, view it as a `List<Number>`, add a `Double`, and corrupt the original list. Arrays made exactly that choice (`Integer[]` is an `Object[]`) and pay for it with `ArrayStoreException` at runtime. Generics chose a compile-time error instead, so `List<Number> numbers = new ArrayList<Integer>()` does not compile, even though `Integer` extends `Number`.

**Bounded type parameters.** `<T extends Comparable<? super T>>` says "any `T` that can compare itself to its own type or a supertype". The bound is what the compiler lets you call on a `T`; without one, `T` is only an `Object`.

**Wildcards.** `List<? extends Number>` is "a list of some unknown subtype of `Number`". You can read elements as `Number`, but you cannot add anything except `null`, because the compiler does not know whether the list holds `Integer`s or `Double`s. `List<? super Integer>` is the mirror image: you can add `Integer`s, but what you read back is only known to be `Object`. The rule for choosing is **PECS**, producer-extends, consumer-super: if the method reads from a parameter, use `? extends`; if it writes into a parameter, use `? super`; if it does both, use the exact type.

**Generic method or wildcard?** If a type variable would appear only once in the signature, use a wildcard (`void printAll(Collection<?> items)`). If it appears twice, or you need to return it, declare a type parameter (`<T> T first(List<T> items)`).

**Erasure.** `javac` checks the type arguments and then throws them away. `List<String>` becomes `List` in the class file, and a type variable becomes its bound (`Object`, or `Comparable` for `<T extends Comparable<T>>`). A `Version implements Comparable<Version>` therefore has to satisfy the erased interface method `compareTo(Object)`, so the compiler generates a hidden **bridge method** `compareTo(Object)` that casts and delegates to `compareTo(Version)`. Erasure is why you cannot write `new T[10]`, `new T()`, `instanceof List<String>`, a `static T` field, or two overloads that differ only in type arguments. Type arguments do survive in one place: the `Signature` attribute of fields, methods and superclasses. That is what Jackson's `new TypeReference<List<Order>>() {}` and Spring's `ParameterizedTypeReference` read: the anonymous subclass records `List<Order>` as its superclass's type argument.

## Example: the `copy` signature and every wrong version of it

The correct signature reads from `source` and writes into `destination`:

```java
import java.util.ArrayList;
import java.util.List;

public class Copy {

    static <T> void copy(List<? super T> destination, List<? extends T> source) {
        for (T element : source) {
            destination.add(element);
        }
    }

    public static void main(String[] arguments) {
        List<Integer> integers = List.of(1, 2, 3);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();
        copy(numbers, integers);
        copy(objects, integers);
        System.out.println(numbers + " " + objects);   // [1, 2, 3] [1, 2, 3]
    }
}
```

Each simplification fails, and the error messages (from `javac` 21) tell you which side is wrong:

```java
static <T> void copy(List<T> destination, List<T> source)
// copy(numbers, integers):
// error: method copy ... cannot be applied to given types;
//   required: List<T>,List<T>   found: List<Number>,List<Integer>
//   reason: inference variable T has incompatible equality constraints Integer,Number
```

```java
static <T> void copy(List<? extends T> destination, List<? extends T> source)
// destination.add(element):
// error: incompatible types: T cannot be converted to CAP#1
//   where CAP#1 is a fresh type-variable: CAP#1 extends T from capture of ? extends T
```

```java
static <T> void copy(List<? super T> destination, List<? super T> source)
// for (T element : source):
// error: incompatible types: CAP#1 cannot be converted to T
//   where CAP#1 ... extends Object super: T from capture of ? super T
```

`CAP#1` is the compiler's name for "whatever the wildcard actually is", called a capture. You cannot add a `T` to a list of `? extends T` because the list might be a `List<SubclassOfT>`; you cannot read a `T` from a list of `? super T` because it might be a `List<Object>`.

## Example: what erasure forbids, and the bridge method

```java
public class Box<T> {
    private T[] elements = new T[10];              // error: generic array creation

    static boolean isStringList(Object value) {
        return value instanceof List<String>;      // error: Object cannot be safely cast to List<String>
    }

    static void handle(List<String> names) {}
    static void handle(List<Integer> ids) {}       // error: name clash: handle(List<Integer>) and
                                                   //   handle(List<String>) have the same erasure
}
```

The bridge method is visible with `javap -p` on a class that implements `Comparable<Version>`:

```text
public final class Version implements java.lang.Comparable<Version> {
  public int compareTo(Version);
  public int compareTo(java.lang.Object);    // synthetic bridge, generated by javac
}
```

If `compareTo(Object)` appears in a stack trace, that is the bridge calling your method after a cast, and a `ClassCastException` there means something put a non-`Version` into a collection sorted by `Version`, usually through a raw type.

## Pitfalls

- Returning wildcards from an API (`List<? extends Order> findAll()`). Callers now have to deal with captures. Put wildcards on parameters, return exact types.
- Raw types "to make it compile". A raw `List` turns off checking for the whole expression; the `ClassCastException` appears where the element is used, not where the wrong one was inserted. Compile with `-Xlint:unchecked,rawtypes` and treat warnings as bugs.
- `new HashMap<>(...)` passed where `Map<String, ? extends Number>` is expected is fine; `Map<String, Number>` passed where `Map<String, Integer>` is expected is not. Invariance applies to every type argument, including `Map` values.
- Generic arrays. `(T[]) new Object[capacity]` with `@SuppressWarnings("unchecked")` is acceptable only when the array never escapes the class (this is what `ArrayList` does). Returning it as `T[]` fails with `ClassCastException` at the caller.
- Varargs of generic types (`List<String>... lists`) create a generic array behind your back; mark such methods `@SafeVarargs` only if they really never store into the array.
- Primitives are not type arguments. `List<int>` does not exist; `List<Integer>` boxes every element. Use `IntStream`, `int[]` or a specialised collection when it matters.

## Check yourself

1. Why does `List<? extends Number>` let you call `get(0)` but not `add(1)`? Which single argument can you still pass to `add`?
2. Write the signature of a method that sums the values of a `Map` whose keys can be anything and whose values are `BigDecimal` or a subtype.
3. The compiler rejects overloads `handle(List<String>)` and `handle(List<Integer>)` but accepts `handle(List<String>)` and `handle(Set<String>)`. Explain both decisions with erasure.
4. `new TypeReference<List<Order>>() {}` works, but the same expression with `List<T>` inside a generic method does not give Jackson the element type. Why not?

## Go deeper

- [Angelika Langer: Java Generics FAQ](http://www.angelikalanger.com/GenericsFAQ/JavaGenericsFAQ.html) · the most complete reference on wildcards, capture and erasure; read the entries on "wildcard capture" and "bridge methods".
- [Baeldung: The Basics of Java Generics](https://www.baeldung.com/java-generics) · a short refresher if the syntax itself is new.
- [JLS 4.6: Type Erasure](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6) · the exact rules, two paragraphs long.
- [Effective Java, 3rd edition](https://www.oreilly.com/library/view/effective-java/9780134686097/) · chapter 5 (items 26 to 33) is the practical guide: PECS, generic methods, typesafe heterogeneous containers (paid).

---

Part of [Java](../README.md) · item 1.7
