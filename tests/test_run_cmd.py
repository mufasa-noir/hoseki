from __future__ import annotations

from pathlib import Path

import pytest

from hoseki.approval import ApprovalGate
from hoseki.audit import AuditLog
from hoseki.config import (
    CommandsConfig,
    LimitsConfig,
    SandboxConfig,
    SecretsConfig,
)
from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.jail import PathJail
from hoseki.tools.run_cmd import RunCmdArgs, _check_allowlist, run_cmd


def _ctx(tmp_path: Path, workspace: Path, **overrides) -> ToolContext:
    audit = AuditLog(tmp_path / "audit.jsonl")
    gate = ApprovalGate(audit=audit)
    gate.set_auto_for_tests(True)
    return ToolContext(
        jail=PathJail(workspace),
        limits=LimitsConfig(),
        secrets=SecretsConfig(),
        audit=audit,
        approval=gate,
        commands=overrides.get("commands", CommandsConfig(
            allowlist=["echo", "git status"],
            unsafe_host_exec=True,
        )),
        sandbox=overrides.get("sandbox", SandboxConfig(mode="host")),
    )


def test_allowlist_blocks_unlisted() -> None:
    with pytest.raises(ToolError):
        _check_allowlist("rm -rf /", ["ls", "echo"])


def test_allowlist_allows_prefix() -> None:
    _check_allowlist("echo hello", ["echo"])
    _check_allowlist("git status", ["git status"])


def test_allowlist_rejects_chaining() -> None:
    with pytest.raises(ToolError):
        _check_allowlist("echo ok; rm -rf /", ["echo"])


def test_run_echo_host(tmp_path: Path, workspace: Path) -> None:
    ctx = _ctx(tmp_path, workspace)
    r = run_cmd(RunCmdArgs(cmd="echo hello", timeout=10), ctx)
    assert r.ok
    assert "hello" in r.output


def test_run_refuses_empty_allowlist(tmp_path: Path, workspace: Path) -> None:
    ctx = _ctx(tmp_path, workspace, commands=CommandsConfig(
        allowlist=[], unsafe_host_exec=True,
    ))
    with pytest.raises(ToolError):
        run_cmd(RunCmdArgs(cmd="echo hi", timeout=10), ctx)


def test_run_refused_when_mode_refuse(tmp_path: Path, workspace: Path) -> None:
    ctx = _ctx(tmp_path, workspace, sandbox=SandboxConfig(mode="refuse"))
    with pytest.raises(ToolError):
        run_cmd(RunCmdArgs(cmd="echo hi", timeout=10), ctx)


def test_run_denied_by_operator(tmp_path: Path, workspace: Path) -> None:
    ctx = _ctx(tmp_path, workspace)
    ctx.approval.set_auto_for_tests(False)
    r = run_cmd(RunCmdArgs(cmd="echo hi", timeout=10), ctx)
    assert not r.ok