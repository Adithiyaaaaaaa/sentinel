# Delivery phases

The full SENTINEL brief is the product direction. Phases 1–5 are implemented within the coverage documented in [analysis.md](analysis.md). Features below are not implied to exist merely because their package directory is reserved.

| Phase | Scope | State |
| --- | --- | --- |
| 1 | Repository registration and bounded browsing; ignored-file-aware indexing; language and tooling detection; FastAPI; SQLAlchemy; SQLite/PostgreSQL migrations; background scans; measured dashboard; sample fixture | Implemented |
| 2 | Language ASTs, deterministic security/quality rules, finding evidence, code viewer | Implemented for Python, JavaScript, TypeScript/TSX; 15 rules |
| 3 | Ollama provider, model selection, context packages, strict structured reasoning, explicit uncertainty | Implemented; see [local AI](local-ai.md) |
| 4 | Call/property graph, architecture analysis, local embedding search, repository map | Implemented with bounded lexical coverage; [limits](graph-search.md) |
| 5 | Reviewed patches, generated tests, sandboxed validation, rollback | Implemented for Python/pytest; real Docker validation unverified on this host. [Coverage](reviewed-changes.md) |
| 6 | Git hotspots, branch/diff review, finding-level scan comparisons | Planned |
| 7 | CLI, policy-based CI review, exports, Tauri desktop shell | Planned |
| 8 | Incremental indexing, distributed worker option, hardening, scale benchmarks, broader UX polish | Planned |

Phase 1's Git branch/commit detection and scan history are useful indexing metadata; they are not Phase 6 risk analysis or finding comparisons. The included GitHub workflow checks the application itself; it is not yet a SENTINEL CLI review integration.

The sample repository contains eight patterns detected by the Phase 2 analyzer. Findings include structural evidence and exact source locations. Security, maintainability, architecture, and health scores should remain absent until their transparent calculations are implemented and tested.


