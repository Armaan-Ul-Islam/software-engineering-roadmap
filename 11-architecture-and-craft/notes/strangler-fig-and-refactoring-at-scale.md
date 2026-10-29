# Refactoring at scale: strangler fig, branch by abstraction, parallel change, and paying down debt

> **In one sentence:** Changes too large for one pull request are made as a sequence of small, releasable steps in which the old and new implementations coexist behind a seam (a routing layer for a whole system, an interface for a component, a widened signature for an API) until the old one has no callers and is deleted; the Mikado method finds the order of those steps, and technical debt is managed the same way, one named, visible item at a time.

**Why it matters:** Every engineer has seen the long-lived migration branch that drifted for three months, merged with a hundred conflicts, and was reverted after a weekend of incidents. The alternative is not a cleverer branch but no branch: ship the migration in slices to production, each one safe to stop at. This is also how a monolith becomes services without a rewrite (item 7.3), and how a team with a backlog of debt actually reduces it rather than talking about it.

## The idea

Four techniques, from the largest unit of change to the smallest:

**Strangler fig** (a whole application or subsystem). Put a routing layer in front of the legacy system (a reverse proxy, an API gateway, or a facade class). Build the replacement for one capability at a time behind it. Route that capability's traffic to the new implementation, watch it, and leave the old code in place as the fallback until you trust the new path. Repeat until the legacy system handles nothing and can be switched off. The name is Fowler's, after the fig that grows around a host tree until the host is gone. The two things that make it work are that the routing layer is the only piece that knows which path is live, and that the old system never changes shape during the migration.

**Branch by abstraction** (a component inside one codebase, where you cannot route traffic). Introduce an interface in front of the thing being replaced, make every caller use the interface (this step is the bulk of the work and is pure refactoring), write the new implementation behind the same interface, switch over with a toggle or by configuration, delete the old implementation, and finally delete the interface if it served no other purpose. At every commit the code compiles, the tests pass, and trunk is releasable.

**Parallel change, also called expand, migrate, contract** (an API with many callers). To change a method signature, a database column or a message schema: *expand* by adding the new form next to the old; *migrate* callers one at a time to the new form, each in its own small commit; *contract* by deleting the old form when nothing uses it. A database column rename becomes: add the new column, write both, backfill, read from the new, stop writing the old, drop the old. Each step is deployable and reversible on its own.

**The Mikado method** (finding the order). Try the change you want. When it breaks, write down what would have to be true first as a prerequisite, revert, and try the prerequisite. Repeat until you reach a change that can be made without breaking anything; make that one and commit. The prerequisites form a graph whose leaves are safe changes; working the leaves inward reaches the goal in a sequence of small green commits, and the graph is the plan you can show the team. Reverting on every failed attempt is the point: it keeps the working tree clean and the knowledge in the graph.

**Technical debt.** Ward Cunningham's metaphor was for debt taken on deliberately: ship the simple model now, knowing you will learn and must refactor. Fowler's quadrant sorts the reality: deliberate or inadvertent, prudent or reckless. "We must ship now and deal with the consequences" is prudent-deliberate; "we don't have time for design" is reckless-deliberate; "now we know how we should have done it" is prudent-inadvertent and unavoidable; "what's layering?" is reckless-inadvertent. The management of it is the same in every quadrant: name each item specifically ("the orders table is read by three modules; extraction requires an API first"), put it where the team plans work, attach what it costs (the extra day every change in that area takes, the incident it caused), and pay it down inside the feature work it slows rather than in a mythical cleanup sprint. Pay down the debt that is on the path of coming changes; debt in code nobody touches costs nothing.

## Example: branch by abstraction for a shipping-rate lookup

The legacy rate table is a hard-coded class called from eleven places. It is being replaced by a carrier API with weight-based pricing. The steps, each a separate pull request:

**Step 1: introduce the seam.** Extract `ShippingRates` as an interface, make `LegacyRateTable` implement it, and change all eleven callers to depend on the interface. No behaviour change.

```java
public interface ShippingRates {
    Quote quote(String countryCode, int weightInGrams);
}

public record Quote(BigDecimal amount, String source) {}
```

**Step 2: build the new path and run it in shadow.** `CarrierApiRates` implements the interface. A comparing wrapper calls both, returns the old answer, and logs disagreements. This runs in production for as long as it takes to understand every mismatch.

```java
public final class ComparingRates implements ShippingRates {
    private final ShippingRates current;
    private final ShippingRates candidate;

    public ComparingRates(ShippingRates current, ShippingRates candidate) {
        this.current = current;
        this.candidate = candidate;
    }

    @Override
    public Quote quote(String countryCode, int weightInGrams) {
        Quote currentQuote = current.quote(countryCode, weightInGrams);
        Quote candidateQuote = candidate.quote(countryCode, weightInGrams);
        if (currentQuote.amount().compareTo(candidateQuote.amount()) != 0) {
            System.out.println("MISMATCH " + countryCode + " " + weightInGrams + "g: "
                + currentQuote.amount() + " vs " + candidateQuote.amount());
        }
        return currentQuote;
    }
}
```

**Step 3: switch over incrementally.** A toggle decides per country (or per customer, or per percentage) which implementation answers.

```java
public final class ToggledRates implements ShippingRates {
    private final ShippingRates whenOff;
    private final ShippingRates whenOn;
    private final List<String> countriesOnNewPath;

    public ToggledRates(ShippingRates whenOff, ShippingRates whenOn, List<String> countriesOnNewPath) {
        this.whenOff = whenOff;
        this.whenOn = whenOn;
        this.countriesOnNewPath = countriesOnNewPath;
    }

    @Override
    public Quote quote(String countryCode, int weightInGrams) {
        ShippingRates chosen = countriesOnNewPath.contains(countryCode) ? whenOn : whenOff;
        return chosen.quote(countryCode, weightInGrams);
    }
}
```

Running both wrappers with a legacy table (79.00 for Norway, 199.00 elsewhere) and a carrier API (39.00 plus 30.00 or 90.00 per kilogram):

```java
ShippingRates step2 = new ComparingRates(new LegacyRateTable(), new CarrierApiRates());
System.out.println("step 2, shadow: " + step2.quote("NO", 1000));
System.out.println("step 2, shadow: " + step2.quote("SE", 2000));

ShippingRates step3 = new ToggledRates(new LegacyRateTable(), new CarrierApiRates(), List.of("NO"));
System.out.println("step 3, toggled: " + step3.quote("NO", 1000));
System.out.println("step 3, toggled: " + step3.quote("SE", 2000));
```

```text
MISMATCH NO 1000g: 79.00 vs 69.00
step 2, shadow: Quote[amount=79.00, source=legacy-table]
MISMATCH SE 2000g: 199.00 vs 219.00
step 2, shadow: Quote[amount=199.00, source=legacy-table]
step 3, toggled: Quote[amount=69.00, source=carrier-api]
step 3, toggled: Quote[amount=199.00, source=legacy-table]
```

The mismatches in step 2 are the point of the shadow run: here they are expected (the pricing model changed), and the business signs off on the new numbers before any customer sees them. Where the migration is supposed to be behaviour-preserving, a mismatch is a bug in the new path found at zero cost.

**Step 4: contract.** When every country is on the new path and the toggle has been fully on for long enough, delete `LegacyRateTable`, `ComparingRates` and `ToggledRates`, and wire `CarrierApiRates` directly. If `ShippingRates` now has one implementation and no test fake, consider deleting the interface too.

The same shape applies at the system level with a strangler fig: the routing layer plays the role of `ToggledRates`, the capability being replaced is `LegacyRateTable`, and the shadow run is a traffic mirror.

## Pitfalls

- A migration branch instead of a seam. Long-lived branches merge badly, hide the work from the team and cannot be stopped halfway. Every technique here keeps trunk releasable.
- Stopping after migrate. The expand and migrate steps ship; the contract step has no visible benefit, so it never gets scheduled, and the code carries two implementations and a toggle forever. Create the contract ticket when you create the expand one.
- Changing the old system while strangling it. New features go into the new path only, or the fig never catches up with the tree.
- Shadow runs that compare too much. Comparing full response bodies with timestamps and generated ids reports a mismatch on every call; compare the fields the business cares about.
- Toggles without an owner and a removal date. Each toggle doubles the paths to test (item 7.6 covers putting a fitness function on toggle count).
- Mikado without reverting. Keeping the broken attempt "because I'm nearly there" produces the big-bang change the method exists to avoid.
- Debt tracked in a wiki page nobody opens. If it is not in the backlog with a cost, it is a complaint, not debt.
- Cleanup sprints. They are the first thing cut, and they pay down debt that was not on the path of any change. Attach paydown to the features that the debt slows.

## Check yourself

1. You must rename a column that two services read and one writes, with zero downtime. Write the expand, migrate and contract steps, and say which steps are reversible by redeploying the previous version.
2. In the example, why does `ComparingRates` return the old answer rather than the new one, and what would change if the migration were meant to be behaviour-preserving?
3. A migration has been "in step 3" for eight months with the toggle at 100 percent. What has gone wrong, what does it cost, and what single ticket fixes it?
4. Sort these into Fowler's quadrant: a prototype's data model shipped to production on purpose; a team that has never heard of transactions; a design that turned out wrong after a year of learning. Which of the three deserves the harshest review?

## Go deeper

- [Fowler: Strangler Fig Application](https://martinfowler.com/bliki/StranglerFigApplication.html) · the original two-paragraph description and the reason for the name.
- [Fowler: Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html) · the step list with a diagram per step.
- [Fowler: Parallel Change](https://martinfowler.com/bliki/ParallelChange.html) · expand, migrate, contract, with a Java signature change and a database column as examples.
- [The Mikado Method](https://mikadomethod.info/) · the authors' site, with the graph notation and a worked example.
- [Fowler: Technical Debt Quadrant](https://martinfowler.com/bliki/TechnicalDebtQuadrant.html) · the four kinds of debt and why only one is shameful.
- [Working Effectively with Legacy Code](https://www.oreilly.com/library/view/working-effectively-with/0131177052/) · seams, the mechanism every technique in this note relies on (paid).

---

Part of [Architecture & Craft](../README.md) · items 4.3, 4.4
