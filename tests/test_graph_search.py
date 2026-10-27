import math
import time

import pytest
from sqlalchemy import select
from test_api import api, scan_repository, workspace  # noqa: F401

from backend.analysis.engine import analyze_repository
from backend.analysis.indexer import index_repository
from backend.architecture.graph import build_graph, strongly_connected
from backend.database import EntityEmbedding
from backend.embeddings.service import normalized
from backend.llm.contracts import ProviderError


def test_graph_resolves_imports_calls_and_retains_unknowns(tmp_path):
    (tmp_path / "a.py").write_text(
        "from b import target\ndef caller():\n    return target()\ndef local():\n    return caller()\ndef shadow(caller):\n    return caller()\n"
    )
    (tmp_path / "b.py").write_text("import a\ndef target():\n    return 1\n")
    index = index_repository(tmp_path)
    analysis = analyze_repository(tmp_path, index.files)
    graph = build_graph(tmp_path, index.files, analysis.entities)
    nodes = {n["id"]: n for n in graph["nodes"]}
    calls = [
        (nodes[e["source"]]["name"], nodes[e["target"]]["name"])
        for e in graph["edges"]
        if e["kind"] == "calls"
    ]
    assert ("caller", "target") in calls and ("local", "caller") in calls
    assert not any(source == "shadow" for source, _ in calls)
    assert graph["summary"]["cycles"] == [["a.py", "b.py"]]
    assert any(r["name"] == "caller" for r in graph["unresolved"])
    assert all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])


def test_js_parameter_shadow_and_relative_import(tmp_path):
    (tmp_path / "a.ts").write_text(
        "import { target } from './b'; function run(target: () => void) { target(); } function helper() {} function use() { helper(); }"
    )
    (tmp_path / "b.ts").write_text("export function target() {}")
    index = index_repository(tmp_path)
    graph = build_graph(tmp_path, index.files, analyze_repository(tmp_path, index.files).entities)
    assert any(e["kind"] == "imports" and e["target"] == "file:b.ts" for e in graph["edges"])
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert not any(nodes[e["source"]]["name"] == "run" for e in graph["edges"] if e["kind"] == "calls")


def test_cycles_are_iterative_and_do_not_flag_acyclic_paths():
    assert strongly_connected({"a": {"b"}, "b": {"c"}}) == []
    graph = {str(n): {str(n + 1)} for n in range(3000)}
    graph["3000"] = {"0"}
    assert len(strongly_connected(graph)[0]) == 3001


def test_bare_method_name_does_not_resolve_through_class_namespace(tmp_path):
    (tmp_path / "app.py").write_text(
        "class Service:\n    def target(self):\n        return 1\n    def bare(self):\n        return target()\n    def explicit(self):\n        return self.target()\n"
    )
    index = index_repository(tmp_path)
    graph = build_graph(tmp_path, index.files, analyze_repository(tmp_path, index.files).entities)
    nodes = {node["id"]: node for node in graph["nodes"]}
    calls = [
        (nodes[e["source"]]["name"], nodes[e["target"]]["name"])
        for e in graph["edges"]
        if e["kind"] == "calls"
    ]
    assert ("explicit", "target") in calls
    assert not any(source == "bare" for source, _ in calls)


@pytest.mark.parametrize("vector", [[], [0, 0], [float("nan")], [float("inf")], [True], ["1"], [1] * 4097])
def test_invalid_embedding_vectors(vector):
    with pytest.raises(ProviderError):
        normalized(vector)


def test_normalized_cosine_vectors():
    result = normalized([3, 4])
    assert result == [0.6, 0.8] and math.isclose(sum(v * v for v in result), 1)


def wait_index(client, index_id):
    for _ in range(150):
        result = client.get(f"/api/embeddings/{index_id}").json()
        if result["status"] != "running":
            return result
        time.sleep(0.02)
    pytest.fail("Embedding job did not complete")


def test_graph_and_semantic_api(api, monkeypatch):  # noqa: F811
    client, repo = api
    (repo / "app.py").write_text(
        "def reset_password():\n    password = 'SYNTHETIC-SECRET'\n    return password\ndef payments():\n    return 2\n"
    )
    scan = scan_repository(client, repo)
    graph = client.get(f"/api/scans/{scan['id']}/graph?view=symbols").json()
    assert graph["available"] and graph["summary"]["nodes"] > 0
    limited = client.get(f"/api/scans/{scan['id']}/graph?limit=1").json()
    assert limited["truncated"] and len(limited["nodes"]) == 1
    service = client.app.state.embeddings
    monkeypatch.setattr(service.provider, "models", lambda: [{"name": "test-embedding", "digest": "stable"}])
    seen = []

    def embed(model, texts):
        seen.extend(texts)
        return [[1.0, 0.0] if "password" in text else [0.0, 1.0] for text in texts]

    monkeypatch.setattr(service.provider, "embed", embed)
    response = client.post(f"/api/scans/{scan['id']}/embeddings", json={"model": "test-embedding"})
    assert response.status_code == 202
    index = wait_index(client, response.json()["id"])
    assert index["status"] == "completed" and index["indexed"] == 2 and index["dimensions"] == 2
    assert "SYNTHETIC-SECRET" not in str(seen) and "redacted" in str(seen)
    url = f"/api/embeddings/{index['id']}/search"
    results = client.post(url, json={"query": "forgot password"}).json()
    assert results["items"][0]["name"] == "reset_password" and results["items"][0]["source_verified"]
    assert results["items"][0]["similarity"] == 1
    assert client.post(url, json={"query": "   "}).status_code == 422
    (repo / "app.py").write_text("changed = 1")
    assert not client.post(url, json={"query": "forgot password"}).json()["items"][0]["source_verified"]
    monkeypatch.setattr(service.provider, "models", lambda: [{"name": "test-embedding", "digest": "changed"}])
    assert client.post(url, json={"query": "password"}).status_code == 409
    failure = client.post(f"/api/scans/{scan['id']}/embeddings", json={"model": "test-embedding"})
    failed = wait_index(client, failure.json()["id"])
    assert failed["status"] == "failed"
    with client.app.state.sessions() as session:
        assert not list(
            session.scalars(select(EntityEmbedding).where(EntityEmbedding.index_id == failed["id"]))
        )
    service.lock.acquire()
    try:
        assert client.post(url, json={"query": "password"}).status_code == 429
    finally:
        service.lock.release()
    assert client.get("/api/scans/missing/graph").status_code == 404
    assert client.get("/api/embeddings/missing").status_code == 404
