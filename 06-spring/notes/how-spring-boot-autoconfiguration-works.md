# How Spring Boot auto-configuration works

> **In one sentence:** Auto-configuration is a list of ordinary `@Configuration` classes, loaded from a file in each jar and evaluated after your own configuration, whose `@Conditional` annotations decide bean by bean whether to register a default or back off because you already defined one.

**Why it matters:** "Why is there a `DataSource` when I never defined one" and "why is my `ObjectMapper` ignored" are the same question, and guessing at the answer costs hours. The conditions evaluation report answers it in one read. It is also the mechanism behind every starter you will ever write for your own team.

## The idea

A **starter** such as `spring-boot-starter-data-jpa` contains no code. It is a POM that pulls in the libraries (Hibernate, Spring Data JPA, HikariCP) plus `spring-boot-autoconfigure`, the jar that holds the auto-configuration classes for everything Boot knows about. Spring Boot 4 splits that single jar into one module per technology; the mechanism below is unchanged.

`@SpringBootApplication` is three annotations: `@SpringBootConfiguration`, `@ComponentScan`, and `@EnableAutoConfiguration`. The last one imports `AutoConfigurationImportSelector`, which reads every file named `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` on the classpath. Each line is the fully qualified name of a class annotated with `@AutoConfiguration`. Since Boot 3.0 this file is the only registration mechanism; the old `spring.factories` key is gone.

Two rules make the whole thing work.

1. **Auto-configuration runs after user configuration.** The import selector is a deferred one: all of your `@Configuration` classes and scanned components are registered first. Only then are the auto-configuration classes processed. That is why `@ConditionalOnMissingBean` can see your beans and back off.
2. **Conditions are evaluated in two phases.** Cheap conditions that only need class metadata (`@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnWebApplication`) run while configuration classes are parsed. Conditions that need to know which beans exist (`@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnSingleCandidate`) run later, during bean registration. Because the order in which user configuration classes are processed is not defined, the bean conditions are only reliable inside auto-configuration classes. Using them in your own `@Configuration` is a gamble the reference documentation warns against.

The conditions you will meet most:

| Annotation | Matches when |
|---|---|
| `@ConditionalOnClass(DataSource.class)` | the class is on the classpath (checked by name, so the annotated class can be loaded even when the referenced class is absent) |
| `@ConditionalOnMissingClass("...")` | it is not |
| `@ConditionalOnBean` / `@ConditionalOnMissingBean` | a bean of the type (or name) does or does not exist yet |
| `@ConditionalOnProperty(name = "spring.jpa.open-in-view", havingValue = "true", matchIfMissing = true)` | the property has the value, or is absent and `matchIfMissing` is set |
| `@ConditionalOnWebApplication(type = SERVLET)` | the context is a servlet web application |
| `@ConditionalOnResource`, `@ConditionalOnExpression` | a classpath resource exists, a SpEL expression is true |

**Ordering.** Because `@ConditionalOnBean` only sees beans registered so far, an auto-configuration that depends on another one's beans must run after it: `@AutoConfiguration(after = DataSourceAutoConfiguration.class)`. `before` and `@AutoConfigureOrder` exist for the other direction. Ordering is between auto-configuration classes only; it does not reorder your own configuration.

**Overriding.** Three levers, from gentlest to bluntest:

1. Set properties. `spring.datasource.hikari.maximum-pool-size=20` customises the auto-configured bean without replacing it.
2. Define your own bean of the same type. The auto-configured one backs off via `@ConditionalOnMissingBean`. Check the report afterwards: some beans are conditional on a *name*, and a bean of the same type but a different name then gives you two.
3. Exclude the class: `@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)` or `spring.autoconfigure.exclude=...`. Use this when you want none of it, for example a JPA application whose `DataSource` comes from your own module.

## Example: reading the conditions evaluation report

Run the application with `--debug` (or set `debug=true`), or call the Actuator `conditions` endpoint. The report has four parts: positive matches, negative matches, exclusions, and unconditional classes. Here is the abridged section for the data source on a plain Boot 3 application with `spring-boot-starter-data-jpa` and the PostgreSQL driver:

```text
============================
CONDITIONS EVALUATION REPORT
============================

Positive matches:
-----------------

   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes 'javax.sql.DataSource', 'org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType' (OnClassCondition)
      - @ConditionalOnMissingBean (types: io.r2dbc.spi.ConnectionFactory; SearchStrategy: all) did not find any beans (OnBeanCondition)

   DataSourceConfiguration.Hikari matched:
      - @ConditionalOnClass found required class 'com.zaxxer.hikari.HikariDataSource' (OnClassCondition)
      - @ConditionalOnProperty (spring.datasource.type=com.zaxxer.hikari.HikariDataSource) matched (OnPropertyCondition)
      - @ConditionalOnMissingBean (types: javax.sql.DataSource; SearchStrategy: all) did not find any beans (OnBeanCondition)
```

Each line is one condition and the class in parentheses is the condition implementation that evaluated it. "Matched" means every condition on that class passed, so its `@Bean` methods were registered. Now add your own `@Bean DataSource dataSource()` and run again. The Hikari configuration moves to the other section:

```text
Negative matches:
-----------------

   DataSourceConfiguration.Hikari:
      Did not match:
         - @ConditionalOnMissingBean (types: javax.sql.DataSource; SearchStrategy: all) found beans of type 'javax.sql.DataSource' dataSource (OnBeanCondition)
      Matched:
         - @ConditionalOnClass found required class 'com.zaxxer.hikari.HikariDataSource' (OnClassCondition)
         - @ConditionalOnProperty (spring.datasource.type=com.zaxxer.hikari.HikariDataSource) matched (OnPropertyCondition)
```

How to read it when something is missing:

1. Find the auto-configuration class that would create the bean you expected. The class names are predictable (`JacksonAutoConfiguration`, `FlywayAutoConfiguration`), and the Boot reference lists them.
2. Look for it under "Negative matches". The lines under "Did not match" are the reasons; "Matched" lists the conditions that did pass, which tells you how close you were.
3. Conditions on a class short-circuit. If the class-level `@ConditionalOnClass` failed, the nested classes and `@Bean` methods were never evaluated and will not appear at all; look at the parent.
4. Check "Exclusions" for an `exclude` you or a colleague added months ago.

Writing your own auto-configuration is the same thing in reverse: an `@AutoConfiguration` class with `@ConditionalOnClass` at the top and `@ConditionalOnMissingBean` on each `@Bean`, listed in the `AutoConfiguration.imports` file of your library jar. Keep it out of the component-scanned packages, or it will be picked up as ordinary configuration and the ordering guarantees disappear.

## Pitfalls

- A `@ConditionalOnMissingBean` in your own `@Configuration` class. It may be evaluated before the bean it is checking for is registered, depending on scan order, and the result changes when someone renames a package.
- Defining a bean to override the default, but the default is not conditional on your bean's type. You now have two beans, and injection by type fails with `NoUniqueBeanDefinitionException`. The report shows the auto-configured one still under "Positive matches".
- Expecting the report in production logs. `--debug` also raises log levels for the core packages; use the Actuator `conditions` endpoint there, secured like every other endpoint (item 2.5).
- Putting an auto-configuration class inside the scanned package during development. It works until the ordering matters.
- Treating `spring.autoconfigure.exclude` as a performance switch. Conditions that do not match cost almost nothing at startup; exclude for correctness, not speed.
- Forgetting that `@ConditionalOnProperty` without `matchIfMissing` means "absent property, no bean". Many "it works locally, not in the container" stories are one missing environment variable away from this.

## Check yourself

1. Why does `@ConditionalOnMissingBean` work reliably in Boot's own auto-configuration but not in a `@Configuration` class in your application?
2. You add `@Bean ObjectMapper customObjectMapper()`. Afterwards your controllers still use the default Jackson settings. What would you look for in the conditions report, and what are two possible explanations?
3. An auto-configuration depends on a `DataSource` existing. Which annotation does it need beyond `@ConditionalOnBean(DataSource.class)`, and why?
4. In which order are these processed: a scanned `@Service`, your `@Configuration`, and `HibernateJpaAutoConfiguration`? What would break if the order were different?

## Go deeper

- [Spring Boot: Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html) · the reference for the imports file, the condition annotations, ordering, and testing auto-configurations with `ApplicationContextRunner`.
- [Marco Behler: What is Spring Boot?](https://www.marcobehler.com/guides/spring-boot) · derives starters and auto-configuration from the problems they solve.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/index.html) · the appendix lists every auto-configuration class, which is how you know what to look for in the report.

---

Part of [Spring](../README.md) · items 2.1, 2.2
