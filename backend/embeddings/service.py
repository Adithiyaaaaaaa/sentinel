"""Local entity vectors and exact cosine retrieval, bounded to 1,000 entities."""

import math
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, select, update

from backend.analysis.engine import read_indexed_source
from backend.database import (
    CodeEntity,
    EmbeddingIndex,
    EntityEmbedding,
    Finding,
    IndexedFile,
    Repository,
    Scan,
    utcnow,
)
from backend.llm.contracts import ProviderError
from backend.llm.ollama import OllamaProvider
from backend.security.paths import allowed_directory

KINDS = ("function", "method", "class", "api")
MAX_ENTITIES = 1000


def normalized(vector):
    if not isinstance(vector, list) or not 1 <= len(vector) <= 4096:
        raise ProviderError("Embedding dimensions are invalid.")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
        raise ProviderError("Embedding contains invalid values.")
    norm = math.sqrt(math.fsum(float(v) ** 2 for v in vector))
    if not norm or not math.isfinite(norm):
        raise ProviderError("Embedding has no finite nonzero magnitude.")
    return [float(v) / norm for v in vector]


class EmbeddingProvider(OllamaProvider):
    def models(self):
        return super().models("embedding")

    def embed(self, model, texts):
        info = self.request("/api/show", {"model": model})
        if (
            info.get("remote_host")
            or info.get("remote_model")
            or "cloud" in model.lower()
            or info.get("details", {}).get("format") != "gguf"
            or "embedding" not in info.get("capabilities", [])
        ):
            raise ProviderError("An installed local GGUF embedding model is required.")
        result = self.request(
            "/api/embed",
            {"model": model, "input": texts, "truncate": False, "keep_alive": "5m"},
            self.settings.ollama_timeout,
        )
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ProviderError("Embedding response count does not match the requested entities.")
        rows = [normalized(v) for v in vectors]
        if len({len(v) for v in rows}) != 1:
            raise ProviderError("Embedding dimensions are inconsistent.")
        return rows


def entity_text(entity, source, redacted, findings):
    span = []
    budget = 2400
    for n in range(entity.start_line, min(entity.end_line, entity.start_line + 59, len(source)) + 1):
        line = "[secret assignment redacted]" if n in redacted else source[n - 1][:400]
        if len(line) + 1 > budget:
            break
        span.append(line)
        budget -= len(line) + 1
    return (
        f"File {entity.file}\n{entity.kind} {entity.name.replace('_', ' ')}\n"
        f"Features: {', '.join(entity.features[:12])}\n"
        f"Static patterns: {', '.join(f.title for f in findings if entity.start_line <= f.line <= entity.end_line)}\n"
        + "\n".join(span)
    )[:3600]


class EmbeddingService:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings
        self.provider = EmbeddingProvider(settings)
        self.lock = threading.BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-embedding")

    def recover(self):
        with self.sessions.begin() as session:
            ids = list(session.scalars(select(EmbeddingIndex.id).where(EmbeddingIndex.status == "running")))
            if ids:
                session.execute(delete(EntityEmbedding).where(EntityEmbedding.index_id.in_(ids)))
                session.execute(
                    update(EmbeddingIndex)
                    .where(EmbeddingIndex.id.in_(ids))
                    .values(
                        status="failed",
                        indexed=0,
                        error="Embedding build was interrupted. Build a new index.",
                        completed_at=utcnow(),
                    )
                )

    def submit(self, index_id):
        self.executor.submit(self.run, index_id)

    def run(self, index_id):
        try:
            with self.sessions() as session:
                index = session.get(EmbeddingIndex, index_id)
                scan = session.get(Scan, index.scan_id)
                root = allowed_directory(
                    session.get(Repository, scan.repository_id).path, self.settings.roots()
                )
                entities = list(
                    session.scalars(
                        select(CodeEntity)
                        .where(CodeEntity.scan_id == scan.id, CodeEntity.kind.in_(KINDS))
                        .order_by(CodeEntity.file, CodeEntity.start_line, CodeEntity.key)
                        .limit(MAX_ENTITIES)
                    )
                )
                files = {
                    f.path: f
                    for f in session.scalars(select(IndexedFile).where(IndexedFile.scan_id == scan.id))
                }
                findings = list(session.scalars(select(Finding).where(Finding.scan_id == scan.id)))
            current_file, source, redacted, file_findings = None, [], set(), []
            dimensions = 0
            for offset in range(0, len(entities), 8):
                batch = entities[offset : offset + 8]
                texts = []
                for entity in batch:
                    if entity.file != current_file:
                        file = files[entity.file]
                        source = read_indexed_source(root, file.path, file.sha256, 512 * 1024).splitlines()
                        file_findings = [f for f in findings if f.file == entity.file]
                        redacted = {
                            n
                            for f in file_findings
                            if f.rule_id == "SEC-001"
                            for n in range(f.line, f.end_line + 1)
                        }
                        current_file = entity.file
                    texts.append(entity_text(entity, source, redacted, file_findings))
                vectors = self.provider.embed(index.model, texts)
                if dimensions and len(vectors[0]) != dimensions:
                    raise ProviderError("Model dimensions changed during index construction.")
                dimensions = len(vectors[0])
                with self.sessions.begin() as session:
                    session.add_all(
                        EntityEmbedding(
                            index_id=index_id, entity_key=e.key, source_hash=files[e.file].sha256, vector=v
                        )
                        for e, v in zip(batch, vectors, strict=True)
                    )
                    job = session.get(EmbeddingIndex, index_id)
                    job.indexed, job.dimensions = offset + len(batch), dimensions
            inventory = self.provider.models()
            if not any(m["name"] == index.model and m["digest"] == index.model_digest for m in inventory):
                raise ProviderError("Embedding model changed during indexing. Build a new index.")
            with self.sessions.begin() as session:
                job = session.get(EmbeddingIndex, index_id)
                job.status, job.completed_at = "completed", utcnow()
        except Exception as exc:  # noqa: BLE001 -- sanitize worker failures and discard partial vectors
            error = (
                str(exc)
                if isinstance(exc, ProviderError)
                else "Embedding build failed; source may have changed or become inaccessible. Rescan and rebuild."
            )
            with self.sessions.begin() as session:
                session.execute(delete(EntityEmbedding).where(EntityEmbedding.index_id == index_id))
                job = session.get(EmbeddingIndex, index_id)
                job.status, job.error, job.completed_at, job.indexed = "failed", error, utcnow(), 0
        finally:
            self.lock.release()

    def close(self):
        self.executor.shutdown(wait=True)
