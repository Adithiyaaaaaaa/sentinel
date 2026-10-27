# SENTINEL API

Base URL for direct local development: `http://127.0.0.1:8000`. The frontend uses the same-origin `/api` proxy. Generated OpenAPI is available at `/openapi.json` and Swagger UI at `/docs`.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service and database health |
| GET | `/api/settings` | Effective repository roots, sample path, and feature/privacy state |
| GET | `/api/browse?path=...` | Child directories inside permitted roots |
| GET | `/api/repositories` | Registered repositories and latest scans |
| POST | `/api/repositories` | Register `{ "path": "...", "ignore_patterns": [] }` |
| POST | `/api/repositories/{id}/scans` | Queue a background scan; returns HTTP 202 |
| GET | `/api/repositories/{id}/scans` | Historical scans for a repository |
| GET | `/api/scans/{id}` | Scan status, progress, metrics, and failure details |
| GET | `/api/scans/{id}/files` | Paginated file snapshot; accepts `q`, `language`, `offset`, and `limit` |

Scan status is one of `queued`, `running`, `completed`, or `failed`. Scan metrics describe the files successfully indexed, not all files present on disk. `languages` maps names to `files` and `lines`; line counts include blank and comment lines. Dependency count reflects declarations detected from supported manifests.

File records include their repository-relative path, detected language, line count, byte count, and SHA-256 hash. They contain no file source text. Errors use FastAPI's `detail` response field; input validation can return its standard structured list of validation errors.

The client polls scan status until a terminal state. Polling is the progress transport; server-sent events and distributed workers are later scalability work. Do not treat a queued or running scan's zero counters as a completed analysis.

Scan history returns up to the 100 most recent scans. The files endpoint defaults to 100 rows and accepts a maximum `limit` of 500; clients use `offset` for subsequent pages. Search matches paths and the language filter uses the exact detected language name.

Folder browsing enumerates at most 10,000 entries and returns at most 500 subdirectories. A `truncated` flag reports partial listings; users can enter a full path to select a directory outside that listing. Repeating a scan request while that repository is already queued or running returns the same active scan. A full global queue returns HTTP 429 without leaving a phantom queued scan.

## Static analysis

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/rules` | Versioned rule metadata, confidence, and limitations |
| GET | `/api/scans/{id}/findings` | Filter by severity, category, status, language, CWE, OWASP, minimum confidence, or title/path search |
| GET | `/api/findings/{id}` | Finding with structural evidence and remediation guidance |
| POST | `/api/findings/{id}/status` | Save `{ "status": "confirmed" }` for this scan |
| GET | `/api/scans/{id}/entities` | Paginated extracted entities, optional exact `path` |
| GET | `/api/scans/{id}/source?path=...&line=1&context=12` | Hash-verified source excerpt with detected secret assignments redacted |

Findings use `sort=risk|severity|confidence|file|detected_at`, `offset`, and `limit` (default 50, maximum 200). Risk, severity, confidence, and detection time sort highest/newest first; file sorts ascending. Text search escapes SQL wildcards. `min_confidence` is 0–1. Review statuses are `open`, `confirmed`, `false_positive`, `fixed`, and `ignored`. Status is manual triage, not proof of a fix, and is not copied to subsequent scans.

Entities accept maximum 500 rows. Source context is 0–50 lines per side, and individual lines are truncated at 4,000 characters. Only files in the scan and within current allowed roots can be viewed. Changed, unreadable, or linked files return 409 and require a rescan; unindexed paths return 404. Full source is not saved in the database.

`analysis_summary` reports ruleset version, parsed/failed/unsupported/unprocessed files, entity count, finding count, and severity counts. Historical scans have an empty summary. A completed scan does not imply complete language or security coverage.

## Local reasoning

See [local AI API and configuration](local-ai.md) for model discovery, context preview, background requests, and request history. `/api/settings` reports `ai_enabled: true` for provider capability; `/api/llm/models` reports actual Ollama availability.

## Graphs and semantic retrieval

See [graph and embedding endpoints](graph-search.md#api) for repository maps, embedding model discovery, index jobs, and cosine-ranked searches. These endpoints were added in API 0.4.0 with migration `0004_graph_search`.

## Reviewed changes

Migration `0005_reviewed_patches` adds proposals and test runs. The API supports context preview, generated diffs/tests, explicit validation, apply, and rollback. See [reviewed-change endpoints and approval contract](reviewed-changes.md#api).
