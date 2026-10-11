"""Secret-file deny-list and cheap output redaction."""
from __future__ import annotations

import fnmatch
import re

from hoseki.config import SecretsConfig


_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA[REDACTED]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"), "gh[REDACTED]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "xox[REDACTED]"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "sk-[REDACTED]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
            r"-----END [A-Z ]*PRIVATE KEY-----"
        ),
        "[REDACTED PRIVATE KEY]",
    ),
]


def is_denied(rel_path: str, patterns: list[str]) -> bool:
    """Check whether a relative path matches any deny glob.

    Matches against the file name, the full relative path, and every suffix
    starting at a path boundary. This lets patterns like ``.git/config`` or
    ``.ssh/*`` apply to nested paths (``foo/.git/config``).
    """
    if not rel_path:
        return False
    rel = rel_path.replace("\\", "/")
    parts = rel.split("/")
    name = parts[-1]
    for pat in patterns:
        if fnmatch.fnmatchcase(name, pat):
            return True
        if fnmatch.fnmatchcase(rel, pat):
            return True
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if fnmatch.fnmatchcase(suffix, pat):
                return True
    return False


def redact(text: str, cfg: SecretsConfig) -> str:
    if not cfg.redact:
        return text
    out = text
    for pattern, replacement in _REDACTIONS:
        out = pattern.sub(replacement, out)
    return out