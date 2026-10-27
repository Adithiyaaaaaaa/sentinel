"""Bounded graph views and explicit local semantic-index jobs."""

import math
from datetime import UTC
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from backend.analysis.engine import read_indexed_source
from backend.database import (
    CodeEntity,
    EmbeddingIndex,
    EntityEmbedding,
    Repository,
    Scan,
    utcnow,
)
from backend.embeddings.service import KINDS, MAX_ENTITIES
from backend.llm.contracts import ProviderError
from backend.security.paths import allowed_directory


class IndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=255)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=30)


def index_out(index):
    result = {
        key: getattr(index, key)
        for key in (
            "id",
            "scan_id",
            "model",
            "model_digest",
            "status",
            "total",
            "indexed",
            "skipped",
            "dimensions",
            "error",
            "created_at",
            "completed_at",
        )
    }
    for key in ("created_at", "completed_at"):
        if result[key] and result[key].tzinfo is None:
            result[key] = result[key].replace(tzinfo=UTC)
    return result


def graph_router(sessions, settings, service):
    router = APIRouter(prefix="/api", tags=["Architecture and search"])

    @router.get("/scans/{scan_id}/graph")
    def graph(
        scan_id: str,
        view: Literal["files", "symbols"] = "files",
        file: str | None = Query(None, max_length=2048),
        limit: int = Query(120, ge=1, le=500),
    ):
        with sessions() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise HTTPException(404, "Scan not found.")
            data = scan.graph_data
            if not data:
                return {
                    "available": False,
                    "nodes": [],
                    "edges": [],
                    "summary": {},
                    "truncated": False,
                    "unresolved": [],
                }
            all_nodes = {n["id"]: n for n in data["nodes"]}
            if view == "files":
                nodes = [n for n in data["nodes"] if n["kind"] in {"file", "external"}]
                edges = {}
                for edge in data["edges"]:
                    if edge["kind"] not in {"calls", "imports", "depends_on"}:
                        continue
                    source, target = all_nodes[edge["source"]], all_nodes[edge["target"]]
                    source_id = "file:" + source["file"]
                    target_id = "file:" + target["file"] if target.get("file") else target["id"]
                    if source_id != target_id:
                        edges.setdefault(
                            (source_id, target_id, edge["kind"]),
                            edge | {"source": source_id, "target": target_id},
                        )
                edges = list(edges.values())
            else:
                nodes, edges = data["nodes"], data["edges"]
            if file:
                selected = {n["id"] for n in nodes if n.get("file") == file}
                links = [e for e in edges if e["source"] in selected or e["target"] in selected]
                selected |= {e[k] for e in links for k in ("source", "target")}
                nodes = [n for n in nodes if n["id"] in selected]
                edges = links
            count = len(nodes)
            nodes = nodes[:limit]
            ids = {n["id"] for n in nodes}
            links = [e for e in edges if e["source"] in ids and e["target"] in ids]
            summary = dict(data["summary"])
            summary["coupling"] = sorted(
                summary["coupling"], key=lambda n: (-(n["fan_in"] + n["fan_out"]), n["file"])
            )[:30]
            summary["cycle_count"] = len(summary["cycles"])
            summary["cycles"] = summary["cycles"][:30]
            return {
                "available": True,
                "nodes": nodes,
                "edges": links[:2000],
                "summary": summary,
                "matching_nodes": count,
                "truncated": count > limit or len(links) > 2000 or summary["truncated"],
                "unresolved": [r for r in data["unresolved"] if not file or r["file"] == file][:100],
            }

    @router.get("/embeddings/models")
    def models():
        try:
            return {"available": True, "models": service.provider.models(), "error": None}
        except ProviderError as exc:
            return {"available": False, "models": [], "error": str(exc)}

    @router.get("/scans/{scan_id}/embeddings")
    def indexes(scan_id: str):
        with sessions() as session:
            if session.get(Scan, scan_id) is None:
                raise HTTPException(404, "Scan not found.")
            return [
                index_out(i)
                for i in session.scalars(
                    select(EmbeddingIndex)
                    .where(EmbeddingIndex.scan_id == scan_id)
                    .order_by(EmbeddingIndex.created_at.desc())
                    .limit(20)
                )
            ]

    @router.get("/embeddings/{index_id}")
    def status(index_id: str):
        with sessions() as session:
            index = session.get(EmbeddingIndex, index_id)
            if index is None:
                raise HTTPException(404, "Embedding index not found.")
            return index_out(index)

    @router.post("/scans/{scan_id}/embeddings", status_code=202)
    def build(scan_id: str, payload: IndexRequest):
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Local embedding work is busy. Try again shortly.")
        submitted = False
        try:
            try:
                model = next((m for m in service.provider.models() if m["name"] == payload.model), None)
            except ProviderError as exc:
                raise HTTPException(503, str(exc)) from None
            if model is None:
                raise HTTPException(422, "Choose an installed local embedding model.")
            with sessions.begin() as session:
                scan = session.get(Scan, scan_id)
                if scan is None:
                    raise HTTPException(404, "Scan not found.")
                if scan.status != "completed":
                    raise HTTPException(409, "Complete the repository scan first.")
                total = session.scalar(
                    select(func.count())
                    .select_from(CodeEntity)
                    .where(CodeEntity.scan_id == scan_id, CodeEntity.kind.in_(KINDS))
                )
                if not total:
                    raise HTTPException(422, "This scan has no supported callable entities to embed.")
                index = EmbeddingIndex(
                    scan_id=scan_id,
                    model=payload.model,
                    model_digest=model["digest"],
                    total=total,
                    skipped=max(0, total - MAX_ENTITIES),
                )
                session.add(index)
                session.flush()
                result = index_out(index)
            try:
                service.submit(index.id)
            except RuntimeError:
                with sessions.begin() as session:
                    job = session.get(EmbeddingIndex, index.id)
                    job.status, job.error, job.completed_at = (
                        "failed",
                        "Embedding worker is unavailable.",
                        utcnow(),
                    )
                raise HTTPException(503, "Embedding worker is unavailable.") from None
            submitted = True
            return result
        finally:
            if not submitted:
                service.lock.release()

    @router.post("/embeddings/{index_id}/search")
    def search(index_id: str, payload: SearchRequest):
        if not payload.query.strip():
            raise HTTPException(422, "Enter a search query.")
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Local embedding work is busy. Try again shortly.")
        try:
            with sessions() as session:
                index = session.get(EmbeddingIndex, index_id)
                if index is None:
                    raise HTTPException(404, "Embedding index not found.")
                if index.status != "completed":
                    raise HTTPException(409, "This embedding index is not complete.")
                try:
                    model = next((m for m in service.provider.models() if m["name"] == index.model), None)
                    if model is None or model["digest"] != index.model_digest:
                        raise HTTPException(
                            409, "The embedding model is missing or changed. Restore it or build a new index."
                        )
                    query = service.provider.embed(index.model, [payload.query.strip()])[0]
                except ProviderError as exc:
                    raise HTTPException(503, str(exc)) from None
                if len(query) != index.dimensions:
                    raise HTTPException(409, "Embedding dimensions changed. Rebuild the index.")
                rows = list(
                    session.scalars(select(EntityEmbedding).where(EntityEmbedding.index_id == index_id))
                )
                scored = sorted(
                    ((math.fsum(a * b for a, b in zip(query, row.vector, strict=True)), row) for row in rows),
                    key=lambda x: (-x[0], x[1].entity_key),
                )[: payload.limit]
                entities = {
                    e.key: e
                    for e in session.scalars(select(CodeEntity).where(CodeEntity.scan_id == index.scan_id))
                }
                scan = session.get(Scan, index.scan_id)
                root = allowed_directory(session.get(Repository, scan.repository_id).path, settings.roots())
                verified, items = {}, []
                for score, row in scored:
                    entity = entities.get(row.entity_key)
                    if entity is None:
                        continue
                    if entity.file not in verified:
                        try:
                            read_indexed_source(root, entity.file, row.source_hash)
                            verified[entity.file] = True
                        except (ValueError, OSError, UnicodeError):
                            verified[entity.file] = False
                    items.append(
                        {
                            "key": entity.key,
                            "file": entity.file,
                            "name": entity.name,
                            "kind": entity.kind,
                            "line": entity.start_line,
                            "end_line": entity.end_line,
                            "similarity": round(max(-1, min(1, score)), 6),
                            "source_verified": verified[entity.file],
                        }
                    )
                return {
                    "index_id": index.id,
                    "model": index.model,
                    "items": items,
                    "meaning": "Cosine similarity ranks semantic proximity; it is not relevance probability or security confidence.",
                }
        finally:
            service.lock.release()

    return router
