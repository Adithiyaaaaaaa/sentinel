# Repository graphs and local semantic search

Phase 4 adds a persisted graph to new scans and an explicitly requested local embedding index. Existing scans without graph data require a rescan. Neither feature executes repository code.

## Repository map

The map shows files, functions, methods, classes, API entities, and external/unresolved import references. Edges represent lexical containment, API exposure, imports, external dependencies, and uniquely matched calls. Switch between file dependencies and symbols, select a node to inspect evidence and hash-verified source, or focus on one file and its neighbors.

Python and JavaScript/TypeScript support conservative lexical call matching. Python qualified imports can resolve cross-file calls; JavaScript cross-file calls, dynamic dispatch, inheritance, database entities, and read/write data flows are not resolved. An unresolved call is retained as unknown. A resolved edge is a static reference, not proof of runtime behavior. Import references do not certify that a package is installed.

Graphs are capped at 5,000 nodes and 20,000 edges, with at most 20,000 unresolved references. Responses return at most 500 nodes and 2,000 edges; truncation is explicit. File coupling counts unique incoming/outgoing local file dependencies. Strongly connected groups identify dependency cycles without automatically labeling them defects. Missing edges can hide cycles. Relevant graph relationships also enter local AI context as cited structural evidence, with these limitations preserved.

## Embedding index

Install and run Ollama with a local embedding-capable GGUF model. For example, explicitly run `ollama pull embeddinggemma`, then select it under **Semantic search** and choose **Build semantic index**. SENTINEL never downloads models automatically. The verified `embeddinggemma:latest` model occupied about 622 MB and produced 768-dimensional vectors; model tags can change.

The index covers at most 1,000 functions, methods, classes, and API entities from the selected completed scan. Each input includes AST metadata and up to 60 source lines, capped at 2,400 source characters and 3,600 total characters. Detected secret assignments are redacted. Other private content may remain. Inputs go only to the configured loopback Ollama service through its [embedding endpoint](https://docs.ollama.com/api/embed), without proxy environment variables or redirects. Local Ollama remains trusted software.

Source paths and hashes are verified during indexing. Vectors must be finite, nonzero, consistently dimensioned, and at most 4,096 dimensions. The model digest is checked before and after indexing. Failed or interrupted builds delete partial vectors and retain a failed job record. One build or query runs at a time per API process; busy requests return 429.

Search embeds a query of up to 500 characters and ranks the stored normalized vectors by exact cosine similarity. Results include entity name, path, line, similarity, and source-verification state. Similarity is neither a relevance probability nor security confidence. Changed source is flagged; the source viewer refuses stale excerpts. A changed model digest requires a new index. Search quality depends on the model and bounded input; no retrieval-quality benchmark is claimed.

Vectors, model identity/digest, entity keys, fingerprints, progress, and timestamps are persisted locally. Source excerpts and search queries are not persisted by this feature. Vectors encode source semantics and must be treated as private data. This is bounded exact search, not an approximate vector database or incremental index.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/scans/{id}/graph` | `view=files|symbols`, optional exact `file`, `limit=1..500` |
| GET | `/api/embeddings/models` | Installed local embedding-capable models and availability |
| POST | `/api/scans/{id}/embeddings` | Start `{ "model": "installed-name" }`, returns 202 |
| GET | `/api/scans/{id}/embeddings` | Latest 20 index jobs |
| GET | `/api/embeddings/{id}` | Running, completed, or failed index state |
| POST | `/api/embeddings/{id}/search` | `{ "query": "password storage", "limit": 10 }`; limit 1–30 |

Incomplete indexes and changed model digests return 409. Missing records return 404. Invalid inputs return 422. Model/provider failures are surfaced explicitly without fabricated search results.
