"""SENTINEL: deterministic repository analysis over a local API."""
import os
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.migration import MigrationContext
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api.analysis_routes import analysis_router
from backend.api.graph_routes import graph_router
from backend.api.llm_routes import llm_router
from backend.api.patch_routes import patch_router
from backend.api.schemas import FileOut, FilePage, RepositoryCreate, RepositoryOut, ScanOut
from backend.config import Settings
from backend.database import IndexedFile, Repository, Scan, make_engine
from backend.embeddings.service import EmbeddingService
from backend.llm.ollama import OllamaProvider
from backend.llm.service import ReasoningService
from backend.logging_config import configure_logging
from backend.patches.service import PatchService
from backend.security.paths import allowed_directory
from backend.workers.scanner import ScanWorker

SCHEMA_REVISION = "0005_reviewed_patches"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    sessions = sessionmaker(engine, expire_on_commit=False)
    worker = ScanWorker(sessions, settings)
    reasoning = ReasoningService(sessions, OllamaProvider(settings))
    embeddings = EmbeddingService(sessions, settings)
    patches = PatchService(sessions, settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configure_logging()
        with engine.connect() as connection:
            if MigrationContext.configure(connection).get_current_revision() != SCHEMA_REVISION:
                raise RuntimeError("Database schema is not current. Run: python -m alembic upgrade head")
        worker.recover_interrupted()
        reasoning.recover()
        embeddings.recover()
        patches.recover()
        yield
        worker.close()
        reasoning.close()
        embeddings.close()
        patches.close()
        engine.dispose()

    app = FastAPI(title="SENTINEL Local API", version="0.5.0", description="Local repository indexing and deterministic AST analysis. Optional local Ollama reasoning; no cloud inference. Explicit reviewed changes with Docker-only validation.", lifespan=lifespan)
    app.include_router(analysis_router(sessions, settings))
    app.include_router(llm_router(sessions, settings, reasoning))
    app.state.reasoning = reasoning
    app.state.embeddings = embeddings
    app.state.patches = patches
    app.include_router(patch_router(sessions, settings, patches))
    app.include_router(graph_router(sessions, settings, embeddings))
    app.state.engine, app.state.sessions, app.state.worker = engine, sessions, worker
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "backend", "testserver"])
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"], allow_credentials=False)

    @app.middleware("http")
    async def local_request_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        # Same-origin Swagger requests are safe; TrustedHostMiddleware still
        # rejects DNS-rebinding hosts before any endpoint is reached.
        same_origin = str(request.base_url).rstrip("/")
        if origin and origin not in settings.cors_origins and origin != same_origin:
            return JSONResponse({"detail": "This browser origin is not allowed."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site requests to the local service are blocked."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def repository_out(session: Session, repo: Repository) -> RepositoryOut:
        latest = session.scalar(select(Scan).where(Scan.repository_id == repo.id).order_by(Scan.created_at.desc()).limit(1))
        return RepositoryOut.model_validate(repo).model_copy(update={"latest_scan": ScanOut.model_validate(latest) if latest else None})

    @app.get("/api/health")
    def health():
        with sessions() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok", "version": "0.5.0", "database": "connected"}

    @app.get("/api/settings")
    def local_settings():
        return {"allowed_roots": [str(p) for p in settings.roots()], "demo_path": settings.demo_path,
                "telemetry": False, "source_upload": False, "ai_enabled": True, "phase": 5}

    @app.get("/api/browse")
    def browse(path: str | None = Query(default=None, max_length=2048)):
        roots = settings.roots()
        if not roots:
            raise HTTPException(403, "No allowed repository roots are configured.")
        directory = allowed_directory(path or str(roots[0]), roots)
        children = []
        truncated = False
        try:
            # Bound enumeration before sorting: directories with millions of entries
            # must not materialize their entire listing in the API process.
            with os.scandir(directory) as entries:
                for examined, entry in enumerate(entries):
                    if examined >= 10_000 or len(children) >= 500:
                        truncated = True
                        break
                    if entry.name.startswith(".") or entry.name in {"node_modules", "vendor", "dist", "build", "target"}:
                        continue
                    child = Path(entry.path)
                    if entry.is_symlink() or (hasattr(child, "is_junction") and child.is_junction()):
                        continue
                    if entry.is_dir(follow_symlinks=False) and any(child.resolve().is_relative_to(root) for root in roots):
                        children.append({"name": child.name, "path": str(child)})
            children.sort(key=lambda item: item["name"].lower())
        except OSError:
            raise HTTPException(403, "This folder cannot be read.") from None
        parent = str(directory.parent) if directory.parent != directory and any(directory.parent.is_relative_to(root) for root in roots) else None
        return {"path": str(directory), "parent": parent, "directories": children, "roots": [str(root) for root in roots], "truncated": truncated}

    @app.get("/api/repositories", response_model=list[RepositoryOut])
    def repositories():
        with sessions() as session:
            return [repository_out(session, repo) for repo in session.scalars(select(Repository).order_by(Repository.created_at.desc()))]

    @app.post("/api/repositories", response_model=RepositoryOut, status_code=201)
    def add_repository(payload: RepositoryCreate):
        if any(len(pattern) > 500 or "\x00" in pattern for pattern in payload.ignore_patterns):
            raise HTTPException(422, "Ignore patterns must be at most 500 characters and contain no null bytes.")
        root = allowed_directory(payload.path, settings.roots())
        # Serialize mutations in this single-process local deployment, including duplicate registration.
        with worker.lock, sessions.begin() as session:
            repo = session.scalar(select(Repository).where(Repository.path == str(root)))
            if repo is None:
                repo = Repository(name=root.name or str(root), path=str(root), ignore_patterns=payload.ignore_patterns)
                session.add(repo)
                session.flush()
            elif payload.ignore_patterns != repo.ignore_patterns:
                active = session.scalar(select(Scan.id).where(Scan.repository_id == repo.id, Scan.status.in_(["queued", "running"])))
                if active:
                    raise HTTPException(409, "Wait for this repository's active scan before changing ignore patterns.")
                repo.ignore_patterns = payload.ignore_patterns
            return repository_out(session, repo)

    @app.post("/api/repositories/{repository_id}/scans", response_model=ScanOut, status_code=202)
    def start_scan(repository_id: str):
        with worker.lock:
            with sessions.begin() as session:
                repo = session.get(Repository, repository_id)
                if repo is None:
                    raise HTTPException(404, "Repository not found.")
                allowed_directory(repo.path, settings.roots())
                active = session.scalar(select(Scan).where(Scan.repository_id == repository_id, Scan.status.in_(["queued", "running"])))
                if active:
                    return ScanOut.model_validate(active)
                scan = Scan(repository_id=repository_id)
                session.add(scan)
                session.flush()
                result = ScanOut.model_validate(scan)
            if not worker.submit(result.id):
                with sessions.begin() as session:
                    stale = session.get(Scan, result.id)
                    if stale:
                        session.delete(stale)
                raise HTTPException(429, "The local scan queue is full. Wait for an active scan to complete.")
            return result

    @app.get("/api/repositories/{repository_id}/scans", response_model=list[ScanOut])
    def scans(repository_id: str):
        with sessions() as session:
            if session.get(Repository, repository_id) is None:
                raise HTTPException(404, "Repository not found.")
            return [ScanOut.model_validate(scan) for scan in session.scalars(select(Scan).where(Scan.repository_id == repository_id).order_by(Scan.created_at.desc()).limit(100))]

    @app.get("/api/scans/{scan_id}", response_model=ScanOut)
    def get_scan(scan_id: str):
        with sessions() as session:
            scan = session.get(Scan, scan_id)
            if scan is None:
                raise HTTPException(404, "Scan not found.")
            return ScanOut.model_validate(scan)

    @app.get("/api/scans/{scan_id}/files", response_model=FilePage)
    def files(scan_id: str, q: str = Query(default="", max_length=255), language: str | None = Query(default=None, max_length=64), offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
        with sessions() as session:
            if session.get(Scan, scan_id) is None:
                raise HTTPException(404, "Scan not found.")
            filters = [IndexedFile.scan_id == scan_id]
            if q:
                filters.append(IndexedFile.path.icontains(q, autoescape=True))
            if language:
                filters.append(IndexedFile.language == language)
            total = session.scalar(select(func.count()).select_from(IndexedFile).where(*filters)) or 0
            items = session.scalars(select(IndexedFile).where(*filters).order_by(IndexedFile.path).offset(offset).limit(limit))
            return FilePage(items=[FileOut.model_validate(item) for item in items], total=total, offset=offset, limit=limit)

    return app


app = create_app()

