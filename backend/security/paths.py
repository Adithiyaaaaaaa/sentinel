"""Constrain all filesystem discovery to explicitly configured local roots."""
from pathlib import Path

from fastapi import HTTPException


def allowed_directory(raw_path: str, roots: list[Path]) -> Path:
    try:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise HTTPException(400, "Use an absolute repository path.")
        resolved = candidate.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in roots):
            raise HTTPException(403, "This folder is outside SENTINEL_ALLOWED_ROOTS. Add its parent to your local configuration.")
        if not resolved.is_dir():
            raise HTTPException(400, "Select a directory, not a file.")
        if candidate.is_symlink() or (hasattr(candidate, "is_junction") and candidate.is_junction()):
            raise HTTPException(400, "Select the original folder, not a filesystem link.")
        return resolved
    except (OSError, ValueError, RuntimeError):
        raise HTTPException(400, "The folder does not exist or cannot be accessed.") from None

