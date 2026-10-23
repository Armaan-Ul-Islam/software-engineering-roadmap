# Trunk-based development and feature flags

> **In one sentence:** Everyone integrates into one branch at least daily, unfinished work is hidden behind flags instead of parked on branches, and so deploying code and releasing a feature become two separate decisions made by two different people.

**Why it matters:** Long-lived branches hide integration conflicts until release week and force big-bang releases that nobody can roll back cleanly. Continuous delivery (item 2.4) is only possible when the trunk is always releasable, and feature flags are what make that possible without shipping half-finished features to users. Unmanaged, the same flags turn into permanent `if` statements that nobody dares to remove.

## The idea

**Three branching models.**

| Model | Branch lifetime | Integration happens | Release from |
|---|---|---|---|
| Git flow | weeks: `develop`, `release`, `hotfix`, long feature branches | at release time, all at once | release branches merged back and forth |
| GitHub flow | days: a feature branch and a pull request | on merge to `main` | `main` |
| Trunk-based | hours to a day or two, or commits straight to trunk | daily or more often | trunk, or a release branch cut from trunk that is never merged back (fixes are made on trunk and cherry-picked) |

Trunk-based development works because small diffs are easy to review (item 1.2), merge conflicts stay trivial, and CI tests the real integrated state rather than each branch's private universe. DORA's research associates it with higher delivery performance. It requires a fast pipeline on every commit, same-day code review (or pairing), and a way to merge work that is not finished.

**Hiding unfinished work.** *Branch by abstraction*: introduce an interface, add the new implementation behind it, switch, remove the old one. *Keystone interface*: build the back end first and add the user-facing entry point last. *Feature flags*: a runtime condition that selects the path. Fowler's categories matter for hygiene: *release toggles* hide incomplete work and live weeks; *experiment toggles* run A/B tests and live until the result is in; *ops toggles* are kill switches and may live long; *permission toggles* gate features per customer and are really product configuration.

**Deploy is not release.** Deploying puts code in production, dark. Releasing exposes it, by flipping a flag: for employees first, then one percent of customers, then everyone. Rollback becomes a configuration change rather than a redeploy, and testing in production with real data becomes possible before any customer sees the feature. This is what lets a team deploy many times a day while product decides when features appear.

**Flag hygiene.** Every flag has an owner, a purpose, a type, a creation date and a removal date with a ticket. Release toggles default to off; the off path is the proven one. Removing the flag and the old path is part of the feature's definition of done. Test both paths, and in particular the combination that will actually ship. Evaluate a flag once per request at the edge of the code and pass the decision down, so one request never sees both behaviours. Keep the count of active release toggles small, and never nest them. Configuration can start as a property; a flag service (OpenFeature is the vendor-neutral API, with providers such as Unleash, LaunchDarkly or flagd) adds targeting, percentages and an audit log.

## Example: a flag-guarded code path and the life of the flag

```java
import java.util.Map;

public interface FeatureFlags {

    boolean isEnabled(String flagName, String customerId);
}

public final class PercentageFeatureFlags implements FeatureFlags {

    private final Map<String, Integer> rolloutPercentageByFlag;

    public PercentageFeatureFlags(Map<String, Integer> rolloutPercentageByFlag) {
        this.rolloutPercentageByFlag = Map.copyOf(rolloutPercentageByFlag);
    }

    @Override
    public boolean isEnabled(String flagName, String customerId) {
        int percentage = rolloutPercentageByFlag.getOrDefault(flagName, 0);
        int bucket = Math.floorMod((flagName + ":" + customerId).hashCode(), 100);
        return bucket < percentage;
    }
}
```

Bucketing on a stable hash of flag name and customer id means a customer sees the same behaviour on every request while the rollout is at 10 percent, and including the flag name means a customer is not always in the first 10 percent for every flag. `String.hashCode` is specified by the language, so the buckets agree across instances and JVM versions. The percentages come from configuration, for example `@ConfigurationProperties(prefix = "features")` bound to `features.new-pricing-engine=10`.

```java
public final class PricingService {

    // Release toggle. Owner: pricing team. Remove by 2026-12-01, ticket PRC-311.
    static final String NEW_PRICING_ENGINE = "new-pricing-engine";

    private final FeatureFlags featureFlags;
    private final LegacyPricingEngine legacyPricingEngine;
    private final RuleBasedPricingEngine ruleBasedPricingEngine;

    public PricingService(FeatureFlags featureFlags,
                          LegacyPricingEngine legacyPricingEngine,
                          RuleBasedPricingEngine ruleBasedPricingEngine) {
        this.featureFlags = featureFlags;
        this.legacyPricingEngine = legacyPricingEngine;
        this.ruleBasedPricingEngine = ruleBasedPricingEngine;
    }

    public Price priceFor(Order order) {
        if (featureFlags.isEnabled(NEW_PRICING_ENGINE, order.customerId())) {
            return ruleBasedPricingEngine.price(order);
        }
        return legacyPricingEngine.price(order);
    }
}
```

One decision point, both engines behind the same interface, and the flag's metadata next to its constant. Tests cover both paths with a stub: `FeatureFlags everythingOn = (flagName, customerId) -> true;` and its `false` twin.

The flag's lifecycle:

| Step | Trunk | Flag | Who decides |
|---|---|---|---|
| 1 | Several small pull requests add `RuleBasedPricingEngine` behind the flag, each merged the day it is opened | 0 percent | developers |
| 2 | Deployed to production dark; enabled for internal test customers; prices from both engines compared in a metric | 1 percent | developers and QA |
| 3 | Ramp while watching the SLIs (item 5.5) and the price-difference metric | 10, 50, 100 percent | product and developers |
| 4 | Soak at 100 percent for a release or two; the flag is now a kill switch | 100 percent | on-call, if needed |
| 5 | Delete `LegacyPricingEngine`, the `if`, the configuration key and the tests of the old path; close PRC-311 | gone | developers |

Steps 1 and 2 are deployments; step 3 is the release. Nothing in step 5 needs a deploy window, because removing a flag at 100 percent changes no behaviour.

## Pitfalls

- Branches that live for weeks "because the feature is not done". That is precisely the situation flags exist for; the branch is the problem, not the feature.
- Flags that are never removed. Each one doubles the number of code paths to test; after a year nobody knows which flags are load-bearing, and reusing an old flag name for a new purpose has caused famous production disasters.
- Evaluating the same flag in several places. Two evaluations in one request can disagree (a percentage changed between them, or a different key was used), and the request sees half of each behaviour.
- Testing only the on path. The off path rots until the day the kill switch is needed.
- Random rollout per request instead of a stable bucket. Users flicker between behaviours and bug reports cannot be reproduced.
- Flags that change data. If the new path writes a new format, both paths must read it, which is the expand-contract problem from item 6.2 in disguise.
- Treating a permission toggle like a release toggle. Per-customer features are product configuration with a long life; name and store them as such instead of leaving them in the flag backlog.
- Calling it trunk-based while the build stays red. A broken trunk blocks everyone; fixing or reverting it is the team's first task.

## Check yourself

1. Your team merges feature branches after two or three weeks and dreads release week. Which two practices from this note change that, and what must the pipeline provide first?
2. Why is bucketing on a hash of flag name and customer id better than `Math.random()` for a percentage rollout, and what does including the flag name prevent?
3. Define "done" for a release toggle, and describe one mechanical way to enforce the removal date (for example a test that fails after it).
4. A flag has been at 100 percent for six months and the old path still exists. List the costs it still imposes on the team.

## Go deeper

- [Trunk Based Development](https://trunkbaseddevelopment.com/) · the practice in detail, including release branches and how large teams do it.
- [Martin Fowler: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) · the toggle categories, implementation techniques and hygiene rules this note condenses.
- [Martin Fowler: Branch By Abstraction](https://martinfowler.com/bliki/BranchByAbstraction.html) · making large changes incrementally on trunk without a flag.
- [DORA](https://dora.dev/) · the research linking trunk-based development and small batches to delivery performance.
- [OpenFeature](https://openfeature.dev/) · the vendor-neutral flag evaluation API when a property file is no longer enough.

---

Part of [DevOps & Delivery](../README.md) · item 1.1
