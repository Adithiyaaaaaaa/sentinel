"""Strict single-file unified diffs; no fuzzy matching or target execution."""

import ast
import difflib
import hashlib
import re


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_diff(source: str, patch: str, path: str) -> str:
    if len(patch) > 24000 or not source.endswith("\n") or "\r" in patch:
        raise ValueError("Patch exceeds limits or uses unsupported line endings.")
    rows = patch.splitlines(keepends=True)
    if len(rows) < 3 or rows[:2] != [f"--- a/{path}\n", f"+++ b/{path}\n"]:
        raise ValueError("Only a unified diff for the selected file is accepted.")
    original = source.splitlines(keepends=True)
    output, cursor, index, changed = [], 0, 2, False
    while index < len(rows):
        match = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@[^\n]*\n", rows[index])
        if not match:
            raise ValueError("Invalid unified diff hunk header.")
        old_start, old_count, new_start, new_count = (int(v) if v is not None else 1 for v in match.groups())
        start = old_start - 1 if old_count else old_start
        if start < cursor or start > len(original):
            raise ValueError("Overlapping or out-of-range patch hunks.")
        output.extend(original[cursor:start])
        cursor = start
        if (new_start - 1 if new_count else new_start) != len(output):
            raise ValueError("Patch new-line coordinates do not match.")
        consumed = produced = 0
        index += 1
        while index < len(rows) and not rows[index].startswith("@@ "):
            row = rows[index]
            if not row or row[0] not in " +-" or not row.endswith("\n"):
                raise ValueError("Unsupported patch content.")
            if row[0] in " -":
                if cursor >= len(original) or original[cursor] != row[1:]:
                    raise ValueError("Patch context does not match the indexed source.")
                consumed += 1
                cursor += 1
            if row[0] in " +":
                output.append(row[1:])
                produced += 1
            changed |= row[0] in "+-"
            index += 1
        if (consumed, produced) != (old_count, new_count):
            raise ValueError("Patch hunk counts do not match.")
    output.extend(original[cursor:])
    result = "".join(output)
    if not changed or result == source or len(result.encode()) > 128000:
        raise ValueError("Patch must contain a bounded, nonempty change.")
    ast.parse(result)
    return result


def canonical_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{path}", f"b/{path}")
    )


def validate_tests(source: str, module: str | None = None, symbol: str | None = None):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            f"Generated pytest is invalid at line {exc.lineno or '?'}: {exc.msg}."
        ) from None
    tests = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    if not tests or not any(isinstance(n, ast.Assert) for test in tests for n in ast.walk(test)):
        raise ValueError("Generated pytest code must contain test functions and assertions.")
    if module:
        imports = {
            name
            for node in ast.walk(tree)
            for name in (
                [item.name for item in node.names]
                if isinstance(node, ast.Import)
                else [node.module]
                if isinstance(node, ast.ImportFrom) and node.level == 0
                else []
            )
        }
        if module not in imports:
            raise ValueError("Generated tests must import the selected repository module directly.")
    if symbol:
        references = {
            node.id if isinstance(node, ast.Name) else node.attr
            for test in tests
            for node in ast.walk(test)
            if isinstance(node, (ast.Name, ast.Attribute))
        }
        if symbol not in references:
            raise ValueError(f"Generated tests must exercise the selected symbol {symbol}.")
