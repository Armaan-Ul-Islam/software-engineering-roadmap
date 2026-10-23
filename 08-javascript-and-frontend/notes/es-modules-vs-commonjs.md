# ES modules vs CommonJS

> **In one sentence:** CommonJS (`require`, `module.exports`) is Node's original, synchronous, dynamic module system and ES modules (`import`, `export`) are the language standard with static structure and live bindings; Node runs both, decides which one a file is from its extension and the nearest `package.json`, and most "it works in one project but not the other" errors come from mixing them.

**Why it matters:** Java has one module story per build tool. JavaScript has two module systems in the same runtime, and the errors they produce when mixed (`Cannot use import statement outside a module`, `require is not defined in ES module scope`, `ERR_MODULE_NOT_FOUND` for a file that clearly exists) stop more backend developers in their first Node week than anything else. Library authors face the same split as the dual-package problem, which can silently load two copies of one library into your application.

## The idea

**CommonJS (CJS).** Node wraps each file in a function with `require`, `module`, `exports`, `__filename` and `__dirname` as parameters. `require()` is an ordinary synchronous function call: it resolves the path, loads and runs the file once, caches `module.exports`, and returns it. Because it is a function, it can be called anywhere, conditionally, with a computed string. What you get back is a value, copied at the moment of the call.

**ES modules (ESM).** `import` and `export` are declarations, not calls. They must be at the top level, and the specifier must be a string literal, so the whole dependency graph is known before any code runs. The runtime links modules first and executes them afterwards, which makes two things possible: **live bindings** (an imported name is a view onto the exporting module's variable, not a copy) and **top-level `await`**. ESM code is always strict mode, has no `require`, `__dirname` or `module`, and gets `import.meta.url` (and, from Node 20.11, `import.meta.dirname` and `import.meta.filename`) instead. Loading something at runtime is done with `import()`, which returns a promise and works in both systems.

**How Node decides which system a file is.**

| File | Treated as |
|---|---|
| `.mjs` | always ESM |
| `.cjs` | always CommonJS |
| `.js` | ESM if the nearest `package.json` has `"type": "module"`, otherwise CommonJS |

New projects should set `"type": "module"` and use `.js` everywhere; config files for tools that still require CommonJS can be named `.cjs`.

**Resolution differs.** CommonJS lets you write `require("./utilities")` and finds `utilities.js` or `utilities/index.js`. ESM requires the full path with extension for relative imports: `import ... from "./utilities.js"`. In TypeScript with modern `moduleResolution` settings you write `.js` in the import even though the source file is `.ts`; that is intentional, the extension refers to the emitted file. Bare specifiers (`"react"`, `"zod"`) are resolved through the package's `exports` map in its `package.json`, which also decides which file an `import` gets and which a `require` gets.

**Interop.** ESM can import CommonJS: the default import is `module.exports`, and Node also tries to detect named exports by scanning the CommonJS source for `exports.name = ...` patterns. Names assigned dynamically are not detected. Those named imports are snapshots, not live bindings. In the other direction, Node 20 cannot `require()` an ES module at all (`ERR_REQUIRE_ESM`); Node 22.12 and later can, as long as the module has no top-level `await`.

**The dual-package problem.** A library that ships both a CommonJS build and an ESM build, selected by conditional `exports` (`"import"` and `"require"`), can be loaded twice in one process: your code imports the ESM file while a dependency requires the CommonJS file. Each copy has its own module state, so singletons are duplicated and `instanceof` fails across the boundary. The fixes are to ship one format, or to make the ESM entry a thin wrapper that re-exports the CommonJS build so the state lives in one place.

## Example: one module, both ways

The CommonJS version, in a project without `"type": "module"`:

```javascript
// counter.cjs
let count = 0;

function increment() {
  count += 1;
}

module.exports = { count, increment };
```

```javascript
// use.cjs
const { count, increment } = require("./counter.cjs");

increment();
console.log(count);   // 0: the exports object received a copy of count at export time
```

The ESM version, with `{ "type": "module" }` in `package.json`:

```javascript
// counter.js
export let count = 0;

export function increment() {
  count += 1;
}
```

```javascript
// use.js
import { count, increment } from "./counter.js";

increment();
console.log(count);   // 1: a live binding to the module's variable
```

Same code, different answer. The CommonJS module exported the *value* `0`; the ES module exported the *binding*. (Exporting a mutable `let` is a demonstration, not a recommendation: expose a function that returns the current value instead.)

## Example: the errors you see when mixing them

Each of these was produced with Node 22; the wording is Node's.

1. `require` in an ES module (a `.js` file under `"type": "module"`):
   `ReferenceError: require is not defined in ES module scope, you can use import instead`, followed by Node's explanation that the file is treated as an ES module because of the `package.json`, and the suggestion to rename it `.cjs`.
2. `import` in a CommonJS file:
   `SyntaxError: Cannot use import statement outside a module`. The fix is `"type": "module"`, or renaming to `.mjs`, or using `require`.
3. Relative import without an extension in ESM (`import { increment } from "./counter"`):
   `Error [ERR_MODULE_NOT_FOUND]: Cannot find module '/project/counter' imported from /project/use.js`. The file exists; the specifier is incomplete. Add `.js`.
4. `__dirname` or `module.exports` in ESM:
   `ReferenceError: __dirname is not defined in ES module scope` and `ReferenceError: module is not defined in ES module scope`. Use `import.meta.dirname` (Node 20.11+) or `fileURLToPath(import.meta.url)`, and `export`.
5. A named import from a CommonJS module whose export Node could not detect statically:
   `SyntaxError: Named export 'formatMoney' not found. The requested module './legacy.cjs' is a CommonJS module, which may not support all module.exports as named exports.` Node's own message shows the fix: `import legacy from "./legacy.cjs"; const { formatMoney } = legacy;`.

## Pitfalls

- Copying a `require`-based snippet from a blog into a `"type": "module"` project, or the reverse. Read the error's second line; Node tells you which rule classified the file.
- Forgetting the extension in ESM imports, then "fixing" it with a bundler that happens to resolve it. The code works in Vite and fails in plain Node tests.
- Destructuring a CommonJS export and expecting later changes to show up. CommonJS exports are object properties; destructuring copies them at that moment.
- Mixing module systems inside a monorepo so that the same library is loaded twice. The symptom is a `Symbol`, class or context object that is "the same" by name but fails `===` or `instanceof`. Check with `node --trace-require-module` or by logging `import.meta.url` from inside the library.
- Relying on `exports` conditions you have not tested. If `package.json` has an `exports` map, deep imports like `library/dist/internal.js` are blocked with `ERR_PACKAGE_PATH_NOT_EXPORTED`, which breaks consumers who relied on them.
- Treating `import()` as ESM-only. Dynamic `import()` is the supported way to load an ES module from CommonJS on Node 20, and the only way to load one conditionally in either system.

## Check yourself

1. Why can a bundler tree-shake unused exports from an ES module but not from a CommonJS module? Which property of ESM makes that possible?
2. The same file content runs as CommonJS in project A and fails as ESM in project B. What are the two things that could differ between the projects?
3. A dependency you `import` throws because `instanceof MyLibraryError` is `false` for an error that was clearly thrown by that library. What has probably happened, and how would you confirm it?
4. In TypeScript, your import says `./utilities.js` but the file on disk is `utilities.ts`. Why is that correct, and what would break if you wrote `./utilities`?

## Go deeper

- [Node.js: ECMAScript modules](https://nodejs.org/api/esm.html) · the authoritative description of resolution, interop and `import.meta`.
- [Node.js: Modules: Packages](https://nodejs.org/api/packages.html) · `"type"`, the `exports` map, conditional exports and the dual-package hazard section.
- [Node.js: Modules: CommonJS modules](https://nodejs.org/api/modules.html) · the module wrapper, the resolution algorithm and the cache.
- [javascript.info: Modules](https://javascript.info/modules) · the browser side: `<script type="module">`, deferred execution, strict mode and live bindings.
- [Sindre Sorhus: Pure ESM package](https://gist.github.com/sindresorhus/a39789f98801d908bbc7ff3ecc99d99c) · the FAQ that the maintainers of hundreds of popular packages link to when they drop CommonJS.

---

Part of [JavaScript & Frontend](../README.md) · item 1.8
