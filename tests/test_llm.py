import json
import time

import httpx
import pytest
from pydantic import ValidationError
from test_api import api, scan_repository, workspace  # noqa: F401 -- shared integration fixtures

from backend.config import Settings
from backend.llm.contracts import ProviderError, Reasoning
from backend.llm.ollama import OllamaProvider


def answer():
    return {
        "verdict": "possible",
        "severity": "high",
        "confidence": 0.8,
        "root_cause": "Literal assigned to secret-like name.",
        "impact": "Exposure if deployed.",
        "explanation": "The AST matches a credential pattern.",
        "code_path": "Module assignment.",
        "fix_strategy": "Use protected configuration.",
        "fix_risks": "Missing configuration may prevent startup.",
        "tests_required": ["Check missing-configuration behavior."],
        "uncertainty": ["May be a demonstration value."],
        "evidence_refs": ["E0"],
    }


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://localhost:11434",
        "http://127.0.0.1.evil",
        "http://127.0.0.1/api",
        "http://user:pass@127.0.0.1",
        "http://127.0.0.1?x=1",
    ],
)
def test_provider_is_loopback_only(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_url=url)


@pytest.mark.parametrize(
    "change",
    [{"confidence": 2}, {"verdict": "secure"}, {"uncertainty": []}, {"extra": "unsafe"}, {"root_cause": 123}],
)
def test_response_contract_rejects_invalid_outputs(change):
    with pytest.raises(ValidationError):
        Reasoning.model_validate(answer() | change)


def test_provider_filters_cloud_and_checks_citations(monkeypatch):
    provider = OllamaProvider(Settings(_env_file=None))
    local = {"name": "local:latest", "details": {"format": "gguf"}, "digest": "abc"}
    monkeypatch.setattr(
        provider,
        "request",
        lambda *args: {"models": [local, local | {"name": "remote-cloud"}, local | {"remote_host": "evil"}]},
    )
    assert [m["name"] for m in provider.models()] == ["local:latest"]
    payload = answer()

    def request(route, body=None, timeout=5):
        if route == "/api/show":
            return {"details": {"format": "gguf"}}
        assert body["stream"] is False and body["format"]["additionalProperties"] is False
        assert "tools" not in body
        return {"done": True, "message": {"content": json.dumps(payload)}}

    monkeypatch.setattr(provider, "request", request)
    assert provider.reason("local", {"evidence": [{"id": "E0"}]}).verdict == "possible"
    payload["evidence_refs"] = ["E99"]
    with pytest.raises(ProviderError, match="outside"):
        provider.reason("local", {"evidence": [{"id": "E0"}]})
    payload["evidence_refs"] = []
    with pytest.raises(ProviderError, match="without evidence"):
        provider.reason("local", {"evidence": [{"id": "E0"}]})


def test_provider_sanitizes_transport_failure(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("private provider response")

    monkeypatch.setattr(httpx.Client, "stream", fail)
    with pytest.raises(ProviderError, match="Cannot reach local Ollama") as error:
        OllamaProvider(Settings(_env_file=None)).models()
    assert "private" not in str(error.value)


def wait_job(client, job_id):
    for _ in range(150):
        job = client.get(f"/api/analyses/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    pytest.fail("Reasoning job did not finish")


def test_context_job_and_failure_are_persisted(api, monkeypatch):  # noqa: F811
    client, repo = api
    scan = scan_repository(client, repo)
    finding = client.get(f"/api/scans/{scan['id']}/findings").json()["items"][0]
    base = f"/api/findings/{finding['id']}"
    preview = client.get(base + "/context").json()
    assert "not-a-real-key" not in json.dumps(preview)
    assert "redacted" in json.dumps(preview)
    provider = client.app.state.reasoning.provider
    monkeypatch.setattr(provider, "models", lambda: [{"name": "test-local", "digest": "test-digest"}])
    seen = []

    def reason(model, context):
        seen.append(context)
        return Reasoning.model_validate(answer())

    monkeypatch.setattr(provider, "reason", reason)
    payload = {"model": "test-local", "context_hash": preview["context_hash"]}
    assert client.post(base + "/analyses", json=payload | {"context_hash": "0" * 64}).status_code == 409
    assert client.post(base + "/analyses", json=payload | {"model": "remote"}).status_code == 422
    response = client.post(base + "/analyses", json=payload)
    assert response.status_code == 202
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "completed" and job["response"]["verdict"] == "possible"
    assert job["model_digest"] == "test-digest" and seen
    assert "package" not in job and "source" not in job["context_summary"]
    assert client.get(f"/api/findings/{finding['id']}").json()["status"] == "open"
    assert client.get(base + "/analyses").json()[0]["id"] == job["id"]

    def fail(*args):
        raise RuntimeError("private model content")

    monkeypatch.setattr(provider, "reason", fail)
    failed = wait_job(client, client.post(base + "/analyses", json=payload).json()["id"])
    assert failed["status"] == "failed" and "private" not in failed["error"]
    service = client.app.state.reasoning
    service.lock.acquire()
    try:
        assert client.post(base + "/analyses", json=payload).status_code == 429
    finally:
        service.lock.release()

    def reject_submit(*args):
        raise RuntimeError("executor closed")

    monkeypatch.setattr(service, "submit", reject_submit)
    assert client.post(base + "/analyses", json=payload).status_code == 503
    assert client.get(base + "/analyses").json()[0]["status"] == "failed"
    assert service.lock.acquire(blocking=False)
    service.lock.release()
    (repo / "skip.py").write_text("changed = True", encoding="utf-8")
    assert client.get(base + "/context").status_code == 409
    assert client.post(base + "/analyses", json=payload).status_code == 409


def test_model_unavailable_is_honest(api, monkeypatch):  # noqa: F811
    client, _ = api

    def fail():
        raise ProviderError("Cannot reach local Ollama.")

    monkeypatch.setattr(client.app.state.reasoning.provider, "models", fail)
    result = client.get("/api/llm/models").json()
    assert not result["available"] and result["models"] == []
    assert client.get("/api/analyses/missing").status_code == 404
    assert client.get("/api/findings/missing/context").status_code == 404


def test_interrupted_reasoning_recovers(api):  # noqa: F811
    from backend.database import AIAnalysis

    client, repo = api
    scan = scan_repository(client, repo)
    finding = client.get(f"/api/scans/{scan['id']}/findings").json()["items"][0]
    with client.app.state.sessions.begin() as session:
        job = AIAnalysis(
            finding_id=finding["id"], model="test-local", context_hash="0" * 64, context_summary={}
        )
        session.add(job)
        session.flush()
        job_id = job.id
    client.app.state.reasoning.recover()
    restored = client.get(f"/api/analyses/{job_id}").json()
    assert restored["status"] == "failed" and "interrupted" in restored["error"]
