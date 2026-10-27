"""Explicit proposal, validation, apply and rollback actions."""

from datetime import UTC
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from backend.database import Patch, TestRun, utcnow
from backend.llm.contracts import ProviderError
from backend.patches.service import preview


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str | None = Field(default=None, max_length=36)
    entity_id: str | None = Field(default=None, max_length=36)
    kind: Literal["fix", "tests"] = "fix"

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.finding_id) == bool(self.entity_id):
            raise ValueError("Select exactly one finding or function.")
        return self


class Generate(Target):
    model: str = Field(min_length=1, max_length=255)
    context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved: Literal[True]


def record_out(record, fields):
    output = {key: getattr(record, key) for key in fields.split()}
    for key in ("created_at", "updated_at", "completed_at"):
        if output.get(key) is not None and output[key].tzinfo is None:
            output[key] = output[key].replace(tzinfo=UTC)
    return output


def patch_out(job):
    return record_out(
        job,
        "id scan_id finding_id entity_id kind path model model_digest status source_hash after_hash review_hash diff tests explanation risks error created_at updated_at",
    )


def patch_router(sessions, settings, service):
    router = APIRouter(prefix="/api", tags=["Reviewed changes"])

    @router.get("/patches/capabilities")
    def capabilities():
        return {
            "languages": ["Python"],
            "test_framework": "pytest",
            "sandbox": service.sandbox.availability(),
            "limits": "Single-file fixes; generated pytest tests plus indexed tests/. No automatic dependency installation or coverage delta.",
        }

    @router.post("/patches/preview")
    def context(payload: Target):
        with sessions() as session:
            package, digest, _, _ = preview(session, settings, **payload.model_dump())
            return {
                "package": package,
                "context_hash": digest,
                "persistence": "Successful proposals store the original file, replacement, diff, and generated tests locally for review and rollback.",
            }

    @router.get("/patches")
    def history(
        finding_id: str | None = Query(None, max_length=36),
        entity_id: str | None = Query(None, max_length=36),
    ):
        if bool(finding_id) == bool(entity_id):
            raise HTTPException(422, "Select exactly one finding or function.")
        with sessions() as session:
            condition = Patch.finding_id == finding_id if finding_id else Patch.entity_id == entity_id
            return [
                patch_out(job)
                for job in session.scalars(
                    select(Patch).where(condition).order_by(Patch.created_at.desc()).limit(20)
                )
            ]

    @router.get("/patches/{job_id}")
    def status(job_id: str):
        with sessions() as session:
            job = session.get(Patch, job_id)
            if job is None:
                raise HTTPException(404, "Proposal not found.")
            result = patch_out(job)
            result["test_runs"] = [
                record_out(run, "id status result error created_at completed_at")
                for run in session.scalars(
                    select(TestRun)
                    .where(TestRun.patch_id == job_id)
                    .order_by(TestRun.created_at.desc())
                    .limit(10)
                )
            ]
            return result

    @router.post("/patches", status_code=202)
    def generate(payload: Generate):
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Another change operation is running.")
        submitted = False
        job_id = None
        try:
            try:
                model = next((m for m in service.provider.models() if m["name"] == payload.model), None)
            except ProviderError as exc:
                raise HTTPException(503, str(exc)) from None
            if model is None:
                raise HTTPException(422, "Choose an installed local model.")
            with sessions.begin() as session:
                package, digest, fingerprint, scan_id = preview(
                    session,
                    settings,
                    finding_id=payload.finding_id,
                    entity_id=payload.entity_id,
                    kind=payload.kind,
                )
                if digest != payload.context_hash:
                    raise HTTPException(409, "Source or context changed. Preview again.")
                job = Patch(
                    scan_id=scan_id,
                    finding_id=payload.finding_id,
                    entity_id=payload.entity_id,
                    kind=payload.kind,
                    path=package["path"],
                    model=payload.model,
                    model_digest=model["digest"],
                    source_hash=fingerprint,
                )
                session.add(job)
                session.flush()
                job_id, result = job.id, patch_out(job)
            service.executor.submit(service.generate, job_id, package)
            submitted = True
            return result
        except RuntimeError:
            if job_id:
                service.fail(job_id, "failed", "Worker is shutting down. Generate again after restart.")
            raise HTTPException(503, "Change worker is unavailable.") from None
        finally:
            if not submitted:
                service.lock.release()

    @router.post("/patches/{job_id}/validate", status_code=202)
    def validate(job_id: str, payload: Approval):
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Another change operation is running.")
        submitted, run_id = False, None
        try:
            available = service.sandbox.availability()
            if not available["available"]:
                raise HTTPException(503, available["error"])
            with sessions.begin() as session:
                job = session.get(Patch, job_id)
                if job is None:
                    raise HTTPException(404, "Proposal not found.")
                if (
                    job.status not in {"ready", "validated", "validation_failed"}
                    or job.review_hash != payload.review_hash
                ):
                    raise HTTPException(409, "Review the current completed proposal first.")
                job.status, job.error, job.updated_at = "validating", None, utcnow()
                job.validation_snapshot = {}
                run = TestRun(patch_id=job.id)
                session.add(run)
                session.flush()
                run_id = run.id
            service.executor.submit(service.validate, job_id, run_id)
            submitted = True
            return status(job_id)
        except RuntimeError:
            if run_id:
                service.fail(job_id, "validation_failed", "Worker is shutting down.")
                with sessions.begin() as session:
                    run = session.get(TestRun, run_id)
                    run.status, run.error, run.completed_at = "failed", "Worker is shutting down.", utcnow()
            raise HTTPException(503, "Change worker is unavailable.") from None
        finally:
            if not submitted:
                service.lock.release()

    @router.post("/patches/{job_id}/{action}")
    def change(job_id: str, action: Literal["apply", "rollback"], payload: Approval):
        if not service.lock.acquire(blocking=False):
            raise HTTPException(429, "Another change operation is running.")
        try:
            service.change(job_id, payload.review_hash, rollback=action == "rollback")
            return status(job_id)
        finally:
            service.lock.release()

    return router
