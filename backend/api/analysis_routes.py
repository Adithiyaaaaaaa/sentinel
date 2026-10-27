"""Finding triage and bounded, fingerprint-verified source inspection."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.analysis.engine import read_indexed_source
from backend.api.schemas import (
    EntityOut,
    EvidenceOut,
    FindingOut,
    FindingPage,
    FindingStatus,
    FindingStatusUpdate,
)
from backend.config import Settings
from backend.database import CodeEntity, Finding, FindingEvidence, IndexedFile, Repository, Scan, utcnow
from backend.security.paths import allowed_directory
from backend.security.rules import RULES, RULESET_VERSION


def analysis_router(sessions: sessionmaker, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["Static analysis"])

    def finding_out(session: Session, finding: Finding) -> FindingOut:
        evidence = session.scalars(
            select(FindingEvidence)
            .where(FindingEvidence.finding_id == finding.id)
            .order_by(FindingEvidence.line)
        )
        return FindingOut.model_validate(finding).model_copy(
            update={"evidence": [EvidenceOut.model_validate(item) for item in evidence]}
        )

    @router.get("/rules")
    def rules() -> dict:
        return {"version": RULESET_VERSION, "rules": [rule.metadata() for rule in RULES.values()]}

    @router.get("/scans/{scan_id}/findings", response_model=FindingPage)
    def findings(
        scan_id: str,
        severity: Literal["critical", "high", "medium", "low"] | None = None,
        category: Literal["security", "quality", "performance", "reliability"] | None = None,
        status: FindingStatus | None = None,
        language: str | None = Query(default=None, max_length=64),
        q: str = Query(default="", max_length=255),
        cwe: str | None = Query(default=None, max_length=32),
        owasp: str | None = Query(default=None, max_length=32),
        min_confidence: float = Query(default=0, ge=0, le=1),
        sort: Literal["risk", "severity", "confidence", "file", "detected_at"] = "risk",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=200),
    ) -> FindingPage:
        with sessions() as session:
            if session.get(Scan, scan_id) is None:
                raise HTTPException(404, "Scan not found.")
            filters = [Finding.scan_id == scan_id, Finding.confidence >= min_confidence]
            for column, value in (
                (Finding.severity, severity),
                (Finding.category, category),
                (Finding.status, status),
                (Finding.language, language),
                (Finding.cwe, cwe),
                (Finding.owasp, owasp),
            ):
                if value:
                    filters.append(column == value)
            if q:
                filters.append(
                    Finding.file.icontains(q, autoescape=True) | Finding.title.icontains(q, autoescape=True)
                )
            order = {
                "risk": Finding.risk.desc(),
                "confidence": Finding.confidence.desc(),
                "file": Finding.file.asc(),
                "severity": case({"critical": 0, "high": 1, "medium": 2, "low": 3}, value=Finding.severity),
                "detected_at": Finding.detected_at.desc(),
            }[sort]
            total = session.scalar(select(func.count()).select_from(Finding).where(*filters)) or 0
            rows = session.scalars(
                select(Finding)
                .where(*filters)
                .order_by(order, Finding.file, Finding.line, Finding.id)
                .offset(offset)
                .limit(limit)
            )
            return FindingPage(
                items=[finding_out(session, finding) for finding in rows],
                total=total,
                offset=offset,
                limit=limit,
            )

    @router.get("/findings/{finding_id}", response_model=FindingOut)
    def get_finding(finding_id: str) -> FindingOut:
        with sessions() as session:
            finding = session.get(Finding, finding_id)
            if finding is None:
                raise HTTPException(404, "Finding not found.")
            return finding_out(session, finding)

    @router.post("/findings/{finding_id}/status", response_model=FindingOut)
    def update_status(finding_id: str, payload: FindingStatusUpdate) -> FindingOut:
        with sessions.begin() as session:
            finding = session.get(Finding, finding_id)
            if finding is None:
                raise HTTPException(404, "Finding not found.")
            finding.status, finding.updated_at = payload.status, utcnow()
            return finding_out(session, finding)

    @router.get("/scans/{scan_id}/entities")
    def entities(
        scan_id: str,
        path: str | None = Query(default=None, max_length=2048),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=200, ge=1, le=500),
    ) -> dict:
        with sessions() as session:
            if session.get(Scan, scan_id) is None:
                raise HTTPException(404, "Scan not found.")
            filters = [CodeEntity.scan_id == scan_id]
            if path:
                filters.append(CodeEntity.file == path)
            count = session.scalar(select(func.count()).select_from(CodeEntity).where(*filters)) or 0
            items = session.scalars(
                select(CodeEntity)
                .where(*filters)
                .order_by(CodeEntity.file, CodeEntity.start_line, CodeEntity.id)
                .offset(offset)
                .limit(limit)
            )
            return {
                "items": [EntityOut.model_validate(item) for item in items],
                "total": count,
                "offset": offset,
                "limit": limit,
            }

    @router.get("/scans/{scan_id}/source")
    def source(
        scan_id: str,
        path: str = Query(min_length=1, max_length=2048),
        line: int = Query(default=1, ge=1),
        context: int = Query(default=12, ge=0, le=50),
    ) -> dict:
        with sessions() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise HTTPException(404, "Scan not found.")
            file = session.scalar(
                select(IndexedFile).where(IndexedFile.scan_id == scan_id, IndexedFile.path == path)
            )
            if file is None:
                raise HTTPException(404, "File is not part of this scan.")
            repo = session.get(Repository, scan.repository_id)
            root = allowed_directory(repo.path, settings.roots())
            try:
                content = read_indexed_source(root, file.path, file.sha256)
            except (OSError, ValueError, UnicodeError):
                raise HTTPException(
                    409,
                    "This file changed, became inaccessible, or became a filesystem link since the scan. Rescan before inspecting source.",
                ) from None
            lines = content.splitlines()
            if line > max(1, len(lines)):
                raise HTTPException(422, "Line is outside this file.")
            # Findings persist structural descriptions only. Hide detected secret
            # assignments in the source excerpt too, including multiline literals.
            secrets = session.scalars(
                select(Finding).where(
                    Finding.scan_id == scan_id, Finding.file == path, Finding.rule_id == "SEC-001"
                )
            )
            redacted = {number for finding in secrets for number in range(finding.line, finding.end_line + 1)}
            start, end = max(1, line - context), min(len(lines), line + context)
            return {
                "path": file.path,
                "language": file.language,
                "sha256": file.sha256,
                "verified": True,
                "start_line": start,
                "end_line": end,
                "total_lines": len(lines),
                "lines": [
                    {
                        "number": number,
                        "text": "[hardcoded secret assignment redacted]"
                        if number in redacted
                        else lines[number - 1][:4000],
                        "redacted": number in redacted,
                        "truncated": len(lines[number - 1]) > 4000,
                    }
                    for number in range(start, end + 1)
                ],
            }

    return router
