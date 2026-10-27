"""Explicit local reasoning requests and inspectable context."""

from datetime import UTC

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.database import AIAnalysis, Finding, utcnow
from backend.llm.context import build_context, context_identity
from backend.llm.contracts import ProviderError


class ReasonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=255)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def job_out(job):
    result = {
        key: getattr(job, key)
        for key in (
            "id",
            "finding_id",
            "model",
            "model_digest",
            "status",
            "created_at",
            "completed_at",
            "context_hash",
            "context_summary",
            "response",
            "error",
        )
    }
    for field in ("created_at", "completed_at"):
        value = result[field]
        if value is not None and value.tzinfo is None:
            result[field] = value.replace(tzinfo=UTC)
    return result


def llm_router(sessions, settings, service):
    router = APIRouter(prefix="/api", tags=["Local reasoning"])

    @router.get("/llm/models")
    def models():
        try:
            return {
                "available": True,
                "provider": "ollama",
                "models": service.provider.models(),
                "error": None,
            }
        except ProviderError as exc:
            return {"available": False, "provider": "ollama", "models": [], "error": str(exc)}

    @router.get("/findings/{finding_id}/context")
    def context(finding_id: str):
        with sessions() as session:
            finding = session.get(Finding, finding_id)
            if finding is None:
                raise HTTPException(404, "Finding not found.")
            package = build_context(session, settings, finding)
            digest, summary = context_identity(package)
            return {"context_hash": digest, "summary": summary, "package": package}

    @router.get("/findings/{finding_id}/analyses")
    def history(finding_id: str):
        with sessions() as session:
            if session.get(Finding, finding_id) is None:
                raise HTTPException(404, "Finding not found.")
            return [
                job_out(job)
                for job in session.scalars(
                    select(AIAnalysis)
                    .where(AIAnalysis.finding_id == finding_id)
                    .order_by(AIAnalysis.created_at.desc())
                    .limit(20)
                )
            ]

    @router.get("/analyses/{job_id}")
    def status(job_id: str):
        with sessions() as session:
            job = session.get(AIAnalysis, job_id)
            if job is None:
                raise HTTPException(404, "Analysis not found.")
            return job_out(job)

    @router.post("/findings/{finding_id}/analyses", status_code=202)
    def reason(finding_id: str, payload: ReasonRequest):
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Another local analysis is running. Wait for it to finish.")
        submitted = False
        try:
            try:
                inventory = service.provider.models()
            except ProviderError as exc:
                raise HTTPException(503, str(exc)) from None
            model = next((row for row in inventory if row["name"] == payload.model), None)
            if model is None:
                raise HTTPException(422, "Choose an installed local model from the current inventory.")
            with sessions.begin() as session:
                finding = session.get(Finding, finding_id)
                if finding is None:
                    raise HTTPException(404, "Finding not found.")
                package = build_context(session, settings, finding)
                digest, summary = context_identity(package)
                if digest != payload.context_hash:
                    raise HTTPException(
                        409, "Context changed. Preview the context again before requesting analysis."
                    )
                job = AIAnalysis(
                    finding_id=finding_id,
                    model=payload.model,
                    model_digest=model["digest"],
                    context_hash=digest,
                    context_summary=summary,
                )
                session.add(job)
                session.flush()
                result = job_out(job)
            try:
                service.submit(job.id, payload.model, package)
            except RuntimeError:
                with sessions.begin() as session:
                    interrupted = session.get(AIAnalysis, job.id)
                    interrupted.status = "failed"
                    interrupted.error = "Local reasoning worker is shutting down. Try again after restart."
                    interrupted.completed_at = utcnow()
                raise HTTPException(503, "Local reasoning worker is unavailable.") from None
            submitted = True
            return result
        finally:
            if not submitted:
                service.lock.release()

    return router
