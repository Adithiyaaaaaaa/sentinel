"""Explicit local configuration. Repository configuration is never executed."""
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{(PROJECT_ROOT / '.sentinel' / 'sentinel.db').as_posix()}"
    allowed_roots: list[str] = Field(default_factory=lambda: [str(PROJECT_ROOT)])
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    demo_path: str = str(PROJECT_ROOT / "examples" / "sample-repository")
    max_workers: int = Field(default=2, ge=1, le=8)
    max_queued_scans: int = Field(default=8, ge=1, le=64)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_timeout: int = Field(default=180, ge=10, le=600)
    sandbox_image: str = ""
    sandbox_timeout: int = Field(default=60, ge=5, le=300)

    @field_validator("sandbox_image")
    @classmethod
    def pinned_sandbox(cls, value: str) -> str:
        import re

        if value and not re.fullmatch(r"sha256:[a-f0-9]{64}", value):
            raise ValueError("Sandbox image must be an installed Docker image ID (sha256:...)")
        return value

    @field_validator("ollama_url")
    @classmethod
    def local_ollama(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1"}
                or url.username or url.password or url.query or url.fragment or url.path not in {"", "/"}):
            raise ValueError("Ollama must use a literal loopback HTTP address without credentials or a path")
        _ = url.port
        return value.rstrip("/")

    def roots(self) -> list[Path]:
        return [Path(root).expanduser().resolve() for root in self.allowed_roots]

