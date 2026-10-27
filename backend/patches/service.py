"""Persisted proposal jobs and guarded, recoverable single-file changes."""

import ast
import json
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from backend.analysis.engine import read_indexed_source
from backend.database import CodeEntity, Finding, IndexedFile, Patch, Repository, Scan, TestRun, utcnow
from backend.llm.contracts import ProviderError
from backend.patches.diff import apply_diff, canonical_diff, digest, validate_tests
from backend.patches.provider import PatchProvider
from backend.patches.sandbox import DockerSandbox, SandboxError
from backend.security.paths import allowed_directory


def source_for(session, settings, scan_id, path, expected=None):
    scan = session.get(Scan, scan_id)
    repo = session.get(Repository, scan.repository_id)
    root = allowed_directory(repo.path, settings.roots())
    file = session.scalar(select(IndexedFile).where(IndexedFile.scan_id == scan_id, IndexedFile.path == path))
    if file is None:
        raise ValueError("Source is not indexed.")
    source = read_indexed_source(root, path, expected or file.sha256, 128000)
    # A round-trip must preserve every byte, including BOM/newline representation.
    if digest(source.encode()) != (expected or file.sha256):
        raise ValueError("This workflow requires UTF-8 without BOM and preserved line endings.")
    return root, file, source


def preview(session, settings, *, finding_id=None, entity_id=None, kind="fix"):
    target = session.get(Finding, finding_id) if finding_id else session.get(CodeEntity, entity_id)
    if target is None:
        raise HTTPException(404, "Finding or function not found.")
    if target.language != "Python" or (entity_id and target.kind not in {"function", "method"}):
        raise HTTPException(422, "Reviewed changes currently support Python functions and findings only.")
    if kind == "fix" and not finding_id:
        raise HTTPException(422, "Select a finding to generate a fix.")
    try:
        _, file, source = source_for(session, settings, target.scan_id, target.file)
        if len(source) > 12000 or "\r" in source or not source.endswith("\n"):
            raise ValueError(
                "Generation requires a Python file under 12,000 characters with LF endings and a final newline."
            )
        if session.scalar(
            select(Finding.id).where(
                Finding.scan_id == target.scan_id, Finding.file == target.file, Finding.rule_id == "SEC-001"
            )
        ):
            raise ValueError(
                "This file contains a detected secret. Remove the secret and rescan before patch generation."
            )
        ast.parse(source)
    except (ValueError, OSError, SyntaxError, UnicodeError) as exc:
        raise HTTPException(
            409,
            str(exc)
            if isinstance(exc, ValueError)
            else "Source is stale, unreadable, or invalid; rescan first.",
        ) from None
    scan = session.get(Scan, target.scan_id)
    package = {
        "kind": kind,
        "path": target.file,
        "source": source,
        "selection": {
            "name": target.symbol if finding_id else target.name,
            "line": target.line if finding_id else target.start_line,
        },
        "finding": {"title": target.title, "recommendation": target.recommendation} if finding_id else None,
        "detected_test_frameworks": scan.test_frameworks,
        "test_framework": "pytest",
        "limits": "Single Python file; generated tests and indexed tests/ only. No coverage measurement or runtime guarantee.",
    }
    context_hash = digest(json.dumps(package, sort_keys=True).encode())
    return package, context_hash, file.sha256, target.scan_id


def review_digest(job):
    return digest(
        json.dumps(
            {"diff": job.diff, "tests": job.tests, "source_hash": job.source_hash, "path": job.path},
            sort_keys=True,
        ).encode()
    )


class PatchService:
    def __init__(self, sessions, settings):
        self.sessions, self.settings = sessions, settings
        self.provider, self.sandbox = PatchProvider(settings), DockerSandbox(settings)
        self.lock = threading.BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-patches")

    def recover(self):
        with self.sessions.begin() as session:
            for job in session.scalars(
                select(Patch).where(
                    Patch.status.in_(["generating", "validating", "applying", "rolling_back"])
                )
            ):
                if job.status in {"applying", "rolling_back"}:
                    try:
                        source_for(session, self.settings, job.scan_id, job.path, job.after_hash)
                        job.status = "applied"
                    except (ValueError, OSError, HTTPException):
                        try:
                            source_for(session, self.settings, job.scan_id, job.path, job.source_hash)
                            job.status = "rolled_back"
                        except (ValueError, OSError, HTTPException):
                            job.status = "conflict"
                    job.error = "An interrupted file operation was reconciled with current content. Review before proceeding."
                else:
                    job.status = "failed" if job.status == "generating" else "validation_failed"
                    job.error = (
                        "Operation interrupted by API restart. Request generation or validation again."
                    )
                job.updated_at = utcnow()
            for run in session.scalars(select(TestRun).where(TestRun.status == "running")):
                run.status, run.error, run.completed_at = "failed", "Validation was interrupted.", utcnow()

    def generate(self, job_id, package):
        try:
            with self.sessions() as session:
                job = session.get(Patch, job_id)
            proposal = self.provider.generate(job.model, package)
            module = job.path[:-3].replace("/", ".").removesuffix(".__init__")
            validate_tests(proposal.tests, module, package["selection"]["name"])
            before = package["source"]
            if job.kind == "fix":
                after = apply_diff(before, proposal.diff, job.path)
                delta = canonical_diff(before, after, job.path)
                if sum(line.startswith(("+", "-")) for line in delta.splitlines()[2:]) > 200:
                    raise ValueError("Generated change is too large for single-file review.")
            else:
                if proposal.diff:
                    raise ValueError("Test-only generation must not change repository source.")
                after, delta = before, ""
            models = self.provider.models()
            if not any(m["name"] == job.model and m["digest"] == job.model_digest for m in models):
                raise ValueError("Local model changed during generation. Generate again.")
            with self.sessions.begin() as session:
                job = session.get(Patch, job_id)
                source_for(session, self.settings, job.scan_id, job.path, job.source_hash)
                job.original, job.replacement = before, after
                job.diff, job.tests = delta, proposal.tests
                job.explanation, job.risks = proposal.explanation, proposal.risks
                job.after_hash, job.status = digest(after.encode()), "ready"
                job.review_hash = review_digest(job)
                job.updated_at = utcnow()
        except Exception as exc:  # noqa: BLE001 -- sanitize background job failures
            self.fail(
                job_id,
                "failed",
                str(exc)
                if isinstance(exc, (ValueError, ProviderError)) and not isinstance(exc, SyntaxError)
                else "Proposal rejected: invalid syntax, stale source, or unavailable local model.",
            )
        finally:
            self.lock.release()

    def fail(self, job_id, status, error):
        with self.sessions.begin() as session:
            job = session.get(Patch, job_id)
            job.status, job.error, job.updated_at = status, error[:512], utcnow()

    def snapshot(self, session, job, destination):
        scan = session.get(Scan, job.scan_id)
        repo = session.get(Repository, scan.repository_id)
        root = allowed_directory(repo.path, self.settings.roots())
        files = list(
            session.scalars(
                select(IndexedFile).where(IndexedFile.scan_id == job.scan_id).order_by(IndexedFile.path)
            )
        )
        # Only Python sources are copied; no .env, credentials, binaries or package scripts.
        files = [f for f in files if f.language == "Python"]
        if len(files) > 1000 or sum(f.size_bytes for f in files) > 32 * 1024 * 1024:
            raise ValueError("Python validation snapshot exceeds 1,000 files or 32 MiB.")
        fingerprints = {}
        for file in files:
            source = read_indexed_source(root, file.path, file.sha256)
            fingerprints[file.path] = file.sha256
            target = destination / file.path
            if not target.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Invalid indexed path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                job.replacement if file.path == job.path else source, encoding="utf-8", newline=""
            )
        return fingerprints

    def validate(self, job_id, run_id):
        try:
            with tempfile.TemporaryDirectory(prefix="sentinel-validation-") as folder:
                root = Path(folder)
                repository, generated = root / "repository", root / "generated"
                repository.mkdir()
                generated.mkdir()
                with self.sessions() as session:
                    job = session.get(Patch, job_id)
                    snapshot = self.snapshot(session, job, repository)
                    (generated / "sentinel_generated_test.py").write_text(job.tests, encoding="utf-8")
                result = self.sandbox.run(repository, generated)
            with self.sessions.begin() as session:
                job, run = session.get(Patch, job_id), session.get(TestRun, run_id)
                job.status = "validated" if result["passed"] else "validation_failed"
                job.error = (
                    None
                    if result["passed"]
                    else "Sandbox tests failed. Staged changes were discarded; repository files were not modified."
                )
                job.validation_snapshot = snapshot if result["passed"] else {}
                job.updated_at = utcnow()
                run.status, run.result, run.error, run.completed_at = (
                    "passed" if result["passed"] else "failed",
                    result,
                    job.error,
                    utcnow(),
                )
        except Exception as exc:  # noqa: BLE001 -- sanitize background job failures
            error = (
                str(exc)
                if isinstance(exc, (ValueError, SandboxError))
                else "Validation failed. No repository files were modified."
            )
            self.fail(job_id, "validation_failed", error)
            with self.sessions.begin() as session:
                run = session.get(TestRun, run_id)
                run.status, run.error, run.completed_at = "failed", error[:512], utcnow()
        finally:
            self.lock.release()

    def change(self, job_id, review_hash, rollback=False):
        # Persist intent and backup before the filesystem mutation; recover() reconciles crashes.
        with self.sessions.begin() as session:
            job = session.get(Patch, job_id)
            if job is None:
                raise HTTPException(404, "Proposal not found.")
            required = "applied" if rollback else "validated"
            if job.status != required or job.kind != "fix" or review_hash != job.review_hash:
                raise HTTPException(
                    409, "Review the current proposal and complete validation before changing files."
                )
            expected = job.after_hash if rollback else job.source_hash
            try:
                root, _, _ = source_for(session, self.settings, job.scan_id, job.path, expected)
                if not rollback:
                    if not job.validation_snapshot:
                        raise ValueError("Validation snapshot is missing.")
                    for path, fingerprint in job.validation_snapshot.items():
                        read_indexed_source(root, path, fingerprint)
            except (ValueError, OSError, UnicodeError):
                raise HTTPException(
                    409, "Source changed since validation or application. No files were overwritten."
                ) from None
            content = job.original if rollback else job.replacement
            target = root / job.path
            job.status, job.updated_at = "rolling_back" if rollback else "applying", utcnow()
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(prefix=".sentinel-change-", dir=target.parent)
            with os.fdopen(fd, "wb") as stream:
                stream.write(content.encode())
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, target.stat().st_mode)
            read_indexed_source(root, job.path, expected, 128000)
            os.replace(temporary, target)
            with self.sessions.begin() as session:
                job = session.get(Patch, job_id)
                job.status, job.error, job.updated_at = (
                    "rolled_back" if rollback else "applied",
                    None,
                    utcnow(),
                )
        except (OSError, ValueError):
            self.fail(
                job_id,
                "conflict",
                "File operation could not complete safely. Review current content; the saved original is retained.",
            )
            raise HTTPException(
                409, "File operation failed or source changed. Review current content."
            ) from None
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()

    def close(self):
        self.executor.shutdown(wait=True)
