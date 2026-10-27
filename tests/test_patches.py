import io
import subprocess
import time
from pathlib import Path

import pytest
from test_api import api, scan_repository, workspace  # noqa: F401

from backend.config import Settings
from backend.database import Patch
from backend.patches.diff import apply_diff, canonical_diff, validate_tests
from backend.patches.provider import PatchProvider, Proposal
from backend.patches.sandbox import DockerSandbox

BEFORE = "import random\n\ndef token():\n    return random.randint(1, 9)\n"
AFTER = "import secrets\n\ndef token():\n    return secrets.randbelow(9) + 1\n"
TESTS = "from app import token\n\ndef test_token_range():\n    assert 1 <= token() <= 9\n"


def wait_job(client, job_id):
    for _ in range(150):
        result = client.get(f"/api/patches/{job_id}").json()
        if result["status"] not in {"generating", "validating"}:
            return result
        time.sleep(0.02)
    pytest.fail("Change job did not complete")


def proposal(client, repo, monkeypatch):
    (repo / "app.py").write_text(BEFORE, encoding="utf-8", newline="")
    scan = scan_repository(client, repo)
    finding = next(
        f for f in client.get(f"/api/scans/{scan['id']}/findings").json()["items"] if f["file"] == "app.py"
    )
    service = client.app.state.patches
    monkeypatch.setattr(service.provider, "models", lambda: [{"name": "local-test", "digest": "stable"}])
    monkeypatch.setattr(
        service.provider,
        "generate",
        lambda *_: Proposal(
            diff=canonical_diff(BEFORE, AFTER, "app.py"),
            tests=TESTS,
            explanation="Use a cryptographic generator.",
            risks=["Range behavior needs review."],
        ),
    )
    target = {"finding_id": finding["id"], "kind": "fix"}
    context = client.post("/api/patches/preview", json=target)
    assert context.status_code == 200
    generated = client.post(
        "/api/patches", json={**target, "model": "local-test", "context_hash": context.json()["context_hash"]}
    )
    assert generated.status_code == 202, generated.text
    job = wait_job(client, generated.json()["id"])
    assert job["status"] == "ready", job
    assert "original" not in job and "replacement" not in job
    assert (repo / "app.py").read_text() == BEFORE
    return job, service


def test_strict_diff():
    patch = canonical_diff(BEFORE, AFTER, "app.py")
    assert apply_diff(BEFORE, patch, "app.py") == AFTER
    for invalid in [
        patch.replace("a/app.py", "a/../app.py"),
        patch.replace("import random", "import os"),
        patch.replace("-1,4", "-1,8"),
        patch + "--- a/other.py\n",
        patch.replace("+import secrets", "+def broken("),
    ]:
        with pytest.raises((ValueError, SyntaxError)):
            apply_diff(BEFORE, invalid, "app.py")
    with pytest.raises(ValueError):
        validate_tests("def test_empty():\n    pass\n")
    with pytest.raises(ValueError):
        validate_tests("def test_fake():\n    assert True\n", "app")
    with pytest.raises(ValueError):
        validate_tests("from app import token\n\ndef test_other():\n    assert True\n", "app", "token")


def test_patch_provider_uses_compatible_json_mode(monkeypatch):
    provider = PatchProvider(Settings(_env_file=None))
    response = Proposal(
        diff="",
        tests="from app import hello\n\ndef test_hello():\n    assert hello() == 'hello'\n",
        explanation="Exercise the selected function.",
        risks=["Only the supplied context was available."],
    )

    def request(route, payload=None, timeout=5):
        if route == "/api/show":
            return {"details": {"format": "gguf"}}
        assert route == "/api/chat"
        assert payload["format"]["type"] == "object" and payload["stream"] is False
        assert payload["format"]["required"] == ["diff", "tests", "explanation", "risks"]
        assert payload["options"]["num_ctx"] == 4096
        return {"done": True, "message": {"content": response.model_dump_json()}}

    monkeypatch.setattr(provider, "request", request)
    assert provider.generate("local", {"kind": "fix"}) == response


def test_patch_provider_test_only_uses_python_source(monkeypatch):
    provider = PatchProvider(Settings(_env_file=None))
    source = "from app import hello\n\ndef test_hello():\n    assert hello() == 'hello'\n"

    def request(route, payload=None, timeout=5):
        if route == "/api/show":
            return {"details": {"format": "gguf"}}
        assert route == "/api/chat" and "format" not in payload
        assert payload["options"]["num_predict"] == 700
        return {
            "done": True,
            "done_reason": "length",
            "message": {"content": f"```python\n{source}```"},
        }

    monkeypatch.setattr(provider, "request", request)
    proposal = provider.generate("local", {"kind": "tests"})
    assert proposal.diff == "" and proposal.tests == source


def test_review_validation_apply_rollback(api, monkeypatch):  # noqa: F811
    client, repo = api
    job, service = proposal(client, repo, monkeypatch)
    approval = {"review_hash": job["review_hash"], "approved": True}
    url = f"/api/patches/{job['id']}"
    assert client.post(url + "/apply", json=approval).status_code == 409
    assert client.post(url + "/apply", json={"review_hash": job["review_hash"]}).status_code == 422
    monkeypatch.setattr(service.sandbox, "availability", lambda: {"available": True})

    def staged(repository, generated):
        assert (repository / "app.py").read_text() == AFTER
        assert (generated / "sentinel_generated_test.py").read_text() == TESTS
        assert (repo / "app.py").read_text() == BEFORE
        assert not (repository / "package.json").exists()
        return {"passed": True, "exit_code": 0, "reported_counts": {"passed": 1}, "coverage_delta": None}

    monkeypatch.setattr(service.sandbox, "run", staged)
    assert client.post(url + "/validate", json={**approval, "review_hash": "0" * 64}).status_code == 409
    assert client.post(url + "/validate", json=approval).status_code == 202
    assert wait_job(client, job["id"])["status"] == "validated"
    assert client.post(url + "/apply", json=approval).json()["status"] == "applied"
    assert (repo / "app.py").read_text() == AFTER
    (repo / "app.py").write_text(AFTER + "# user edit\n")
    assert client.post(url + "/rollback", json=approval).status_code == 409
    (repo / "app.py").write_text(AFTER, newline="")
    assert client.post(url + "/rollback", json=approval).json()["status"] == "rolled_back"
    assert (repo / "app.py").read_text() == BEFORE


def test_failed_validation_and_stale_snapshot_never_apply(api, monkeypatch):  # noqa: F811
    client, repo = api
    job, service = proposal(client, repo, monkeypatch)
    approval = {"review_hash": job["review_hash"], "approved": True}
    url = f"/api/patches/{job['id']}"
    monkeypatch.setattr(service.sandbox, "availability", lambda: {"available": False, "error": "Unavailable"})
    assert client.post(url + "/validate", json=approval).status_code == 503
    assert client.get(url).json()["status"] == "ready"
    monkeypatch.setattr(service.sandbox, "availability", lambda: {"available": True})
    monkeypatch.setattr(service.sandbox, "run", lambda *_: {"passed": False, "exit_code": 1})
    client.post(url + "/validate", json=approval)
    assert wait_job(client, job["id"])["status"] == "validation_failed"
    assert (repo / "app.py").read_text() == BEFORE
    assert client.post(url + "/apply", json=approval).status_code == 409
    monkeypatch.setattr(service.sandbox, "run", lambda *_: {"passed": True, "exit_code": 0})
    client.post(url + "/validate", json=approval)
    assert wait_job(client, job["id"])["status"] == "validated"
    (repo / "skip.py").write_text("# changed dependency\n")
    assert client.post(url + "/apply", json=approval).status_code == 409
    assert (repo / "app.py").read_text() == BEFORE


def test_secret_context_refusal_and_test_only_generation(api, monkeypatch):  # noqa: F811
    client, repo = api
    (repo / "app.py").write_text("def hello():\n    return 'hello'\n", encoding="utf-8", newline="")
    scan = scan_repository(client, repo)
    finding = client.get(f"/api/scans/{scan['id']}/findings").json()["items"][0]
    assert client.post("/api/patches/preview", json={"finding_id": finding["id"]}).status_code == 409
    entity = next(
        e for e in client.get(f"/api/scans/{scan['id']}/entities").json()["items"] if e["name"] == "hello"
    )
    target = {"entity_id": entity["id"], "kind": "tests"}
    response = client.post("/api/patches/preview", json=target)
    assert response.status_code == 200, response.text
    context = response.json()
    service = client.app.state.patches
    monkeypatch.setattr(service.provider, "models", lambda: [{"name": "local", "digest": "stable"}])
    monkeypatch.setattr(
        service.provider,
        "generate",
        lambda *_: Proposal(
            diff="",
            tests="from app import hello\ndef test_hello():\n    assert hello() == 'hello'\n",
            explanation="Check greeting.",
            risks=["Only a simple example."],
        ),
    )
    response = client.post(
        "/api/patches", json={**target, "model": "local", "context_hash": context["context_hash"]}
    )
    assert wait_job(client, response.json()["id"])["status"] == "ready"
    with client.app.state.sessions.begin() as session:
        job = session.get(Patch, response.json()["id"])
        job.status = "generating"
    service.recover()
    assert client.get(f"/api/patches/{job.id}").json()["status"] == "failed"


def test_interrupted_apply_recovery(api, monkeypatch):  # noqa: F811
    client, repo = api
    job, service = proposal(client, repo, monkeypatch)
    (repo / "app.py").write_text(AFTER, newline="")
    with client.app.state.sessions.begin() as session:
        session.get(Patch, job["id"]).status = "applying"
    service.recover()
    assert client.get(f"/api/patches/{job['id']}").json()["status"] == "applied"


def test_sandbox_fails_closed_without_configuration():
    sandbox = DockerSandbox(Settings(_env_file=None, sandbox_image=""))
    assert not sandbox.availability()["available"]
    with pytest.raises(ValueError):
        sandbox.run(Path("."), Path("."))
    with pytest.raises(ValueError):
        Settings(_env_file=None, sandbox_image="python:latest")


def test_sandbox_fixed_command_and_cleanup(monkeypatch, tmp_path):
    sandbox = DockerSandbox(Settings(_env_file=None, sandbox_image="sha256:" + "a" * 64))
    monkeypatch.setattr(sandbox, "availability", lambda: {"available": True})
    monkeypatch.setattr(sandbox, "command", lambda: ["docker", "--host", "unix:///var/run/docker.sock"])
    calls = []

    class Process:
        def __init__(self, args, **kwargs):
            calls.append(args)
            assert "shell" not in kwargs
            self.stdout = io.BytesIO(b"2 passed in 0.01s\n")

        def wait(self, timeout):
            return 0

        def poll(self):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", Process)
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args))
    result = sandbox.run(tmp_path, tmp_path)
    assert result["passed"] and result["reported_counts"]["passed"] == 2
    for flag in (
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pull=never",
        "--user=65534:65534",
        "--memory=512m",
        "--pids-limit=64",
    ):
        assert flag in calls[0]
    assert calls[-1][-3:-1] == ["rm", "--force"]

    class Timeout(Process):
        def wait(self, timeout):
            if timeout != 5:
                raise subprocess.TimeoutExpired("docker", timeout)
            return -1

    monkeypatch.setattr(subprocess, "Popen", Timeout)
    with pytest.raises(ValueError, match="timed out"):
        sandbox.run(tmp_path, tmp_path)
    assert calls[-1][-3:-1] == ["rm", "--force"]
