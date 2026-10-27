# Local Ollama reasoning

Phase 3 adds optional model opinions to deterministic findings. Open a finding, choose **Ask local AI**, inspect the context, select an installed model, and choose **Analyze locally**. Returning to the finding restores the latest persisted request. No model is downloaded automatically.

## Configuration

Ollama must be installed and running with a local GGUF chat model. Configure `SENTINEL_OLLAMA_URL` (default `http://127.0.0.1:11434`) and `SENTINEL_OLLAMA_TIMEOUT` (default 180 seconds, range 10–600). Only literal IPv4/IPv6 loopback HTTP endpoints are accepted; redirects, proxy environment variables, credentials, remote hosts, and cloud model entries are blocked. Model metadata is checked again before inference. The Ollama service itself is trusted local software; SENTINEL cannot enforce the behavior of a modified service.

For Docker, this loopback-only provider cannot reach host Ollama through a gateway hostname. Use the native local launcher for Phase 3 inference. Remote/cloud providers are deliberately not enabled.

## Context and validation

The preview includes the selected finding, stable evidence IDs, up to 37 nearby source lines (600 characters per line, 12,000 source characters total), nearby AST entities and lexical call names, up to 30 dependency declarations, other same-file static findings, and indexed Git branch/commit. The serialized context is capped at 48,000 bytes. New scans add up to six relevant lexical graph relationships with evidence references. Dynamic dispatch remains unresolved; related-file source and Git history are unavailable. See [graph coverage](graph-search.md).

Source paths and hashes are revalidated when previewing and submitting. Detected secret assignments are redacted. Other sensitive content may remain: inspect the preview before submitting. A matching context digest is required at submission so the preview cannot silently change. Context is an observation of the indexed source, not a guarantee that files remain unchanged after submission.

The provider uses Ollama's [chat endpoint](https://docs.ollama.com/api/chat) with a [JSON schema](https://docs.ollama.com/capabilities/structured-outputs), temperature zero, 8,192 context tokens, and a 2,200-token output budget. Pydantic validates strict types, field lengths, verdict/severity enums, confidence bounds, tests, and uncertainty. Evidence references must exist in the supplied package. A non-uncertain verdict requires evidence references. Incomplete or invalid output is rejected without fabricated fallback text. There is no automatic retry.

Repository content is explicitly treated as untrusted data in the system prompt. Models receive no tools, shell access, or patch capability. Prompt injection can still affect model opinions; schema checks and valid references do not prove semantic truth. A model's `confirmed` means its unverified opinion, never verified exploitation. Self-reported confidence is not calibrated. The UI labels all output as an unverified model opinion, separate from deterministic severity and triage status.

## Persistence and lifecycle

One model request runs at a time per API process; concurrent submissions receive HTTP 429. Requests return HTTP 202 promptly and are polled by the UI. Navigation does not cancel a request. Timeouts and failures are persisted with sanitized error text. Interrupted requests become failed when the API restarts. Run one API process, as for scan workers.

The database stores model name/digest, request timestamps, context digest, source fingerprint, structural context summary, validated response, and status. Full context and source excerpts are not persisted by this feature. Model-generated prose may quote supplied source, so inspect analysis records before sharing a database. Ollama memory/logging behavior is controlled by the local Ollama installation. Failed raw responses are not stored. No status, severity, or source file is changed by an opinion.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/llm/models` | Installed local model inventory or an explicit unavailable state |
| GET | `/api/findings/{id}/context` | Reviewable package, summary, and context hash |
| POST | `/api/findings/{id}/analyses` | Start `{ "model": "installed-name", "context_hash": "preview-hash" }` |
| GET | `/api/analyses/{id}` | Running, completed, or failed request |
| GET | `/api/findings/{id}/analyses` | Up to 20 latest requests for a finding |

