from __future__ import annotations

from hoseki.config import IgnoreConfig
from hoseki.ignore import IgnoreRules


def test_default_dirs_ignored(workspace):
    rules = IgnoreRules(workspace, IgnoreConfig())
    assert rules.is_ignored_dir(workspace / "node_modules")
    assert rules.is_ignored_dir(workspace / "__pycache__")
    assert rules.is_ignored_dir(workspace / ".git")
    assert rules.is_ignored_dir(workspace / "build")


def test_gitignore_respected(workspace):
    rules = IgnoreRules(workspace, IgnoreConfig())
    assert rules.is_ignored_file(workspace / "debug.log")
    assert rules.is_ignored_dir(workspace / "local-only")


def test_extra_dirs(workspace):
    rules = IgnoreRules(workspace, IgnoreConfig(extra_dirs=["custom"]))
    (workspace / "custom").mkdir()
    assert rules.is_ignored_dir(workspace / "custom")


def test_extra_files(workspace):
    rules = IgnoreRules(workspace, IgnoreConfig(extra_files=["*.min.js"]))
    (workspace / "x.min.js").write_text("//")
    assert rules.is_ignored_file(workspace / "x.min.js")


def test_respect_disabled(workspace):
    rules = IgnoreRules(
        workspace,
        IgnoreConfig(use_defaults=False, respect_gitignore=False),
    )
    assert not rules.is_ignored_dir(workspace / "node_modules")
    assert not rules.is_ignored_file(workspace / "debug.log")