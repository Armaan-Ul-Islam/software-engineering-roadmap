# Stack, heap and object layout: what a Java object really costs

> **In one sentence:** Every Java object lives on the heap and costs a header plus its fields rounded up to 8 bytes, while the stack holds only primitives and references, so an `Integer` is 16 bytes, an empty `ArrayList` is 40, and a "small" object graph is often several times larger than the data in it.

**Why it matters:** Heap size drives GC cost, cache behaviour and cloud bills, and the real size of an object is nowhere in the source code. The engineer who knows that a `Map<Long, Long>` entry costs around 80 bytes (entry, boxed key, boxed value) rather than 16 will pick a different data structure before the heap dump forces the question. Interviewers ask "where does this variable live?" to see whether you can draw the picture.

## The idea

A running thread has a **stack** of frames, one per active method call. A frame holds the method's local variables and its operand stack: primitives (`int`, `long`, `double`, `boolean`...) and **references**. A reference is an address-like value, 4 or 8 bytes, that points into the heap. The frame is popped on return and nothing in it is ever garbage collected; it is simply gone. The stack is small and fixed (`ThreadStackSize` is 1 MB on Linux x86-64 and 2 MB on macOS Apple Silicon; `-Xss` changes it), which is why unbounded recursion ends in `StackOverflowError`.

Every **object** and every **array**, including every `String` and every boxed `Integer`, lives on the **heap**, shared by all threads and managed by the garbage collector. A `List<Integer>` local variable is a 4-byte reference in a frame; the `ArrayList`, its backing `Object[]`, and each `Integer` are separate heap objects. `static` fields live on the heap too, inside the `java.lang.Class` object of the declaring class; the class metadata itself (method bytecode, constant pool, vtables) lives in Metaspace, which is native memory, not heap. Primitive fields are stored inline in their object; a field of reference type stores only the reference, and the referenced object is somewhere else on the heap. The JIT compiler may keep an object that never escapes a method entirely in registers (item 1.4), but that is an optimisation you cannot see from the source.

A HotSpot object on a 64-bit JVM is laid out like this:

1. **Mark word**, 8 bytes: identity hash code, GC age, and lock state.
2. **Class pointer**, 4 bytes with compressed class pointers (the default), 8 without.
3. **Fields**, reordered by the JVM: it packs them by size and fills gaps, so declaration order says nothing about layout. Arrays add a 4-byte length here, then the elements.
4. **Padding** up to the next multiple of 8 (`ObjectAlignmentInBytes`).

So the minimum object is 16 bytes, and the header alone is 12. References are 4 bytes because of **compressed oops**: with a heap below 32 GB the JVM stores a 64-bit address as a 32-bit value shifted by 3 bits (objects are 8-byte aligned, so the low three bits carry no information). Cross 32 GB and references double in size, which is why a 36 GB heap can hold fewer objects than a 31 GB one.

## Example: ask the JVM with JOL

[JOL](https://github.com/openjdk/jol) reads the real layout from the running JVM. Put `jol-core` on the classpath (or download `jol-cli-<version>-full.jar` from Maven Central) and run:

```java
import java.util.ArrayList;
import org.openjdk.jol.info.ClassLayout;
import org.openjdk.jol.info.GraphLayout;

public class ObjectLayoutDemo {

    static final class Order {
        boolean paid;
        long id;
        int quantity;
        String reference;
    }

    public static void main(String[] arguments) {
        System.out.println(ClassLayout.parseInstance(Integer.valueOf(42)).toPrintable());
        System.out.println(ClassLayout.parseInstance(new ArrayList<>()).toPrintable());
        System.out.println(GraphLayout.parseInstance(new ArrayList<>()).toFootprint());
        System.out.println(ClassLayout.parseInstance(new Order()).toPrintable());
    }
}
```

Output on OpenJDK 25 with default flags (trimmed):

```text
java.lang.Integer object internals:
OFF  SZ   TYPE DESCRIPTION               VALUE
  0   8        (object header: mark)     0x0000000000000001 (non-biasable; age: 0)
  8   4        (object header: class)    0x001a1cb8
 12   4    int Integer.value             42
Instance size: 16 bytes

java.util.ArrayList object internals:
OFF  SZ                 TYPE DESCRIPTION               VALUE
  0   8                      (object header: mark)     ...
  8   4                      (object header: class)    ...
 12   4                  int AbstractList.modCount     0
 16   4                  int ArrayList.size            0
 20   4   java.lang.Object[] ArrayList.elementData     []
Instance size: 24 bytes

java.util.ArrayList footprint:
     COUNT       AVG       SUM   DESCRIPTION
         1        16        16   [Ljava.lang.Object;
         1        24        24   java.util.ArrayList
         2                  40   (total)

ObjectLayoutDemo$Order object internals:
OFF  SZ               TYPE DESCRIPTION               VALUE
  0   8                    (object header: mark)     ...
  8   4                    (object header: class)    ...
 12   4                int Order.quantity            0
 16   8               long Order.id                  0
 24   1            boolean Order.paid                false
 25   3                    (alignment/padding gap)
 28   4   java.lang.String Order.reference           null
Instance size: 32 bytes
```

Reading it:

- An `Integer` is 16 bytes to carry 4 bytes of payload: 12 bytes of header and no padding. An `int[1000]` costs 16 bytes of header plus 4,000 bytes; an `Integer[1000]` costs 4,016 bytes of references plus up to 16,000 bytes of boxes.
- An empty `ArrayList` is 24 bytes plus a 16-byte empty `Object[]` (the empty array is a shared constant until the first `add`, so a million empty lists share one). The first `add` allocates a 10-slot array: 16 + 40 = 56 bytes, so a list holding one element costs 80 bytes.
- The JVM moved `quantity` into the 4-byte gap after the header, put the `long` next, and placed the `boolean` and the reference last. Three bytes are lost to alignment. Declaring the fields in another order changes nothing.
- A `String` is 24 bytes (`hash`, `coder`, `hashIsZero`, and a reference) plus its `byte[]`; `"hello"` is 48 bytes in total, 5 of them text.

Two variations are worth running yourself. With `-XX:-UseCompressedOops`, every reference becomes 8 bytes: `ArrayList` grows to 32 bytes and `Order` to 40. With `-XX:+UseCompactObjectHeaders` (JEP 450 made this an experimental option in JDK 24; JEP 519 made it a product option in JDK 25, still off by default), the header shrinks to 8 bytes, but `Integer`, `ArrayList` and `Order` stay 16, 24 and 32 bytes, because the saved 4 bytes become padding. Only `int[3]` shrinks, from 32 to 24. Compact headers pay off across a whole heap of mixed objects, not on any single class you can point at.

## Pitfalls

- Boxing in collections. `Map<Long, Long>` pays for a `HashMap$Node` (32 bytes), a boxed key (24 bytes) and a boxed value (24 bytes) per entry. Primitive-specialised collections (Eclipse Collections, fastutil) or a `long[]` cut this by five to ten times.
- Trusting `Integer.valueOf` to be free. Only values from -128 to 127 are cached; `valueOf(1000)` allocates 16 bytes every time, and autoboxing in a hot loop allocates on every iteration.
- Assuming `new byte[0]` or an empty `ArrayList` is free. Every array has a 16-byte header; a million "empty" per-request lists are still millions of objects once they are populated. Lazily create collections that are usually empty, or use `List.of()`.
- Reasoning from field declaration order. The JVM reorders fields, so manual "padding fields" against false sharing can end up anywhere (item 1.5 and the `@Contended` annotation).
- Growing the heap past 32 GB "for headroom". References double in size and the cache footprint grows with them; measure the live set first, and if you really need more, go well past 32 GB.
- Expecting `sizeof`. Java has no operator for object size; JOL and `jcmd <pid> GC.class_histogram` (shallow sizes per class) are the tools.

## Check yourself

1. A method declares `int count = 3; String name = "x"; int[] values = new int[4];`. Draw what is in the frame and what is on the heap, with byte sizes.
2. Why is an `Integer` 16 bytes and not 12 or 20? What single JVM flag would make it 24 bytes?
3. A class has fields `byte flag; long id; byte state;`. What is its instance size with default flags, and where do the two bytes end up?
4. Your service holds 50 million `Map<Long, Long>` entries. Estimate the heap, then propose a structure that holds the same data in under 1 GB.

## Go deeper

- [JOL: Java Object Layout](https://github.com/openjdk/jol) · the tool used above; the `README` lists the CLI commands (`internals`, `footprint`, `estimates`).
- [Shipilёv: JVM Anatomy Quarks](https://shipilev.net/jvm/anatomy-quarks/) · short, measured posts; start with the quarks on object headers, compressed references and field layout.
- [Baeldung: Stack Memory and Heap Space in Java](https://www.baeldung.com/java-stack-heap) · the frame-and-heap picture with diagrams, for a first pass.
- [JEP 450: Compact Object Headers](https://openjdk.org/jeps/450) · what the 8-byte header stores and what it saves across real heaps.

---

Part of [Memory & Concurrency](../README.md) · items 1.1, 1.2
