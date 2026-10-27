"""Intentionally weak authentication examples. Never use in an application."""

import hashlib
import random

# Synthetic value, deliberately labelled so it cannot be mistaken for a real key.
SIGNING_SECRET = "SENTINEL_DEMO_NOT_A_REAL_SECRET_000000"


def password_digest(password: str) -> str:
    # Fixture: a fast, unsalted hash is unsuitable for password storage.
    return hashlib.md5(password.encode()).hexdigest()


def create_reset_token() -> str:
    # Fixture: predictable random generator and a small search space.
    return str(random.randint(100000, 999999))


def is_admin(request_headers: dict[str, str]) -> bool:
    # Fixture: an untrusted request header is treated as authorization.
    return request_headers.get("X-Role") == "admin"
