# AI-assisted development as a skill: briefing, reviewing and keeping ownership

> **In one sentence:** A coding agent is a fast, tireless, over-confident junior colleague with no memory of your codebase: it produces good work when you give it a precise brief, a way to check itself, and a real review, and it produces plausible wrong work when you give it a vague wish and merge what comes back.

**Why it matters:** The productivity gain is real and so is the failure mode: pull requests nobody on the team can explain, a design that drifted because the agent chose the easiest local change ten times in a row, generated tests that assert the implementation rather than the behaviour, and a hallucinated library method that compiled against nothing. The engineers who get the most out of these tools are not the ones who type the least; they are the ones who already know what good looks like and use the agent to get there faster while staying the owner of every line.

## The idea

**Two kinds of tools.** Inline assistants complete the line or the function you are writing; you remain the author and review each suggestion as you accept it. Coding agents take a task, read the repository, edit files, run commands and tests, and come back with a diff. The second kind is where the gains and the risks concentrate, and the rest of this note is about them.

**What to delegate.** Work whose correctness you can check faster than you could write it: boilerplate and plumbing, a migration between two well-known APIs, a first draft of tests for existing code, a change that follows an existing pattern in the codebase ("add a DELETE endpoint like the PUT one"), exploration of unfamiliar code ("where is the retry policy decided and who calls it?"), and throwaway scripts. Keep for yourself the decisions: boundaries between modules, data models, transaction scope, concurrency, anything security-sensitive, and any change where the hard part is deciding what to build rather than building it.

**How to brief.** The agent knows only what is in its context. A good brief has:

1. The goal in one sentence, and the acceptance criteria: the test that should pass, the command that should succeed, the observable behaviour.
2. The constraints: what not to touch, which library to use, which pattern in the codebase to copy (name the file).
3. The conventions: a repository instructions file (many tools read `AGENTS.md` or a tool-specific equivalent) that states naming rules, error-handling rules, test commands and what must never be committed. Write it once, keep it short, and every session starts with it.
4. A feedback loop: the compiler, the test suite, a linter, a type checker. An agent that can run the tests fixes its own mistakes; one that cannot ships them to you.

Write the test or the interface first when you can. A failing test is the most precise brief there is.

**How to review.** Read every line as if a contractor you do not know had written it, because that is the situation. Look specifically for: methods or parameters that do not exist in the library version you use; error handling that catches broadly and swallows; missing authorisation or tenant checks on a new endpoint; data loaded in bulk and filtered in memory; a new dependency added to avoid writing ten lines; tests that mock the thing under test or assert the mock was called; and scope creep, where the agent "also fixed" something unrelated. Run it. Then ask whether you could explain the change in a design review; if not, you are not done.

**Keeping ownership of the design.** Work in small, reviewable steps, one concern per diff. Decide the structure yourself and let the agent fill it in, rather than asking for a feature and accepting whatever architecture arrives. When the agent's approach differs from yours, decide explicitly instead of drifting. Commit messages and pull request descriptions are yours; they record why, which the agent cannot know. The codebase should look as if one careful team wrote it, not as if several sessions each solved a local problem.

**Security and hygiene.** The agent reads files, and files can contain instructions meant for it: a comment in a dependency, a README in a cloned repository, a build log (item 6.1). Give it least privilege: read-only where possible, no production credentials, no ability to push or deploy without a human step, and tool calls that can delete or spend shown for confirmation. Secrets in the working tree end up in the context; keep them out. Generated code can reproduce licensed snippets verbatim; be alert to large blocks that arrive fully formed with no relation to your codebase's style.

## Example: a brief, an illustrative draft, and the review that caught two defects

The brief, pasted into the agent together with the repository's instructions file:

```text
Add GET /customers/{customerId}/invoices returning the customer's OPEN invoices as InvoiceSummary records.
Acceptance: a @WebMvcTest in InvoiceControllerTest passes for a customer with two open and one paid invoice.
Constraints: follow the style of OrderController and OrderRepository. Use a repository query; do not filter in Java.
The caller must be the customer or have the SUPPORT role, as in OrderController.requireAccess.
Do not touch other endpoints. Run ./mvnw -q test -Dtest=InvoiceControllerTest before reporting.
```

The draft the agent returned (illustrative; the shape of mistakes is what matters, not the exact text):

```java
@GetMapping("/customers/{customerId}/invoices")
public List<InvoiceSummary> openInvoices(@PathVariable long customerId) {
    try {
        return invoiceRepository.findAll().stream()
                .filter(invoice -> invoice.customerId() == customerId && invoice.status() == InvoiceStatus.OPEN)
                .map(InvoiceSummary::from)
                .toList();
    } catch (Exception exception) {
        log.error("failed to load invoices", exception);
        return List.of();
    }
}
```

The test passed. The review found three problems in nine lines: the brief's "use a repository query" was ignored and every invoice in the system is loaded and filtered in memory; the access check from the brief is missing, so any authenticated caller can read any customer's invoices; and the broad catch turns a database outage into an empty list with a 200 status. A test that only checks the happy path for one customer cannot see any of them. The corrected version, written after re-briefing with the three findings:

```java
@GetMapping("/customers/{customerId}/invoices")
public List<InvoiceSummary> openInvoices(@PathVariable long customerId, @AuthenticationPrincipal AppUser caller) {
    accessPolicy.requireAccess(caller, customerId);
    return invoiceRepository.findByCustomerIdAndStatus(customerId, InvoiceStatus.OPEN).stream()
            .map(InvoiceSummary::from)
            .toList();
}
```

with `findByCustomerIdAndStatus` declared on the repository and two further tests: a different customer gets 403, and the paid invoice is absent. The agent wrote the second draft and the tests in a couple of minutes; the value came from a reviewer who knew that "filter in Java" and "missing access check" are the two things to look for in any generated endpoint.

The instructions file that would have prevented two of the three on the first pass:

```text
# Working in this repository
- Endpoints: every handler calls accessPolicy.requireAccess(caller, resourceOwnerId) before loading data.
- Data access: filter in the query, never with findAll().stream().filter(...).
- Errors: never catch Exception in controllers; let the global handler map exceptions to responses.
- Tests: every new endpoint has a forbidden-caller test and a negative-data test.
- Run ./mvnw -q test -Dtest=<TestClass> for the touched classes before reporting.
```

## Pitfalls

- Merging what you did not read. The test passed and the authorisation check is missing.
- Vague briefs. "Add invoice listing" produces a design; "add this endpoint, like that one, with these tests" produces a diff.
- No feedback loop. An agent that cannot run the tests cannot know it broke them.
- Trusting library knowledge. The agent remembers an API as it was, or as it plausibly could be; verify against the version in your build.
- Generated tests that lock in the implementation. Mocks asserted on call counts, happy path only, no forbidden-caller case.
- Design by accretion. Ten locally reasonable changes and nobody can draw the architecture.
- Accepting unrelated changes bundled into the diff. Reformatting, renamed variables, a "small improvement" to another class: split them out or reject them.
- Running agents with production credentials or push rights. Prompt injection through repository content is real (item 6.1), and a deletion is a deletion.
- Letting the tool replace learning. If you could not have written it, you cannot review it; use the agent to explain as well as to produce, and read the explanation.

## Check yourself

1. Rewrite the brief "make the invoice page faster" so that an agent can act on it and you can verify the result. What did you have to find out first?
2. The draft in the example passed its test. Name the three defects and, for each, the test or instruction that would have caught it without a human reading the code.
3. Which of these would you delegate and which would you keep: choosing between optimistic and pessimistic locking for a hot row, writing the migration script once chosen, adding a forbidden-caller test to every endpoint, deciding the module boundary for a new payments feature?
4. A colleague says the agent "knows the codebase". What does it actually know at the start of a session, and what should you do about it?

## Go deeper

- [Simon Willison: Here's how I use LLMs to help me write code](https://simonwillison.net/2025/Mar/11/using-llms-for-code/) · a practitioner's working method: context, briefs, testing, and where the tools fail.
- [Simon Willison: The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) · why an agent with private data, untrusted content and a way to send data out is dangerous; applies directly to coding agents with repository access.
- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) · the agent loop and the case for simple, inspectable workflows, which is what a good coding session is.
- [Anthropic documentation](https://docs.anthropic.com/) · the documentation for one vendor's coding agent, including permissions, instruction files and tool configuration.

---

Part of [AI Engineering](../README.md) · item 7.5
