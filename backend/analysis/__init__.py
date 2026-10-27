"""Deterministic, read-only repository analysis."""

from backend.analysis.indexer import IndexedFile, IndexResult, index_repository

__all__ = ["IndexResult", "IndexedFile", "index_repository"]
