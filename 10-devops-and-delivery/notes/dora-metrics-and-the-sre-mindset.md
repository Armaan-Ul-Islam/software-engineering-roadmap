# DORA metrics and the SRE mindset

> **In one sentence:** DORA's four key metrics (deployment frequency, lead time for changes, change failure rate and time to recover from a failed deployment) measure how fast and how safely a team delivers, the research shows that speed and stability improve together rather than trade off, and the SRE mindset (toil budgets, error budgets, automation over heroics) is how a product team gets there and stays there.

**Why it matters:** "We cannot deploy more often, it would be too risky" is the most common wrong belief in software delivery, and DORA's data is the standard rebuttal. The metrics also give a team a way to argue for engineering investment in a language a manager accepts: lead time went from nine days to one, change failures halved. On the operations side, a team that spends its weeks on manual deploys, restarts and ticket-driven toil never has the hours to remove the causes; the SRE idea of capping toil and spending the rest on engineering is the way out.

## The idea

**The four keys.** DORA (DevOps Research and Assessment, the research programme behind the book *Accelerate* and the yearly *State of DevOps* reports) measures software delivery performance with four metrics:

| Metric | Measures | What it answers |
|---|---|---|
| Deployment frequency | how often the team deploys to production | throughput |
| Lead time for changes | time from a commit to that code running in production | throughput |
| Change failure rate | share of deployments that cause a degradation needing remediation (rollback, hotfix, patch) | stability |
| Failed deployment recovery time | time to restore service after such a deployment (earlier reports call it time to restore service) | stability |

Later reports added a fifth measure, operational reliability (whether the service meets its availability and performance expectations), which is what SLOs (item 5.5) track.

**The central finding.** Teams that deploy more often also fail less often and recover faster. Throughput and stability are not a trade-off; the practices that make deployments small and frequent (trunk-based development, continuous integration, automated tests, continuous delivery, loosely coupled architecture, monitoring) also make each deployment less likely to fail and easier to undo. The reports cluster respondents into performance levels; in the 2019 report the top cluster, "elite", deployed on demand (multiple times a day), had a lead time under one day, restored service in under an hour and had a change failure rate between 0 and 15 percent, while the lowest cluster deployed between once a month and once every six months with lead times in the same range. The cluster boundaries are revised in each report, so quote the year when you quote a number. The metrics are outcomes; the capabilities are what you change.

**Measuring honestly.** Lead time starts at the commit, not at the merge or the deploy request, so it includes review and queue time, which is usually where the days go. Use the median per period, not the mean, so one rewrite does not hide a slow month. Change failure rate needs a definition of "failure" the team agrees on before measuring: an incident, a rollback, a hotfix deploy. Recovery time runs from when the failure became visible to when service was restored, which is usually a rollback (item 6.4), not from when the fix was merged.

**Toil.** The SRE book defines toil as work tied to running a service that is manual, repetitive, automatable, tactical, without enduring value, and that grows linearly with the service: restarting the thing, running the deploy by hand, rotating a credential, answering the same ticket. Google caps toil at 50 percent of an SRE's time so the other half goes into engineering that removes toil or improves reliability. In a product team with no SRE title the same rule applies: measure how much of the week goes to operating the service, name the biggest item, and automate it as a planned piece of work rather than a side project.

**Error budgets.** The gap between the SLO and 100 percent is a budget that the team spends on change. While it lasts, ship; when it is exhausted, reliability work takes priority over features until it recovers. That turns "how risky is this release" from an argument into a number (item 5.5). It also removes the incentive for operations to say no to everything: the budget is there to be spent.

**The SRE mindset inside a product team.** Own what you run: the team that writes the service is on call for it, carries the pager with sane rotations, writes the runbooks and the postmortems (item 8.2), and treats incidents as data about the system rather than about people. Automate the next deployment rather than performing it. Measure, then decide. Keep the service boring: a reliable system is one where the interesting work is in the product, not in keeping the lights on.

## Example: computing lead time from Git, and reading a month of deployments

Lead time for one deploy, from commit timestamps and the deploy tag's date. A repository where `v1.1.0` was deployed on 7 October at 14:00:

```bash
$ git log --format='%cI %s' v1.0.0..v1.1.0
2026-10-07T09:05:00+01:00 refactor: extract PricingPolicy
2026-10-06T16:40:00+01:00 fix(pricing): round VAT per line
2026-10-06T10:15:00+01:00 feat(export): add CSV export of invoices

$ DEPLOYED_AT=$(git for-each-ref --format='%(taggerdate:iso-strict)' refs/tags/v1.1.0)
$ git log --format='%cI %s' v1.0.0..v1.1.0 | while read -r committed_at subject; do
    hours=$(python3 -c "from datetime import datetime; print(round((datetime.fromisoformat('$DEPLOYED_AT') - datetime.fromisoformat('$committed_at')).total_seconds() / 3600, 1))")
    echo "$hours h  $subject"
  done
4.9 h  refactor: extract PricingPolicy
21.3 h  fix(pricing): round VAT per line
27.8 h  feat(export): add CSV export of invoices
```

The median lead time for this deploy is 21.3 hours: under a day, because the team deploys daily. The same three commits deployed in a fortnightly release would have had lead times of up to two weeks without any code being written more slowly. A deployment tool that records the deployed commit and the timestamp (a tag, a row in a deployments table, or the deployment events on GitHub) is all the data needed; the four keys can be computed from that table plus the incident list.

A month for one team, from such a table:

| Week | Deploys | Median lead time | Failed deploys | Recovery |
|---|---|---|---|---|
| 1 | 9 | 19 h | 1 (rollback, 12 min) | 12 min |
| 2 | 11 | 14 h | 0 | |
| 3 | 4 | 61 h | 1 (hotfix, 3 h 40 min) | 3 h 40 min |
| 4 | 10 | 16 h | 0 | |

Deployment frequency: 34 in 20 working days, well above daily. Lead time: the median over all 34 is around 16 hours, but week 3 stands out: 4 deploys and 61 hours. Looking at that week finds the cause (a release branch cut for a customer demo, item 1.3, with the pipeline paused for two days). Change failure rate: 2 of 34, roughly 6 percent. Recovery: the week 1 failure was fixed by the rehearsed rollback in 12 minutes; the week 3 failure needed a forward fix because the deploy included a one-step column rename (item 6.2), and the 3 hours 40 minutes went on writing and testing that fix. The retrospective action is not "deploy less"; it is "no more one-step renames, and never pause the pipeline for a demo".

## Pitfalls

- Treating the metrics as targets. A team told to raise deployment frequency deploys empty changes; a team told to lower change failure rate stops calling incidents failures. Measure to find the bottleneck, then fix the bottleneck.
- Comparing teams by the numbers. A payments service and an internal dashboard have different change failure costs. The useful comparison is the same team over time.
- Lead time measured from merge. It flatters the team by hiding review queues, the place where most lead time actually sits.
- Mean instead of median. One migration that took three weeks turns a good month into a bad chart.
- A change failure rate of zero. Either nothing is being deployed, or failures are not being counted. Both are findings.
- Toil nobody measures. Ask each engineer to log one week of operational work; the total is always larger than anyone guessed, and the top item is usually automatable in a sprint.
- Automation as a side project. Toil reduction that is not planned work loses to feature work every time; put it on the board with an owner, like a feature.
- An error budget with no policy. The budget is spent, nothing changes, and the SLO becomes a dashboard decoration. Agree in advance what happens when it runs out.
- Calling the pager rotation "SRE" without the engineering half. Being on call for a service you cannot change is operations under a new name; the point of the mindset is that the on-call engineer has the authority and the time to remove the causes.

## Check yourself

1. Your team deploys every two weeks with a two-day release test, and a manager proposes a third test day to reduce incidents. Using the DORA findings, what would you propose instead, and which two metrics would you expect to move first?
2. Define lead time for changes precisely enough to compute it from a Git history and a deployments table, and say what would be wrong with starting the clock at the merge.
3. Classify these as toil or not: a weekly manual certificate renewal; writing the automation for that renewal; a one-off data fix after an incident; answering the same "how do I get access" ticket every few days. For the toil items, what would you do about them?
4. A team's error budget for the quarter is spent by week six. What should happen according to the SRE model, and what makes that decision easier than the equivalent argument without a budget?

## Go deeper

- [DORA](https://dora.dev/) · the metrics, their definitions, the capabilities that drive them and the yearly reports with the current benchmarks.
- [Accelerate](https://itrevolution.com/product/accelerate/) · Forsgren, Humble and Kim; the research method and the evidence behind the four keys (paid).
- [Google SRE Book: Eliminating Toil](https://sre.google/sre-book/eliminating-toil/) · the definition of toil and the 50 percent rule.
- [Google SRE Book: Embracing Risk](https://sre.google/sre-book/embracing-risk/) · where error budgets come from and how they settle the features-versus-reliability argument.
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/) · the rest, free online; the chapters on release engineering and postmortem culture pair with items 2.4 and 8.2.

---

Part of [DevOps & Delivery](../README.md) · items 8.3, 8.4
