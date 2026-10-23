# LLM fundamentals for engineers: tokens, context, sampling and hallucination

> **In one sentence:** A language model is a function from a sequence of tokens to a probability distribution over the next token, and every design constraint you will meet (context limits, cost, non-determinism, hallucination) follows from that one fact.

**Why it matters:** Features built on models fail in production for reasons that never show up in a demo: a prompt that silently outgrew the context window once real documents were attached, a "deterministic" temperature-zero call that still produced different output, a confident answer quoting an invoice number that does not exist. Knowing the mechanism tells you which parts of a feature belong to the model and which must stay in ordinary code.

## The idea

**Tokens.** The model never sees characters or words. A tokeniser, trained together with the model, splits text into tokens from a fixed vocabulary of a few tens of thousands of fragments. Common English words are usually one token each, often with the leading space attached; rare words, identifiers, numbers, code and most non-English text are split into several. Each model family has its own tokeniser, so counts differ between providers. A common rule of thumb for English prose is about three quarters of a word per token, but the only reliable way to know is to measure with the provider's token-counting endpoint or tokeniser tool.

**The context window.** Every request has a maximum number of tokens the model can attend to, input and output together. Everything the model will use must be inside it: the system prompt, the conversation so far, retrieved documents, tool definitions, tool results, and the room you leave for the answer. Overflow produces an error or silent truncation, depending on the provider. Window sizes change with every model generation; look them up in the provider's model documentation rather than remembering them.

**Next-token prediction.** Generation is a loop: the model reads the whole context, outputs a probability for every token in its vocabulary, one token is chosen and appended, and the loop repeats until a stop token or a length limit. Two consequences for engineers. Latency grows with the number of output tokens because they are produced one at a time, while input is processed in parallel. And the model has no memory between requests: whatever it "remembers" is text you sent again.

**Embeddings.** An embedding model maps text to a fixed-length vector in which similar meanings end up close together; they power retrieval (item 3.1). Vectors from different embedding models are not comparable.

**Sampling.** The distribution over the next token is sampled, not simply maximised. *Temperature* rescales the probabilities before sampling: at 0 the most likely token is taken every time (greedy decoding), and higher values flatten the distribution so unlikely tokens are chosen more often. *Top-p* (nucleus sampling) restricts the choice to the smallest set of tokens whose probabilities add up to p; *top-k* keeps the k most likely. Even at temperature 0 the output is not guaranteed to be identical between runs: floating-point arithmetic on batched GPU hardware is not associative, requests are routed to different machines, and providers update serving infrastructure. Some providers offer a seed parameter, documented as best effort.

**Hallucination.** The training objective rewards plausible continuations, not verified ones. When the context does not contain the answer, the model still produces the most plausible-looking text: a reference number in the right format, an API method that should exist, a citation with a convincing title. The model's expressed confidence is poorly calibrated to its correctness, so "I am certain" means little. Hallucination is most likely for precise specifics (numbers, identifiers, URLs, quotes), for questions whose premise is false, and whenever the answer is not in the context and the prompt does not allow "not found".

**What models are good and bad at.** Good: transforming text that is in front of them (summarise, rewrite, translate, classify, extract into a structure), turning fuzzy natural language into a structured intent, drafting candidates for a human to review, and writing code against well-known APIs. Bad: exact arithmetic and counting, recalling specifics from memory, satisfying long lists of constraints simultaneously, consistency across runs, and knowing anything about the current state of your system that you did not put in the prompt.

**The design constraints that follow.**

1. Treat model output as untrusted input. Parse it into a schema and validate it like a request body (item 2.2).
2. Keep deterministic logic deterministic. Arithmetic, date handling, lookups, authorisation and business rules live in code; the model decides *what* the user wants, code decides *whether* and *how* it happens.
3. Budget tokens. Count them, truncate deliberately rather than accidentally, reserve space for the answer, and log usage per request (item 2.4).
4. Design for variance. Replace "it worked when I tried it" with an evaluation set (item 5.1), make side effects idempotent, and never assert on exact strings.

## Example: how a tokeniser splits a sentence

Take the text `Invoice INV-2024-00017 is overdue by 3 days.` A byte-pair tokeniser would produce something like the split below. The exact boundaries differ between tokenisers; the shape is what matters.

```text
Invoice| INV|-|202|4|-|000|17| is| overdue| by| 3| days|.
```

Eight words became roughly a dozen tokens. The ordinary words are one token each, with their leading space. The identifier is broken into fragments at letter, digit and punctuation boundaries, and the digits are grouped in short runs that have nothing to do with how a human reads the number. This is why models mis-copy identifiers and why a change of one digit can slip through: to the model, `INV-2024-00017` is a sequence of half a dozen loosely related pieces, not an atom. JSON keys, UUIDs, code and non-English text cost more tokens per character than English prose, which is why a prompt that fits comfortably in a demo can overflow on real input.

## Example: what temperature does

Suppose that after `The invoice is` the model's top candidates are:

| Next token | Probability |
|---|---|
| ` overdue` | 0.42 |
| ` paid` | 0.31 |
| ` due` | 0.15 |
| ` disputed` | 0.07 |
| everything else | 0.05 |

At temperature 0 the model picks ` overdue` on (almost) every run. At temperature 1 it picks ` overdue` about 42 times in 100 and ` paid` about 31 times. With top-p 0.9 the tail (` disputed` and everything else) is cut off before sampling. For extraction and classification use temperature 0 and still validate; reserve higher temperatures for tasks where variety is the point, such as generating several candidate subject lines.

## Pitfalls

- Estimating tokens from characters or words measured on English prose and applying the estimate to JSON, code or another language. Measure with the provider's counter.
- Treating temperature 0 as deterministic and writing tests that assert the exact output string. Assert properties (valid schema, correct label, contains the required id) instead.
- Letting the model add up totals, compute dates or count items. The result looks right and is off by one. Do it in code and give the model the result.
- Asking the model about the state of your system ("is order 8812 shipped?") without giving it the data. It will answer anyway.
- Filling the window because it is there. Cost and latency grow, and models attend less reliably to material buried in the middle of a long context. Include what is relevant, near the question.
- Forgetting that tool definitions, tool results and retrieved chunks consume the same window as the conversation.

## Check yourself

1. Why can a prompt that works for English support tickets break when the same feature receives Norwegian tickets or stack traces, even though the number of words is similar?
2. A colleague sets temperature to 0 and writes a unit test asserting the exact output string. Give two reasons this test is flaky and say what the test should assert instead.
3. Which of these belong in code rather than in the model: computing VAT on an order, deciding whether a free-text complaint is about billing or delivery, checking that a returned customer id exists, summarising a thread? Justify each.
4. A model returns a confident reference to "RFC 7231, section 6.5.9". What about next-token prediction makes this likely, and which step in your architecture catches it?

## Go deeper

- [Andrej Karpathy: Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g) · one hour on what these systems are, from training to hallucination.
- [Andrej Karpathy: Deep Dive into LLMs like ChatGPT](https://www.youtube.com/watch?v=7xTGNNLPyMI) · shows tokenisation live and explains why models struggle with spelling and counting.
- [Hugging Face: How to generate text](https://huggingface.co/blog/how-to-generate) · greedy decoding, beam search, top-k and top-p with runnable code.
- [Simon Willison's blog](https://simonwillison.net/) · running commentary on what models can and cannot do in practice.

---

Part of [AI Engineering](../README.md) · items 1.1, 1.2, 1.4
