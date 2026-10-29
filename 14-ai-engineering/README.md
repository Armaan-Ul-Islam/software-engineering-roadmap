# AI Engineering

> Building with large language models as a backend developer: how models work well enough to use them, prompting and structured output, retrieval-augmented generation, tool use and agents, evaluation and observability, cost and latency, security, and the Java options (Spring AI, LangChain4j).

**Prerequisites:** [Spring](../06-spring/README.md), [Databases](../04-databases/README.md)

**Done when you can:**

- Explain tokens, context windows, sampling and why models hallucinate, and turn that into design constraints for a feature.
- Get reliable structured output from a model and validate it at the boundary like any other untrusted input.
- Build a retrieval pipeline (chunking, embeddings, vector search in PostgreSQL, reranking) and measure whether it actually helps.
- Implement a tool-calling loop safely, with least-privilege tools and human confirmation where side effects matter.
- Write an evaluation set for an LLM feature and run it in CI like any other test suite.
- Name the prompt-injection risks of a feature and the mitigations you applied.

## Roadmap

### 1. How models work, for engineers

- [ ] 1.1 Tokens, context windows, embeddings, transformers at a glance; the model as a next-token predictor · [notes](notes/llm-fundamentals-for-engineers.md) · [Andrej Karpathy: Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g) · [Andrej Karpathy: Deep Dive into LLMs like ChatGPT](https://www.youtube.com/watch?v=7xTGNNLPyMI)
- [ ] 1.2 Sampling: temperature, top-p, why outputs are not deterministic; hallucination and calibration · [notes](notes/llm-fundamentals-for-engineers.md) · [Hugging Face: How to generate text](https://huggingface.co/blog/how-to-generate)
- [ ] 1.3 The model landscape: hosted APIs vs open-weight models, capability tiers, price per token, latency, rate limits · [Artificial Analysis](https://artificialanalysis.ai/) · [LMArena](https://lmarena.ai/)
- [ ] 1.4 What models are good and bad at, and where deterministic code should stay deterministic · [notes](notes/llm-fundamentals-for-engineers.md) · [Simon Willison's blog](https://simonwillison.net/)

### 2. Prompting and structured output

- [ ] 2.1 System prompts, instructions, few-shot examples, delimiters, reasoning space; prompt versioning · [notes](notes/prompting-and-context-engineering.md) · [Prompt Engineering Guide](https://www.promptingguide.ai/) · [Anthropic documentation](https://docs.anthropic.com/)
- [ ] 2.2 Structured output: JSON schemas, constrained decoding, validating and retrying; mapping to Java records · [notes](notes/structured-output-and-validation.md) · [OpenAI: Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) · [Spring AI: Structured Output Converter](https://docs.spring.io/spring-ai/reference/api/structured-output-converter.html)
- [ ] 2.3 Context engineering: what goes in the window, ordering, summarisation, caching repeated prefixes · [notes](notes/prompting-and-context-engineering.md) · [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [ ] 2.4 Cost and latency: token budgets, streaming, prompt caching, batching, routing tasks to smaller models · [notes](notes/cost-and-latency-engineering-for-llm-features.md) · [OpenAI: Latency optimization](https://platform.openai.com/docs/guides/latency-optimization)

### 3. Retrieval-augmented generation

- [ ] 3.1 Embeddings and vector similarity; chunking strategies; metadata; hybrid search (BM25 plus vectors); reranking · [notes](notes/rag-pipeline-essentials.md) · [Pinecone: Retrieval-Augmented Generation](https://www.pinecone.io/learn/retrieval-augmented-generation/) · [Eugene Yan: Patterns for Building LLM-based Systems](https://eugeneyan.com/writing/llm-patterns/)
- [ ] 3.2 pgvector in PostgreSQL: HNSW and IVFFlat indexes, filtering, when a dedicated vector database is justified · [notes](notes/rag-pipeline-essentials.md) · [pgvector](https://github.com/pgvector/pgvector) · [Spring AI: PGvector store](https://docs.spring.io/spring-ai/reference/api/vectordbs/pgvector.html)
- [ ] 3.3 Evaluating retrieval: recall and precision at k, faithfulness, building a golden set · [notes](notes/rag-pipeline-essentials.md) · [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/)
- [ ] 3.4 Document pipelines: parsing PDFs and HTML, deduplication, refresh, access control on retrieved content · [notes](notes/document-ingestion-pipelines.md) · [LangChain4j: RAG](https://docs.langchain4j.dev/tutorials/rag)

### 4. Tool use, agents and MCP

- [ ] 4.1 Tool calling: schemas, the loop (model proposes, code executes, result returned), parallel calls, error handling · [notes](notes/tool-calling-and-agent-patterns.md) · [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) · [Spring AI: Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [ ] 4.2 Agent patterns: prompt chaining, routing, parallelisation, orchestrator-workers, evaluator-optimizer; when a workflow beats an agent · [notes](notes/tool-calling-and-agent-patterns.md) · [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [ ] 4.3 The Model Context Protocol: servers, tools, resources, prompts; connecting agents to your systems · [notes](notes/mcp-explained.md) · [Model Context Protocol](https://modelcontextprotocol.io/) · [Spring AI: MCP](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html)
- [ ] 4.4 Safety for tools: least privilege, read-only by default, confirmation for side effects, sandboxing, audit logs · [OWASP GenAI Security Project](https://genai.owasp.org/)
- [ ] 4.5 Memory and state: conversation history, summarisation, long-term stores, idempotent tool effects · [LangChain4j: Chat memory](https://docs.langchain4j.dev/tutorials/chat-memory)

### 5. Evaluation, observability and operations

- [ ] 5.1 Evals as tests: golden sets, LLM-as-judge with calibration against humans, regression suites in CI · [notes](notes/evals-for-llm-features.md) · [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) · [Eugene Yan: Evaluation and hallucination detection](https://eugeneyan.com/writing/evals/)
- [ ] 5.2 Tracing LLM calls: prompts, tokens, latency, cost per request; OpenTelemetry GenAI conventions; tools such as Langfuse · [notes](notes/observability-and-reliability-for-llm-calls.md) · [OpenTelemetry: Semantic conventions for generative AI](https://opentelemetry.io/docs/specs/semconv/gen-ai/) · [Langfuse](https://langfuse.com/)
- [ ] 5.3 Reliability: timeouts, retries with backoff on 429 and 5xx, fallbacks between models, circuit breakers, graceful degradation · [notes](notes/observability-and-reliability-for-llm-calls.md) · [AWS Builders' Library: Timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/)
- [ ] 5.4 Cost control: budgets per feature, caching, model routing, monitoring token usage · [notes](notes/cost-and-latency-engineering-for-llm-features.md) · [Artificial Analysis](https://artificialanalysis.ai/)
- [ ] 5.5 Feedback loops: capturing user feedback, shipping behind flags, continuous improvement of prompts and data · [Chip Huyen: Building A Generative AI Platform](https://huyenchip.com/2024/07/25/genai-platform.html)

### 6. Security and responsible use

- [ ] 6.1 Prompt injection (direct and indirect), data exfiltration through tools and rendered links, jailbreaks; the OWASP Top 10 for LLM applications · [notes](notes/prompt-injection-and-defences.md) · [OWASP Top 10 for LLM Applications](https://genai.owasp.org/llm-top-10/) · [Simon Willison: Prompt injection series](https://simonwillison.net/series/prompt-injection/)
- [ ] 6.2 Defences: privilege separation, treating model output as untrusted input, allow-listed tools, output filtering, a human in the loop · [notes](notes/prompt-injection-and-defences.md) · [Simon Willison: The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- [ ] 6.3 Data handling: personal data in prompts, provider data policies, regional hosting, retention; GDPR obligations (see Security 10.2) · [CNIL: GDPR developer's guide](https://www.cnil.fr/en/gdpr-developers-guide)
- [ ] 6.4 Responsible use: disclosure to users, bias, over-reliance, when not to use a model; the EU AI Act at a glance · [EU Artificial Intelligence Act](https://artificialintelligenceact.eu/)

### 7. Java and Spring tooling

- [ ] 7.1 Spring AI: `ChatClient`, advisors, structured output, tool calling, vector stores, evaluation support · [notes](notes/spring-ai-quickstart.md) · [Spring AI Reference](https://docs.spring.io/spring-ai/reference/)
- [ ] 7.2 LangChain4j: AI services, RAG, tools, embedding stores · [LangChain4j](https://docs.langchain4j.dev/)
- [ ] 7.3 Provider SDKs and raw HTTP: when a framework is overhead · [notes](notes/local-models-and-testing-llm-features.md) · [Anthropic documentation](https://docs.anthropic.com/) · [OpenAI API reference](https://platform.openai.com/docs/api-reference)
- [ ] 7.4 Running models locally for development and tests: Ollama; recording and replaying responses in tests · [notes](notes/local-models-and-testing-llm-features.md) · [Ollama](https://ollama.com/)
- [ ] 7.5 AI-assisted development as a skill: coding agents, reviewing generated code, keeping ownership of the design · [notes](notes/ai-assisted-development-as-a-skill.md) · [Simon Willison: Here's how I use LLMs to help me write code](https://simonwillison.net/2025/Mar/11/using-llms-for-code/)

## Resources

### Start here

- [Andrej Karpathy: Intro to Large Language Models](https://www.youtube.com/watch?v=zjkBMFhNj_g) · one hour that explains what these systems are.
- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents) · the clearest guide to agent patterns and when not to build one.
- [Prompt Engineering Guide](https://www.promptingguide.ai/) · free, comprehensive, kept current.
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) · how to make LLM features testable.
- [Spring AI Reference](https://docs.spring.io/spring-ai/reference/) · the Java path to everything above.

### Books

- [AI Engineering](https://www.oreilly.com/library/view/ai-engineering/9781098166298/) · Chip Huyen; the systems view of building with foundation models (paid).
- [Build a Large Language Model (From Scratch)](https://www.manning.com/books/build-a-large-language-model-from-scratch) · Sebastian Raschka; for understanding what is inside (paid).
- [Hands-On Large Language Models](https://www.oreilly.com/library/view/hands-on-large-language/9781098150952/) · Alammar and Grootendorst; visual and practical (paid).

### Courses and videos

- [Hugging Face LLM Course](https://huggingface.co/learn/llm-course) · free; transformers, fine-tuning, and the ecosystem.
- [DeepLearning.AI short courses](https://www.deeplearning.ai/short-courses/) · free one-hour courses on RAG, agents, evals and more.
- [Anthropic courses](https://github.com/anthropics/courses) · free notebooks on prompting, tool use and evaluations.
- [Jeremy Howard: A Hackers' Guide to Language Models](https://www.youtube.com/watch?v=jkrNMKz9pWU) · a code-first tour.

### References

- [Simon Willison's blog](https://simonwillison.net/), [Eugene Yan](https://eugeneyan.com/), [Lilian Weng](https://lilianweng.github.io/), [Chip Huyen](https://huyenchip.com/blog/) · the practitioners worth following.
- [Model Context Protocol](https://modelcontextprotocol.io/) · specification and SDKs.
- [OWASP GenAI Security Project](https://genai.owasp.org/) · the Top 10 for LLM applications and agent security guidance.
- [Latent Space](https://www.latent.space/) · newsletter and podcast for AI engineers.
- [roadmap.sh: AI Engineer](https://roadmap.sh/ai-engineer) · visual overview.
