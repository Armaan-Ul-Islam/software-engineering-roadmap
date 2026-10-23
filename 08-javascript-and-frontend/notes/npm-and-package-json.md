# npm and package.json

> **In one sentence:** `package.json` declares what your project is, which scripts it runs and which dependency *ranges* it accepts, while `package-lock.json` records the exact tree that was installed, and `npm ci` is the command that makes a build reproduce that tree instead of re-resolving it.

**Why it matters:** npm is the largest package registry in existence and the most attacked. A build that passed yesterday and fails today, a Docker image that ships `devDependencies`, a transitive package that was hijacked overnight: all three come from not understanding ranges, lockfiles and install scripts. For a Maven user the concepts map well (`pom.xml`, dependency scopes, a lock that Maven does not have), which makes the differences easy to miss.

## The idea

**The manifest.** `package.json` is the equivalent of `pom.xml` for a project and of the published artifact's metadata for a library. The fields that matter day to day:

| Field | Meaning |
|---|---|
| `name`, `version` | identity; `version` follows semver and matters mostly for published libraries |
| `private: true` | refuses `npm publish`; set it on every application |
| `type` | `"module"` makes `.js` files ES modules (see item 1.8) |
| `scripts` | named commands run with `npm run <name>`; `npm start`, `npm test` are shortcuts |
| `dependencies` | needed at runtime by whoever installs the package |
| `devDependencies` | needed to build and test; not installed by consumers of a library, skipped by `npm install --omit=dev` |
| `peerDependencies` | "the host project must provide this" (a React component library declares `react` here) |
| `engines` | the Node versions you support; enforced only with `engine-strict=true` |
| `exports`, `main`, `types`, `files` | what a *library* exposes and ships; irrelevant for an application |
| `overrides` | force a version for a transitive dependency, typically to pick up a security fix |
| `workspaces` | sub-packages in a monorepo that share one lockfile and one `node_modules` |
| `packageManager` | pins the package manager and version for Corepack |

**Scripts.** `npm run build` runs the `build` script with `node_modules/.bin` on the `PATH`, so `"build": "tsc -b && vite build"` works without paths. `pre<name>` and `post<name>` scripts run around `<name>` automatically. Arguments after `--` are passed through: `npm test -- --watch`.

**Semver ranges.** Versions are `MAJOR.MINOR.PATCH`. A range in `package.json` says what you accept; the lockfile says what you got.

| Range | Accepts | Note |
|---|---|---|
| `1.4.2` | exactly 1.4.2 | pin |
| `~1.4.2` | `>=1.4.2 <1.5.0` | patches only |
| `^1.4.2` | `>=1.4.2 <2.0.0` | the default `npm install` writes |
| `^0.4.2` | `>=0.4.2 <0.5.0` | below 1.0, caret treats the minor as breaking |
| `^0.0.4` | `>=0.0.4 <0.0.5` | and below 0.1, the patch |

Ranges only matter at *resolution* time: when there is no lockfile, when you add a package, or when the lockfile does not satisfy the manifest. A library that honours semver badly can still break you inside `^`, which is one reason the lockfile exists.

**The lockfile.** `package-lock.json` records every package in the tree with its exact version, resolved URL and integrity hash. Commit it. `npm install` reads it and installs that tree if it satisfies `package.json`, otherwise it resolves anew and rewrites the lock. `npm ci` is the CI and Docker command: it requires a lockfile, deletes `node_modules`, installs exactly what the lock says, and fails if the lock and the manifest disagree instead of quietly updating anything. It is also faster.

**`npx`.** `npx <command>` runs a binary from the local `node_modules/.bin`, or, if the package is not installed, downloads it to a cache and runs it once. Handy for scaffolding (`npx create-vite@latest`); also a way to run arbitrary code from the internet, so pin the version and know what you are running.

**Workspaces.** `"workspaces": ["packages/*"]` turns a repository into a monorepo: one `npm install` at the root installs everything, links the local packages into `node_modules` so they import each other by name, and keeps a single lockfile. `npm run test --workspaces` runs a script everywhere; `-w packages/api` targets one.

**pnpm and Yarn** solve the same problem differently. pnpm stores each package version once on disk and hard-links it into projects, and its strict `node_modules` layout stops code from importing packages it never declared (a common hidden bug with npm's flattened layout). Yarn (Berry) offers Plug'n'Play, which removes `node_modules` altogether, or a classic layout. Both are faster than npm on large trees; the concepts in this note (manifest, ranges, lockfile, frozen installs with `pnpm install --frozen-lockfile` or `yarn install --immutable`) are the same.

**Supply-chain hygiene.** The registry is open; anyone can publish. The practices that matter: commit the lockfile and use `npm ci`; review lockfile diffs in pull requests, especially new transitive packages; run `npm audit` and triage rather than blindly `npm audit fix`; use `overrides` to patch a vulnerable transitive version when the direct dependency lags; consider `ignore-scripts=true` in `.npmrc` so that install-time scripts (`postinstall`, the usual malware vector) do not run, re-enabling them for the few packages that need them; prefer packages with provenance attestations and few dependencies; and keep publishing credentials behind two-factor authentication. Automated update bots are a net positive only if someone reads what they open.

## Example: an annotated manifest

A React application that talks to a Spring API, as created by Vite and adjusted:

```json
{
  "name": "orders-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "engines": { "node": ">=20" },
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "lint": "eslint .",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "eslint": "^9.12.0",
    "typescript": "~5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  },
  "overrides": {
    "semver": "^7.5.4"
  }
}
```

1. `private: true` and the placeholder version: this is an application, never published, so `version` is meaningless and `exports`/`main` are absent.
2. `"type": "module"` so that `vite.config.ts` and any Node scripts use `import`.
3. `scripts`: `build` type-checks first because Vite strips types without checking them (see item 2.5); `tsc -b` uses the project references the Vite template generates.
4. `dependencies` versus `devDependencies`: for a bundled frontend both end up in the `dist` folder or nowhere, so the split documents intent rather than changing the artifact. For a Node service or a Docker image it decides what `npm ci --omit=dev` installs.
5. `typescript` with `~`: TypeScript does not follow semver (minor releases can break compilation), so accept patches only. Everything else with `^`.
6. `overrides`: a transitive `semver` package below 7.5.2 had a known regular-expression vulnerability; this forces the fixed line everywhere in the tree until the direct dependencies update.

The version numbers above are illustrative ranges; run `npm outdated` to see what is current rather than copying them.

## Pitfalls

- `npm install` in CI. It can rewrite the lockfile and install something different from what the developer tested. Use `npm ci`.
- Lockfile not committed, or `.gitignore`d by a template. Every machine resolves its own tree; "works on my machine" becomes a certainty.
- `--omit=dev` for a frontend build. The build tools *are* dev dependencies, so the production build fails. The flag is for Node runtimes, not for bundled assets.
- Phantom dependencies. Importing a package you never declared because npm hoisted it into `node_modules`. It works until a dependency update moves it; pnpm's strict layout makes this an error from day one.
- Running `npx something` from a tutorial without a version. You run whatever is `latest` at that moment, including a compromised release.
- `npm audit` as a gate with zero tolerance. It reports advisories for dev-only tooling and for code paths you never execute; triage, and fix what is reachable at runtime.

## Check yourself

1. Your lockfile says `lodash 4.17.20` and `package.json` says `^4.17.0`. What does `npm install` install? What about `npm ci`? What changes if someone edits the manifest to `^4.18.0`?
2. Why does a library put `react` in `peerDependencies` rather than `dependencies`, and what would go wrong if it did the opposite?
3. A Docker build for a Node API runs `npm install` and copies `node_modules` into the image. Name three things wrong with that and the commands that fix them.
4. A `postinstall` script in a transitive dependency is the attack vector in several real incidents. What setting blocks it, what breaks when you turn it on, and how do you handle the exceptions?

## Go deeper

- [npm docs: package.json](https://docs.npmjs.com/cli/v10/configuring-npm/package-json) · every field, including `exports` and `overrides`.
- [Semantic Versioning 2.0.0](https://semver.org/) · the specification; short, and worth reading once in full.
- [npm docs: npm ci](https://docs.npmjs.com/cli/v10/commands/npm-ci) · what it does differently from `npm install`, in the maintainers' words.
- [npm docs: workspaces](https://docs.npmjs.com/cli/v10/using-npm/workspaces) · setting up and running scripts across a monorepo.
- [pnpm](https://pnpm.io/) · the motivation page explains the content-addressable store and the strict `node_modules` layout.

---

Part of [JavaScript & Frontend](../README.md) · item 3.2
