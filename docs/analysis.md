# Deterministic analysis coverage

Ruleset `2.0.0` parses Python with the standard-library AST and JavaScript, TypeScript, and TSX with Tree-sitter. No target code is imported or executed. Other languages are indexed without AST or security analysis. Syntax-invalid files are reported as failed and produce no findings.

Entities include classes, functions/methods, imports, variables, Python decorators identified as API routes, and JavaScript exports as features. Functions retain source spans, lexical call names, branch complexity, and detected feature flags. These are syntax observations, not a resolved whole-program graph; caller relationships are not yet computed.

## Rule coverage

| ID | Pattern | Python | JS / TS |
| --- | --- | --- | --- |
| SEC-001 | Secret-like assignment with a literal of at least eight characters | Yes | Yes |
| SEC-002 | Constructed dynamic string reaches execute/query | Yes | Yes |
| SEC-003 | Dynamic shell command | os/subprocess | child_process namespace calls |
| SEC-004 | Dynamic code evaluation | eval/exec | eval/Function calls |
| SEC-005 | Unsafe deserialization API | pickle, yaml.load | — |
| SEC-006 | MD5/SHA-1 hashing | hashlib | — |
| SEC-007 | Predictable random call in token-related function | random | — |
| SEC-008 | Function parameter reaches a file read path | Yes | — |
| SEC-009 | Caller header compared with admin role | Yes | — |
| SEC-010 | Dynamic HTML sink or dangerouslySetInnerHTML | — | Yes |
| REL-001 | HTTP request without explicit timeout | requests/httpx calls | — |
| QUAL-001 | Empty exception handler | pass-only handler | empty catch |
| QUAL-002 | Function branch complexity above 10 | Yes | Yes |
| QUAL-003 | Function spans more than 80 physical lines | Yes | Yes |
| PERF-001 | Database execution inside a loop | Yes | — |

The `/api/rules` endpoint is the authoritative metadata catalog with CWE/OWASP mappings, severity, confidence, impact, verification questions, and suggested remediation. Mappings are rule taxonomy, not a compliance assessment.

## Evidence and interpretation

Every finding stores its rule version via the owning scan, path, lines, symbol, structural evidence, confidence, and remediation guidance. Literal secret values and full source are not stored. A confirmed verdict confirms a syntax pattern, not a verified exploit. Confidence values are hand-assigned rule heuristics, not calibrated probabilities.

Priority is `round(severity_weight × confidence)`, using critical 100, high 75, medium 45, and low 20. This is a transparent sorting aid, not a repository health score or exploit probability. The present rules produce high/medium/low findings; no rule assigns critical severity.

The source viewer rechecks allowed roots, links, and the indexed SHA-256 before displaying a bounded excerpt. Changed files require rescanning. Detected secret assignment spans are redacted, including multiline literals. This does not identify every possible secret. Manual review status belongs to a single scan; marking something fixed does not prove a code change.

## Limits

Local assignment resolution is conservative and incomplete. There is no interprocedural taint tracking, runtime type resolution, sanitization proof, reachability proof, alias/shadowing completeness, dependency vulnerability database, or exploit execution. API names may refer to unrelated methods; safe wrappers and aliases may hide risky calls. Review all matches in context. No findings does not certify security.

Parsing is bounded to 512 KiB and 75,000 AST nodes per supported file, 100,000 entities and 10,000 findings per scan. Indexing has separate broader limits. Review warnings and coverage counts for partial results. The current worker uses threads, not OS-isolated parser processes; untrusted pathological input remains a hardening concern for a future phase.

The sample's eight findings are hardcoded signing material, dynamic SQL, MD5, predictable reset tokens, parameter-derived receipt paths, a caller-supplied admin role, a swallowed exception, and database calls in a loop. It yields five parsed files and 29 code entities. Sample application code is never executed during verification.
