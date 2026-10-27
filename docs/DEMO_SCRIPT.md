# Demonstration script

This script produces a focused 60 to 90 second SENTINEL demonstration without overstating coverage.

## Preparation

1. Start the production application with `scripts/serve.ps1`.
2. Confirm the sample repository has a completed scan.
3. Start Ollama and install the selected chat and embedding models if demonstrating optional AI.
4. Close unrelated applications and remove personal paths from the visible browser area when possible.
5. Record at 1920 by 1080 or higher with the browser zoom set for readable text.

## Voiceover and actions

### 0–10 seconds: Positioning

Action: Show Overview.

Voiceover:

> SENTINEL is a local-first code review and repository intelligence platform. Deterministic analysis finds the evidence; optional local AI explains or proposes changes without becoming the source of findings.

### 10–25 seconds: Deterministic findings

Action: Open Findings, select the hardcoded-secret fixture, and show the exact evidence and source location.

Voiceover:

> Every match includes a rule, severity, confidence rationale, exact location, structural evidence, and a source fingerprint. A match still requires engineering review.

### 25–40 seconds: Repository structure

Action: Open Repository map, show node and edge totals, then focus a backend file.

Voiceover:

> SENTINEL also maps files, symbols, dependencies, and resolvable lexical calls while keeping unresolved relationships visible.

### 40–55 seconds: Semantic search

Action: Open Semantic search and search for `payment failure handling` using the local embedding index.

Voiceover:

> Local embeddings let you navigate by meaning. Bounded entity excerpts go only to the configured loopback Ollama service.

### 55–75 seconds: Guarded AI assistance

Action: Open a finding explanation or an existing patch proposal and show validation gates.

Voiceover:

> Model output is labeled, schema-validated, evidence-cited, and stored as an inert proposal. Applying a change requires matching fingerprints, explicit approval, and optional Docker-only test validation.

### 75–90 seconds: Close

Action: Return to Overview and show the GitHub repository URL.

Voiceover:

> SENTINEL keeps source analysis on your machine. The project is open source under the MIT License. Try the sample repository or contribute a new analysis rule.

## Recording checklist

- Do not claim complete vulnerability detection.
- Do not show real credentials or private repository content.
- Keep the local-only and deterministic-versus-AI distinction visible.
- Add captions.
- Export one full video and one 30-second excerpt.
- Place the final video link near the top of the README.
