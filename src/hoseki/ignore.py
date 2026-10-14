"""Gitignore-aware path ignoring for read tools.

Loads the workspace root's .gitignore once (via pathspec) plus a hardcoded
list of directories that should never be walked (node_modules, .next, .git,
etc.). Subdirectory .gitignore files are NOT consulted — see "Known
limitations" at the bottom. In practice, root-only covers the vast majority
of repos.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from hoseki.config import IgnoreConfig


# Directories we never walk into, regardless of .gitignore.
DEFAULT_IGNORE_DIRS: list[str] = [
    # VCS metadata
    ".git", ".hg", ".svn",
    # JS / TS ecosystem
    "node_modules", "bower_components", "jspm_packages",
    ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache",
    ".yarn", ".pnpm-store",
    # Python
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env", ".tox",
    # Rust / JVM / Go
    "target", ".gradle",
    # Editors / OS
    ".idea", ".vscode",
    # Build outputs
    "dist", "build",
]


class IgnoreRules:
    """Precomputed ignore rules for a single workspace root.

    The rules are immutable once constructed. Build one per tool call — the
    cost is a single .gitignore read, which is negligible.
    """

    def __init__(self, root: Path, cfg: IgnoreConfig):
        self.root = Path(root).resolve()
        self.cfg = cfg

        # Directory names that are always skipped.
        self.default_dirs: set[str] = set()
        if cfg.use_defaults:
            self.default_dirs.update(DEFAULT_IGNORE_DIRS)
        self.default_dirs.update(cfg.extra_dirs)

        # File name globs that are always skipped (e.g. "*.min.js").
        self.extra_file_globs: list[str] = list(cfg.extra_files)

        # Root .gitignore, loaded once.
        self._root_spec = None
        if cfg.respect_gitignore:
            self._load_root_gitignore()

    def _load_root_gitignore(self) -> None:
        gitignore = self.root / ".gitignore"
        if not gitignore.is_file():
            return
        try:
            import pathspec
        except ImportError:
            # pathspec missing — silently skip gitignore. The default
            # ignore dirs still apply.
            return
        try:
            text = gitignore.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        try:
            self._root_spec = pathspec.GitIgnoreSpec.from_lines(
                text.splitlines()
            )
        except Exception:
            self._root_spec = None

    # -- checks ------------------------------------------------------------

    def is_ignored_dir(self, abs_path: Path) -> bool:
        """True if this directory should not be descended into."""
        if abs_path.name in self.default_dirs:
            return True
        if self._matches_extra_file_globs(abs_path.name):
            return True
        if self._root_spec is not None:
            rel = self._rel_posix(abs_path)
            if rel is None:
                return False
            # Trailing slash signals dir-only patterns in gitignore.
            if self._root_spec.match_file(rel):
                return True
            if self._root_spec.match_file(rel + "/"):
                return True
        return False

    def is_ignored_file(self, abs_path: Path) -> bool:
        """True if this file should be skipped from results."""
        if self._matches_extra_file_globs(abs_path.name):
            return True
        if self._root_spec is not None:
            rel = self._rel_posix(abs_path)
            if rel is None:
                return False
            if self._root_spec.match_file(rel):
                return True
        return False

    # -- helpers -----------------------------------------------------------

    def _matches_extra_file_globs(self, name: str) -> bool:
        for pat in self.extra_file_globs:
            if fnmatch.fnmatchcase(name, pat):
                return True
        return False

    def _rel_posix(self, abs_path: Path) -> str | None:
        try:
            rel = abs_path.relative_to(self.root)
        except ValueError:
            return None
        return rel.as_posix() if rel.parts else "."


# ---------------------------------------------------------------------------
# Known limitations
#
# - Subdirectory .gitignore files are not consulted. If a repo relies on
#   them, add the relevant directory names to [ignore].extra_dirs in config.
# - Negation patterns within the root .gitignore work (pathspec handles
#   them). If you find a case where an un-ignored file is still being
#   skipped, that's the first place to look.
# - Symlinks are never followed by the tools, so we don't need to worry
#   about cycles in ignore resolution.
# ---------------------------------------------------------------------------