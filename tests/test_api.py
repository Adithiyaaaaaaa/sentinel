"""Exercise real HTTP routes, migrations, background indexing, and persistence."""
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.api.main import create_app
from backend.config import PROJECT_ROOT, Settings
from backend.database import Repository, Scan, make_engine


def migration_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config


@pytest.fixture
def workspace(tmp_path: Path):
    root = tmp_path / "repositories"
    root.mkdir()
    repo = root / "payments"
    repo.mkdir()
    (repo / "app.py").write_text("import os\n\ndef hello():\n    return 'hello'\n", encoding="utf-8")
    (repo / "package.json").write_text('{"dependencies":{"react":"^19.0.0"}}', encoding="utf-8")
    (repo / "skip.py").write_text("password = 'not-a-real-key'\n", encoding="utf-8")
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    command.upgrade(migration_config(database_url), "head")
    settings = Settings(_env_file=None, database_url=database_url, allowed_roots=[str(root)], demo_path=str(repo))
    return settings, repo


@pytest.fixture
def api(workspace):
    settings, repo = workspace
    with TestClient(create_app(settings)) as client:
        yield client, repo


def scan_repository(client: TestClient, path: Path, ignore_patterns: list[str] | None = None) -> dict:
    response = client.post("/api/repositories", json={"path": str(path), "ignore_patterns": ignore_patterns or []})
    assert response.status_code == 201, response.text
    repo_id = response.json()["id"]
    response = client.post(f"/api/repositories/{repo_id}/scans")
    assert response.status_code == 202, response.text
    scan_id = response.json()["id"]
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/scans/{scan_id}")
        assert response.status_code == 200
        scan = response.json()
        if scan["status"] in {"completed", "failed"}:
            assert scan["status"] == "completed", scan
            return scan
        time.sleep(0.02)
    pytest.fail("Background indexing timed out")


def test_real_scan_results_filtering_and_history(api):
    client, repo = api
    first = scan_repository(client, repo, ["skip.py"])
    assert first["total_files"] == 2
    assert first["total_lines"] == 5
    assert first["languages"]["Python"] == {"files": 1, "lines": 4}
    assert first["dependency_count"] == 1
    assert first["frameworks"] == ["React"]
    assert first["progress"] == 100
    assert first["duration_ms"] >= 0
    assert first["started_at"].endswith("+00:00")
    files = client.get(f"/api/scans/{first['id']}/files", params={"language": "Python", "q": "app"}).json()
    assert files["total"] == 1
    assert files["items"][0]["path"] == "app.py"
    assert len(files["items"][0]["sha256"]) == 64
    assert "content" not in files["items"][0]
    literal_filter = client.get(f"/api/scans/{first['id']}/files", params={"q": "%"}).json()
    assert literal_filter["total"] == 0
    page = client.get(f"/api/scans/{first['id']}/files", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    (repo / "new.ts").write_text("export const version = 1;\n", encoding="utf-8")
    second = scan_repository(client, repo, ["skip.py"])
    assert second["total_files"] == 3
    history = client.get(f"/api/repositories/{first['repository_id']}/scans").json()
    assert [scan["id"] for scan in history] == [second["id"], first["id"]]
    assert client.get(f"/api/scans/{first['id']}").json()["total_files"] == 2
    repos = client.get("/api/repositories").json()
    assert len(repos) == 1 and repos[0]["latest_scan"]["id"] == second["id"]


def test_folder_boundary_and_browser_boundary(api, tmp_path):
    client, repo = api
    assert client.post("/api/repositories", json={"path": str(tmp_path)}).status_code == 403
    assert client.get("/api/browse", params={"path": str(tmp_path)}).status_code == 403
    assert client.post("/api/repositories", json={"path": "relative/path"}).status_code == 400
    assert client.post("/api/repositories", json={"path": str(repo / 'app.py')}).status_code == 400
    assert client.post("/api/repositories", json={"path": str(repo / 'missing')}).status_code == 400
    assert client.get("/api/settings", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.post("/api/repositories", json={"path": str(repo)}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
    assert client.get("/api/health", headers={"Origin": "http://localhost:3000"}).status_code == 200
    assert client.post("/api/repositories", json={"path": str(repo)}, headers={"Origin": "http://testserver"}).status_code == 201
    browse = client.get("/api/browse").json()
    assert browse["parent"] is None
    assert browse["directories"] == [{"name": "payments", "path": str(repo)}]
    assert client.get("/api/browse", params={"path": str(repo)}).json()["parent"] == str(repo.parent)


def test_validation_and_openapi(api):
    client, repo = api
    assert client.get("/api/health").json() == {"status": "ok", "version": "0.5.0", "database": "connected"}
    privacy = client.get("/api/settings").json()
    assert not privacy["telemetry"] and not privacy["source_upload"] and privacy["ai_enabled"]
    assert client.get("/api/scans/missing").status_code == 404
    assert client.get("/api/scans/missing/files").status_code == 404
    assert client.post("/api/repositories/missing/scans").status_code == 404
    assert client.get("/api/repositories/missing/scans").status_code == 404
    assert client.get("/api/scans/missing/files?limit=9999").status_code == 422
    assert client.post("/api/repositories", json={"path": str(repo), "ignore_patterns": ["a" * 501]}).status_code == 422
    assert client.post("/api/repositories", json={"path": str(repo), "execute": True}).status_code == 422
    schema = client.get("/openapi.json").json()
    assert "/api/repositories/{repository_id}/scans" in schema["paths"]


def test_index_survives_restart(workspace):
    settings, repo = workspace
    with TestClient(create_app(settings)) as client:
        result = scan_repository(client, repo)
    with TestClient(create_app(settings)) as restarted:
        restored = restarted.get(f"/api/scans/{result['id']}").json()
        assert restored["status"] == "completed"
        assert restored["total_files"] == 3
        assert restarted.get(f"/api/scans/{result['id']}/files").json()["total"] == 3


def test_interrupted_scan_is_recoverable(workspace):
    settings, repo = workspace
    app = create_app(settings)
    with app.state.sessions.begin() as session:
        saved_repo = Repository(name="payments", path=str(repo))
        session.add(saved_repo)
        session.flush()
        interrupted = Scan(repository_id=saved_repo.id, status="running")
        session.add(interrupted)
        session.flush()
        scan_id = interrupted.id
    with TestClient(app) as client:
        failed = client.get(f"/api/scans/{scan_id}").json()
        assert failed["status"] == "failed"
        assert "stopped" in failed["error"]
        assert scan_repository(client, repo)["status"] == "completed"


def test_migration_roundtrip_and_model_parity(workspace):
    settings, _ = workspace
    config = migration_config(settings.database_url)
    command.check(config)
    engine = make_engine(settings.database_url)
    assert set(inspect(engine).get_table_names()) == {"alembic_version", "repositories", "scans", "files", "dependencies", "code_entities", "findings", "finding_evidence", "ai_analyses", "embedding_indexes", "entity_embeddings", "patches", "test_runs"}
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def test_service_requires_migrations(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'empty.db').as_posix()}", allowed_roots=[str(tmp_path)])
    with pytest.raises(RuntimeError, match="alembic upgrade head"), TestClient(create_app(settings)):
        pass


def test_duplicate_scan_is_idempotent_and_full_queue_rolls_back(api, monkeypatch):
    client, repo = api
    repository = client.post("/api/repositories", json={"path": str(repo)}).json()
    url = f"/api/repositories/{repository['id']}/scans"
    worker = client.app.state.worker
    monkeypatch.setattr(worker, "submit", lambda _id: False)
    assert client.post(url).status_code == 429
    assert client.get(url).json() == []
    monkeypatch.setattr(worker, "submit", lambda _id: True)
    first = client.post(url).json()
    second = client.post(url).json()
    assert first["id"] == second["id"]
    assert len(client.get(url).json()) == 1
    changed = client.post("/api/repositories", json={"path": str(repo), "ignore_patterns": ["*.py"]})
    assert changed.status_code == 409


def test_worker_failure_releases_queue_and_does_not_disclose_exception(api, monkeypatch):
    from backend.workers import scanner

    client, repo = api
    original = scanner.index_repository

    def fail(*_args):
        raise RuntimeError("PRIVATE_SOURCE_DO_NOT_DISCLOSE")

    monkeypatch.setattr(scanner, "index_repository", fail)
    repository = client.post("/api/repositories", json={"path": str(repo)}).json()
    scan = client.post(f"/api/repositories/{repository['id']}/scans").json()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/scans/{scan['id']}")
        if response.json()["status"] == "failed":
            break
        time.sleep(0.02)
    assert response.json()["status"] == "failed"
    assert "PRIVATE_SOURCE" not in response.text
    assert client.get(f"/api/scans/{scan['id']}/files").json()["items"] == []
    monkeypatch.setattr(scanner, "index_repository", original)
    assert scan_repository(client, repo)["status"] == "completed"


def test_large_folder_browse_is_bounded(api):
    client, repo = api
    for number in range(502):
        (repo / f"directory-{number:04d}").mkdir()
    result = client.get("/api/browse", params={"path": str(repo)}).json()
    assert result["truncated"] is True
    assert len(result["directories"]) == 500


def test_findings_evidence_filters_triage_and_source(api):
    client, repo = api
    (repo / "app.py").write_text(
        'def search(connection, name):\n    query = f"SELECT * FROM users WHERE name = {name}"\n    return connection.execute(query)\n',
        encoding="utf-8",
    )
    scan = scan_repository(client, repo)
    base = f"/api/scans/{scan['id']}"
    assert scan["analysis_summary"]["finding_count"] == 2
    result = client.get(base + "/findings").json()
    assert result["total"] == 2
    assert "not-a-real-key" not in str(result)
    sql = next(f for f in result["items"] if f["rule_id"] == "SEC-002")
    assert sql["line"] == 3 and sql["evidence"]
    assert sql["risk"] == round(sql["risk_basis"]["severity_weight"] * sql["confidence"])
    for params in ({"cwe": "CWE-89"}, {"q": "SQL"}, {"language": "Python", "min_confidence": .95}, {"limit": 1, "offset": 1}):
        assert len(client.get(base + "/findings", params=params).json()["items"]) == 1
    assert client.get(base + "/findings", params={"q": "%"}).json()["total"] == 0
    assert client.get(base + "/findings", params={"severity": "critical"}).json()["total"] == 0
    for sort in ("risk", "severity", "confidence", "file", "detected_at"):
        assert client.get(base + "/findings", params={"sort": sort}).status_code == 200
    url = f"/api/findings/{sql['id']}"
    assert client.post(url + "/status", json={"status": "false_positive"}).json()["status"] == "false_positive"
    assert client.get(url).json()["status"] == "false_positive"
    assert client.get(base + "/findings?status=false_positive").json()["total"] == 1
    assert client.post(url + "/status", json={"status": "invalid"}).status_code == 422
    assert client.post(url + "/status", json={"status": "fixed", "risk": 0}).status_code == 422
    excerpt = client.get(base + "/source", params={"path": "app.py", "line": 3}).json()
    assert excerpt["verified"] and excerpt["lines"][2]["number"] == 3
    redacted = client.get(base + "/source", params={"path": "skip.py"})
    assert "not-a-real-key" not in redacted.text
    assert redacted.json()["lines"][0]["redacted"]
    entities = client.get(base + "/entities?path=app.py").json()
    assert any(e["name"] == "search" and e["kind"] == "function" for e in entities["items"])
    assert client.get(base + "/source", params={"path": "../outside.py"}).status_code == 404
    assert client.get(base + "/source", params={"path": "app.py", "line": 999}).status_code == 422
    assert client.get(base + "/source", params={"path": "app.py", "context": 51}).status_code == 422
    (repo / "app.py").write_text("print('changed')\n", encoding="utf-8")
    assert client.get(base + "/source?path=app.py").status_code == 409
    assert client.get(url).json()["line"] == 3  # Immutable evidence survives source changes.
    (repo / "skip.py").unlink()
    assert client.get(base + "/source?path=skip.py").status_code == 409


def test_analysis_routes_validate_requests(api):
    client, _ = api
    assert len(client.get("/api/rules").json()["rules"]) == 15
    for route in ("findings", "entities", "source?path=app.py"):
        assert client.get(f"/api/scans/missing/{route}").status_code == 404
    assert client.get("/api/findings/missing").status_code == 404
    assert client.post("/api/findings/missing/status", json={"status": "ignored"}).status_code == 404
    for query in ("severity=urgent", "min_confidence=2", "sort=arbitrary", "limit=201", "status=other"):
        assert client.get(f"/api/scans/missing/findings?{query}").status_code == 422


def test_phase_one_migration_preserves_history(tmp_path):
    from sqlalchemy import text

    database_url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    config = migration_config(database_url)
    command.upgrade(config, "0001_repository_index")
    engine = make_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO repositories (id, name, path, ignore_patterns, created_at) VALUES ('repo', 'legacy', '/legacy', '[]', CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO scans (id, repository_id, status, created_at, progress, stage, total_files, total_lines, total_bytes, skipped_files, languages, frameworks, package_managers, test_frameworks, has_ci, has_docker, dependency_count, warnings) VALUES ('scan', 'repo', 'completed', CURRENT_TIMESTAMP, 100, 'Done', 12, 99, 1024, 0, '{}', '[]', '[]', '[]', 0, 0, 0, '[]')"))
    command.upgrade(config, "head")
    with engine.connect() as connection:
        row = connection.execute(text("SELECT total_files, analysis_summary FROM scans WHERE id='scan'")).one()
        assert row[0] == 12 and row[1] == "{}"
    engine.dispose()



