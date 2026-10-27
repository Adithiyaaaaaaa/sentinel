# Security and privacy

## Local data flow

The browser talks to the local Next.js server. Next.js proxies API requests to the configured local FastAPI service. The API reads files under permitted repository roots and writes scan metadata, AST entities, and structural finding evidence to the configured database. No source code, scan metadata, or telemetry is intentionally transmitted to a third-party service.

`SENTINEL_API_URL` and `SENTINEL_DATABASE_URL` are operator-controlled settings. Pointing them at remote services changes where requests or metadata go. The default setup uses loopback and SQLite; the Compose setup uses an internal PostgreSQL service. Dependency installation and container image downloads require network access during setup, not while indexing.

## Filesystem scope

Only configured allowed roots are browsable and registrable. Canonicalized paths must stay within those roots. Indexing skips symbolic links/junctions, common dependency/build directories, binaries, oversized content, and ignored paths. Repository configuration is treated as data, never as shell instructions.

The `.sentinel` directory may contain local database state and process logs. It is ignored by Git. Do not share a scan database without reviewing its file paths, symbol names, dependency names, and finding metadata. Full source and detected secret literal values are not persisted by the deterministic analysis engine. Validated model responses are persisted separately and may quote source excerpts; inspect those records before sharing. The source endpoint reads bounded excerpts on demand, revalidates the path and SHA-256 hash, and returns HTTP 409 if the file changed. Detected secret assignment lines are redacted, but this is not comprehensive secret removal: undetected secrets may appear in the local source viewer.

## Execution policy

Repository discovery does not execute source code, install packages, run hooks, evaluate configuration, or execute AI commands. Optional Git metadata is obtained with bounded, fixed-argument Git calls. The sample repository is intentionally unsafe and must not be deployed or run as an application.

Reviewed-change endpoints accept explicit approval and a digest of the displayed proposal. Test validation uses a fixed pytest command in a restricted local Docker container; no host fallback or model-authored command is accepted. Source application requires successful staged validation and current hashes. Original and replacement files are persisted for rollback, so patch records contain source text. See [reviewed-change boundaries](reviewed-changes.md) and [local AI boundaries](local-ai.md).

## Deployment boundary

This release is a local single-user tool, with no authentication or multi-tenant isolation. Bind host services to loopback and do not expose the API or frontend to an untrusted network. A permitted path is not authorization for other network users. CORS reduces accidental browser access but is not an authentication system.

Compose publishes only the frontend on loopback, keeps PostgreSQL internal, mounts inspected host repositories read-only, and runs the application services without root privileges. This improves containment but does not make the application a hosted service.

## Reporting a security issue

Use [GitHub private vulnerability reporting](https://github.com/Adithiyaaaaaaa/sentinel/security/advisories/new) for suspected vulnerabilities. Do not open a public issue for a security report.

Provide a minimal reproduction with synthetic file paths and data. Do not paste real secrets or proprietary source. Include platform, configuration relevant to the issue, and whether the problem occurs in the API, path validation, indexer, or browser. The repository owner will acknowledge the report, assess affected versions, coordinate a fix when necessary, and publish an advisory after users have a reasonable opportunity to update.

## Embedding privacy

Semantic indexing sends bounded entity excerpts to local Ollama only when explicitly requested. Detected secret assignments are redacted; other sensitive text may remain. Stored vectors encode source semantics and should be protected like repository data. Queries and raw embedding excerpts are not persisted by SENTINEL. See [embedding boundaries](graph-search.md).


