# JavaScript for Java developers: the mental-model shifts

> **In one sentence:** JavaScript looks like Java but behaves like a dynamically typed, prototype-based language where functions are values, scope is lexical, and `this` is decided by the call site rather than by the class a method was written in.

**Why it matters:** A Java developer can write syntactically valid JavaScript on day one and still spend weeks on bugs that come from carrying Java assumptions across: a `==` that coerces, a `this` that is `undefined` inside a callback, a `const` object that mutates, a loop variable captured by closures. Every one of these is a five-minute concept once named. Reviewing frontend pull requests also requires reading idiomatic JavaScript, which uses objects, closures and array methods where Java would use classes, interfaces and loops.

## The idea

**Types belong to values, not variables.** There are seven primitive types (`string`, `number`, `bigint`, `boolean`, `undefined`, `symbol`, `null`) and one object type, which covers arrays, functions, dates and everything else. `number` is always a 64-bit float: `0.1 + 0.2 === 0.30000000000000004` and integers are exact only up to `Number.MAX_SAFE_INTEGER` (2^53 - 1). `typeof` has two famous quirks: `typeof null` is `"object"` and `typeof []` is `"object"` (use `Array.isArray`).

**`==` coerces, `===` does not.** `==` converts operands to a common type before comparing, by rules nobody remembers: `0 == ""`, `"1" == 1`, `[] == false` and `null == undefined` are all `true`, while `NaN == NaN` is `false`. Use `===` everywhere; the only idiomatic `==` is `value == null` to test for both `null` and `undefined` at once. `NaN` is never equal to anything, so test it with `Number.isNaN`.

**Truthiness.** Exactly eight values are falsy: `false`, `0`, `-0`, `0n`, `""`, `null`, `undefined` and `NaN`. Everything else is truthy, including `"0"`, `"false"`, `[]` and `{}`. `if (items.length)` is idiomatic; `if (items)` is a bug because an empty array is truthy.

**Scope.** `let` and `const` are block scoped like Java locals. `var` is function scoped and hoisted to the top of its function with the value `undefined`, so never use it. `const` forbids reassignment of the binding, not mutation of the object: `const list = []; list.push(1)` is fine. Accessing a `let` or `const` before its declaration throws a `ReferenceError` (the temporal dead zone).

**Closures.** A function captures the *variables* of its enclosing scopes, not their values at creation time. This is what Java's "effectively final" rule prevents you from noticing. Each iteration of a `for (let ...)` loop gets a fresh binding, so closures created in the loop see their own value.

**`this` is a hidden parameter filled in at the call site.** `object.method()` sets `this` to `object`. A plain call `method()` sets it to `undefined` (modules and classes are always strict mode). `method.call(target)` and `method.bind(target)` set it explicitly. Arrow functions have no `this` of their own; they use the `this` of the scope they were written in, which is why they are the fix for most `this` bugs.

**Prototypes, not classes.** Every object has a hidden link to a prototype object; a property lookup that misses walks the chain. `class` syntax creates exactly this structure: methods live on `Counter.prototype`, shared by all instances, and `extends` chains prototypes. There is no overloading, no interfaces at runtime, and no access modifiers except the newer `#privateField` syntax.

**Objects are maps.** `{ timeout: 30 }` is a map from the string `"timeout"` to `30`, iterable with `Object.keys`, `Object.entries` and `for...in`, and serialised directly by `JSON.stringify`. Use `Map` when keys are not strings or when you add and remove entries frequently.

## Example: the same code in Java and idiomatic JavaScript

```java
record Order(String id, BigDecimal total, boolean paid) {}

List<String> paidOrderIds = orders.stream()
        .filter(Order::paid)
        .map(Order::id)
        .toList();

Map<Boolean, List<Order>> byPaid = orders.stream()
        .collect(Collectors.partitioningBy(Order::paid));
```

```javascript
const orders = [
  { id: "A-1", total: 120, paid: true },
  { id: "A-2", total: 80, paid: false },
];

const paidOrderIds = orders.filter((order) => order.paid).map((order) => order.id);

const byPaid = Object.groupBy(orders, (order) => (order.paid ? "paid" : "unpaid"));
// { paid: [ { id: 'A-1', ... } ], unpaid: [ { id: 'A-2', ... } ] }

const { id, ...rest } = orders[0];        // destructuring with a rest element
const updated = { ...orders[0], paid: false };   // a shallow copy with one field changed
```

No class, no type declarations, no `new`. Object literals play the role of records and DTOs, destructuring replaces getters, and spread (`...`) replaces copy constructors and builders. `Object.groupBy` needs Node 21+ or a 2024 browser; `Map.groupBy` is its sibling for non-string keys.

## Example: three `this` traps and their fixes

Save as `traps.mjs` and run with `node traps.mjs`.

```javascript
class Counter {
  count = 0;

  increment() {
    this.count += 1;
    return this.count;
  }
}

// Trap 1: a method is detached from its object and called as a plain function.
const counter = new Counter();
const increment = counter.increment;
try {
  increment();
} catch (error) {
  console.log(error.message);   // Cannot read properties of undefined (reading 'count')
}

// Trap 2: a classic function expression inside a method has its own this (undefined).
class Cart {
  items = [{ price: 10 }, { price: 20 }];
  taxRate = 0.25;

  totalsWithTax() {
    return this.items.map(function (item) {
      return item.price * (1 + this.taxRate);
    });
  }
}
try {
  new Cart().totalsWithTax();
} catch (error) {
  console.log(error.message);   // Cannot read properties of undefined (reading 'taxRate')
}

// Trap 3: an arrow function used as an object method captures the module's this, not the object.
const timer = {
  seconds: 0,
  tick: () => {
    this.seconds += 1;
  },
};
try {
  timer.tick();
} catch (error) {
  console.log(error.message);   // Cannot read properties of undefined (reading 'seconds')
}
```

The fixes, in the same order:

1. Keep the receiver attached. Call through the object (`() => counter.increment()`), bind once (`const increment = counter.increment.bind(counter)`), or declare the method as a class field arrow function (`increment = () => { ... }`), which creates one function per instance but survives being passed around. The browser version of this trap is `button.addEventListener("click", counter.increment)`.
2. Use an arrow function for the callback: `this.items.map((item) => item.price * (1 + this.taxRate))`. Arrow functions inherit `this` from the method.
3. Use method shorthand for object methods: `tick() { this.seconds += 1; }`. In an ES module, top-level `this` is `undefined`; in a CommonJS file it is `module.exports`, so the same code would silently create `module.exports.seconds = NaN` instead of throwing.

The closure trap, for completeness:

```javascript
for (var index = 0; index < 3; index++) {
  setTimeout(() => console.log(index));   // 3 3 3: one shared binding, read after the loop ended
}
for (let index = 0; index < 3; index++) {
  setTimeout(() => console.log(index));   // 0 1 2: one binding per iteration
}
```

## Pitfalls

- Using `==`. The symptom is a comparison that passes for `"1"` and `1` alike, or a `null` check that also matches `0` when written as `!value`.
- Treating `const` as immutability. The reference is fixed; the object is not. Use `Object.freeze` for shallow freezing, or simply never mutate and always spread.
- Checking emptiness with truthiness. `if (array)` and `if (object)` are always true. Check `array.length === 0` or `Object.keys(object).length === 0`.
- Expecting integer arithmetic. `7 / 2` is `3.5`; use `Math.trunc` or `BigInt` for large identifiers. Numbers from a JSON API above 2^53 are silently rounded; send them as strings.
- Passing methods as callbacks. Any time a method name appears without parentheses and without an arrow around it, ask what `this` will be.
- Relying on `instanceof` across boundaries. Objects parsed from JSON have `Object.prototype` as their prototype; they are never instances of your classes. Validate shape instead (see item 2.4).
- Writing Java-style classes for everything. Idiomatic JavaScript uses plain objects for data and functions for behaviour; classes are for things with identity and lifecycle.

## Check yourself

1. `[] == false` is `true` and `[] == ![]` is also `true`. Without memorising the coercion table, what rule would have made both comparisons impossible to write by accident?
2. A colleague "fixes" a lost `this` by wrapping every method in `bind` in the constructor. What does a class field arrow function change about memory and about the prototype chain, and when does it matter?
3. Why does the `var` loop print `3 3 3` even though the callbacks were created when `index` was `0`, `1` and `2`? What does this say about what a closure captures?
4. You receive `{ "id": 9007199254740993 }` from a Java backend that uses `long` identifiers. What does `JSON.parse` give you, and what should the API do instead?

## Go deeper

- [javascript.info: Data types](https://javascript.info/types) and [Object methods, "this"](https://javascript.info/object-methods) · the clearest short treatments of coercion and call-site binding.
- [MDN: Equality comparisons and sameness](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Equality_comparisons_and_sameness) · `==`, `===` and `Object.is` side by side, with the full coercion table.
- [javascript.info: Variable scope, closure](https://javascript.info/closure) · lexical environments explained with diagrams; makes the loop example obvious.
- [MDN: Inheritance and the prototype chain](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide/Inheritance_and_the_prototype_chain) · what `class` really creates.
- [You Don't Know JS Yet: Scope & Closures](https://github.com/getify/You-Dont-Know-JS/blob/2nd-ed/scope-closures/README.md) · the book-length version of the scope and closure story, free.

---

Part of [JavaScript & Frontend](../README.md) · items 1.1, 1.2, 1.3, 1.4
