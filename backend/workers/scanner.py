"""Bounded in-process workers for a single-user local deployment.

Metadata, entities, and structural evidence are persisted; full source is not.
Repository code and package scripts are never run.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from sqlalchemy import delete, update
from sqlalchemy.orm import sessionmaker

from backend.analysis.engine import analyze_repository
from backend.analysis.indexer import index_repository
from backend.architecture.graph import build_graph
from backend.config import Settings
from backend.database import (
    CodeEntity,
    Dependency,
    Finding,
    FindingEvidence,
    IndexedFile,
    Repository,
    Scan,
    utcnow,
)
from backend.security.paths import allowed_directory
from backend.security.rules import RULES, SEVERITY_WEIGHTS

logger = logging.getLogger("sentinel.scanner")


class ScanWorker:
    def __init__(self, sessions: sessionmaker, settings: Settings):
        self.sessions = sessions
        self.settings = settings
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix="sentinel-index")
        self.capacity = threading.BoundedSemaphore(settings.max_queued_scans)
        self.lock = threading.Lock()

    def recover_interrupted(self) -> None:
        with self.sessions.begin() as session:
            session.execute(update(Scan).where(Scan.status.in_(["queued", "running"])).values(
                status="failed", stage="Interrupted", completed_at=utcnow(),
                error="The local service stopped during this scan. Start a new scan to retry."))

    def submit(self, scan_id: str) -> bool:
        if not self.capacity.acquire(blocking=False):
            return False
        try:
            self.executor.submit(self._run, scan_id)
            return True
        except RuntimeError:
            self.capacity.release()
            return False

    def _progress(self, scan_id: str, percent: int, stage: str) -> None:
        with self.sessions.begin() as session:
            session.execute(update(Scan).where(Scan.id == scan_id).values(progress=min(99, max(0, percent)), stage=stage[:255]))

    def _run(self, scan_id: str) -> None:
        start = time.perf_counter()
        try:
            with self.sessions.begin() as session:
                scan = session.get(Scan, scan_id)
                if scan is None:
                    return
                repo = session.get(Repository, scan.repository_id)
                if repo is None:
                    raise ValueError("Repository no longer exists")
                path, patterns = repo.path, list(repo.ignore_patterns)
                scan.status, scan.started_at, scan.stage = "running", utcnow(), "Discovering repository"
            root = allowed_directory(path, self.settings.roots())
            result = index_repository(root, patterns, lambda p, s: self._progress(scan_id, round(p * .5), s))
            analysis = analyze_repository(root, result.files, lambda p, s: self._progress(scan_id, p, s))
            self._progress(scan_id, 92, "Resolving lexical calls and architecture")
            graph = build_graph(root, result.files, analysis.entities)
            self._progress(scan_id, 95, "Saving findings and repository graph")
            with self.sessions.begin() as session:
                scan = session.get(Scan, scan_id)
                if scan is None:
                    return
                for batch_start in range(0, len(result.files), 500):
                    session.add_all(IndexedFile(scan_id=scan_id, **asdict(item)) for item in result.files[batch_start:batch_start + 500])
                    session.flush()
                session.add_all(Dependency(scan_id=scan_id, **item) for item in result.dependencies)
                for batch_start in range(0, len(analysis.entities), 500):
                    session.add_all(CodeEntity(scan_id=scan_id, **asdict(item)) for item in analysis.entities[batch_start:batch_start + 500])
                    session.flush()
                for detection in analysis.detections:
                    rule = RULES[detection.rule_id]
                    metadata = rule.metadata()
                    metadata.pop("id")
                    finding = Finding(scan_id=scan_id, rule_id=rule.id, fingerprint=detection.fingerprint,
                        file=detection.file, language=detection.language, line=detection.line, end_line=detection.end_line,
                        symbol=detection.symbol[:255], risk=rule.risk(),
                        risk_basis={"formula": "round(severity_weight Ã— confidence)", "severity_weight": SEVERITY_WEIGHTS[rule.severity],
                                    "confidence": rule.confidence, "meaning": "Triage priority, not exploit probability or repository health."}, **metadata)
                    session.add(finding)
                    session.flush()
                    session.add(FindingEvidence(finding_id=finding.id, line=detection.line, end_line=detection.end_line,
                                               kind="ast_pattern", description=detection.basis))
                for field in ("total_files", "total_lines", "total_bytes", "skipped_files", "languages", "frameworks", "package_managers", "test_frameworks", "has_docker", "has_ci", "branch", "commit", "warnings"):
                    setattr(scan, field, getattr(result, field))
                scan.dependency_count = len(result.dependencies)
                scan.analysis_summary = analysis.summary
                scan.graph_data = graph
                scan.warnings = (result.warnings + analysis.warnings)[:100]
                scan.status, scan.progress, scan.stage = "completed", 100, "Analysis complete"
                scan.completed_at, scan.duration_ms = utcnow(), round((time.perf_counter() - start) * 1000)
            logger.info("scan_completed", extra={"scan_id": scan_id, "duration_ms": round((time.perf_counter() - start) * 1000), "file_count": result.total_files})
        except Exception as exc:  # noqa: BLE001 â€” worker boundary must persist terminal failure and release capacity
            # Do not log exception text: filesystem/manifest failures may contain source or secrets.
            logger.error("scan_failed", extra={"scan_id": scan_id, "error_type": type(exc).__name__})
            with self.sessions.begin() as session:
                session.execute(delete(IndexedFile).where(IndexedFile.scan_id == scan_id))
                session.execute(delete(Dependency).where(Dependency.scan_id == scan_id))
                session.execute(delete(Finding).where(Finding.scan_id == scan_id))
                session.execute(delete(CodeEntity).where(CodeEntity.scan_id == scan_id))
                session.execute(update(Scan).where(Scan.id == scan_id).values(
                    status="failed", stage="Index failed", completed_at=utcnow(),
                    duration_ms=round((time.perf_counter() - start) * 1000),
                    error="Indexing failed. Check folder access and configured roots, then retry. No repository code was executed."))
        finally:
            self.capacity.release()

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
