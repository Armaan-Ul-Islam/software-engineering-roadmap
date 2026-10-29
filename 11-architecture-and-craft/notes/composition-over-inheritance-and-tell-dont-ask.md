# Composition over inheritance, Tell Don't Ask, and information hiding

> **In one sentence:** Build behaviour by combining small objects that each play a role (an interface) rather than by extending a base class, keep an object's data behind its methods so callers tell it what to do instead of asking for its fields and deciding themselves, and design each module so that it hides one decision that is likely to change behind an interface that is much simpler than what it does.

**Why it matters:** The deepest class hierarchies in a codebase are usually the hardest code to change: a fix in the base class breaks a subclass three levels down that overrode half of it. Getter-driven code (`if (account.getBalance() >= amount) account.setBalance(...)`) spreads one rule across every caller, and the one that forgets it is the production bug. These three ideas, from 1972 (Parnas), the 1990s (the Gang of Four, the Law of Demeter) and 2013 (Fowler on Tell Don't Ask), are the same idea from three angles: put the decision in one place and hide it.

## The idea

**Composition over inheritance.** Inheritance says "is a" and shares implementation; it is the strongest coupling the language offers, because a subclass depends on the parent's private behaviour, its call order, and every future change to it (the fragile base class problem). Composition says "has a" and "uses a": the object holds a reference to something that plays a role, and the role is an interface. The Gang of Four stated the preference in 1994, and the practical reasons are:

- 1.1 Behaviours combine. With inheritance, "retrying" and "audited" variants of two channels need four subclasses, and a third concern makes it eight. With composition, each concern is one wrapper and they stack in any order.
- 1.2 Behaviour can change at runtime. A composed object can be given a different collaborator; a subclass is fixed at `new`.
- 1.3 Tests can substitute collaborators. A role with two implementations has a fake for free.
- 1.4 Liskov violations disappear. Most `UnsupportedOperationException` overrides come from inheriting for reuse (item 2.1).

Inheritance is still right for a genuine subtype whose every method keeps the parent's promises, for sealed hierarchies that model a closed set of cases, and for abstract template methods where the parent owns the algorithm. The test is whether you would be happy for every caller of the parent to receive the child without knowing.

**Interfaces as roles.** Name the interface after what the collaborator does for its client, not after the class that implements it. `Channel`, `Clock`, `PaymentGateway` are roles; `EmailChannelInterface` and `OrderServiceImpl` are the shape of a class with the implementation removed. A role is small, often one or two methods, and the same class may play several.

**Tell, Don't Ask.** Fowler's phrasing: rather than asking an object for data and acting on it, tell the object what to do and let it decide. The code smell is a getter followed by a condition followed by a setter on the same object; the rule it enforces lives in the caller, and every other caller must repeat it. The fix moves the condition into the object as a method with a domain name. This is the operational form of encapsulation, and the reason an anemic domain model (item 3.5) is a problem: every rule is somewhere other than on the data it protects.

**The Law of Demeter.** A method should call methods only on: itself, its parameters, objects it creates, and its own fields. Not on the objects returned by those (`order.getCustomer().getAddress().getCountry()`). Every link in that chain is a structural fact the caller now depends on; move the customer's address and the caller breaks. Ask the nearest object for what you actually need (`order.shippingCountry()`). The law has a well-known exception: fluent interfaces and streams return the same object or a value, not a neighbour's internals, and are not what it warns about.

**Information hiding (Parnas).** The 1972 paper's criterion for splitting a system into modules is not the steps of the processing but the design decisions likely to change: each module hides one such decision (the data format, the storage mechanism, the algorithm) behind an interface that reveals as little as possible about it. Ousterhout's *deep modules* (item 1.2) is the same point measured: a module's value is the functionality it provides divided by the complexity of its interface. `java.io.FileInputStream` is deep; a class with twelve getters and twelve setters is shallow, because it hides nothing. Tell Don't Ask, Demeter, and composition all serve this one criterion: make the interface say what the client wants done, and keep how it is done inside.

## Example: four channel variants from two classes and two wrappers

The inheritance version would need `RetryingEmailChannel`, `AuditedEmailChannel`, `AuditedRetryingSmsChannel` and so on. With a role and two decorators:

```java
import java.util.ArrayList;
import java.util.List;

public interface Channel {
    void send(String recipient, String message);
}

public final class EmailChannel implements Channel {
    @Override
    public void send(String recipient, String message) {
        System.out.println("email to " + recipient + ": " + message);
    }
}

public final class Retrying implements Channel {
    private final Channel delegate;
    private final int maximumAttempts;

    public Retrying(Channel delegate, int maximumAttempts) {
        this.delegate = delegate;
        this.maximumAttempts = maximumAttempts;
    }

    @Override
    public void send(String recipient, String message) {
        for (int attempt = 1; ; attempt++) {
            try {
                delegate.send(recipient, message);
                return;
            } catch (IllegalStateException exception) {
                if (attempt == maximumAttempts) {
                    throw exception;
                }
                System.out.println("attempt " + attempt + " failed: " + exception.getMessage());
            }
        }
    }
}

public final class Audited implements Channel {
    private final Channel delegate;
    private final List<String> auditLog;

    public Audited(Channel delegate, List<String> auditLog) {
        this.delegate = delegate;
        this.auditLog = auditLog;
    }

    @Override
    public void send(String recipient, String message) {
        delegate.send(recipient, message);
        auditLog.add("sent to " + recipient);
    }
}
```

Wired with an `SmsChannel` whose first two attempts throw `IllegalStateException("gateway timeout")`:

```java
List<String> auditLog = new ArrayList<>();
Channel email = new Audited(new EmailChannel(), auditLog);
Channel sms = new Audited(new Retrying(new SmsChannel(), 3), auditLog);
email.send("ada@example.com", "Your order has shipped");
sms.send("+4799999999", "Your order has shipped");
System.out.println(auditLog);
```

```text
email to ada@example.com: Your order has shipped
attempt 1 failed: gateway timeout
attempt 2 failed: gateway timeout
sms to +4799999999: Your order has shipped
[sent to ada@example.com, sent to +4799999999]
```

Neither wrapper knows what it wraps; neither channel knows it is wrapped. Swapping the order (`Retrying(Audited(...))`) changes the semantics to "audit every attempt", and that is a wiring decision, not a new class. This is the Decorator pattern (item 3.2), and it is what Spring does when it proxies a bean for `@Transactional` or `@Retryable`.

## Example: Tell, Don't Ask on an account

Asking:

```java
if (account.getBalance().subtract(amount).compareTo(account.getOverdraftLimit().negate()) >= 0) {
    account.setBalance(account.getBalance().subtract(amount));
}
```

Every caller must know the overdraft rule, and this one silently does nothing when it fails. Telling:

```java
import java.math.BigDecimal;

public final class Account {
    private BigDecimal balance;
    private final BigDecimal overdraftLimit;

    public Account(BigDecimal balance, BigDecimal overdraftLimit) {
        this.balance = balance;
        this.overdraftLimit = overdraftLimit;
    }

    public void withdraw(BigDecimal amount) {
        BigDecimal newBalance = balance.subtract(amount);
        if (newBalance.compareTo(overdraftLimit.negate()) < 0) {
            throw new IllegalArgumentException("Withdrawal of " + amount + " would exceed the overdraft limit");
        }
        balance = newBalance;
    }

    public BigDecimal balance() {
        return balance;
    }
}
```

```java
Account account = new Account(new BigDecimal("100.00"), new BigDecimal("50.00"));
account.withdraw(new BigDecimal("120.00"));
System.out.println("balance after first withdrawal: " + account.balance());
account.withdraw(new BigDecimal("50.00"));
```

```text
balance after first withdrawal: -20.00
Exception in thread "main" java.lang.IllegalArgumentException: Withdrawal of 50.00 would exceed the overdraft limit
```

`setBalance` and `getOverdraftLimit` are gone, so the rule cannot be bypassed. The `balance()` query stays: Tell Don't Ask is not "no getters", it is "no decisions made outside the object on the object's behalf". Queries for display and reporting are fine; a query followed by a command on the same object is the smell.

## Pitfalls

- Inheriting to reuse a few methods. The subclass gets the whole parent surface, including methods that make no sense for it, and the override that throws is a Liskov violation waiting for a caller.
- Deep hierarchies "for extensibility". Three levels of abstract base classes, each with template methods, where a reader must open five files to find out what one call does. Prefer a role and a strategy.
- Interfaces that mirror a class. `OrderService` plus `OrderServiceImpl` with twelve methods is not a role; nobody will ever write a second implementation. Roles are small and named for the client's need.
- Demeter applied to value objects and builders. `order.total().amount()` and `LocalDate.now().plusDays(3).getDayOfWeek()` are not violations; they return values, not another object's internals.
- Tell Don't Ask taken to mean "no queries at all", which produces objects that render their own HTML. Commands belong with the data; presentation asks.
- Wrapper chains without a factory. Six nested `new` calls at every injection point is wiring duplication; build the chain once in a `@Configuration` method or a factory.
- Information hiding by `private` alone. A class whose public interface exposes its storage layout (`getRows()`, `setIndexMap(...)`) hides nothing, whatever the field modifiers say.

## Check yourself

1. `ArrayList` could have been implemented as a subclass of a hypothetical `ResizableArray`, or by holding an array as a field. Which did the JDK choose, and what would the other choice have exposed?
2. Rewrite `if (order.getStatus() == Status.PLACED && order.getPlacedAt().isBefore(cutoff)) { order.setStatus(Status.EXPIRED); }` in Tell Don't Ask form, and say which rule moved and where to.
3. Is `customer.orders().stream().filter(Order::isOpen).count()` a Law of Demeter violation? What about `customer.getAccount().getBank().getSwiftCode()`? Explain the difference.
4. Parnas says a module should hide a decision likely to change. Name the decision hidden by `Channel` in the example, and one decision the example still leaks.

## Go deeper

- [Fowler: Tell, Don't Ask](https://martinfowler.com/bliki/TellDontAsk.html) · the principle, the smell, and Fowler's warning against applying it to every getter.
- [Composition over inheritance](https://en.wikipedia.org/wiki/Composition_over_inheritance) · the Gang of Four argument with the combinatorial example spelled out.
- [Parnas: On the Criteria To Be Used in Decomposing Systems into Modules](https://www.win.tue.nl/~wstomv/edu/2ip30/references/criteria_for_modularization.pdf) · the original paper; the two decompositions of the same program in section 3 are still the clearest illustration of information hiding.
- [A Philosophy of Software Design](https://web.stanford.edu/~ouster/cgi-bin/book.php) · deep modules, information hiding and leakage, with examples of each (paid).
- [refactoring.guru: Decorator](https://refactoring.guru/design-patterns/decorator) · the pattern the first example uses, with the trade-offs against subclassing.

---

Part of [Architecture & Craft](../README.md) · items 2.4, 2.5
