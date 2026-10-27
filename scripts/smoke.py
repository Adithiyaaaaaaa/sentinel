"""Exercise a running local API against its configured sample without executing source."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def request(base: str, route: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + route,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("--url must be a local HTTP endpoint")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    health = request(base, "/api/health")
    if health["status"] != "ok":
        raise RuntimeError(f"API is not healthy: {health}")
    settings = request(base, "/api/settings")
    repository = request(base, "/api/repositories", {"path": settings["demo_path"]})
    scan = request(base, f"/api/repositories/{repository['id']}/scans", {})
    deadline = time.monotonic() + args.timeout
    while scan["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.2)
        scan = request(base, f"/api/scans/{scan['id']}")
    if scan["status"] != "completed":
        raise RuntimeError(f"Scan did not complete: {scan['status']}: {scan.get('error')}")
    files = request(base, f"/api/scans/{scan['id']}/files?limit=100")
    history = request(base, f"/api/repositories/{repository['id']}/scans")
    if files["total"] != scan["total_files"] or files["total"] < 1:
        raise RuntimeError("Persisted file totals do not match the scan")
    if not any(item["id"] == scan["id"] for item in history):
        raise RuntimeError("Completed scan is missing from history")
    if sum(value["files"] for value in scan["languages"].values()) != scan["total_files"]:
        raise RuntimeError("Language file totals do not match the scan")
    findings = request(base, f"/api/scans/{scan['id']}/findings?limit=100")
    expected_rules = {"SEC-001", "SEC-002", "SEC-006", "SEC-007", "SEC-008", "SEC-009", "QUAL-001", "PERF-001"}
    if {item["rule_id"] for item in findings["items"]} != expected_rules or findings["total"] != 8:
        raise RuntimeError("Sample findings do not match the eight expected deterministic patterns")
    if not all(item["evidence"] for item in findings["items"]):
        raise RuntimeError("A finding is missing structural evidence")
    secret = next(item for item in findings["items"] if item["rule_id"] == "SEC-001")
    params = urllib.parse.urlencode({"path": secret["file"], "line": secret["line"], "context": 0})
    excerpt = request(base, f"/api/scans/{scan['id']}/source?{params}")
    if not excerpt["verified"] or not all(line["redacted"] for line in excerpt["lines"]):
        raise RuntimeError("Secret evidence was not fingerprint-verified and redacted")
    print(json.dumps({
        "status": "passed",
        "scan_id": scan["id"],
        "files": scan["total_files"],
        "lines": scan["total_lines"],
        "languages": scan["languages"],
        "dependencies": scan["dependency_count"],
        "analysis": scan["analysis_summary"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, ValueError, KeyError, RuntimeError) as exc:
        print(f"SENTINEL smoke test failed: {exc}", file=sys.stderr)
        sys.exit(1)
