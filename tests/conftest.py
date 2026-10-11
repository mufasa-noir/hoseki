from __future__ import annotations

from pathlib import Path

import pytest

from hoseki.config import Config, LimitsConfig, SecretsConfig, ServerConfig


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text(
        "import os\n\ndef main():\n    print('hello')\n    # TODO: add args\n"
    )
    (root / "README.md").write_text("# demo\n")
    (root / ".env").write_text("SUPER_SECRET=1\n")
    (root / "id_rsa").write_text("fake private key\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[user]\n  name = x\n")
    return root


@pytest.fixture
def config(workspace: Path, tmp_path: Path) -> Config:
    return Config(
        workspace_root=workspace,
        server=ServerConfig(),
        limits=LimitsConfig(),
        secrets=SecretsConfig(),
        token_file=tmp_path / "token",
        audit_log=tmp_path / "audit.jsonl",
        allowed_origins=["chrome-extension://*"],
        allow_missing_origin=True,
    )