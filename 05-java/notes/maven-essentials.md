# Maven essentials: lifecycle, scopes and dependency mediation

> **In one sentence:** Maven runs a fixed sequence of lifecycle phases, each bound to plugin goals, over a `pom.xml` whose dependencies are resolved transitively with a nearest-wins rule; most build problems are either a goal in the wrong phase or two paths to different versions of the same artifact, and `dependency:tree`, `dependencyManagement`, BOMs, exclusions and the enforcer plugin are how you handle the second.

**Why it matters:** Everyone runs `mvn clean install` several times a day; few can say what it does, which is why builds are slower than they need to be, why tests end up in the wrong phase, and why a `NoSuchMethodError` at runtime, which is almost always a dependency conflict, can cost a day. Understanding mediation turns that day into ten minutes.

## The idea

**Lifecycles and phases.** Maven has three lifecycles: `clean` (`pre-clean`, `clean`, `post-clean`), `default` (the build) and `site`. The default lifecycle's phases, in order, include `validate`, `compile`, `test-compile`, `test`, `package`, `verify`, `install` and `deploy`, with `process-resources`-style phases in between. Running a phase runs every earlier phase in the same lifecycle. So `mvn clean install` means: run the `clean` lifecycle up to `clean` (delete `target/`), then the default lifecycle up to `install`: copy resources, compile main code, copy test resources, compile tests, run unit tests with Surefire, build the jar, run `verify` (where Failsafe integration tests go, if configured), and copy the jar into `~/.m2/repository`. The bindings from phase to goal come from the `<packaging>` (`jar`, `war`, `pom`) and from `<executions>` in your plugins.

**Plugins and goals.** A plugin is a jar of goals; `compiler:compile`, `surefire:test` and `jar:jar` are goals that packaging binds to phases. You can run a goal directly (`mvn dependency:tree`) without any phase. `mvn help:effective-pom` prints the pom after parents, profiles and defaults are merged, which is the one to read when a build does something you did not write.

**Scopes.** `compile` (the default) is on every classpath and transitive. `provided` is on the compile and test classpaths, not packaged and not transitive: servlet APIs, Lombok, annotation processors. `runtime` is excluded at compile time but present for tests and at run time: JDBC drivers, Logback. `test` is for JUnit, Mockito and Testcontainers. `import` is only legal in `dependencyManagement` and pulls in a BOM. A `compile` dependency's own `runtime` dependencies arrive as `runtime`; its `provided` and `test` ones do not arrive at all.

**The reactor.** A parent pom lists `<modules>`; Maven orders them by their dependencies on each other and builds them in that order. `-pl payments -am` builds `payments` and the modules it depends on; `-rf :payments` resumes a failed build there. The parent holds `<dependencyManagement>` and `<pluginManagement>`, which set versions and configuration without adding anything to a module's classpath.

**Transitive dependencies and mediation.** Maven builds the complete graph and then keeps exactly one version per `groupId:artifactId`: the **nearest** one, meaning the shortest path from your pom, and on a tie the first declared. A version you declare directly is always nearest. Maven does not choose the highest version (Gradle does). This is how a direct dependency on an old version silently downgrades a library that a newer transitive dependency was compiled against, and the result is a `NoSuchMethodError` when the newer code calls a method that does not exist in the old jar.

**Controlling it.** `<dependencyManagement>` declares a version (and optionally scope or exclusions) that applies wherever that artifact appears in the graph, including transitively; it overrides mediation without adding the dependency. A **BOM** (bill of materials) is a `pom`-packaged artifact consisting of a large `dependencyManagement` block; `spring-boot-dependencies`, `junit-bom`, `jackson-bom` and `testcontainers-bom` exist so that every artifact of a family is on the same version. Import one with `<type>pom</type><scope>import</scope>` and leave versions out of your `<dependencies>`. `<exclusions>` remove a transitive dependency from one path (the standard case is swapping a logging binding). The **enforcer plugin** fails the build on rules: `dependencyConvergence` (no artifact may be requested in two versions anywhere), `requireUpperBoundDeps` (mediation must never pick a lower version than some path asked for, which is exactly the `NoSuchMethodError` guard), `banDuplicatePomDependencyVersions`, `requireJavaVersion`, `requireMavenVersion`.

## Example: a `NoSuchMethodError` caused by nearest-wins

The application depends on `report-service:1.0.0`, which was compiled against `greeting-lib:2.0.0`, and also directly on `greeting-lib:1.0.0` because someone needed it once. It compiles. At runtime:

```text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String com.example.greeting.Greeter.greet(java.lang.String)'
	at com.example.report.Reporter.report(Reporter.java:7)
	at com.example.app.Main.main(Main.java:7)
```

The class exists (otherwise it would be `NoClassDefFoundError`), the method does not: version conflict. Ask Maven which version won and why:

```text
$ mvn dependency:tree -Dverbose -Dincludes=com.example:greeting-lib
[INFO] com.example:app:jar:1.0.0
[INFO] +- com.example:report-service:jar:1.0.0:compile
[INFO] |  \- (com.example:greeting-lib:jar:2.0.0:compile - omitted for conflict with 1.0.0)
[INFO] \- com.example:greeting-lib:jar:1.0.0:compile
```

Without `-Dverbose` the tree shows only the winner, which is why conflicts are invisible in a casual look. The fix is to manage the version once, where every module sees it:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>greeting-lib</artifactId>
      <version>2.0.0</version>
    </dependency>
  </dependencies>
</dependencyManagement>
```

And to make the next conflict fail the build instead of production, add the enforcer with `dependencyConvergence` (or the more lenient `requireUpperBoundDeps`). With the conflict still present it reports:

```text
[ERROR] Rule 0: org.apache.maven.enforcer.rules.dependency.DependencyConvergence failed with message:
[ERROR] Dependency convergence error for com.example:greeting-lib:jar:2.0.0 paths to dependency are:
[ERROR] +-com.example:app:jar:1.0.0
[ERROR]   +-com.example:report-service:jar:1.0.0:compile
[ERROR]     +-com.example:greeting-lib:jar:2.0.0:compile
[ERROR] and
[ERROR] +-com.example:app:jar:1.0.0
[ERROR]   +-com.example:greeting-lib:jar:1.0.0:compile
```

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-enforcer-plugin</artifactId>
  <version>3.5.0</version>
  <executions>
    <execution>
      <id>enforce</id>
      <goals>
        <goal>enforce</goal>
      </goals>
      <configuration>
        <rules>
          <dependencyConvergence/>
          <requireJavaVersion>
            <version>[21,)</version>
          </requireJavaVersion>
        </rules>
      </configuration>
    </execution>
  </executions>
</plugin>
```

## Pitfalls

- `mvn clean install` on CI out of habit. `install` writes to the local repository, which lets a module built alone pick up a stale sibling from `~/.m2` and hide reactor problems. Use `mvn verify`; install only when another local project needs the artifact.
- `-Dmaven.test.skip=true` when you meant `-DskipTests`. The first skips compiling tests too, and breaks modules that depend on a sibling's test jar.
- Unpinned plugin versions. Maven warns about it for a reason: the same pom builds differently on a different Maven version. Pin them in `pluginManagement`.
- Adding a direct dependency only to pin a version. Use `dependencyManagement`; a direct dependency also changes transitivity and shows up as unused in `mvn dependency:analyze`.
- Excluding a transitive dependency the library actually needs. You trade a `NoSuchMethodError` for a `ClassNotFoundException` at a different time. Prefer managing the version.
- Mixed versions within one family (`jackson-databind` 2.17 with `jackson-core` 2.15). Import the family's BOM.
- Surefire reporting `Tests run: 0` after a JUnit upgrade. Surefire found no engine for your tests; check that `junit-jupiter` (not only the API) is on the test classpath, and make zero tests a failure with `-Dsurefire.failIfNoTests=true`.
- `SNAPSHOT` dependencies in a release build, or a stale snapshot that needs `-U` to refresh.

## Check yourself

1. What exactly runs when you type `mvn test`, and why is `mvn install` usually the wrong command on a CI server?
2. Your pom declares `lib:1.0`; a dependency two levels down needs `lib:2.0`. Which version is on the classpath, and what are two different ways to get `2.0` everywhere?
3. Why does `mvn dependency:tree` not show the losing version by default, and what does `-Dverbose` add?
4. Which enforcer rule would have caught the example, and how does `requireUpperBoundDeps` differ from `dependencyConvergence` in strictness?

## Go deeper

- [Marco Behler: mvn clean install, a short guide to Maven](https://www.marcobehler.com/guides/mvn-clean-install-a-short-guide-to-maven) · the lifecycle explained by what actually happens to your files.
- [Maven: Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) · the reference for scopes, mediation, `dependencyManagement` and BOM import.
- [Maven: Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) · every phase of the three lifecycles and the default bindings per packaging.
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/) · the rule catalogue, including `dependencyConvergence` and `requireUpperBoundDeps`.
- [Maven: Getting Started](https://maven.apache.org/guides/getting-started/) · if you have never written a pom from scratch.

---

Part of [Java](../README.md) · items 6.1, 6.2
