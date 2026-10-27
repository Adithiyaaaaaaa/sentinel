# Usage guide

## Analyze a local repository

1. Place the repository under a configured allowed root.
2. Start SENTINEL and select **Open repository**.
3. Register the repository directory.
4. Select **Run scan**.
5. Read the coverage statement before interpreting counts.
6. Rescan when files change.

SENTINEL never installs repository dependencies or runs package scripts while indexing.

## Analyze a GitHub repository

Clone or download it first:

```shell
git clone https://github.com/OWNER/REPOSITORY.git
```

For private repositories, authenticate through Git Credential Manager or GitHub CLI. Add the clone parent directory to `SENTINEL_ALLOWED_ROOTS`, restart the API, and register the clone. Credentials stay outside SENTINEL.

## Overview

Overview reports indexed files and lines, detected languages, declared dependencies, frameworks, package managers, test tools, deterministic finding counts, scan duration, and the exact selected scan.

Counts are bounded by language and parser coverage. A zero count does not certify security.

## Findings

Use search, severity, category, status, and sorting controls to narrow deterministic matches. Open a finding to review its rule basis, file, line, symbol, evidence, confidence heuristic, and fingerprint-verified source.

Review statuses record engineering judgment. They do not modify source files.

## Repository map

Switch between files/dependencies and symbols/calls. Select a node to focus its neighborhood. Coupling ranks are descriptive, and a resolved cycle is not automatically a defect. Dynamic dispatch and unresolved calls can hide relationships.

## Semantic search

1. Start Ollama and install an embedding model.
2. Select the model.
3. Build the semantic index explicitly.
4. Enter a natural-language query such as `payment failure handling`.

SENTINEL embeds bounded callable-entity excerpts. Detected secret assignments are redacted. Vectors and metadata are stored locally; normal source excerpts are not stored in the semantic index.

## Local reasoning

Open a finding and request an explanation from an installed local model. The model receives bounded, redacted context and must return a validated schema with evidence citations. Treat the response as an unverified opinion, not as a deterministic finding.

## Reviewed changes

Patch generation supports bounded Python findings and function-level pytest suggestions. A proposal remains inert until it passes syntax, symbol, diff, model-digest, and fingerprint checks.

Validation is available only through the configured pinned Docker image. The sandbox has no network, uses a read-only root filesystem, drops capabilities, and applies resource limits. There is no host-execution fallback. Applying a proposal requires explicit approval and a matching source fingerprint. Rollback history is persisted.

## Scan history

Each scan is an immutable selected snapshot. Choose a historical run to inspect its index and findings. Stale source excerpts, AI contexts, and patch operations are rejected when fingerprints no longer match.

## API access

With the API running, use Swagger UI at <http://127.0.0.1:8000/docs> or consult the [API reference](api.md).

## Operational safety

- Keep ports 3000, 8000, and 11434 bound to loopback for the local edition.
- Limit allowed roots to deliberate repository directories.
- Review evidence before accepting a finding or AI proposal.
- Require Docker validation before applying generated changes.
- Back up important repositories and use version control.
