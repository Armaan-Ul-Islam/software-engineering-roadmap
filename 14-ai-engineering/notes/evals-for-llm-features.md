# Evals for LLM features: golden sets, judges and a CI gate

> **In one sentence:** An eval is a test suite for a probabilistic component: a fixed set of inputs with expected properties, graded by deterministic checks wherever possible and by an LLM judge calibrated against human labels where not, run on every change so that quality, cost and latency regressions show up as numbers instead of as customer complaints.

**Why it matters:** "I tried five examples and it looked fine" is how most LLM features ship, and it is why they break a month later when the prompt is tweaked, the retriever is tuned or the provider retires a model version. Prompt changes have non-local effects: fixing one case silently degrades three others. Without an eval you cannot tell improvement from noise, and you cannot say no to a change that feels better and measures worse.

## The idea

**The golden set.** A collection of cases, each with an input and the properties a good output must have. Source the inputs from real traffic (anonymised) and add deliberately hard ones: ambiguous inputs, inputs where the right answer is "not found" or a refusal, inputs in the wrong language, inputs containing instructions aimed at the model. Label them with humans, not with the model you are testing. Start with a few dozen and grow it the way you grow a regression suite: every production failure becomes a case.

**Grading, cheapest first.**

1. **Deterministic checks.** Exact match on a label from a closed set, JSON validates against the schema, the output contains the required ids and nothing else, the code compiles, the agent left the database in the expected state. Free, reproducible, and the right choice whenever the output space is constrained. Grade an agent by the end state it produced, not by the transcript.
2. **Pairwise comparison.** A judge sees the input and two candidate outputs and picks the better one or declares a tie. Judges are better at "which is better" than at absolute scores. Randomise which candidate is A and which is B, or position bias will decide.
3. **Pointwise rubric.** A judge scores one output against concrete, checkable criteria ("mentions the double charge", "does not promise a refund"), one judge call per criterion, with structured output so parsing is deterministic. Avoid holistic "rate helpfulness 1 to 5" scores; they are unreproducible and hide what went wrong.
4. **Human spot checks.** For properties no rubric captures. Expensive, so used on a sample and to calibrate the judge.

**Calibrating the judge.** An LLM judge is itself an LLM feature and needs its own eval. Take a few dozen cases a human labelled independently, run the judge, and measure agreement (per cent agreement, or Cohen's kappa if the classes are imbalanced). Iterate on the judge prompt until agreement on clear-cut cases is high; while it is low the judge's scores cannot steer decisions. Test it on known negatives: an empty answer, "I don't know", and a confident answer to the wrong question must all fail. Use a different model, ideally a different family, from the one under test; models prefer their own style. Tell the judge not to reward length, and have it treat the candidate text as data, not as instructions. Re-calibrate whenever the judge model changes.

**Regression suites in CI.** Run the suite on every change to a prompt, a model version, a retrieval setting or a tool description, exactly as unit tests run on code changes. Record per-case results, not just the aggregate. Because outputs vary between runs, measure the variance first (run the baseline several times) and set gates with a margin wider than that noise. Keep cost bounded: a tagged subset on every pull request, the full set nightly, and the whole report stored as a build artifact so trends are visible.

**Cost and latency alongside quality.** Record input and output tokens, model and latency per case and report p50 and p95 as absolute numbers before percentages. A change that improves quality by two points and doubles tokens is a product decision, not an obvious win, and it is only a decision if the numbers are on the same page.

**When quality drops.** Read the failing cases before touching anything. Classify each: retrieval miss, formatting, a genuine behaviour change, or a judge error. If more than roughly one failure in ten is the judge being wrong, fix the judge first; otherwise you are measuring its blind spots. Bisect the change (prompt, model version, retriever, data), roll back or pin the model version, and add the failing inputs to the golden set so the regression cannot return unnoticed.

## Example: an eval case and the gate around it

One case for the ticket-triage feature from item 2.2, stored as data next to the code:

```json
{
  "id": "triage-0042",
  "input": {
    "ticket": "Hi, I was charged twice for order 8812 and still have no delivery date."
  },
  "expected": {
    "category": "BILLING",
    "urgencyAtLeast": 3,
    "mentionedOrderIds": ["8812"],
    "summaryRubric": [
      "mentions the double charge",
      "mentions the missing delivery date",
      "does not promise a refund"
    ]
  },
  "source": "production ticket, 2026-09-14, anonymised",
  "tags": ["billing", "multi-issue"]
}
```

`category`, `urgencyAtLeast` and `mentionedOrderIds` are graded deterministically. Each rubric line is a separate judge call that returns `{"pass": true|false, "reason": "..."}`. Every run also records tokens and latency.

The report compares the candidate with the stored baseline, and the gate is a set of thresholds per metric:

| Metric | Baseline (prompt v12) | Candidate (prompt v13) | Gate | Result |
|---|---|---|---|---|
| Category accuracy | 0.96 | 0.97 | at least 0.95 | pass |
| Order ids exactly right | 0.99 | 0.99 | at least 0.98 | pass |
| Rubric lines passed (judge) | 0.91 | 0.84 | no more than 0.03 below baseline | fail |
| Mean tokens per case | 1,120 | 1,480 | at most 1,500 | pass |
| Latency p95 | 2.8 s | 2.6 s | at most 4.0 s | pass |

The numbers are illustrative. The candidate fails on the judged metric, so the build fails, and the next step is to read the cases that flipped from pass to fail rather than to argue with the aggregate.

In CI this is a test class or a script with four steps: load the cases, run the feature against the model (with retries on transport errors but never on "wrong" answers), grade, and write the report. The pull-request job runs the cases tagged for the feature touched; the nightly job runs everything. Deterministic parts of the pipeline (parsing, validation, prompt assembly) are covered separately by ordinary unit tests with recorded model responses (item 7.4), so the eval spends its budget only on model behaviour. Spring AI ships evaluator helpers of the LLM-judge kind for relevance and fact checking; they fit into this structure as graders and need the same calibration as any judge.

## Pitfalls

- A golden set invented by the developer in an afternoon. It tests what you thought of, which is exactly what the prompt already handles. Mine real traffic and keep adding.
- Using the model under test as its own judge. It rewards its own phrasing.
- One holistic score. It cannot be calibrated and does not tell you what broke. Grade properties separately.
- One run per configuration. The difference between 0.91 and 0.89 may be noise; measure variance before setting gates.
- A judge rubric of "is this response helpful?" Replace it with properties a careful human could check in ten seconds.
- Ground truth the model can see. If the expected answer is in a retrievable document or in the prompt, the eval measures copying.
- Unversioned prompts and datasets. A report you cannot reproduce six months later is a screenshot, not evidence.
- Running the eval once, before launch. Models get retired and silently updated; the suite has to run on a schedule, not only on your commits.

## Check yourself

1. Temperature is 0 for the feature under test. Why is a single run of the suite still not enough to declare a regression, and what do you do about it?
2. Which properties of the triage output can be graded deterministically and which need a judge? Why not let the judge grade everything?
3. Your judge agrees with human labels on 70 per cent of clear-cut cases. Can its scores gate a release? What do you do next?
4. The judged metric drops seven points after a model version upgrade and nothing else changed. List the steps you take, in order.

## Go deeper

- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) · the practical case for evals, with the levels from unit checks to human review.
- [Eugene Yan: Evaluation and hallucination detection](https://eugeneyan.com/writing/evals/) · a survey of eval methods and metrics, and what the research says about LLM judges.
- [Anthropic courses](https://github.com/anthropics/courses) · free notebooks that include building evaluations with code-based and model-based grading.
- [Spring AI: Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html) · the judge-style evaluators the framework ships and how they plug into tests.

---

Part of [AI Engineering](../README.md) · item 5.1
