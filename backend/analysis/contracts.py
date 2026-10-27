"""Parser-neutral records. Evidence describes syntax; source text is not persisted."""

from dataclasses import dataclass, field
from hashlib import sha256


@dataclass
class Entity:
    key: str
    file: str
    language: str
    kind: str
    name: str
    start_line: int
    end_line: int
    parent: str | None = None
    dependencies: list[str] = field(default_factory=list)
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
    complexity: int = 1
    features: list[str] = field(default_factory=list)


@dataclass
class Detection:
    rule_id: str
    file: str
    language: str
    line: int
    end_line: int
    symbol: str
    basis: str

    @property
    def fingerprint(self) -> str:
        return sha256(f"{self.rule_id}:{self.file}:{self.line}:{self.symbol}".encode()).hexdigest()


@dataclass
class ParsedFile:
    entities: list[Entity] = field(default_factory=list)
    detections: list[Detection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parsed: bool = True


def entity_key(path: str, kind: str, name: str, line: int) -> str:
    return sha256(f"{path}:{kind}:{name}:{line}".encode()).hexdigest()
