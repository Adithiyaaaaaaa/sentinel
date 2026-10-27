# Analyzer boundary

The working Phase 1 analyzer is Python code in `backend/analysis`. It returns metadata about discovered text files, language totals, tooling, and dependency declarations without executing repository code.

This package reserves the cross-language adapter boundary. Future parser adapters must emit versioned entities and evidence, preserve file/line provenance, report failures explicitly, and never treat a model's statement as deterministic evidence. There is no separate JavaScript analyzer runtime in Phase 1.
