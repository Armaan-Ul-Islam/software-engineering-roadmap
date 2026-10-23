# RAG pipeline essentials: chunking, pgvector, hybrid search and measuring retrieval

> **In one sentence:** Retrieval-augmented generation is a search problem first and a prompting problem second: if the passage with the answer is not in the top k results, no prompt will rescue the answer, so build the retriever like a search system and measure it with a golden set.

**Why it matters:** Most "the assistant gave a wrong answer" tickets in RAG systems are retrieval failures: the chunk with the answer was split in half, excluded by a metadata filter, or ranked twelfth. Teams that cannot measure recall at k spend weeks rewriting prompts and change nothing. The pgvector index trade-offs are also a favourite interview topic because they are concrete and most candidates have only read about them.

## The idea

The pipeline has two halves. At ingestion time you parse documents, split them into chunks, embed each chunk and store it with metadata. At query time you embed the question, retrieve the closest chunks (optionally filtered and reranked), put them in the prompt and ask the model to answer from them, citing the chunks it used. Every stage can lose the answer.

**Chunking.** A chunk is the unit of retrieval and the unit the model reads. Small chunks give sharper similarity scores but may cut the answer off from its context; large chunks carry context but dilute the score and eat the window. A few hundred tokens with an overlap of a sentence or two is a common starting point, then measure. Prefer structure-aware splitting (headings, paragraphs, code blocks, table rows with their header) over fixed character counts, and prefix each chunk with its document title and section path so a sentence like "this limit does not apply" remains interpretable on its own. Store the chunk position so you can fetch neighbouring chunks when a hit lands at a boundary.

**Embeddings and similarity.** An embedding model turns each chunk into a vector; the query is embedded with the same model and compared by cosine similarity (or distance). Vectors capture meaning, which is their strength and their weakness: "cancel my plan" finds "terminate a subscription", but an error code such as `E-4471` is a few odd tokens that often match unrelated codes.

**Metadata filtering.** Tenant, document type, language, date and access control are SQL predicates, not similarity. Filter in the `WHERE` clause. With an approximate index the filter is applied *after* the index scan, so a selective filter can return fewer rows than you asked for; the fixes are below.

**Hybrid search and reranking.** Lexical search (BM25 in search engines, `tsvector` ranking in PostgreSQL) is exact on identifiers and rare terms; vector search is good on paraphrase. Run both, then merge with reciprocal rank fusion: each result scores the sum over the lists of `1 / (60 + rank)`, so documents that appear high in both lists win. Then rerank the top few dozen candidates with a cross-encoder reranker, which scores query and passage together and is far more precise than comparing two independent vectors, at the cost of one extra model call.

**pgvector: HNSW vs IVFFlat.** By default pgvector does exact nearest-neighbour search, which has perfect recall and scans every row. Two approximate indexes trade recall for speed. HNSW builds a layered graph; it has the better speed-recall trade-off but slower builds and more memory, and it can be created on an empty table. IVFFlat clusters vectors into `lists` and searches `probes` of them; it builds faster and uses less memory, but must be created after the data is loaded and gives lower query performance for the same recall. Both can index `vector` columns up to 2,000 dimensions. The query-time knobs `hnsw.ef_search` (default 40) and `ivfflat.probes` (default 1) trade speed for recall, and from pgvector 0.8.0 `hnsw.iterative_scan` and `ivfflat.iterative_scan` keep scanning until a filtered query has enough rows.

**When a dedicated vector database is justified.** When the vector workload must scale independently of your transactional database (hundreds of millions of vectors, heavy concurrent ingestion). Until then PostgreSQL wins: chunks live next to the data they describe, access control is a join, and backups and transactions are the ones you already have.

**Evaluating retrieval.** Build a golden set of real questions (from logs, not from your imagination), each labelled with the chunk ids that answer it. For each configuration compute recall at k (fraction of relevant chunks that appear in the top k) and precision at k (fraction of the top k that are relevant). For the generation half, measure faithfulness (every claim in the answer is supported by a retrieved chunk) and answer relevance with an LLM judge calibrated against human labels (item 5.1). Change one thing at a time and re-run.

## Example: table, indexes and a similarity query

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunk (
    id           bigserial PRIMARY KEY,
    tenant_id    int  NOT NULL,
    document_id  uuid NOT NULL,
    chunk_index  int  NOT NULL,
    content      text NOT NULL,
    content_tsv  tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    embedding    vector(1024) NOT NULL,   -- must equal your embedding model's dimension
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX document_chunk_embedding_hnsw ON document_chunk
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX document_chunk_tsv_gin ON document_chunk USING gin (content_tsv);
```

The two-argument `to_tsvector('english', content)` is immutable and therefore allowed in a generated column; the one-argument form depends on a session setting and is rejected. `m` and `ef_construction` shown are pgvector's defaults.

The query embedding arrives from your application as a vector literal (`'[0.012, -0.031, ...]'`). The `<=>` operator is cosine distance, so similarity is `1 - distance`:

```sql
SET hnsw.ef_search = 100;

SELECT id, document_id, chunk_index, content, 1 - (embedding <=> $1) AS similarity
FROM document_chunk
WHERE tenant_id = $2
ORDER BY embedding <=> $1
LIMIT 10;
```

Hybrid retrieval with reciprocal rank fusion, in one statement:

```sql
WITH vector_hits AS (
    SELECT id, row_number() OVER (ORDER BY embedding <=> $1) AS hit_rank
    FROM document_chunk
    WHERE tenant_id = $2
    ORDER BY embedding <=> $1
    LIMIT 50
), keyword_hits AS (
    SELECT id, row_number() OVER (ORDER BY ts_rank_cd(content_tsv, query) DESC) AS hit_rank
    FROM document_chunk, plainto_tsquery('english', $3) AS query
    WHERE tenant_id = $2 AND content_tsv @@ query
    ORDER BY ts_rank_cd(content_tsv, query) DESC
    LIMIT 50
)
SELECT id, sum(1.0 / (60 + hit_rank)) AS rrf_score
FROM (SELECT * FROM vector_hits UNION ALL SELECT * FROM keyword_hits) AS hits
GROUP BY id
ORDER BY rrf_score DESC
LIMIT 10;
```

With Spring AI, `VectorStore.similaritySearch` with a `SearchRequest` (query, `topK`, a portable filter expression) covers the vector half against a table the framework manages; the hybrid query above is yours to write.

## Example: a small retrieval evaluation

Five golden questions, each with its relevant chunk ids, evaluated at k = 5 for two configurations. The numbers are the kind of output your own evaluation produces, not a benchmark.

| Question | Relevant chunks | Vector only: relevant in top 5 | Hybrid + rerank: relevant in top 5 |
|---|---|---|---|
| How do I cancel a subscription? | c17 | 1 | 1 |
| What does error E-4471 mean? | c88 | 0 | 1 |
| Which plans include SSO? | c40, c41 | 1 | 2 |
| Refund policy for annual plans? | c23 | 1 | 1 |
| Is there an API rate limit? | c61 | 0 | 1 |

Recall at 5 is the mean over questions of relevant-found divided by relevant-total: vector only gives (1 + 0 + 0.5 + 1 + 0) / 5 = 0.50, hybrid gives (1 + 1 + 1 + 1 + 1) / 5 = 1.00. Precision at 5 is relevant-found divided by 5, averaged: 0.12 against 0.24. The identifier and the rare term ("SSO", "rate limit") are exactly where lexical search earns its place, which you would not have known without the table.

## Pitfalls

- Creating an IVFFlat index on an empty or tiny table. The clusters are meaningless and recall collapses; load first, index after, re-index after bulk changes.
- Changing the embedding model, or mixing models, without re-embedding every chunk. Similarity scores become noise with no error.
- A selective filter plus an approximate index returning three rows instead of ten, silently. Enable iterative scans (0.8.0 and later), raise `ef_search`, use a partial index per tenant, or fall back to exact search for small filtered sets.
- Not storing which chunks were retrieved for each answer. Without that trace (item 5.2) a wrong answer cannot be diagnosed.
- Retrieving documents the user is not allowed to see. Access control belongs in the retrieval query, not in the prompt (item 3.4).

## Check yourself

1. A user asks about error code `E-4471` and vector search returns chunks about unrelated errors. Why does this happen, and which component of the pipeline fixes it?
2. Your tenant filter matches one per cent of rows. With an HNSW index the query returns three rows instead of ten. Explain the mechanism and give two fixes.
3. After halving the chunk size, precision at 5 rose and recall at 5 fell. What happened, and which metric matters more for a question-answering assistant?
4. Under what conditions would you move from pgvector to a dedicated vector database, and what do you give up?

## Go deeper

- [pgvector](https://github.com/pgvector/pgvector) · the README is the reference for operators, index parameters, filtering behaviour and iterative scans.
- [Spring AI: PGvector store](https://docs.spring.io/spring-ai/reference/api/vectordbs/pgvector.html) · configuration of the managed table, index type and filter expressions.
- [PostgreSQL: Controlling Text Search](https://www.postgresql.org/docs/current/textsearch-controls.html) · `to_tsvector`, `tsquery` and ranking functions for the lexical half of hybrid search.
- [Eugene Yan: Patterns for Building LLM-based Systems](https://eugeneyan.com/writing/llm-patterns/) · RAG, evals and guardrails as engineering patterns, with the research behind each.
- [Hamel Husain: Your AI Product Needs Evals](https://hamel.dev/blog/posts/evals/) · how to build the golden set and the evaluation loop around it.

---

Part of [AI Engineering](../README.md) · items 3.1, 3.2, 3.3
