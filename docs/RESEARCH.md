# Research and methodology

## Abstract

SENTINEL investigates whether a local-first engineering intelligence platform can combine deterministic static analysis with optional generative models without making AI the source of security findings or silently modifying source code. The system indexes repositories, extracts structural evidence, records reproducible findings, builds a relationship graph, and applies validation and approval gates to all model-assisted outputs.

## Motivation

Modern code review tools often split repository inventory, static analysis, architectural exploration, semantic retrieval, and AI assistance across separate services. Cloud-first products can also require source upload, creating privacy and governance concerns. SENTINEL explores a single local workspace in which deterministic evidence remains primary and AI is constrained to explanations or proposals.

## Research questions

1. Can useful repository intelligence be produced without executing repository code?
2. Can findings remain reproducible while still offering local natural-language assistance?
3. Can generated changes be bounded by schemas, source fingerprints, exact diffs, approvals, and isolated tests?
4. Can repository graphs and embeddings improve navigation while keeping their uncertainty visible?
5. What architectural changes are required to move a filesystem-oriented local tool to a secure hosted service?

## Method

The implementation uses a layered method:

1. Safe discovery applies allowed-root checks, ignore rules, size limits, binary detection, and fingerprinting.
2. Language-aware parsers extract syntax and callable entities without importing repository modules.
3. Deterministic rules emit structured findings with exact evidence.
4. SQL persistence records repositories, scans, files, entities, findings, reviews, graph data, embeddings, jobs, proposals, validations, applies, and rollbacks.
5. The web interface presents coverage statements and uncertainty alongside output.
6. Optional Ollama workflows use bounded and redacted prompts plus strict response schemas.
7. Patch workflows add syntax, symbol, diff, model-digest, fingerprint, approval, and Docker validation gates.

## Evaluation strategy

The current evaluation combines:

- unit and integration tests for indexing, analysis, API behavior, local reasoning, graph/search, and patches;
- migration checks against SQLite and PostgreSQL;
- Ruff and TypeScript static checks;
- production frontend builds;
- API smoke testing using an intentionally vulnerable sample repository; and
- browser verification of the principal review workflows.

The checked project reports 117 automated tests. The verification record documents executed commands and environmental limits.

## Design findings

Deterministic and generative layers benefit from a strict separation. Deterministic findings can be reproduced from a scan and rule version, while model output depends on model identity, model digest, prompt context, and sampling behavior. Treating model responses as persisted jobs or inert proposals makes failures and uncertainty reviewable.

File fingerprints are central to safe interaction. They prevent historical evidence, cached explanations, and generated patches from being applied to source that changed after scanning.

Local execution improves privacy but does not eliminate risk. Allowed roots, link rejection, redaction, Docker isolation, and explicit approval are still required because repositories and model output are untrusted inputs.

## Limitations

- Deterministic coverage is bounded to implemented rules and supported syntax.
- JavaScript and TypeScript resolution is conservative and does not model complete runtime behavior.
- Dynamic dispatch, reflection, generated code, and framework magic reduce graph completeness.
- Semantic similarity is a navigation aid, not proof of correctness or vulnerability.
- Local models can produce incorrect explanations and patches.
- Docker validation is only as representative as the pinned image and selected tests.
- The current product is designed for one trusted local user, not hostile multi-tenancy.
- Direct GitHub URL ingestion is not implemented in the local edition.

## Future research directions

- Incremental indexing and changed-line analysis
- Language-server and compiler-assisted symbol resolution
- Data-flow, taint, and interprocedural analysis
- Rule packs with provenance, versioning, and benchmark fixtures
- Evaluation datasets for finding precision and patch acceptance
- Model comparisons using fixed contexts and repeatable scoring
- Retrieval strategies combining graph neighborhoods and embeddings
- GitHub App ingestion with immutable commit snapshots
- Multi-tenant isolation and disposable worker design
- Pull-request annotations and CI quality gates
- Policy-as-code for allowed models, repositories, and validation profiles

## Reproducibility

Dependency constraints, npm lockfile, migrations, test fixtures, CI configuration, and verification commands are committed to the repository. Run the commands in [verification](verification.md) and record the operating system, Python version, Node.js version, database, Ollama model names and digests, Docker image digest, and selected commit.

## Related material

- [Detailed project report](SENTINEL_DETAILED_REPORT.md)
- [Architecture](architecture.md)
- [Analysis coverage](analysis.md)
- [Security and privacy](security.md)
- [Roadmap](roadmap.md)
- [Project abstract](../output/pdf/SENTINEL_Project_Abstract.pdf)
