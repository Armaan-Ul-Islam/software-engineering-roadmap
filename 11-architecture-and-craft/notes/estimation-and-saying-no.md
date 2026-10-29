# Estimation, risk, and saying no

> **In one sentence:** An estimate is a range with a stated confidence, produced by breaking the work into tasks small enough to reason about, estimating each, multiplying by how uncertain you are, and doing the riskiest piece first so the range narrows early; and "no" is a trade-off stated out loud (what it costs in scope, time or quality) rather than a refusal or a silent yes.

**Why it matters:** The single number given in a hallway becomes a commitment, the commitment becomes a deadline, and the deadline becomes a weekend. Engineers are not bad at estimating because they lack skill; they are bad at it because they estimate the work they can see and give a number instead of a range. And most late projects were late on day one, when someone said yes to a scope that nobody had broken down. Saying no well is the senior skill that makes estimates mean anything.

## The idea

**Why it is hard.** Software estimation is estimating something you have never built, in a codebase whose surprises you have not met, with requirements that change as the customer sees the result. The unknowns are not symmetric: a task almost never takes a tenth of the estimate, and sometimes takes ten times. So the distribution is skewed, the average is above the most likely value, and a single number systematically under-delivers.

**The method** (Jacob Kaplan-Moss's version, which is the one that survives contact with a real team):

1. Break the work into tasks small enough that you can picture doing each one. A day or less is the target; anything you cannot break down is itself a finding.
2. Estimate each task's expected time, in whatever unit you use consistently.
3. Attach an uncertainty level to each task and multiply by it to get a worst case: low (1.1x, you have done this exact thing before), moderate (1.5x, familiar territory with some unknowns), high (2x, new to you or to the codebase), extreme (5x, you do not know what you do not know).
4. Sum both columns. Communicate the result as "between the expected total and the worst-case total", with the extreme-uncertainty tasks named.
5. Any task at extreme uncertainty gets a time-boxed spike first, not an estimate; the spike's output is a better breakdown.
6. Track actuals against estimates. After a few iterations the multipliers become yours rather than borrowed.

**Confidence ranges.** Say "two to four weeks, 90 percent confident" rather than "three weeks". The width of the range *is* information: a wide range says "we need a spike before we commit", and a narrow one says "this is well understood". Steve McConnell's cone of uncertainty describes the same thing over time: early estimates are off by a factor of four in either direction and the range narrows as decisions are made. Promising a narrow range early is the error, not estimating.

**Surfacing risk early.** Order the work so that the range narrows fastest: the unfamiliar integration, the performance question, the migration with the unknown data quality go first, even when they are not on the critical path for the demo. A walking skeleton (item 5.5) exists for this reason. Report risk as soon as it is seen, with a number: "the partner API is rate-limited to 10 requests per second, which makes the backfill a four-day job instead of a four-hour one", not "there are some concerns".

**Saying no.** A request arrives that does not fit. The options, best to worst:

- 1.1 **Yes, and here is what it costs.** "We can add that; it moves the release by a week" or "it fits if we drop the export feature". Scope, time and quality are the three variables, and the requester chooses which one moves. This is the honest default; it is a yes with its price tag.
- 1.2 **Not now.** "This is valuable, and it goes after the pagination work, so about six weeks." A no to the timing, not to the idea, with a date.
- 1.3 **No, because.** The reason is the point: a conflict with a decision already recorded (item 9.2), a risk the requester may not have seen, or a cheaper way to get the same outcome. Offer the alternative.
- 1.4 **A silent yes.** Agreeing to protect the relationship, then missing the date. This is the worst outcome for every party, and it is the common one.

Never give a number under pressure in a meeting. "I will have a range for you by tomorrow morning" is an acceptable answer to any estimation question, and the range you produce the next day will be the one you can defend.

## Example: a keyset pagination change, estimated

The feature is the one in item 9.2's example ADR: replace offset pagination of `GET /orders` with cursors, keep the old parameters for a year, migrate the portal and the partners. Broken down with expected days, an uncertainty level, and the worst case computed from it:

```java
import java.util.List;

public class Estimate {

    public enum Uncertainty {
        LOW(1.1), MODERATE(1.5), HIGH(2.0), EXTREME(5.0);

        private final double multiplier;

        Uncertainty(double multiplier) {
            this.multiplier = multiplier;
        }

        public double multiplier() {
            return multiplier;
        }
    }

    public record Task(String name, double expectedDays, Uncertainty uncertainty) {
        public double worstCaseDays() {
            return expectedDays * uncertainty.multiplier();
        }
    }

    public static void main(String[] arguments) {
        List<Task> tasks = List.of(
            new Task("Add cursor parameters to the orders endpoint", 1.0, Uncertainty.LOW),
            new Task("Composite index and query rewrite", 1.0, Uncertainty.MODERATE),
            new Task("Deprecation headers and usage metric", 0.5, Uncertainty.LOW),
            new Task("Migrate the partner integration", 2.0, Uncertainty.HIGH),
            new Task("Portal 'load more' control", 1.5, Uncertainty.MODERATE),
            new Task("Backfill cursor support in the reporting export", 1.0, Uncertainty.EXTREME));

        double expected = 0;
        double worst = 0;
        System.out.printf("%-52s %8s %10s %8s%n", "Task", "expected", "uncert.", "worst");
        for (Task task : tasks) {
            expected += task.expectedDays();
            worst += task.worstCaseDays();
            System.out.printf("%-52s %8.1f %10s %8.1f%n", task.name(), task.expectedDays(), task.uncertainty(), task.worstCaseDays());
        }
        System.out.printf("%-52s %8.1f %10s %8.1f%n", "Total (days)", expected, "", worst);
    }
}
```

```text
Task                                                 expected    uncert.    worst
Add cursor parameters to the orders endpoint              1.0        LOW      1.1
Composite index and query rewrite                         1.0   MODERATE      1.5
Deprecation headers and usage metric                      0.5        LOW      0.6
Migrate the partner integration                           2.0       HIGH      4.0
Portal 'load more' control                                1.5   MODERATE      2.3
Backfill cursor support in the reporting export           1.0    EXTREME      5.0
Total (days)                                              7.0                14.4
```

What this table says to the requester: "seven to fifteen working days, and the range is wide because of one item: nobody on the team knows how the reporting export paginates. Give us half a day to look at it first and we will come back with a narrower range." Two things to notice. The extreme-uncertainty task contributes a third of the worst case from a seventh of the expected time, which is the signal that it should be the spike. And the partner migration is the second largest risk, so it goes first in the plan, even though the portal change is the one the product owner wants to see demonstrated.

After the half-day spike, the export turns out to use the same repository method as the endpoint. The task drops to 0.5 days at low uncertainty, the worst case falls from 14.4 to 10 days, and the range reported is "seven to ten days". That is the narrowing the cone describes, bought with four hours.

Now the request arrives: "can you also add sorting by customer name while you are in there?" The answer from the breakdown: "Yes. Each sort order needs its own composite index and cursor encoding, so that is one to two more days, and it means we ship in the week after the partner's freeze. Or we ship cursors first and add the sort in the following release. Which do you prefer?" That is a yes with a price, and the requester now has the decision instead of the engineer having the weekend.

## Pitfalls

- Estimating the whole feature as one number. The error on a seven-task breakdown is the sum of seven small errors; the error on one guess is unbounded.
- Averaging the expected and worst cases into a single "realistic" figure. The range was the information; the average throws it away and still gets quoted as a commitment.
- Padding instead of ranges. A hidden 50 percent buffer gets cut by the first manager who notices, and then there is no buffer and no honesty.
- Omitting the work around the code: review, deployment, migration, documentation, the partner's testing window. They are tasks and they go in the table.
- Doing the easy, visible work first. The demo looks great in week one and the unknown integration blows up in week four, when there is no time left to react.
- Treating a spike as a failure to estimate. It is the cheapest estimate you will ever buy.
- Reporting risk without a number or a decision. "I'm a bit worried about the export" gets nodded at; "the export may add five days; do we want a spike or do we descope it?" gets answered.
- Saying no by going quiet. The request did not go away; it went to the deadline.

## Check yourself

1. A stakeholder asks "roughly how long?" in a meeting about work you have not broken down. Give the exact sentence you say, and what you deliver the next morning.
2. In the example, why is the export task the spike and the partner migration the first task, rather than the other way round? What property of each decides?
3. A feature is estimated at "three weeks". Rewrite that as an estimate with a range, a confidence, and the one thing that would narrow it.
4. The product owner wants a feature that conflicts with an accepted ADR. Write the "no, because" in three sentences, including the alternative you offer.

## Go deeper

- [Jacob Kaplan-Moss: Software Estimation Is Hard](https://jacobian.org/2021/may/20/estimation/) · the method in this note, from someone who has run engineering organisations on it; short and specific.
- [Malte Ubl: Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/) · the document where the breakdown, the risks and the open questions belong.
- [Fowler: Yagni](https://martinfowler.com/bliki/Yagni.html) · the cost of saying yes to presumptive features, which is the strongest argument for "not now".
- [Kent Beck: Tidy First?](https://www.oreilly.com/library/view/tidy-first/9781098151232/) · the economics of software change, including why option value makes "later" sometimes the right answer (paid).

---

Part of [Architecture & Craft](../README.md) · item 9.6
