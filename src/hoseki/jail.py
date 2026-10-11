"""Path jail: guarantees every resolved path stays inside the workspace root."""
from __future__ import annotations

from pathlib import Path

from hoseki.errors import JailError


class PathJail:
    """Resolves user-supplied paths inside a fixed root.

    The jail uses ``Path.resolve()`` (which follows symlinks) and requires the
    result to be a subpath of the root. ``..`` segments are collapsed by
    ``resolve`` and any escape is rejected by the ``relative_to`` check.
    """

    def __init__(self, root: Path):
        resolved = Path(root).expanduser().resolve()
        if not resolved.exists():
            raise JailError(f"workspace root does not exist: {resolved}")
        if not resolved.is_dir():
            raise JailError(f"workspace root is not a directory: {resolved}")
        self.root: Path = resolved

    def resolve(self, rel: str) -> Path:
        if rel is None:
            raise JailError("path is required")
        if not isinstance(rel, str):
            raise JailError(f"path must be a string, got {type(rel).__name__}")
        if "\x00" in rel:
            raise JailError("path contains a NUL byte")

        candidate = Path(rel)
        if not candidate.is_absolute():
            candidate = self.root / candidate

        try:
            resolved = candidate.resolve(strict=False)
        except OSError as e:
            raise JailError(f"cannot resolve path {rel!r}: {e}") from e

        try:
            resolved.relative_to(self.root)
        except ValueError as e:
            raise JailError(
                f"path {rel!r} resolves outside the workspace root"
            ) from e

        return resolved

    def relative(self, abs_path: Path) -> str:
        return str(abs_path.relative_to(self.root))