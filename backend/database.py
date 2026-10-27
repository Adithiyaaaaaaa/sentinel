"""SQLAlchemy persistence shared by the API and background index workers."""
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(2048), unique=True)
    ignore_patterns: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(255), default="Waiting for index worker")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    total_lines: Mapped[int] = mapped_column(Integer, default=0)
    total_bytes: Mapped[int] = mapped_column(Integer, default=0)
    skipped_files: Mapped[int] = mapped_column(Integer, default=0)
    languages: Mapped[dict] = mapped_column(JSON, default=dict)
    frameworks: Mapped[list] = mapped_column(JSON, default=list)
    package_managers: Mapped[list] = mapped_column(JSON, default=list)
    test_frameworks: Mapped[list] = mapped_column(JSON, default=list)
    has_docker: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ci: Mapped[bool] = mapped_column(Boolean, default=False)
    branch: Mapped[str | None] = mapped_column(String(255))
    commit: Mapped[str | None] = mapped_column(String(64))
    dependency_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(1024))
    analysis_summary: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    graph_data: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    __table_args__ = (Index("ix_scans_repo_created", "repository_id", "created_at"),)


class IndexedFile(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(64), index=True)
    lines: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("scan_id", "path", name="uq_files_scan_path"),)


class Dependency(Base):
    __tablename__ = "dependencies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(1024))
    ecosystem: Mapped[str] = mapped_column(String(64))


class CodeEntity(Base):
    __tablename__ = "code_entities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    file: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    parent: Mapped[str | None] = mapped_column(String(64))
    dependencies: Mapped[list] = mapped_column(JSON)
    callers: Mapped[list] = mapped_column(JSON)
    callees: Mapped[list] = mapped_column(JSON)
    complexity: Mapped[int] = mapped_column(Integer)
    features: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("scan_id", "key", name="uq_entity_scan_key"),)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(64))
    file: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(64))
    line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    symbol: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    severity: Mapped[str] = mapped_column(String(16), index=True)
    category: Mapped[str] = mapped_column(String(32))
    cwe: Mapped[str | None] = mapped_column(String(32))
    owasp: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    verdict: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="open")
    risk: Mapped[int] = mapped_column(Integer)
    risk_basis: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(Text)
    exploitability: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("scan_id", "fingerprint", name="uq_finding_scan_fingerprint"),)


class EmbeddingIndex(Base):
    __tablename__ = "embedding_indexes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    model_digest: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total: Mapped[int] = mapped_column(Integer, default=0)
    indexed: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    dimensions: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(512))


class EntityEmbedding(Base):
    __tablename__ = "entity_embeddings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    index_id: Mapped[str] = mapped_column(ForeignKey("embedding_indexes.id", ondelete="CASCADE"), index=True)
    entity_key: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("index_id", "entity_key", name="uq_embedding_entity"),)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(255))
    model_digest: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="running")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    context_hash: Mapped[str] = mapped_column(String(64))
    context_summary: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(512))


class Patch(Base):
    __tablename__ = "patches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[str | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("code_entities.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(2048))
    model: Mapped[str] = mapped_column(String(255))
    model_digest: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="generating")
    source_hash: Mapped[str] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    review_hash: Mapped[str | None] = mapped_column(String(64))
    diff: Mapped[str | None] = mapped_column(Text)
    tests: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    original: Mapped[str | None] = mapped_column(Text)
    replacement: Mapped[str | None] = mapped_column(Text)
    validation_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestRun(Base):
    __tablename__ = "test_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    patch_id: Mapped[str] = mapped_column(ForeignKey("patches.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)


def make_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    sqlite = url.get_backend_name() == "sqlite"
    if sqlite and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {}, pool_pre_ping=True)
    if sqlite:
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine

