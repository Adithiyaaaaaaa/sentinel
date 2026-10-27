# SENTINEL

Local repository intelligence. Detect with code. Reason with AI. Verify with tests.

[![SENTINEL checks](https://github.com/Adithiyaaaaaaa/sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/Adithiyaaaaaaa/sentinel/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-b9f45d.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/Adithiyaaaaaaa/sentinel?display_name=tag&sort=semver)](https://github.com/Adithiyaaaaaaa/sentinel/releases)

SENTINEL implements repository indexing and **static analysis, local reasoning, repository graphs, and semantic search (Phases 1–5, with bounded coverage)**: Python AST and JavaScript/TypeScript/TSX parsing, 15 deterministic security/quality/performance rules, persisted evidence, review status, and a fingerprint-verified source viewer. The dashboard uses actual scan results.

The included sample produces eight pattern findings (four high, four medium). Matches require engineering review; confidence is a rule heuristic, not exploit verification. Other languages remain indexed only. See [analysis coverage](docs/analysis.md) and [the roadmap](docs/roadmap.md). Optional local Ollama explanations now use validated, evidence-cited JSON. See [local AI setup and boundaries](docs/local-ai.md). Repository maps and local embedding search are available; see [graph and search coverage](docs/graph-search.md). Python patch review, generated pytest suggestions, Docker-only validation, and guarded apply/rollback are available; see [reviewed changes](docs/reviewed-changes.md). CLI and the Tauri shell remain future phases.

![SENTINEL repository overview](docs/assets/sentinel-overview.png)

## Documentation

| Guide | Purpose |
| --- | --- |
| [Installation guide](docs/INSTALLATION.md) | Requirements, Windows and Unix setup, first scan, Ollama, and troubleshooting |
| [Usage guide](docs/USAGE.md) | Local and GitHub repositories, findings, graphs, search, and reviewed changes |
| [Output gallery](docs/OUTPUT_GALLERY.md) | Verified product screens and what each output means |
| [Demonstration script](docs/DEMO_SCRIPT.md) | A truthful 60–90 second product walkthrough |
| [Deployment and hosting](docs/HOSTING.md) | Local production, Docker, Vercel limitations, and hosted architecture |
| [Research and methodology](docs/RESEARCH.md) | Motivation, method, research questions, limitations, and future work |
| [Launch kit](docs/LAUNCH.md) | Repository metadata, announcement drafts, article ideas, and launch checklist |
| [Detailed project report](docs/SENTINEL_DETAILED_REPORT.md) | Complete technical and project report |
| [Architecture](docs/architecture.md) | System boundaries, pipelines, graph, retrieval, and workers |
| [API reference](docs/api.md) | FastAPI endpoints and contracts |
| [Security and privacy](docs/security.md) | Filesystem, execution, privacy, and deployment boundaries |
| [Verification](docs/verification.md) | Automated and browser verification record |
| [Contribution guide](CONTRIBUTING.md) | Development workflow, quality gates, rules, and pull requests |

The one-page Times New Roman academic abstract is available as the [SENTINEL Project Abstract](output/pdf/SENTINEL_Project_Abstract.pdf).

## Why SENTINEL

| Principle | SENTINEL approach |
| --- | --- |
| Evidence before generation | Deterministic parsers and rules create findings; AI never becomes the finding source |
| Local by default | Repository analysis, persistence, embeddings, and optional model inference stay on the machine |
| Reproducible review | Scan identity, rule versions, file fingerprints, exact locations, and evidence are persisted |
| Guarded changes | Generated code remains inert until schema, syntax, diff, fingerprint, approval, and validation gates pass |
| Honest boundaries | Parser coverage, unresolved graph calls, model uncertainty, and sandbox requirements remain visible |

## What SENTINEL is

SENTINEL is a local-first engineering intelligence workspace for understanding and reviewing a software repository. It combines deterministic code analysis with optional local AI assistance. The deterministic engine is the source of findings; AI output is visibly labeled as an unverified opinion or proposal and must pass structural validation before it can be reviewed further.

Use SENTINEL to:

- inventory files, languages, frameworks, package managers, dependencies, and test tooling;
- find bounded security, quality, and performance patterns in Python, JavaScript, TypeScript, and TSX;
- inspect exact evidence and hash-verified source without storing normal source text in scan records;
- explore files, symbols, lexical call relationships, and repository structure;
- search callable entities semantically with a local embedding model;
- ask a local Ollama model to explain a finding using a redacted, evidence-linked context;
- generate reviewable Python fixes or pytest suggestions;
- validate approved proposals in a locked-down Docker container before applying them; and
- preserve scan, finding-review, reasoning, search-index, patch, validation, apply, and rollback history.

SENTINEL is not a compiler, malware sandbox, penetration test, proof of exploitability, or replacement for human review. It does not install repository dependencies or run package scripts during indexing.

## How it works

```text
Local folder or locally cloned GitHub repository
                    |
                    v
      bounded discovery and fingerprinting
                    |
          +---------+----------+
          |                    |
          v                    v
 deterministic parsers     metadata detectors
 and AST rules             manifests/tooling
          |                    |
          +---------+----------+
                    |
                    v
       SQLite/PostgreSQL intelligence model
     files, entities, evidence, graphs, history
                    |
          +---------+----------+
          |                    |
          v                    v
   Next.js review UI     optional local Ollama
                              |
                              v
                  schema, citation, AST, diff,
                   fingerprint and approval gates
                              |
                              v
                  optional Docker-only validation
```

1. The API resolves the requested path against `SENTINEL_ALLOWED_ROOTS` and rejects traversal, symlinks, junctions, oversized inputs, ignored/generated folders, and unsupported binary content.
2. The indexer reads metadata and supported text safely. Python uses the standard AST; JavaScript, TypeScript, and TSX use syntax-tree parsing. Repository code is not imported or executed.
3. Deterministic rules create findings with exact file, line, symbol, fingerprint, risk basis, and evidence records.
4. A conservative graph builder records files, entities, containment, imports, and resolvable lexical calls. Semantic search stores local embeddings for callable entities.
5. The dashboard reads persisted results through FastAPI. Source excerpts are loaded from disk only after verifying that their SHA-256 fingerprint still matches the selected scan.
6. Optional AI workflows send bounded, redacted context only to an installed loopback Ollama model. The application validates response schemas and evidence references.
7. Patch/test proposals remain inert until explicitly reviewed. Tests can run only in the configured pinned Docker sandbox; source changes require another explicit approval and matching file fingerprints.

## Project status

Phases 1-5 are implemented: indexing, deterministic analysis, local AI reasoning, repository graph/semantic search, and reviewed Python changes. The verified Windows build currently passes 117 automated tests plus Ruff, TypeScript, migration-drift, production-build, live API smoke, and browser checks. See [verification](docs/verification.md) for evidence and limitations.

## Quick start on Windows

```powershell
git clone https://github.com/Adithiyaaaaaaa/sentinel.git sentinel
Set-Location sentinel
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c requirements-lock.txt -e ".[dev]"
npm ci
Copy-Item .env.example .env
.\scripts\serve.ps1
```

Open <http://127.0.0.1:3000>. The production launcher applies migrations, builds the web application, starts the FastAPI service on `127.0.0.1:8000`, and starts the Next.js production server on `127.0.0.1:3000`.

For a faster development loop, run `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1` instead.

## Analyze a local repository

1. Put the repository inside a directory listed in `SENTINEL_ALLOWED_ROOTS`.
2. Open SENTINEL and select **Open repository**.
3. Choose the directory and register it.
4. Select **Run scan**.
5. Review the coverage statement before interpreting the counts.
6. Open **Findings** for deterministic evidence, **Repository map** for structure, **Semantic search** for intent-based navigation, or **Repository files** for indexed source and symbols.
7. Rescan after files change. SENTINEL deliberately refuses stale source, AI contexts, validation snapshots, and apply operations.

## Analyze a GitHub repository locally

SENTINEL currently accepts filesystem directories rather than GitHub URLs. Clone or download the repository first, then scan the resulting folder:

```powershell
Set-Location C:\projects
git clone https://github.com/OWNER/REPOSITORY.git
```

For a private repository, authenticate with Git Credential Manager or `gh auth login`, then clone it normally. Add `C:/projects` to `SENTINEL_ALLOWED_ROOTS`, restart SENTINEL, and select the cloned folder. This keeps credentials out of SENTINEL and keeps source analysis on your machine.

## Optional local AI

Install and start [Ollama](https://ollama.com/), then install a chat/code model and an embedding model. The verified setup uses:

```powershell
ollama pull qwen2.5-coder:1.5b
ollama pull embeddinggemma
ollama serve
```

SENTINEL accepts only installed local GGUF models returned by the configured loopback Ollama service. Qwen Coder is recommended for patch/test generation; `embeddinggemma` powers semantic search. AI is optional: indexing and deterministic findings work without it.

## Safe reviewed changes

Patch generation currently supports bounded Python findings and function-level pytest suggestions. A generated proposal must pass response validation, Python syntax checks, direct-module import checks, selected-symbol checks, exact single-file diff checks, model-digest checks, and source-fingerprint checks. A failed model response is stored as a failed job, not silently repaired into a change.

Validation requires Docker and a locally available image pinned by exact SHA-256 digest in `SENTINEL_SANDBOX_IMAGE`. The container has no network, a read-only root filesystem, dropped capabilities, a non-root user, CPU/memory/process limits, and only a staged read-only repository snapshot. There is no host-execution fallback. See [reviewed changes](docs/reviewed-changes.md).

## Hosting and deployment choices

### Recommended: local production deployment

```powershell
.\scripts\serve.ps1
```

This is the fully supported mode. It preserves local filesystem access, SQLite, local Ollama, and Docker isolation. Do not expose ports 3000, 8000, or 11434 directly to the public internet.

### Containerized private deployment

Use `docker compose -f docker/compose.yml up --build` for the web application, API, and PostgreSQL. Mount only the repositories that should be readable. The current Compose deployment remains a trusted-user/private-network setup, not an internet-facing multi-tenant service.

### Vercel or other public hosting

The Next.js interface can be hosted on Vercel, but the complete application cannot be moved there unchanged. The existing backend relies on persistent repository files, background workers, SQLite or PostgreSQL, Ollama, and optional Docker. A production online edition should use:

- Vercel for the frontend and short API gateway endpoints;
- a separately hosted FastAPI/worker service on a VM or container platform;
- managed PostgreSQL instead of SQLite;
- a durable queue instead of process-local executors;
- short-lived isolated workspaces for downloaded repositories;
- object storage only for deliberately retained reports/artifacts;
- a GitHub App with read-only Contents permission for private repositories;
- a hosted model provider or a privately hosted inference service;
- per-user authentication, authorization, quotas, audit logs, retention controls, and abuse prevention; and
- disposable sandbox workers for any test execution.

For public repositories, a future hosted edition can accept a GitHub URL, resolve a commit SHA, download the GitHub archive, verify size/type limits, extract it safely, scan it, store only intended results, and destroy the workspace. Private repositories require explicit GitHub App installation and short-lived installation tokens. See [deployment](docs/deployment.md) and [the detailed report](docs/SENTINEL_DETAILED_REPORT.md).

## Run locally

Requirements: Python 3.11 or newer, Node.js 22 or newer, npm, and optionally Git. No model, cloud account, Redis, or database server is needed for the SQLite configuration.

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -c requirements-lock.txt -e ".[dev]"
npm ci
Copy-Item .env.example .env
python -m alembic upgrade head
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy with `cp .env.example .env` instead.

Start the API in the first terminal:

```shell
python -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000
```

Start the web application in the second terminal:

```shell
npm run dev
```

Open [SENTINEL](http://localhost:3000). Choose **Scan sample repository** or select **Open repository** and enter a path within a configured allowed root. A folder browser lists only permitted directories. Once a scan completes, the dashboard shows measured repository statistics and analysis coverage. Open **Findings** to filter matches, inspect evidence and source, jump to symbols, and save review status. Older Phase 1 scans remain readable; rescan to collect findings.

On Windows, `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1` starts both services, applies migrations, and stops its API process when the frontend exits. Optional `-ApiPort 8001 -WebPort 3001` arguments configure the local proxy and permitted browser origins together. The launcher refuses to adopt an existing service on its API port.

Interactive API documentation: [Swagger UI](http://127.0.0.1:8000/docs). API health: [health endpoint](http://127.0.0.1:8000/api/health).

## Repository access

Set `SENTINEL_ALLOWED_ROOTS` in `.env` to a JSON array of directories that SENTINEL may index. Use forward slashes in Windows JSON paths:

```dotenv
SENTINEL_ALLOWED_ROOTS=["C:/Users/you/projects"]
```

Omitting `SENTINEL_ALLOWED_ROOTS` permits the SENTINEL project root; an explicit empty array denies all roots. The example configuration uses `["."]`, resolved from the directory where the API starts. Restart the API after changing server settings. Keep allowed roots narrow. SENTINEL resolves paths before access, excludes symlinks and generated/binary content, and never runs repository scripts while indexing. `.gitignore`, `.sentinelignore`, and repository-specific ignore patterns control discovery.

The service is intended for one trusted user on the local machine. It is not a remotely accessible, authenticated multi-user service. Keep both services bound to loopback outside the isolated Compose network. See [security and privacy](docs/security.md).

## Verify

See [the executed verification results](docs/verification.md) for the checked build, API, database, browser workflows, and remaining environment limitations.

```shell
python -m pytest
npm run typecheck
npm run build
python -m alembic current
```

With the API running, `python scripts/smoke.py` registers and scans the included sample, checks persisted file statistics, and reports the API result. The test does not execute sample code or contact external services.

The checked-in Python constraints and npm lockfile record the verified dependency versions. Production builds use Next.js's supported Webpack bundler; development uses Turbopack. On restricted Windows runners, use a writable test directory, for example `python -m pytest --basetemp=.sentinel/test-run`, and grant local socket access for FastAPI's test client.

For the production web server, run `npm run build` and then `npm start` with the API running. The start script prepares local static assets and launches the standalone server on loopback. The API proxy destination is captured at build time.

On Windows, `powershell -ExecutionPolicy Bypass -File scripts/serve.ps1` applies migrations, builds the production UI, and starts both loopback services. Use `-SkipBuild` only when the source and environment have not changed since the last successful build. Stop the foreground process with Ctrl+C; the launcher also stops its API child. Start Ollama separately when using local AI features.

## PostgreSQL and containers

For a local PostgreSQL server, set `SENTINEL_DATABASE_URL=postgresql+psycopg://sentinel:your-password@localhost:5432/sentinel`, then run `python -m alembic upgrade head` before starting the API.

The container configuration runs PostgreSQL, the API, and the web application:

```shell
docker compose -f docker/compose.yml up --build
```

The dashboard is exposed on `127.0.0.1:3000`; PostgreSQL and the API remain inside the Compose network. By default, the host `examples` directory is mounted read-only as `/repositories`. To index another host directory, set `SENTINEL_REPOSITORIES_DIR` before starting Compose. Use `/repositories/...` as the repository path inside the application. See [deployment](docs/deployment.md).

## Layout

```text
apps/web/              Next.js dashboard
apps/desktop/          Tauri plan for Phase 7
backend/api/           FastAPI routes and validation
backend/analysis/      Safe discovery, language and tooling detection
backend/               Persistence, configuration, background indexing
packages/shared-types/ Documented API types
packages/analyzer/     Analyzer boundary and future adapter contract
packages/ui/           Interface components
examples/              Intentionally vulnerable indexing fixture
tests/                 Indexer and API/database tests
docker/                Local PostgreSQL deployment
docs/                  Architecture, API, privacy, roadmap
```

All core indexing works offline after dependencies are installed. No telemetry or source upload is enabled. Source text is parsed locally. Metadata, file hashes, code entities, and structural finding evidence are persisted; the deterministic engine does not persist full source or detected secret literal values. Explicit patch generation does save original/replacement files and generated tests locally for review and rollback.

## License and support

SENTINEL is available under the [MIT License](LICENSE). Use [GitHub Issues](https://github.com/Adithiyaaaaaaa/sentinel/issues) for reproducible bugs and feature proposals. For security-sensitive reports, follow [the security guide](docs/security.md).
