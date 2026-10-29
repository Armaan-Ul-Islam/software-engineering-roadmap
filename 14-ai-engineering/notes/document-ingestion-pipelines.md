# Document ingestion pipelines: parsing, deduplication, refresh and access control

> **In one sentence:** Ingestion is the batch job that turns source documents into chunks the retriever can trust: parse the format into clean text, keep provenance and permissions as metadata, skip what has not changed, replace what has, delete what is gone, and filter by the caller's rights at query time, because whatever the retriever returns is what the model will repeat.

**Why it matters:** Retrieval quality (item 3.1) is capped by what went into the index. A PDF parsed with its page headers interleaved into every paragraph, a help centre indexed twice because it is also mirrored as PDF, a policy document that was withdrawn three months ago but still answers questions, and an HR document visible to every employee because the chunk table has no access column: all of these are ingestion bugs, and the last one is a security incident. The chunking and indexing half of RAG gets the attention; the pipeline that feeds it decides whether the system is trustworthy.

## The idea

**Parsing.** Each format needs a different extractor, and the goal is the same for all: clean, ordered text with the structure that matters (title, headings, tables, page numbers) preserved as text or metadata.

- PDF. A PDF with a text layer yields text in drawing order, which is not always reading order: two-column layouts, footnotes, running headers and footers and page numbers interleave with the body. Strip repeated header and footer lines, join hyphenated line breaks, and keep the page number as metadata for citations. A scanned PDF has no text layer and needs OCR, which is slower and noisier; detect it (little or no text extracted from a large file) and route it to a separate OCR step rather than indexing empty chunks. Tables lose their structure in plain text; extract them as rows with their header repeated, or as Markdown, so a chunk that contains one row still says what the columns mean.
- HTML. Strip navigation, cookie banners, footers, scripts and styles, then keep the headings, lists and links of the main content. The document title and the heading path are the best metadata you will get for free. Apache Tika extracts text from almost every format; jsoup is the better tool for HTML because you can select the content element and discard the rest. Spring AI's ETL pipeline and LangChain4j's document loaders wrap Tika and other parsers; use them, but inspect the text they produce for your documents before trusting it.

**Normalisation and provenance.** Collapse whitespace, normalise Unicode, and drop boilerplate before anything else looks at the text. Store, per document: the source URI, the source system's own version (an ETag, a `Last-Modified` value, or a version id), a content hash of the normalised text, the fetch time, title, language, and the access rule. Per chunk: the document id, the chunk index, the heading path and page number. This is what lets an answer cite its source and lets a reviewer check it.

**Deduplication.** Exact duplicates are a hash comparison over the normalised text. Near duplicates (the same policy as PDF and as a web page, a document with a different footer date, a template filled in twice) need a looser comparison: hash after stripping dates and numbers, or shingling with MinHash if the corpus is large. Decide on a canonical source per document and index that one; if you must index both, group them under one logical document id and collapse to one hit per group at retrieval time, or the top five results will be the same paragraph five times.

**Refresh.** The index is a cache of the source and goes stale the day it is built. A refresh run lists the documents in the source, and for each one compares the source's version or the content hash with what is stored. Unchanged: update the fetch time and the access rule and move on. Changed: parse, chunk, embed and replace the old chunks in one transaction, so a query never sees half of the old version and half of the new. Absent from the source: mark deleted and remove its chunks. Keyed on `(tenant_id, source_uri)`, the run is idempotent, which is what you need when it crashes halfway and restarts. Embedding is the expensive step, so the hash check in front of it is the difference between a nightly job that takes ten minutes and one that re-bills the whole corpus.

**Access control.** The model sees whatever the retriever returns, so a leak is a retrieval bug and the fix is in the query, never in the prompt. Capture the access rule from the source system at ingestion time (the groups that may read a page, a confidentiality level, a tenant), store it on the document, and filter in the `WHERE` clause with the caller's groups resolved by your own authentication. Permissions change independently of content: an employee leaves a group, a page is restricted after the fact. Sync access rules on a shorter schedule than content, and prefer looking the rule up at query time by joining the document table rather than copying it into every chunk, so an update is one row. The pgvector caveat applies: a selective filter with an approximate index can return fewer rows than requested (item 3.2). Documents are also untrusted content: a page may contain text written to manipulate the model (item 6.1); provenance metadata is what lets you trace an odd answer back to the page that caused it.

## Example: the tables and a refresh step

The `document_chunk` table from item 3.2 gains a parent:

```sql
CREATE TABLE document (
    id                uuid PRIMARY KEY,
    tenant_id         int         NOT NULL,
    source_uri        text        NOT NULL,
    source_version    text,
    content_hash      bytea       NOT NULL,
    title             text        NOT NULL,
    allowed_group_ids int[]       NOT NULL,
    fetched_at        timestamptz NOT NULL,
    deleted_at        timestamptz,
    UNIQUE (tenant_id, source_uri)
);

ALTER TABLE document_chunk
    ADD COLUMN heading_path text,
    ADD COLUMN page_number  int,
    ADD CONSTRAINT document_chunk_document_fk
        FOREIGN KEY (document_id) REFERENCES document (id) ON DELETE CASCADE;
```

The retrieval query joins the document to apply the caller's groups and to exclude withdrawn documents. `$2` is the array of group ids the caller belongs to; `&&` is PostgreSQL's array overlap operator:

```sql
SELECT chunk.id, chunk.content, document.title, chunk.heading_path, chunk.page_number, document.source_uri
FROM document_chunk AS chunk
JOIN document ON document.id = chunk.document_id
WHERE document.tenant_id = $1
  AND document.allowed_group_ids && $2
  AND document.deleted_at IS NULL
ORDER BY chunk.embedding <=> $3
LIMIT 10;
```

The refresh step for one document. `SourceDocument` is what the connector fetched (bytes, content type, source version, access rule); the repositories are thin JDBC classes; `Chunker` and `EmbeddingClient` are the pieces from item 3.1:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import org.apache.tika.Tika;
import org.apache.tika.exception.TikaException;
import org.jsoup.Jsoup;
import org.springframework.transaction.support.TransactionTemplate;

public final class DocumentRefreshStep {

    private final Tika tika = new Tika();
    private final DocumentRepository documentRepository;
    private final ChunkRepository chunkRepository;
    private final Chunker chunker;
    private final EmbeddingClient embeddingClient;
    private final TransactionTemplate transactionTemplate;

    public DocumentRefreshStep(DocumentRepository documentRepository, ChunkRepository chunkRepository, Chunker chunker,
                               EmbeddingClient embeddingClient, TransactionTemplate transactionTemplate) {
        this.documentRepository = documentRepository;
        this.chunkRepository = chunkRepository;
        this.chunker = chunker;
        this.embeddingClient = embeddingClient;
        this.transactionTemplate = transactionTemplate;
    }

    public void refresh(SourceDocument sourceDocument) throws IOException, TikaException, NoSuchAlgorithmException {
        Optional<StoredDocument> existing = documentRepository.findBySource(sourceDocument.tenantId(), sourceDocument.sourceUri());
        if (existing.isPresent() && existing.get().sourceVersion().equals(sourceDocument.sourceVersion())) {
            documentRepository.touch(existing.get().id(), sourceDocument.allowedGroupIds(), Instant.now());
            return;
        }
        String normalisedText = normalise(extractText(sourceDocument));
        byte[] contentHash = MessageDigest.getInstance("SHA-256").digest(normalisedText.getBytes(StandardCharsets.UTF_8));
        if (existing.isPresent() && Arrays.equals(existing.get().contentHash(), contentHash)) {
            documentRepository.touch(existing.get().id(), sourceDocument.allowedGroupIds(), Instant.now());
            return;
        }
        List<Chunk> chunks = chunker.split(normalisedText, sourceDocument.title());
        List<float[]> embeddings = embeddingClient.embedAll(chunks.stream().map(Chunk::content).toList());
        transactionTemplate.executeWithoutResult(transactionStatus -> {
            StoredDocument stored = documentRepository.upsert(sourceDocument, contentHash, Instant.now());
            chunkRepository.deleteByDocumentId(stored.id());
            chunkRepository.insertAll(stored.id(), chunks, embeddings);
        });
    }

    private String extractText(SourceDocument sourceDocument) throws IOException, TikaException {
        if (sourceDocument.contentType().startsWith("text/html")) {
            org.jsoup.nodes.Document html = Jsoup.parse(new String(sourceDocument.bytes(), StandardCharsets.UTF_8));
            html.select("nav, header, footer, script, style, aside").remove();
            return html.body().text();
        }
        try (InputStream inputStream = new java.io.ByteArrayInputStream(sourceDocument.bytes())) {
            return tika.parseToString(inputStream);
        }
    }

    private static String normalise(String text) {
        return java.text.Normalizer.normalize(text, java.text.Normalizer.Form.NFC)
                .replaceAll("[ \\t]+", " ")
                .replaceAll("\\n{3,}", "\n\n")
                .strip();
    }
}
```

Two cheap checks sit in front of the expensive embedding call: the source's own version first, the content hash second (a source that bumps its version on every save still produces the same text most of the time). Deleting and inserting chunks inside one transaction keeps readers consistent. A separate pass over the source listing marks documents that no longer exist as deleted; the retrieval query above never returns them.

## Pitfalls

- Indexing a PDF without looking at the extracted text. Running headers inside every paragraph, columns interleaved, tables flattened into word soup, and every chunk slightly wrong.
- Scanned PDFs indexed as empty or near-empty chunks. They match nothing and the document is silently missing from every answer.
- The same content from two sources. The top results are the same paragraph repeated; pick a canonical source or collapse by document group.
- No refresh, or refresh that re-embeds everything. The first goes stale; the second costs the whole corpus every night.
- Deleting old chunks and inserting new ones in separate transactions. Queries in between see a document with half its content.
- Access rules in the prompt ("only answer from documents the user may see"). The model has already seen them. The filter belongs in the query.
- Access rules copied into every chunk and never re-synced. A page restricted last week is still answering questions this week.
- No provenance on chunks. The answer cannot cite anything, and a strange answer cannot be traced to the page that caused it.

## Check yourself

1. A nightly refresh of 50,000 documents re-embeds all of them every night even though a few hundred change. Which two checks would you add, in which order, and why does the order matter?
2. The retrieval query filters on `allowed_group_ids` stored per document. A user is removed from a group at 10:00. What determines when their next query stops returning that document, and how would you shorten that time?
3. A help centre is indexed from its HTML pages and again from the PDF export the marketing team publishes. Describe two ways to stop the duplicate hits and what each costs.
4. Why is "delete chunks, then insert new chunks" done in one transaction here, and what would a reader observe if it were not?

## Go deeper

- [LangChain4j: RAG](https://docs.langchain4j.dev/tutorials/rag) · the ingestion and retrieval stages with the framework's document loaders, parsers and transformers.
- [Spring AI: ETL Pipeline](https://docs.spring.io/spring-ai/reference/api/etl-pipeline.html) · the reader, transformer and writer abstractions, including the Tika-based reader and the text splitters.
- [Spring AI: PGvector store](https://docs.spring.io/spring-ai/reference/api/vectordbs/pgvector.html) · how the managed store handles metadata and filter expressions if you let the framework own the table.
- [pgvector](https://github.com/pgvector/pgvector) · the filtering section explains why a selective access filter can return fewer rows with an approximate index, and the iterative-scan fix.

---

Part of [AI Engineering](../README.md) · item 3.4
