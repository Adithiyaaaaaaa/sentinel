"""Small, reviewable evidence packages; no repository-wide source upload."""

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select

from backend.analysis.engine import read_indexed_source
from backend.database import CodeEntity, Dependency, Finding, FindingEvidence, IndexedFile, Repository, Scan
from backend.security.paths import allowed_directory


def build_context(session, settings, finding: Finding) -> dict:
    scan = session.get(Scan, finding.scan_id)
    repo = session.get(Repository, scan.repository_id)
    root = allowed_directory(repo.path, settings.roots())
    file = session.scalar(
        select(IndexedFile).where(IndexedFile.scan_id == scan.id, IndexedFile.path == finding.file)
    )
    if file is None:
        raise HTTPException(409, "Indexed source is missing. Rescan before requesting reasoning.")
    try:
        source = read_indexed_source(root, file.path, file.sha256)
    except (ValueError, OSError, UnicodeError):
        raise HTTPException(
            409, "Source changed or is inaccessible. Rescan before requesting reasoning."
        ) from None
    lines = source.splitlines()
    start, end = max(1, finding.line - 12), min(len(lines), finding.line + 24)
    secrets = session.scalars(
        select(Finding).where(
            Finding.scan_id == scan.id, Finding.file == file.path, Finding.rule_id == "SEC-001"
        )
    )
    redacted = {n for secret in secrets for n in range(secret.line, secret.end_line + 1)}
    excerpt, budget = [], 12000
    for number in range(start, end + 1):
        value = "[secret assignment redacted]" if number in redacted else lines[number - 1][:600]
        if len(value) > budget:
            break
        excerpt.append({"line": number, "text": value})
        budget -= len(value)
    evidence = [
        {
            "id": "E0",
            "file": finding.file,
            "line": finding.line,
            "end_line": finding.end_line,
            "description": finding.explanation,
        }
    ]
    for item in session.scalars(
        select(FindingEvidence)
        .where(FindingEvidence.finding_id == finding.id)
        .order_by(FindingEvidence.line, FindingEvidence.id)
        .limit(10)
    ):
        evidence.append(
            {
                "id": f"E{len(evidence)}",
                "file": finding.file,
                "line": item.line,
                "end_line": item.end_line,
                "description": item.description,
            }
        )
    entities = session.scalars(
        select(CodeEntity)
        .where(
            CodeEntity.scan_id == scan.id,
            CodeEntity.file == file.path,
            CodeEntity.start_line <= end,
            CodeEntity.end_line >= start,
        )
        .order_by(CodeEntity.start_line, CodeEntity.id)
        .limit(20)
    )
    dependencies = session.scalars(
        select(Dependency)
        .where(Dependency.scan_id == scan.id)
        .order_by(Dependency.name, Dependency.id)
        .limit(30)
    )
    nearby = session.scalars(
        select(Finding)
        .where(Finding.scan_id == scan.id, Finding.file == file.path)
        .order_by(Finding.line, Finding.id)
        .limit(12)
    )
    graph = scan.graph_data or {}
    graph_nodes = {node["id"]: node for node in graph.get("nodes", [])}
    relevant = {
        key
        for key, node in graph_nodes.items()
        if node.get("file") == finding.file
        and node.get("kind") in {"function", "method", "class"}
        and node.get("line", 0) <= finding.line <= node.get("end_line", 0)
    }
    relationships = []
    for edge in graph.get("edges", []):
        if edge["kind"] not in {"calls", "imports"} or not (
            edge["source"] in relevant or edge["target"] in relevant
        ):
            continue
        source_node, target_node = graph_nodes[edge["source"]], graph_nodes[edge["target"]]
        description = f"{source_node['name']} {edge['kind']} {target_node['name']}. {edge['basis']}"
        relationships.append(
            {
                "source": source_node["name"],
                "target": target_node["name"],
                "kind": edge["kind"],
                "file": edge["file"],
            }
        )
        evidence.append(
            {
                "id": f"E{len(evidence)}",
                "file": edge["file"],
                "line": edge["line"],
                "end_line": edge["line"],
                "description": description,
            }
        )
        if len(relationships) >= 6:
            break
    return {
        "schema_version": "1.0",
        "finding": {
            key: getattr(finding, key)
            for key in (
                "id",
                "rule_id",
                "title",
                "file",
                "line",
                "end_line",
                "symbol",
                "severity",
                "confidence",
                "recommendation",
            )
        },
        "evidence": evidence,
        "source": {"sha256": file.sha256, "lines": excerpt},
        "entities": [
            {
                "name": e.name,
                "kind": e.kind,
                "line": e.start_line,
                "end_line": e.end_line,
                "callees": e.callees[:20],
                "complexity": e.complexity,
            }
            for e in entities
        ],
        "dependencies": [
            {"name": d.name, "version": d.version, "ecosystem": d.ecosystem} for d in dependencies
        ],
        "other_static_findings": [{"rule_id": f.rule_id, "line": f.line, "title": f.title} for f in nearby],
        "git": {"branch": scan.branch, "commit": scan.commit},
        "graph": {
            "available": bool(graph),
            "relationships": relationships,
            "scope": graph.get("summary", {}).get("scope", "No graph in this historical scan."),
        },
        "limitations": [
            "Bounded excerpt; full function may be absent.",
            "Detected secret assignments redacted; other sensitive data may remain.",
            "Graph targets are conservative lexical matches, not runtime dispatch proof. No related-file source, Git history, or exploit verification.",
        ],
    }


def context_identity(context: dict) -> tuple[str, dict]:
    raw = json.dumps(context, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if len(raw) > 48000:
        raise HTTPException(422, "Context exceeds the local reasoning budget.")
    return hashlib.sha256(raw).hexdigest(), {
        "schema_version": context["schema_version"],
        "file": context["finding"]["file"],
        "sha256": context["source"]["sha256"],
        "bytes": len(raw),
        "start_line": context["source"]["lines"][0]["line"] if context["source"]["lines"] else 0,
        "end_line": context["source"]["lines"][-1]["line"] if context["source"]["lines"] else 0,
        "evidence": context["evidence"],
        "limitations": context["limitations"],
    }
