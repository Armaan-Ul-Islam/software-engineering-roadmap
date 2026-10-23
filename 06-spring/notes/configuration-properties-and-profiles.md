# Configuration properties, precedence and profiles

> **In one sentence:** Spring Boot merges configuration from a fixed list of sources where later ones win, you should read it through validated `@ConfigurationProperties` types rather than scattered `@Value` strings, and secrets belong in the environment or mounted files, never in a profile file.

**Why it matters:** Configuration is where "works on my machine" lives. A property that binds in `application.yml` but not from the environment variable in Kubernetes, a profile file that quietly ships a staging password, or a typo that leaves a field at its default are all production incidents that validation at startup would have turned into a failed deploy. The precedence rules are also a reliable interview question.

## The idea

Boot's `Environment` is a stack of property sources. When the same key appears in several, the one higher in this list wins (abridged from the reference documentation, highest priority first):

1. `@TestPropertySource` and `properties` on `@SpringBootTest`, and `@DynamicPropertySource` (tests only)
2. Command line arguments (`--server.port=9000`)
3. `SPRING_APPLICATION_JSON` (inline JSON in one environment variable)
4. Java system properties (`-Dserver.port=9000`)
5. OS environment variables
6. `random.*` values
7. Config data: `application.properties` and `application.yml`, with their profile-specific variants
8. `@PropertySource` on `@Configuration` classes (loaded too late to affect logging or `spring.main.*`)
9. `SpringApplication.setDefaultProperties`

Within config data, more specific beats less specific: a profile-specific file beats the plain one, and a file next to the jar (`./config/`, then `./`) beats the one inside it. If both `application.properties` and `application.yml` exist in the same location, the `.properties` file wins.

**Profiles** select which beans and which files apply. `spring.profiles.active=prod` activates `application-prod.yml` and every `@Profile("prod")` bean; `@Profile("!prod")` is the complement. You can also keep several documents in one YAML file separated by `---` and tag each with `spring.config.activate.on-profile`. `spring.profiles.active` cannot be set inside a profile-specific file, and `spring.profiles.group.prod=prod-db,prod-messaging` lets one flag enable several. When nothing is active, the profile named `default` is.

**Relaxed binding** means the key in a file does not have to match the Java name exactly. `payments.api-key`, `payments.apiKey`, `payments.api_key` and the environment variable `PAYMENTS_APIKEY` all bind to a component named `apiKey`. Use kebab-case in files, because that is the canonical form the documentation and IDE metadata use. Environment variables follow a mechanical rule: uppercase, dots become underscores, dashes are removed, list indices become `_0_`: `spring.datasource.url` is `SPRING_DATASOURCE_URL`, and `app.servers[0].host` is `APP_SERVERS_0_HOST`.

**`@ConfigurationProperties`** binds a whole prefix onto a type. With a record, Boot binds through the constructor, so the object is immutable and complete; `@DefaultValue` supplies defaults for absent keys. Add `@Validated` and Bean Validation constraints and the application refuses to start when the configuration is wrong, which is the single best property of this approach. Register the type with `@EnableConfigurationProperties(PaymentsProperties.class)` on a configuration class, or `@ConfigurationPropertiesScan` on the application class. Boot converts strings into `Duration` (`30s`, `5m`, `PT1H`), `DataSize` (`10MB`), `URI`, enums, lists and maps for you.

**Secrets.** The environment is the normal channel: your orchestrator injects `PAYMENTS_APIKEY` and the file refers to it as `${PAYMENTS_APIKEY}` or binds it directly. Mounted files work through config trees: `spring.config.import=optional:configtree:/run/secrets/` turns every file in that directory into a property named after the file, which is how Kubernetes and Docker secrets arrive. Since Boot 3.0 the Actuator `env` endpoint hides all values unless `management.endpoint.env.show-values` is changed, so exposing it no longer leaks secrets by default (item 2.5).

## Example: a validated properties record

```java
@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentsProperties(
        @NotBlank String apiKey,
        @NotNull URI baseUrl,
        @DefaultValue("5s") Duration timeout,
        @DefaultValue @Valid Retry retry) {

    public record Retry(
            @DefaultValue("3") @Min(1) @Max(10) int maxAttempts,
            @DefaultValue("200ms") Duration backoff) {
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentsProperties.class)
public class PaymentsConfiguration {

    @Bean
    RestClient paymentsRestClient(RestClient.Builder builder, PaymentsProperties paymentsProperties) {
        return builder
                .baseUrl(paymentsProperties.baseUrl().toString())
                .defaultHeader("Authorization", "Bearer " + paymentsProperties.apiKey())
                .build();
    }
}
```

The YAML that binds to it, with the secret taken from the environment:

```yaml
payments:
  api-key: ${PAYMENTS_APIKEY:}
  base-url: https://api.payments.example
  timeout: 10s
  retry:
    max-attempts: 50
```

`retry.backoff` is absent, so it takes the default of 200 ms. The `:` after `PAYMENTS_APIKEY` matters: without a default, an unset variable leaves the literal text `${PAYMENTS_APIKEY}` in the property, which is not blank and passes `@NotBlank`. With the empty default, a missing variable becomes an empty string and fails validation at startup, which is what you want. Start the application with the file above and the failure analyser reports:

```text
***************************
APPLICATION FAILED TO START
***************************

Description:

Binding to target [Bindable@2d3ef181 type = com.example.payments.PaymentsProperties, ...] failed:

    Property: payments.retry.max-attempts
    Value: "50"
    Origin: class path resource [application.yml] - 6:19
    Reason: must be less than or equal to 10

Action:

Update your application's configuration
```

The origin line points at the exact file, line and column. Compare that with `@Value("${payments.retry.max-attempts}")`, which would have started happily and hammered the provider fifty times on the first failure.

Validation needs a Bean Validation provider on the classpath (`spring-boot-starter-validation`). Without it, `@Validated` on a properties class is silently ignored, which is worth checking once per project.

## Pitfalls

- `@Value` everywhere. Each use is an untyped string with its own default, no validation, no IDE completion, and no single place that documents what the application needs. Group related settings into one `@ConfigurationProperties` type per concern.
- Profiles as a secret store. `application-prod.yml` with a database password is committed to git and shipped in every jar. Profiles are for behaviour (which beans, which URLs); credentials come from the environment or mounted files.
- One profile per environment with copy-pasted blocks. Prefer a single file with environment variables for the few values that differ; use profiles for genuinely different wiring (an in-memory broker in `local`, for instance).
- Forgetting `@Valid` on a nested record. Constraints inside `Retry` are not checked unless the parent component carries `@Valid`.
- Misspelled keys. Unknown properties are ignored by default, so `payments.timeuot: 10s` leaves the default in place. The IDE metadata (via `spring-boot-configuration-processor`) catches most of these; `ignoreUnknownFields = false` on the annotation makes them fatal.
- Setting `spring.profiles.active` in `application-prod.yml`. Boot rejects it with an `InvalidConfigDataPropertyException`; activate profiles from outside the profile files.
- Assuming the environment variable form of a kebab-case key is obvious. `spring.jpa.open-in-view` is `SPRING_JPA_OPENINVIEW`; when in doubt, log `environment.getProperty("spring.jpa.open-in-view")` once at startup rather than guessing.

## Check yourself

1. `server.port` is 8080 in `application.yml`, 8081 in `application-prod.yml`, `SERVER_PORT=8082` in the environment, and the jar is started with `--server.port=8083` and the `prod` profile. Which port is used, and why?
2. What does `@Validated` on a `@ConfigurationProperties` record buy you that `@Value` cannot, and what has to be on the classpath for it to work?
3. A Kubernetes secret is mounted at `/run/secrets/db-password`. Show two ways to make it available as a Spring property without writing code.
4. Why is a committed `application-staging.yml` containing credentials worse than the same credentials in a CI variable, even if the repository is private?

## Go deeper

- [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) · the authoritative precedence list, relaxed binding rules, config trees, and `@ConfigurationProperties` binding details.
- [Spring Boot: Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) · activation, groups, and profile-specific files.

---

Part of [Spring](../README.md) · items 1.5, 2.3
