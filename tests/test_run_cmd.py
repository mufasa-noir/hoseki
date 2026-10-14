from __future__ import annotations

import pytest

from hoseki.config import CommandsConfig, SandboxConfig
from hoseki.errors import ToolError
from hoseki.tools.run_cmd import RunCmdArgs, _check_allowlist, run_cmd


def test_allowlist_empty_refuses():
    with pytest.raises(ToolError):
        _check_allowlist("echo hi", [])


def test_allowlist_prefix_match():
    _check_allowlist("echo hi", ["echo"])
    _check_allowlist("git status", ["git status"])


def test_allowlist_rejects_chaining():
    with pytest.raises(ToolError):
        _check_allowlist("echo ok; rm -rf /", ["echo"])
    with pytest.raises(ToolError):
        _check_allowlist("echo ok && rm -rf /", ["echo"])
    with pytest.raises(ToolError):
        _check_allowlist("echo `whoami`", ["echo"])


def test_allowlist_rejects_unlisted():
    with pytest.raises(ToolError):
        _check_allowlist("rm -rf /", ["ls", "echo"])


def test_run_cmd_refused_when_sandbox_refuse(ctx):
    with pytest.raises(ToolError):
        run_cmd(RunCmdArgs(cmd="echo hi", timeout=10), ctx)