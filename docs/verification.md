# Phase 5 verification

Verified locally on 27 October 2026 on Windows with SQLite, the production Next.js server, Ollama 0.35.1, `qwen2.5-coder:1.5b` (986 MB, digest prefix `d7372fd82851`), and the earlier installed local GGUF models.

- **117 tests passed**, covering all prior indexing, deterministic analysis, local reasoning, graph/search behavior, plus strict diff parsing, generated-test validation, explicit approvals, staged validation, atomic apply/rollback, stale-source conflicts, interrupted-operation recovery, Docker fail-closed behavior, fixed sandbox commands, and model response compatibility. Ruff, TypeScript, and `alembic check` passed.
- Migration `0005_reviewed_patches` upgraded the existing database and added persisted patch/test-run history without discarding earlier scans, reasoning, graphs, or embeddings.
- The production launcher applied migrations and served the API and UI on loopback only. The visible browser was exercised against the production build, not the development server.
- The live smoke script passed against the deployed API with 13 files, 188 lines, 29 entities, and the expected eight deterministic findings.
- The review UI exposes source context, local-model selection, proposal history, generated pytest source, review acknowledgements, test output, apply, and rollback states. It clearly disables validation/apply when a pinned Docker sandbox is unavailable.
- Local-model output is treated as untrusted: complete-response parsing, Python AST validation, real-module imports, selected-symbol references, exact single-file diff application, source fingerprints, and a bounded correction attempt all run before a proposal can become reviewable.
- A real Qwen Coder request produced a persisted `ready` pytest proposal for `receipt_subject`; the visible review showed its source and risk disclosure. It was not executed because Docker is unavailable. The screenshot is saved at `.sentinel/phase5-reviewed-tests.png`.

Docker is not installed on this host, so no repository tests were executed and no generated change was applied. That boundary was verified in both API tests and the visible production UI. Public cloud deployment is intentionally not offered because repository filesystem access, SQLite state, Ollama, and the Docker sandbox are local-machine trust boundaries.

---

# Phase 4 verification

Verified locally on 25 October 2026 with Ollama 0.35.1 and the explicitly downloaded `embeddinggemma:latest` (about 622 MB, digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`).

- **108 tests passed** in `.sentinel/phase4-complete`, including graph resolution, Python class-scope isolation, JavaScript parameter shadowing, iterative cycle detection, invalid vectors, semantic ranking, secret redaction, stale source, model digest mismatch, failed-build cleanup, and all earlier regression tests. Ruff passed.
- The production Next.js Webpack build and TypeScript validation passed. Its standalone server was exercised through the browser.
- The existing SQLite database upgraded to `0004_graph_search`. `alembic check` found no schema drift; migration round trips remain covered by tests.
- Live smoke verification retained the sample's eight findings. Its graph contains 31 nodes, 20 edges, one matched lexical call, and 18 unresolved calls.
- A real local embedding build indexed all 13 callable entities into 768-dimensional vectors in about 7.5 seconds. The index remained usable after an API restart.
- Real retrieval placed `password_digest` first for “password storage security” (cosine about 0.428) and `test_message_formats_money` first for “format a payment notification” (about 0.583). For “payment failure handling”, `process_refund` ranked third. These are functional examples, not a search-quality benchmark.
- Browser checks verified file and symbol graph views, file focus, relationship evidence, source navigation, embedding model selection, UI-triggered index creation and completion, index history, search results, and redacted source. No console errors were reported.

Screenshots are saved locally in `.sentinel/phase4-repository-map.png` and `.sentinel/phase4-semantic-search.png`. Graph matching is conservative and incomplete; dynamic dispatch, JS cross-file calls, inheritance, and data-flow graphs remain unsupported. Search is capped at 1,000 entities and uses exact cosine ranking. See [coverage and limits](graph-search.md).

Live PostgreSQL and Docker remain unverified. Starlette's TestClient emits its existing single deprecation warning. Temporary verification servers are stopped after testing; the downloaded model and persisted indexes remain available.

---
# Phase 3 verification

Verified locally on 24 October 2026 with the installed Ollama 0.35.1 and `phi3:latest` (3.8B Q4_0, digest `4f222292793889a9a40a020799cfd28d53f3e01af25d48e06c5e708610fc47e9`). No model download was needed.

- **95 tests passed** in `.sentinel/phase3-final`, including loopback URL restrictions, cloud inventory filtering, strict structured response checks, invalid citations, sanitized transport failures, redacted contexts, context-hash mismatch, stale source, concurrency limits, executor shutdown, interrupted-job recovery, persistence, and all prior analyzer/API tests.
- Ruff passed for `backend`, `tests`, and `scripts`.
- The production Next.js Webpack build passed, including TypeScript validation. The standalone server was launched and tested.
- Alembic upgraded the existing SQLite database to `0003_local_reasoning`; migration round trips and schema parity passed.
- A real local-model request analyzed the sample SQL finding with a 5,437-byte context. It completed in about 133 seconds and returned schema-valid reasoning with existing evidence references E0 and E1. The response included uncertainty, remediation risks, and suggested tests. Model claims were not independently verified.
- Browser checks verified the installed model selector, context preview, running-job display, completed opinion, and source/evidence separation. Refreshing after an API restart restored the persisted response with the correct local timestamp. No browser console errors were reported.

The deterministic finding and manual review status remained unchanged. The UI labels all generated reasoning as an unverified model opinion. The real-model result is kept in the local database; raw context and full source are not persisted by the reasoning feature. See [local AI boundaries](local-ai.md).

Live PostgreSQL and Docker remain unverified on this host. The loopback-only Ollama provider currently supports native local deployment, not a host-gateway connection from Compose. Starlette's TestClient emits its existing single deprecation warning.

---

# Phase 2 verification record

Verified locally on Windows with Python 3.13.5, Node.js 22.17.0, Next.js 16.4.3, and SQLite on 24 October 2026.

## Executed checks

- **79 tests passed:** 25 indexer cases, 41 parser/analysis cases, and 13 API/persistence cases. Parser cases cover positive and negative patterns, entity extraction, syntax failures, source fingerprint checks, and the sample's eight findings. API tests cover filters, sorting, status validation/persistence, evidence, redaction, changed/missing source, and preservation of Phase 1 history through migration.
- `npm run typecheck` and `npm run build` passed. The production build uses Webpack, including TypeScript validation and static page generation.
- `npm start` launched the standalone production server; its dashboard and same-origin API proxy were exercised in the browser.
- Migration upgrade/downgrade tests and `python -m alembic check` passed. No model/schema drift was found. Existing local historical scans were preserved.
- `python scripts/smoke.py` passed against the live API, verifying the sample index, persisted history, eight expected rule matches, evidence, and hash-verified secret redaction.
- `python -m ruff check backend tests scripts` passed.

The final regression run used `--basetemp=.sentinel/phase2-final`. Starlette emits one deprecation warning for its httpx-based TestClient.

## Browser verification

The standalone production UI displayed actual coverage and severity counts. Findings navigation, title search, severity filtering, SQL evidence and exact source lines, symbol navigation, secret redaction, and manual review-status saving were exercised through the in-app browser. The sample SQL status was restored to open after checking persistence. No console errors were reported during these interactions.

Prior Phase 1 browser checks covered repository selection, permitted-folder browsing, scanning, switching repositories, file search, language filters, history, privacy settings, and keyboard shortcuts. Those backend behaviors remain covered by the regression suite.

The live sample produced **13 indexed files, 188 physical lines, 9 language/configuration categories, 7 declared dependencies, 5 parsed files, 29 entities, and 8 findings (4 high, 4 medium)**. Eight configuration/documentation files were indexed without AST analysis; no supported files failed or remained unprocessed. Sample application code was never executed.

## Limits

Docker and a live PostgreSQL server are not installed on this host. Live PostgreSQL migration and sample-scan checks are configured in GitHub Actions but were not executed here; container runtime behavior remains unverified locally.

Coverage is limited to the languages and rules documented in [analysis.md](analysis.md). These are deterministic pattern findings, not verified exploits or a complete security audit. Resolved graphs, patches, repository test execution, CLI/report exports, and Tauri remain future phases.


