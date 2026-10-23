# Validation and error handling with Problem Details

> **In one sentence:** Declare constraints on the request types, let Spring MVC reject invalid input before your code runs, and convert every failure into the same RFC 9457 `application/problem+json` body from one `@ControllerAdvice`, so clients can rely on `status`, `type` and a predictable `errors` list.

**Why it matters:** An API whose validation errors arrive as a stack trace on one endpoint, a bare 400 on another and a custom JSON shape on a third is unusable from a frontend. Spring Framework 6 ships `ProblemDetail` and a base advice class that produce a consistent body for every framework exception; you only have to add the validation details and your domain exceptions. The pieces also show up in interviews as "how do you handle errors in a REST API".

## The idea

**Bean Validation** (Jakarta Validation, Hibernate Validator as the implementation; add `spring-boot-starter-validation`) describes constraints declaratively: `@NotBlank`, `@Positive`, `@Email`, `@Size`, `@Valid` for cascading into nested objects. In a controller, three things trigger it:

1. `@Valid` or `@Validated` on a `@RequestBody` or `@ModelAttribute` parameter validates the object after it has been deserialised. A violation raises `MethodArgumentNotValidException`, mapped to 400.
2. Constraints directly on `@RequestParam`, `@PathVariable` or `@RequestHeader` parameters (`@Min(1) int page`). Since Spring Framework 6.1 (Boot 3.2) Spring MVC applies these itself and raises `HandlerMethodValidationException`, also 400. Before 6.1 you needed `@Validated` on the class and got a `ConstraintViolationException`, which maps to 500 unless you handle it.
3. `@Validated(OnCreate.class)` selects a **validation group**, so the same type can require an id on update but forbid it on create. `@Valid` cannot take groups.

A **custom constraint** is an annotation carrying `message`, `groups` and `payload`, plus a `ConstraintValidator`:

```java
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = CurrencyCodeValidator.class)
public @interface CurrencyCode {
    String message() default "must be an ISO 4217 currency code";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

public class CurrencyCodeValidator implements ConstraintValidator<CurrencyCode, String> {
    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        return value == null || Currency.getAvailableCurrencies().stream()
                .anyMatch(currency -> currency.getCurrencyCode().equals(value));
    }
}
```

Returning true for null is deliberate: null-ness is `@NotNull`'s job, so constraints compose.

**Problem Details.** RFC 9457 (which replaced RFC 7807) defines a JSON body with `type`, `title`, `status`, `detail`, `instance` and any extra members, served as `application/problem+json`. Spring Framework 6 models it as `ProblemDetail`, and every Spring MVC exception now implements `ErrorResponse`, which carries a `ProblemDetail` and a status. `ErrorResponseException` is a ready-made exception you can throw with a status and detail from service code when you do not want a custom exception type.

`ResponseEntityExceptionHandler` is the base class for your advice. It already handles all Spring MVC exceptions (not readable body, unsupported media type, missing parameter, no handler found, validation failures) and returns their `ProblemDetail`. Setting `spring.mvc.problemdetails.enabled=true` registers such an advice for you if you define none; as soon as you write your own subclass, Boot's backs off. Spring fills `instance` with the request path when you leave it empty.

## Example: the advice and the JSON it produces

```java
@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private static final URI VALIDATION_TYPE = URI.create("https://api.example.com/problems/validation");

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException exception,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail problem = exception.getBody();
        problem.setType(VALIDATION_TYPE);
        problem.setTitle("Validation failed");
        problem.setDetail("One or more fields are invalid");
        problem.setProperty("errors", exception.getFieldErrors().stream()
                .map(fieldError -> new FieldViolation(fieldError.getField(), fieldError.getDefaultMessage()))
                .toList());
        return handleExceptionInternal(exception, problem, headers, status, request);
    }

    @ExceptionHandler(OrderNotFoundException.class)
    ProblemDetail handleOrderNotFound(OrderNotFoundException exception) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, exception.getMessage());
        problem.setTitle("Order not found");
        problem.setType(URI.create("https://api.example.com/problems/order-not-found"));
        return problem;
    }

    record FieldViolation(String field, String message) {
    }
}
```

The request type:

```java
public record PlaceOrderRequest(
        @NotNull Long productId,
        @Positive int quantity,
        @Email String customerEmail,
        @CurrencyCode String currency) {
}
```

A `POST /api/orders` with `{"productId": 42, "quantity": 0, "customerEmail": "not-an-email", "currency": "EUR"}` returns `400 Bad Request` with `Content-Type: application/problem+json` and this body:

```json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "instance": "/api/orders",
  "errors": [
    { "field": "quantity", "message": "must be greater than 0" },
    { "field": "customerEmail", "message": "must be a well-formed email address" }
  ]
}
```

The messages are Hibernate Validator's defaults, resolved through `ValidationMessages.properties`, so localising them or overriding one (`{jakarta.validation.constraints.Positive.message}`) needs no Java changes. Frontends key on `type` and `errors[].field`, never on the message text.

The base class already maps `HandlerMethodValidationException` (constraints on `@RequestParam` and `@PathVariable` parameters) to a 400 `ProblemDetail`. Override `handleHandlerMethodValidationException` in the same style when you want the `errors` list there too; its validation results are grouped per method parameter rather than per field.

## Pitfalls

- Forgetting `@Valid` on the `@RequestBody` parameter. The constraints are declared, nothing checks them, and the invalid object reaches the service. There is no warning.
- Validating in the service with `if` statements and throwing `IllegalArgumentException`. It becomes a 500 with a stack trace in the log. Either validate at the edge or map the exception in the advice.
- Echoing `rejectedValue` in the error body. For a password or token field that is a leak; include the field name and message only, or whitelist the fields whose values are safe.
- Catching `Exception` in a single `@ExceptionHandler` and returning 500 for everything. It hides the framework's correct 400, 404, 405 and 415 responses; extend `ResponseEntityExceptionHandler` and add handlers for your own types only.
- Two advice classes handling the same exception. Order is decided by `@Order`, otherwise by registration; put all handlers in one class or order them explicitly.
- Building a bespoke error shape. `ProblemDetail` is a standard that client libraries and gateways understand; adding members to it is allowed and covers the custom-field cases.
- Testing only the happy path. A `@WebMvcTest` with an invalid body asserting `jsonPath("$.errors[0].field")` takes a minute to write and pins the contract (item 7.3).

## Check yourself

1. The same `CustomerRequest` type is used for `POST` (no id allowed) and `PUT` (id required). How do you express that without two classes?
2. What is the difference between `MethodArgumentNotValidException` and `HandlerMethodValidationException`, and which parameters produce each?
3. A service throws `ErrorResponseException(HttpStatus.CONFLICT)`. Which component turns it into a response, and does your advice need a handler for it?
4. Why should a client never branch on `detail` or `errors[].message`, and what should it branch on instead?

## Go deeper

- [Spring: Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html) · `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler` and the `instance` and `type` conventions.
- [Spring: Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) · how Spring bootstraps the validator, method validation, and the 6.1 built-in controller validation.
- [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457) · short, and the source of the member names; read the section on extension members.

---

Part of [Spring](../README.md) · item 3.3
