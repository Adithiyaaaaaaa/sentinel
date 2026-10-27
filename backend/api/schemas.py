from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class RepositoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=2048)
    ignore_patterns: list[str] = Field(default_factory=list, max_length=100)


class ScanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    repository_id: str
    status: Literal["queued", "running", "completed", "failed"]
    progress: int
    stage: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    total_files: int
    total_lines: int
    total_bytes: int
    skipped_files: int
    languages: dict[str, dict[str, int]]
    frameworks: list[str]
    package_managers: list[str]
    test_frameworks: list[str]
    has_docker: bool
    has_ci: bool
    branch: str | None
    commit: str | None
    dependency_count: int
    warnings: list[str]
    error: str | None
    analysis_summary: dict

    @field_serializer("created_at", "started_at", "completed_at")
    def utc_dates(self, value: datetime | None) -> str | None:
        return value.replace(tzinfo=value.tzinfo or UTC).isoformat() if value else None


class RepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    path: str
    ignore_patterns: list[str]
    created_at: datetime
    latest_scan: ScanOut | None = None


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    path: str
    language: str
    lines: int
    size_bytes: int
    sha256: str


class FilePage(BaseModel):
    items: list[FileOut]
    total: int
    offset: int
    limit: int


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    line: int
    end_line: int
    kind: str
    description: str


FindingStatus = Literal["open", "confirmed", "false_positive", "fixed", "ignored"]


class FindingStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: FindingStatus


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    scan_id: str
    rule_id: str
    fingerprint: str
    file: str
    language: str
    line: int
    end_line: int
    symbol: str
    title: str
    severity: str
    category: str
    cwe: str | None
    owasp: str | None
    confidence: float
    verdict: str
    status: FindingStatus
    risk: int
    risk_basis: dict
    explanation: str
    impact: str
    exploitability: str
    recommendation: str
    detected_at: datetime
    evidence: list[EvidenceOut] = Field(default_factory=list)


class FindingPage(BaseModel):
    items: list[FindingOut]
    total: int
    offset: int
    limit: int


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    file: str
    language: str
    kind: str
    name: str
    start_line: int
    end_line: int
    parent: str | None
    dependencies: list[str]
    callers: list[str]
    callees: list[str]
    complexity: int
    features: list[str]

