"""Bearer token and Origin/Host validation."""
from __future__ import annotations

import fnmatch
import os
import secrets
from pathlib import Path

from hoseki.config import ServerConfig


def get_or_create_token(path: Path) -> str:
    """Return the stored token, generating one with 0600 perms if missing."""
    path = Path(path).expanduser()
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token

    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)

    # Atomically create with restrictive permissions.
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(token + "\n")
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return token


def verify_token(expected: str, header_value: str | None) -> bool:
    if not header_value:
        return False
    parts = header_value.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return secrets.compare_digest(parts[1].strip(), expected)


def origin_allowed(origin: str | None, patterns: list[str]) -> bool:
    if origin is None:
        return False
    return any(fnmatch.fnmatchcase(origin, pat) for pat in patterns)


def check_origin(
    origin: str | None,
    patterns: list[str],
    allow_missing: bool,
) -> bool:
    if origin is None:
        return allow_missing
    return origin_allowed(origin, patterns)


def check_host(host_header: str | None, server: ServerConfig) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    port = server.port

    allowed = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    }
    return host in allowed