# Launch kit

## Repository description

Local-first AI code review with deterministic findings, repository graphs, semantic search, and guarded fixes.

## Repository topics

`ai-code-review`, `static-analysis`, `code-quality`, `developer-tools`, `security`, `fastapi`, `nextjs`, `ollama`, `local-ai`, `semantic-search`, `repository-analysis`, `python`, `typescript`

## Short announcement

SENTINEL is now open source.

It is a local-first code review and repository intelligence platform that combines deterministic static analysis, evidence-backed findings, repository graphs, local semantic search, and guarded AI-assisted fixes.

The central design rule is simple: AI does not create security findings. Deterministic code analysis produces the evidence; a local model may explain it or propose an inert change that must pass validation and explicit review.

Source analysis stays on the machine running SENTINEL. The first release includes 117 automated tests and an intentionally vulnerable sample repository.

Repository: https://github.com/Adithiyaaaaaaa/sentinel

## Show HN draft

### Title

Show HN: SENTINEL – local-first code review with deterministic findings and guarded AI fixes

### Post

I built SENTINEL because I wanted AI-assisted code review without making a language model the source of security findings or requiring repository source to be uploaded to a cloud service.

SENTINEL indexes a local repository, runs deterministic Python and JavaScript/TypeScript analysis, preserves exact evidence and source fingerprints, builds a dependency and lexical-call graph, and optionally uses local Ollama models for evidence-cited explanations and semantic search.

Generated Python changes remain inert proposals. They pass schema, syntax, symbol, exact-diff, model-digest, and fingerprint checks. Test validation has no host fallback and runs only in a restricted Docker container when configured.

The current release is for one trusted local user. It is not a hosted multi-tenant scanner, and its analysis coverage is deliberately documented as bounded.

I would especially value feedback on the deterministic-versus-generative boundary, rule authoring, graph resolution, installation friction, and safe packaging.

Repository: https://github.com/Adithiyaaaaaaa/sentinel

## LinkedIn draft

I have released SENTINEL, a local-first code review and engineering intelligence platform.

SENTINEL combines deterministic static analysis, evidence-backed findings, repository dependency graphs, local semantic search, and guarded AI-assisted patches. The repository stays on the machine running the application, and AI output is kept separate from deterministic findings.

The first public release includes:

- Python and JavaScript/TypeScript analysis
- 15 deterministic rules
- fingerprint-verified source evidence
- repository maps and semantic search
- local Ollama explanations
- reviewed Python fixes and generated pytest suggestions
- Docker-only validation with no host-execution fallback
- 117 automated tests

The project is available under the MIT License. Feedback and contributions are welcome.

https://github.com/Adithiyaaaaaaa/sentinel

## Technical article titles

1. Why AI Should Not Be the Source of Static-Analysis Findings
2. Preventing Stale AI Patches with Repository Fingerprints
3. Building Local Semantic Code Search with Ollama
4. Mapping a FastAPI and Next.js Repository Without Executing It
5. Designing a Docker-Only Validation Gate for Generated Code

## Launch checklist

- Add repository description and topics.
- Upload `docs/assets/sentinel-social-preview.jpg` as the social preview.
- Publish the `v0.1.0` release using `.github/releases/v0.1.0.md`.
- Enable GitHub Discussions when there is capacity to moderate it.
- Record the demonstration using `docs/DEMO_SCRIPT.md`.
- Add the final video link to the README.
- Publish one technical article before the general announcement.
- Respond to every actionable issue and pull request promptly.
