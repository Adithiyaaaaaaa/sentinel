"""Correlate deterministic parser results against an immutable indexed file fingerprint."""

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.analysis.contracts import Detection, Entity
from backend.analysis.indexer import IndexedFile, _is_link, _safe_bytes
from backend.analysis.javascript_parser import parse_javascript
from backend.analysis.python_parser import parse_python
from backend.security.rules import RULES, RULESET_VERSION

SUPPORTED_LANGUAGES = ("Python", "JavaScript", "TypeScript")
MAX_PARSE_BYTES = 512 * 1024
MAX_ENTITIES = 100_000
MAX_FINDINGS = 10_000


@dataclass
class AnalysisResult:
    entities: list[Entity] = field(default_factory=list)
    detections: list[Detection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def read_indexed_source(root: Path, relative: str, expected_sha256: str, limit: int = 2 * 1024 * 1024) -> str:
    """Revalidate every path component and the file hash before displaying/analyzing source."""
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Invalid indexed path")
    target = root / path
    for parent in (target, *target.parents):
        if parent == root:
            break
        if _is_link(parent):
            raise ValueError("Indexed path became a filesystem link")
    data = _safe_bytes(target, root, limit)
    if data is None:
        raise ValueError("File is not a readable bounded regular file")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("File changed since scan")
    return data.decode("utf-8-sig")


def analyze_repository(
    root: Path, files: list[IndexedFile], progress: Callable[[int, str], None] | None = None
) -> AnalysisResult:
    output = AnalysisResult()
    supported = [file for file in files if file.language in SUPPORTED_LANGUAGES]
    parsed, failed = 0, 0
    for number, file in enumerate(supported):
        if len(output.entities) >= MAX_ENTITIES or len(output.detections) >= MAX_FINDINGS:
            output.warnings.append("Analysis output limit reached; remaining files were not analyzed.")
            break
        try:
            source = read_indexed_source(root, file.path, file.sha256, MAX_PARSE_BYTES)
            result = (
                parse_python(file.path, source)
                if file.language == "Python"
                else parse_javascript(file.path, source, file.language)
            )
            parsed += int(result.parsed)
            failed += int(not result.parsed)
            output.entities.extend(result.entities[: max(0, MAX_ENTITIES - len(output.entities))])
            output.detections.extend(result.detections[: max(0, MAX_FINDINGS - len(output.detections))])
            if len(output.warnings) < 100:
                output.warnings.extend(result.warnings[: 100 - len(output.warnings)])
        except (OSError, ValueError, UnicodeError, RecursionError):
            failed += 1
            if len(output.warnings) < 100:
                output.warnings.append(
                    f"Analysis skipped changed, inaccessible, oversized, or invalid file: {file.path}"
                )
        if progress and (number % 10 == 0 or number + 1 == len(supported)):
            progress(
                55 + round(35 * (number + 1) / max(1, len(supported))),
                f"Analyzing syntax and rules: {number + 1}/{len(supported)} files",
            )
    # Multiple equivalent AST visits should never inflate a finding count.
    output.detections = list({item.fingerprint: item for item in output.detections}.values())
    output.entities = list({item.key: item for item in output.entities}.values())
    counts = Counter(RULES[item.rule_id].severity for item in output.detections)
    output.summary = {
        "ruleset_version": RULESET_VERSION,
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "parsed_files": parsed,
        "failed_files": failed,
        "unsupported_files": len(files) - len(supported),
        "unprocessed_files": len(supported) - parsed - failed,
        "entity_count": len(output.entities),
        "finding_count": len(output.detections),
        "severity_counts": {name: counts[name] for name in ("critical", "high", "medium", "low")},
        "rule_count": len(RULES),
        "scope": "Local AST rules; no interprocedural taint or exploit verification.",
    }
    return output
