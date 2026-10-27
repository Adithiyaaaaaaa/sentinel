"""Bounded, read-only repository indexing without importing repository code.

Language totals describe indexed text files, not parsed syntax. A line is a
physical line (including blank lines); an empty file contributes zero lines.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tomllib
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from pathspec import GitIgnoreSpec

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_FILES = 50_000
MAX_DIRECTORIES = 10_000
MAX_IGNORE_BYTES = 128 * 1024

IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", "node_modules", "dist", "build", "target",
    "__pycache__", ".venv", "venv", "env", "vendor", "coverage", ".next",
    ".nuxt", ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
    ".idea", ".sentinel", ".turbo", "__pypackages__", "htmlcov", "bin", "obj",
})

LANGUAGES = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".mts": "TypeScript", ".cts": "TypeScript", ".java": "Java", ".c": "C", ".h": "C",
    ".cc": "C++", ".cpp": "C++", ".cxx": "C++", ".hpp": "C++", ".hxx": "C++",
    ".go": "Go", ".rs": "Rust", ".php": "PHP", ".cs": "C#", ".kt": "Kotlin",
    ".kts": "Kotlin", ".swift": "Swift", ".rb": "Ruby", ".r": "R", ".dart": "Dart",
    ".scala": "Scala", ".sh": "Shell", ".bash": "Shell", ".ps1": "PowerShell",
    ".vue": "Vue", ".svelte": "Svelte", ".html": "HTML", ".htm": "HTML",
    ".css": "CSS", ".scss": "SCSS", ".sass": "SCSS", ".less": "Less", ".sql": "SQL",
    ".json": "JSON", ".jsonc": "JSON", ".yaml": "YAML", ".yml": "YAML",
    ".toml": "TOML", ".xml": "XML", ".md": "Markdown", ".mdx": "Markdown",
    ".txt": "Text", ".ini": "Configuration", ".cfg": "Configuration",
    ".properties": "Configuration", ".tf": "Terraform", ".graphql": "GraphQL",
    ".gql": "GraphQL", ".proto": "Protocol Buffers", ".ipynb": "Jupyter Notebook",
    ".gradle": "Groovy", ".csproj": "XML", ".fsproj": "XML", ".vbproj": "XML",
    ".ex": "Elixir", ".exs": "Elixir", ".erl": "Erlang",
    ".clj": "Clojure", ".hs": "Haskell", ".lua": "Lua", ".lock": "Lockfile",
}

SPECIAL_FILES = {
    "Dockerfile": "Dockerfile", "Containerfile": "Dockerfile", "Makefile": "Makefile",
    "Gemfile": "Ruby", "Rakefile": "Ruby", "Jenkinsfile": "Groovy",
    ".gitignore": "Configuration", ".sentinelignore": "Configuration",
    ".dockerignore": "Configuration", ".editorconfig": "Configuration",
    "LICENSE": "Text", "LICENSE.txt": "Text", "Procfile": "Configuration",
    "go.mod": "Go Module", "go.sum": "Lockfile",
}

GENERATED_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "poetry.lock",
    "uv.lock", "Cargo.lock", "composer.lock", "go.sum", "Pipfile.lock",
})
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", ".generated.cs", ".g.cs", ".pb.go", ".pb.cc", "_pb2.py")
GENERATED_MARKER = re.compile(r"(?:@generated|automatically generated|auto-generated|code generated .*do not edit)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class IndexedFile:
    path: str
    language: str
    lines: int
    size_bytes: int
    sha256: str


@dataclass(slots=True)
class IndexResult:
    files: list[IndexedFile] = field(default_factory=list)
    languages: dict[str, dict[str, int]] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0
    total_bytes: int = 0
    skipped_files: int = 0
    warnings: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    test_frameworks: list[str] = field(default_factory=list)
    has_docker: bool = False
    has_ci: bool = False
    branch: str | None = None
    commit: str | None = None
    dependencies: list[dict[str, str]] = field(default_factory=list)


class _BoundedWarnings(list[str]):
    """Keep diagnostic memory bounded while preserving an omitted count."""

    def __init__(self) -> None:
        super().__init__()
        self.omitted = 0

    def append(self, message: str) -> None:
        if len(self) < 99:
            super().append(message)
        else:
            self.omitted += 1
            summary = f"{self.omitted} additional warnings omitted"
            if len(self) == 99:
                super().append(summary)
            else:
                self[-1] = summary


def _is_link(path: Path) -> bool:
    """Junctions can escape the root just like symbolic links on Windows."""
    junction_check = getattr(path, "is_junction", None)
    if path.is_symlink() or (junction_check is not None and junction_check()):
        return True
    # Python 3.11 does not expose Path.is_junction. A Windows junction is a
    # reparse point, which lstat can identify without resolving its target.
    if os.name == "nt" and junction_check is None:
        try:
            attributes = getattr(path.lstat(), "st_file_attributes", 0)
            return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
        except FileNotFoundError:
            return False
    return False


def _bounded_walk(
    root: Path, onerror: Callable[[OSError], None], onlimit: Callable[[], None],
) -> Iterator[tuple[Path, list[str], list[str]]]:
    """Like a top-down walk, with bounded enumeration even for empty trees.

    Callers can prune the yielded directory list before traversal resumes.
    A single huge directory cannot cause an unbounded list allocation.
    """
    pending = [root]
    entries_seen = 0
    directories_seen = 0
    while pending:
        current = pending.pop()
        directories: list[str] = []
        names: list[str] = []
        limited = False
        try:
            if _is_link(current):
                continue
            with os.scandir(current) as entries:
                for entry in entries:
                    entries_seen += 1
                    if entries_seen > MAX_FILES + MAX_DIRECTORIES:
                        limited = True
                        break
                    if entry.is_dir(follow_symlinks=False):
                        directories_seen += 1
                        if directories_seen > MAX_DIRECTORIES:
                            limited = True
                            break
                        directories.append(entry.name)
                    else:
                        names.append(entry.name)
        except OSError as error:
            onerror(error)
        yield current, directories, names
        if limited:
            onlimit()
            return
        pending.extend(current / name for name in reversed(directories))


def _safe_bytes(path: Path, root: Path, limit: int) -> bytes | None:
    if _is_link(path) or not path.resolve().is_relative_to(root):
        return None
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        return None
    # No repository paths are executed. Bounded reads also handle a growing file.
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit or _is_link(path):
        return None
    return data


def _ignore_spec(directory: Path, root: Path, warnings: list[str]) -> GitIgnoreSpec | None:
    patterns: list[str] = []
    for name in (".gitignore", ".sentinelignore"):
        candidate = directory / name
        try:
            if candidate.is_file():
                data = _safe_bytes(candidate, root, MAX_IGNORE_BYTES)
                if data is not None:
                    patterns.extend(data.decode("utf-8", errors="replace").splitlines())
        except (OSError, ValueError):
            warnings.append(f"Could not read ignore rules: {candidate.relative_to(root).as_posix()}")
    if not patterns:
        return None
    try:
        return GitIgnoreSpec.from_lines(patterns)
    except (ValueError, TypeError):
        warnings.append(f"Invalid ignore rules in {directory.relative_to(root).as_posix()}")
        return None


def _is_ignored(relative: str, is_dir: bool, specs: list[tuple[str, GitIgnoreSpec]], custom: GitIgnoreSpec) -> bool:
    target = relative + ("/" if is_dir else "")
    ignored = False
    for prefix, spec in specs:
        if prefix and not target.startswith(prefix):
            continue
        match = spec.check_file(target[len(prefix):])
        if match.include is not None:
            ignored = bool(match.include)
    match = custom.check_file(target)
    if match.include is not None:
        ignored = bool(match.include)
    return ignored


def _git_metadata(root: Path) -> tuple[str | None, str | None]:
    # Only ask Git for object metadata; do not invoke hooks, filters, external
    # diffs, credential helpers, or commands supplied by repository config.
    def query(arguments: list[str]) -> str | None:
        try:
            result = subprocess.run(
                ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(root), *arguments],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=5, check=False, shell=False,
                env={**{key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")},
                     "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            value = result.stdout.strip()
            return value if result.returncode == 0 and len(value) < 1024 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    # A subfolder can be selected; Git legitimately discovers its parent root.
    return query(["symbolic-ref", "--quiet", "--short", "HEAD"]), query(["rev-parse", "--verify", "HEAD"])


def _dependency(name: str, version: object, ecosystem: str) -> dict[str, str] | None:
    if not name or len(name) > 200:
        return None
    # Do not retain credential-bearing dependency URLs or local source paths.
    value = str(version) if isinstance(version, (str, int, float)) else "unspecified"
    if any(marker in value for marker in ("://", "git@", "file:", "path:", "../", "\\")):
        value = "external/local reference (redacted)"
    return {"name": name, "version": value[:200], "ecosystem": ecosystem}


def _requirements(content: str) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-", ".", "/")) or "://" in line:
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^\]]+\])?\s*([^;#]*)(?:[;#].*)?$", line)
        if match:
            entry = _dependency(match[1], match[2].strip() or "*", "PyPI")
            if entry:
                dependencies.append(entry)
    return dependencies


def _manifest_metadata(path: str, content: str, dependencies: list[dict[str, str]], managers: set[str], tests: set[str], warnings: list[str]) -> None:
    name = Path(path).name
    try:
        if name == "package.json":
            managers.add("npm")
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("Manifest is not an object")
            manager = data.get("packageManager")
            if isinstance(manager, str) and manager.split("@")[0] in {"npm", "pnpm", "yarn", "bun"}:
                managers.add(manager.split("@")[0])
            for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                values = data.get(section, {})
                if isinstance(values, dict):
                    for dep_name, version in values.items():
                        entry = _dependency(dep_name, version, "npm")
                        if entry:
                            dependencies.append(entry)
        elif name == "pyproject.toml":
            data = tomllib.loads(content)
            managers.add("pip")
            project = data.get("project", {})
            if isinstance(project, dict):
                requirements = project.get("dependencies", [])
                if isinstance(requirements, list):
                    dependencies.extend(_requirements("\n".join(x for x in requirements if isinstance(x, str))))
                optional = project.get("optional-dependencies", {})
                if isinstance(optional, dict):
                    for group in optional.values():
                        if isinstance(group, list):
                            dependencies.extend(_requirements("\n".join(x for x in group if isinstance(x, str))))
            tool = data.get("tool", {})
            if isinstance(tool, dict):
                if "pytest" in tool:
                    tests.add("pytest")
                if "uv" in tool:
                    managers.add("uv")
                poetry = tool.get("poetry")
                if isinstance(poetry, dict):
                    managers.add("Poetry")
                    values = poetry.get("dependencies", {})
                    if isinstance(values, dict):
                        for dep_name, version in values.items():
                            if dep_name == "python":
                                continue
                            if isinstance(version, dict):
                                version = version.get("version", "external/local reference (redacted)")
                            entry = _dependency(dep_name, version, "PyPI")
                            if entry:
                                dependencies.append(entry)
        elif name.startswith("requirements") and name.endswith(".txt"):
            managers.add("pip")
            dependencies.extend(_requirements(content))
        elif name == "Cargo.toml":
            managers.add("Cargo")
            data = tomllib.loads(content)
            for section in ("dependencies", "dev-dependencies", "build-dependencies"):
                values = data.get(section, {})
                if isinstance(values, dict):
                    for dep_name, version in values.items():
                        if isinstance(version, dict):
                            version = version.get("version", "workspace/local reference")
                        entry = _dependency(dep_name, version, "crates.io")
                        if entry:
                            dependencies.append(entry)
        elif name == "go.mod":
            managers.add("Go modules")
            in_require = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped == "require (":
                    in_require = True
                elif stripped == ")":
                    in_require = False
                else:
                    match = re.match(r"(?:require\s+)?([\w./-]+)\s+(v\S+)", stripped)
                    if match and (in_require or stripped.startswith("require ")):
                        entry = _dependency(match[1], match[2], "Go")
                        if entry:
                            dependencies.append(entry)
        elif name == "composer.json":
            managers.add("Composer")
            data = json.loads(content)
            if isinstance(data, dict):
                for section in ("require", "require-dev"):
                    values = data.get(section, {})
                    if isinstance(values, dict):
                        for dep_name, version in values.items():
                            entry = _dependency(dep_name, version, "Packagist")
                            if entry:
                                dependencies.append(entry)
    except (ValueError, TypeError, AttributeError, RecursionError):
        warnings.append(f"Could not parse dependency manifest: {path}")


def index_repository(
    root: Path,
    ignore_patterns: list[str] | None = None,
    progress: Callable[[int, str], None] | None = None,
) -> IndexResult:
    """Return file metadata and manifest-derived facts for a local directory.

    No source text is returned. Excluded directories are pruned, so their
    contents are deliberately not counted in ``skipped_files``.
    """
    root = Path(root).expanduser()
    if _is_link(root):
        raise ValueError("Repository root must not be a symbolic link or junction")
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Repository path must be a directory")
    result = IndexResult()
    result.warnings = _BoundedWarnings()
    custom = GitIgnoreSpec.from_lines(ignore_patterns or [])
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
    managers: set[str] = set()
    frameworks: set[str] = set()
    tests: set[str] = set()
    dependencies: list[dict[str, str]] = []
    specs_by_directory: dict[Path, list[tuple[str, GitIgnoreSpec]]] = {root: []}
    visited = 0
    truncated = False

    def notify(percent: int, message: str) -> None:
        if progress:
            progress(percent, message)

    def walk_error(error: OSError) -> None:
        result.warnings.append("A directory could not be read; its contents were skipped")

    def walk_limit() -> None:
        nonlocal truncated
        truncated = True

    notify(5, "Discovering repository files")
    for current, directories, names in _bounded_walk(root, walk_error, walk_limit):
        inherited = specs_by_directory.pop(current, [])
        prefix = current.relative_to(root).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        local_spec = _ignore_spec(current, root, result.warnings)
        specs = inherited + ([(prefix, local_spec)] if local_spec else [])
        accepted_directories: list[str] = []
        for name in sorted(directories):
            candidate = current / name
            relative = prefix + name
            try:
                if name.lower() in IGNORED_DIRECTORIES or _is_link(candidate) or _is_ignored(relative, True, specs, custom):
                    continue
                accepted_directories.append(name)
                specs_by_directory[candidate] = specs
            except OSError:
                result.warnings.append(f"Could not inspect directory: {relative}")
        directories[:] = accepted_directories
        for name in sorted(names):
            visited += 1
            if visited > MAX_FILES or result.total_bytes >= MAX_TOTAL_BYTES:
                truncated = True
                break
            relative = prefix + name
            path = current / name
            if _is_ignored(relative, False, specs, custom):
                result.skipped_files += 1
                continue
            lower = name.lower()
            # Never index secret-bearing local environment files by default.
            if lower == ".env" or (lower.startswith(".env.") and lower not in {".env.example", ".env.sample", ".env.template"}):
                result.skipped_files += 1
                continue
            if name in GENERATED_NAMES or lower.endswith(GENERATED_SUFFIXES):
                if name == "pnpm-lock.yaml":
                    managers.add("pnpm")
                elif name == "yarn.lock":
                    managers.add("yarn")
                elif name == "uv.lock":
                    managers.add("uv")
                elif name == "poetry.lock":
                    managers.add("Poetry")
                result.skipped_files += 1
                continue
            language = SPECIAL_FILES.get(name) or LANGUAGES.get(path.suffix.lower())
            if name.startswith("Dockerfile."):
                language = "Dockerfile"
            if language is None:
                result.skipped_files += 1
                continue
            try:
                data = _safe_bytes(path, root, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - result.total_bytes))
                if data is None:
                    result.skipped_files += 1
                    result.warnings.append(f"Skipped non-regular, linked, or oversized file: {relative}")
                    continue
                if b"\x00" in data[:8192]:
                    result.skipped_files += 1
                    continue
                try:
                    content = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    result.skipped_files += 1
                    result.warnings.append(f"Skipped non-UTF-8 file: {relative}")
                    continue
                if GENERATED_MARKER.search(content[:1000]):
                    result.skipped_files += 1
                    continue
                lines = len(content.splitlines())
                result.files.append(IndexedFile(relative, language, lines, len(data), hashlib.sha256(data).hexdigest()))
                result.total_lines += lines
                result.total_bytes += len(data)
                stats[language]["files"] += 1
                stats[language]["lines"] += lines
                _manifest_metadata(relative, content, dependencies, managers, tests, result.warnings)
                if language == "Dockerfile" or name in {"compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"}:
                    result.has_docker = True
                if relative.startswith(".github/workflows/") or name in {".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"} or relative == ".circleci/config.yml":
                    result.has_ci = True
                if name in {"pytest.ini", "conftest.py"} or name.startswith("test_") and name.endswith(".py"):
                    tests.add("pytest")
                if lower.startswith("vitest.config."):
                    tests.add("Vitest")
                if lower.startswith("jest.config."):
                    tests.add("Jest")
                if name.endswith("_test.go"):
                    tests.add("Go test")
                if name == "pom.xml":
                    managers.add("Maven")
                if name in {"build.gradle", "build.gradle.kts"}:
                    managers.add("Gradle")
                if name.endswith(".csproj"):
                    managers.add("NuGet")
            except (OSError, ValueError):
                result.skipped_files += 1
                result.warnings.append(f"Could not read file: {relative}")
            if visited % 50 == 0:
                notify(min(85, 15 + visited // 50), f"Indexed {len(result.files):,} files")
        if truncated:
            break
    if truncated:
        result.warnings.append(f"Indexing stopped at a safety limit ({MAX_FILES:,} files / {MAX_DIRECTORIES:,} directories / {MAX_TOTAL_BYTES // (1024 * 1024)} MiB indexed text)")

    known_frameworks = {
        "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "starlette": "Starlette",
        "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte", "express": "Express",
        "@nestjs/core": "NestJS", "@angular/core": "Angular", "nuxt": "Nuxt", "laravel/framework": "Laravel",
        "gin-gonic/gin": "Gin", "github.com/gin-gonic/gin": "Gin", "axum": "Axum", "actix-web": "Actix Web",
    }
    known_tests = {"pytest": "pytest", "jest": "Jest", "vitest": "Vitest", "@playwright/test": "Playwright", "cypress": "Cypress", "phpunit/phpunit": "PHPUnit"}
    unique_dependencies: dict[tuple[str, str, str], dict[str, str]] = {}
    for dep in dependencies:
        dep_name = dep["name"].lower()
        if dep_name in known_frameworks:
            frameworks.add(known_frameworks[dep_name])
        if dep_name in known_tests:
            tests.add(known_tests[dep_name])
        unique_dependencies[(dep["ecosystem"], dep["name"], dep["version"])] = dep
    result.dependencies = [unique_dependencies[key] for key in sorted(unique_dependencies)]
    result.total_files = len(result.files)
    result.languages = dict(sorted(stats.items(), key=lambda item: (-item[1]["lines"], item[0])))
    result.frameworks = sorted(frameworks)
    result.package_managers = sorted(managers)
    result.test_frameworks = sorted(tests)
    notify(90, "Reading Git metadata")
    result.branch, result.commit = _git_metadata(root)
    result.warnings = list(result.warnings)
    notify(95, "Saving repository index")
    return result
