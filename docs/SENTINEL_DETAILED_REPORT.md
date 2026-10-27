# SENTINEL: Detailed Project Report

## Executive summary

SENTINEL is a local-first AI-assisted code review and engineering intelligence platform. It turns a repository directory into an evidence-backed model of files, languages, dependencies, frameworks, source entities, findings, relationships, semantic vectors, AI opinions, and reviewed change proposals. The core design principle is separation of trust: deterministic analysis identifies bounded patterns; local AI can help interpret or propose; structural validators, human approval, fingerprints, and an isolated test sandbox decide whether a proposal may move forward.

The project was built in five implemented phases. The current release provides repository indexing, deterministic static analysis, a persistent review interface, local Ollama reasoning, repository maps, semantic search, and guarded Python fix/test workflows. The verified build passes 117 automated tests, static linting, TypeScript checks, schema-drift checks, production builds, live API smoke tests, and browser workflows.

## 1. Problem statement

Engineering teams often use separate tools for repository inventory, static analysis, architecture exploration, semantic search, AI explanation, test generation, and patch review. These tools frequently upload source code, produce opaque conclusions, lose history between runs, or allow generative output to appear more authoritative than it is.

SENTINEL addresses four needs:

1. **Repository understanding:** give a fast, measurable overview of a codebase without running it.
2. **Evidence-backed review:** connect every deterministic finding to an exact file, line range, symbol, rule, confidence, and risk basis.
3. **Private AI assistance:** use locally installed models while clearly separating model opinion from deterministic evidence.
4. **Safe change handling:** ensure model-authored code cannot be applied merely because it looks plausible.

## 2. Why this project matters

AI coding tools are productive but probabilistic. A model can write convincing code that is syntactically invalid, targets the wrong function, invents behavior, or creates tests that encode an incorrect expectation. SENTINEL encountered these failure modes during real local-model verification. Instead of weakening validation, the system records failed proposals, gives bounded corrective feedback, and requires the final result to pass syntax, import, selected-symbol, diff, source-fingerprint, review, and sandbox gates.

This makes SENTINEL useful as an engineering decision-support system rather than an autonomous code-changing agent. It is particularly appropriate for students, individual developers, security-conscious teams, offline environments, and organizations that want to evaluate local AI without uploading repositories to a third party.

## 3. Objectives

The implemented objectives are:

- index real repositories without executing repository code;
- persist reproducible scan history and content fingerprints;
- detect a documented set of security, quality, and performance patterns;
- show coverage and limitations instead of implying complete security;
- preserve source privacy and redact detected secret assignments;
- provide file, symbol, relationship, and semantic navigation;
- integrate local GGUF models through loopback-only Ollama;
- validate AI responses before displaying or storing them as completed work;
- stage proposed changes away from the original repository;
- require explicit human approval for consequential operations; and
- refuse unsafe operations when Docker, source fingerprints, model identity, or validation evidence is missing.

## 4. System architecture

### 4.1 Web application

The user interface is a Next.js application under `apps/web`. It provides repository registration, scanning, overview metrics, file browsing, findings, evidence and source views, manual review status, repository maps, embedding-index management, semantic search, local AI opinions, and reviewed changes.

The frontend contains no fabricated dashboard records. It renders API state and includes loading, empty, failed, stale, unsupported, and unavailable states. It labels AI content and deterministic content separately.

### 4.2 API and orchestration

FastAPI routes under `backend/api` validate inputs and expose repository, scan, file, finding, graph, search, reasoning, patch, validation, apply, and rollback operations. The service is designed for a single trusted local user and one API process. Background indexing and AI work use bounded process-local executors and single-flight controls.

### 4.3 Persistence

SQLAlchemy models store repositories, scans, indexed-file metadata, dependencies, code entities, findings, evidence, graph data, reasoning jobs, embedding indexes, vectors, patches, and test runs. SQLite is the default local database. Alembic migrations support both SQLite and PostgreSQL. Ordinary scan records store fingerprints and structural metadata rather than full source text. Successful reviewed-change jobs intentionally retain original/replacement text locally to support review and rollback.

### 4.4 Indexing and analysis

The indexer performs bounded directory traversal, honors ignore rules, rejects links and generated/binary content, limits counts and sizes, reads manifests, identifies languages and tooling, and computes SHA-256 fingerprints. Python is parsed with the standard AST. JavaScript, TypeScript, and TSX use syntax-tree parsing. The deterministic ruleset currently contains 15 documented checks. Findings are triage signals, not exploit proofs.

### 4.5 Architecture graph and semantic search

The graph layer records files, entities, containment, imports, and conservatively resolved lexical calls. It intentionally avoids pretending to understand dynamic dispatch, complete data flow, or all cross-file JavaScript behavior. Semantic search embeds callable entities with a local Ollama embedding model and ranks them by cosine similarity. The persisted index is tied to the selected scan and model digest.

### 4.6 Local AI reasoning

The reasoning provider accepts only a configured loopback Ollama URL and installed local GGUF models. Context packages are bounded, source fingerprints are rechecked, detected secret assignments are redacted, and repository text is treated as untrusted data rather than instructions. Reasoning responses must satisfy a strict schema and reference supplied evidence identifiers.

### 4.7 Reviewed changes

The patch service supports Python single-file fixes and function-level pytest suggestions. Generated tests must parse, include test functions and assertions, import the real repository module, and reference the selected symbol. Fixes must be exact unified diffs for the selected path, apply cleanly to the fingerprinted source, preserve Python syntax, and stay below configured change limits.

A proposal becomes eligible for validation only after the user reviews and approves its current review hash. Validation operates on a temporary snapshot and never installs dependencies. Apply is atomic and allowed only after a successful validation snapshot and a second explicit approval. Rollback refuses to overwrite subsequent user edits.

## 5. Security and privacy model

SENTINEL applies defense in depth:

- allowed-root path boundaries;
- canonical path resolution and link/junction rejection;
- ignored/generated/binary exclusions;
- file, repository, response, and queue limits;
- no repository import, build, package install, or script execution during scanning;
- no telemetry or normal source upload;
- loopback-only native services;
- trusted-host, origin, and cross-site request checks;
- secret-aware source redaction and AI exclusion;
- model inventory and digest checks;
- strict Pydantic, evidence, AST, import, symbol, and diff validation;
- exact review hashes and source fingerprints;
- atomic writes with stored recovery intent;
- Docker validation with no network, read-only root, non-root UID, dropped capabilities, process/memory/CPU limits, fixed commands, bounded output, and no host fallback; and
- recovery logic for interrupted scan, reasoning, embedding, validation, apply, and rollback jobs.

The design still assumes a trusted local user. It does not currently provide accounts, tenant isolation, internet-facing rate limits, or secure multi-user repository storage.

## 6. Development approach

The system was built incrementally so each phase remained usable and testable:

1. **Repository indexing:** safe traversal, file metadata, manifests, history, SQLite, migrations, and the initial dashboard.
2. **Deterministic analysis:** parsers, rules, entities, evidence, review status, source fingerprint verification, and findings UX.
3. **Local reasoning:** loopback Ollama, model inventory, bounded/redacted context, evidence-cited schemas, persistence, and concurrency limits.
4. **Repository intelligence:** graph construction, file/entity relationships, local embeddings, persistent indexes, and semantic search.
5. **Reviewed changes:** strict diffs, pytest suggestions, proposal history, sandbox-only validation, explicit approval, atomic apply, rollback, and crash recovery.

The project uses test fixtures with intentionally detectable patterns. Browser validation is performed against the production build. Real local models are tested because integration behavior cannot be fully represented by mocks; real verification exposed model-specific JSON, formatting, syntax, and target-selection failures that are now safely handled or rejected.

## 7. Verification evidence

The latest verified Windows run includes:

- 117 passing automated tests;
- Ruff passing for backend, tests, and scripts;
- TypeScript validation passing;
- the production Next.js build and server passing;
- Alembic reporting no model/migration drift;
- a live API smoke scan reporting 13 files, 188 lines, 29 entities, and eight expected deterministic findings;
- a real `embeddinggemma` semantic index;
- real local reasoning through `phi3`;
- a real structurally valid Qwen Coder pytest proposal; and
- visible browser checks for repository selection, findings, source, graphs, semantic search, AI reasoning, patch history, generated tests, and Docker-unavailable safety states.

Docker and live PostgreSQL were not installed on the verification host. Their behavior is covered by tests and configuration, but a real Docker validation run and a live PostgreSQL deployment remain environment-level verification tasks.

## 8. How to use the system

### Local repositories

Configure a narrow allowed root, start SENTINEL, register a directory, and run a scan. Use the overview to understand coverage before using findings. Review evidence and source, set human triage status, build the semantic index only when needed, and rescan after code changes.

### GitHub repositories

The current supported workflow is to clone the GitHub repository locally and scan its directory. This keeps authentication in Git/GitHub tooling and avoids giving SENTINEL a long-lived token. Public repositories can be cloned anonymously. Private repositories should use Git Credential Manager or the GitHub CLI.

### AI and changes

Use AI explanations as review assistance, not truth. Prefer a code-specialized local model for changes. Read the generated tests and risks before approval. Do not configure a sandbox image you do not trust. If Docker is unavailable, generation and review remain available while validation and apply remain disabled.

## 9. Deployment options

### 9.1 Native local deployment

This is the recommended complete mode. `scripts/serve.ps1` runs migrations, builds the UI, and binds the API and web server to loopback. Ollama and Docker remain separate local services.

### 9.2 Private container deployment

Docker Compose provides the UI, API, and PostgreSQL. Repository mounts should be read-only and narrowly scoped. This mode is suitable for a developer workstation or private trusted network after normal operational hardening.

### 9.3 Public online deployment

The current application should not simply be exposed to the internet. Vercel can host the Next.js frontend, but repository analysis should run in a persistent worker environment. A sound hosted design separates:

- frontend and authentication;
- API gateway and job submission;
- durable PostgreSQL job/result storage;
- queue-backed analysis workers;
- short-lived repository workspaces;
- isolated test runners;
- model inference; and
- retention/deletion policy enforcement.

Public GitHub repositories can be downloaded as commit-pinned archives without authentication. Private repository support should use a GitHub App with minimum read-only Contents permission and short-lived installation tokens. The service must validate GitHub hosts and repository identifiers, prevent server-side request forgery, cap archive and extracted sizes, reject archive traversal and links, enforce quotas, and delete workspaces after analysis.

Vercel function duration and memory limits can accommodate short gateway work, but long repository scans, model inference, and Docker execution are better placed in dedicated workers. A single VM/container deployment is the simplest online prototype; a frontend/API/queue/worker architecture is the scalable production route.

## 10. Current limitations

- Deep static analysis covers Python, JavaScript, TypeScript, and TSX only.
- The ruleset is intentionally small and pattern-based.
- Graph resolution is conservative and incomplete.
- Semantic ranking is exact cosine search over a bounded local index, not a large distributed vector service.
- AI accuracy depends on the installed model; structurally valid tests may still encode incorrect expectations.
- Patch application supports bounded Python single-file changes only.
- Test validation requires a prebuilt compatible Docker image and does not install repository dependencies.
- Local workers are process-bound; the service is not horizontally scalable.
- There is no user authentication, team tenancy, GitHub URL importer, pull-request bot, CLI, export center, or finished desktop shell yet.

## 11. Future options

### Near term

- Add a safe **Clone GitHub repository** workflow for local use.
- Add HTML, JSON, SARIF, and PDF report export.
- Add a CLI for CI and scripted scans.
- Add scan-to-scan diffs, finding baselines, suppression reasons, and policy thresholds.
- Expand rules and test fixtures without overstating language coverage.
- Complete live Docker and PostgreSQL verification.

### Hosted edition

- Add GitHub App installation, repository selection, webhook-triggered rescans, and pull-request status checks.
- Resolve immutable commit archives and display commit/branch/PR context.
- Introduce account and organization tenancy, roles, audit events, quotas, encrypted secrets, regional storage, retention controls, and delete/export workflows.
- Move background work to a durable queue with idempotent, cancellable jobs.
- Run analysis and tests in disposable microVM/container workers with egress policy.
- Use managed PostgreSQL and object storage for intended artifacts.
- Support hosted inference or privately managed GPU inference while preserving model provenance.

### Engineering intelligence

- Cross-scan architecture and risk trends.
- Pull-request-only analysis and changed-line prioritization.
- Broader interprocedural data flow and framework-aware rules.
- Dependency vulnerability feeds and license policy.
- Ownership, hotspots, churn, and test-impact views.
- Retrieval quality evaluation and hybrid lexical/semantic ranking.
- Human feedback loops for false positives and accepted remediation patterns.

### Product interfaces

- Finished Tauri desktop application.
- IDE extension and command-line client.
- GitHub/GitLab pull-request review bot.
- Team dashboards and scheduled reports.
- Evidence-rich remediation playbooks and educational explanations.

## 12. Conclusion

SENTINEL demonstrates that AI-assisted code review can be useful without allowing AI to become the source of truth. The platform combines deterministic evidence, local privacy, persistent engineering context, explicit uncertainty, strict validation, human approval, and fail-closed execution boundaries. Its present form is a capable local repository intelligence tool; its architecture and roadmap provide a credible path toward a secure hosted service, provided that authentication, durable jobs, tenant isolation, repository lifecycle controls, and disposable execution workers are added rather than bypassed.

## Related documentation

- [Architecture](architecture.md)
- [Analysis coverage](analysis.md)
- [API](api.md)
- [Security and privacy](security.md)
- [Local AI](local-ai.md)
- [Graph and semantic search](graph-search.md)
- [Reviewed changes](reviewed-changes.md)
- [Deployment](deployment.md)
- [Roadmap](roadmap.md)
- [Verification record](verification.md)
