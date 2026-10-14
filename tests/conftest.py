from __future__ import annotations

from pathlib import Path

import pytest

from hoseki.approval import ApprovalGate
from hoseki.audit import AuditLog
from hoseki.config import (
    CommandsConfig,
    Config,
    IgnoreConfig,
    LimitsConfig,
    SandboxConfig,
    SecretsConfig,
    ServerConfig,
)
from hoseki.context import ToolContext
from hoseki.jail import PathJail


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A small throwaway workspace with a few files and a .gitignore."""
    root = tmp_path / "ws"
    root.mkdir()

    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "import os\n\n"
        "def main():\n"
        "    print('hello')\n"
        "    # TODO: add args\n"
    )
    (root / "src" / "util.py").write_text("def add(a, b):\n    return a + b\n")

    (root / "README.md").write_text("# demo\n")
    (root / ".env").write_text("SUPER_SECRET=1\n")
    (root / "id_rsa").write_text("fake private key\n")

    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[user]\n  name = x\n")

    (root / "node_modules").mkdir()
    (root / "node_modules" / "lib.js").write_text("module.exports = {};\n")

    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01\x02")

    (root / "build").mkdir()
    (root / "build" / "output.txt").write_text("compiled\n")

    (root / ".gitignore").write_text("*.log\nlocal-only/\n")

    (root / "debug.log").write_text("noise\n")
    (root / "local-only").mkdir()
    (root / "local-only" / "note.txt").write_text("private\n")

    return root


@pytest.fixture
def config(workspace: Path, tmp_path: Path) -> Config:
    return Config(
        workspace_root=workspace,
        server=ServerConfig(),
        limits=LimitsConfig(),
        secrets=SecretsConfig(),
        ignore=IgnoreConfig(),
        commands=CommandsConfig(),
        sandbox=SandboxConfig(mode="refuse"),
        token_file=tmp_path / "token",
        audit_log=tmp_path / "audit.jsonl",
        allowed_origins=["chrome-extension://*"],
        allow_missing_origin=True,
    )


@pytest.fixture
def ctx(workspace: Path, tmp_path: Path) -> ToolContext:
    """A ToolContext with approval auto-bypassed for tests.

    The approval gate's `set_auto_for_tests` hook is the only sanctioned
    bypass; it is unreachable from HTTP, config, or file content.
    """
    audit = AuditLog(tmp_path / "audit.jsonl")
    gate = ApprovalGate(audit=audit)
    gate.set_auto_for_tests(True)
    return ToolContext(
        jail=PathJail(workspace),
        limits=LimitsConfig(),
        secrets=SecretsConfig(),
        audit=audit,
        approval=gate,
        commands=CommandsConfig(),
        sandbox=SandboxConfig(mode="refuse"),
        ignore=IgnoreConfig(),
    )