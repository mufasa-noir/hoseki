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
from hoseki.jail import PathJail
from hoseki.tools.apply_patch import ApplyPatchArgs, apply_patch
from hoseki.tools.write_file import WriteFileArgs, write_file


@pytest.fixture
def ctx(workspace: Path, tmp_path: Path) -> ToolContext:
    audit = AuditLog(tmp_path / "audit.jsonl")
    gate = ApprovalGate(audit=audit)
    return ToolContext(
        jail=PathJail(workspace),
        limits=LimitsConfig(),
        secrets=SecretsConfig(),
        audit=audit,
        approval=gate,
        commands=CommandsConfig(),
        sandbox=SandboxConfig(),
    )


def test_write_new_file_approved(ctx: ToolContext) -> None:
    ctx.approval.set_auto_for_tests(True)
    r = write_file(WriteFileArgs(path="hello.txt", content="hi\n"), ctx)
    assert r.ok
    assert (ctx.jail.root / "hello.txt").read_text() == "hi\n"


def test_write_new_file_denied(ctx: ToolContext) -> None:
    ctx.approval.set_auto_for_tests(False)
    r = write_file(WriteFileArgs(path="hello.txt", content="hi\n"), ctx)
    assert not r.ok
    assert not (ctx.jail.root / "hello.txt").exists()


def test_write_overwrite_shows_diff(ctx: ToolContext) -> None:
    (ctx.jail.root / "a.txt").write_text("old\n")
    ctx.approval.set_auto_for_tests(True)
    r = write_file(WriteFileArgs(path="a.txt", content="new\n"), ctx)
    assert r.ok
    assert (ctx.jail.root / "a.txt").read_text() == "new\n"


def test_write_secret_path_denied(ctx: ToolContext) -> None:
    ctx.approval.set_auto_for_tests(True)
    from hoseki.errors import SecretDenied
    with pytest.raises(SecretDenied):
        write_file(WriteFileArgs(path=".env", content="x=1\n"), ctx)


def test_write_escape_denied(ctx: ToolContext) -> None:
    ctx.approval.set_auto_for_tests(True)
    from hoseki.errors import JailError
    with pytest.raises(JailError):
        write_file(WriteFileArgs(path="../escaped.txt", content="x\n"), ctx)


def test_apply_patch_happy_path(ctx: ToolContext) -> None:
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = (
        "--- a/greet.txt\n"
        "+++ b/greet.txt\n"
        "@@ -1,2 +1,2 @@\n"
        " hello\n"
        "-world\n"
        "+earth\n"
    )
    ctx.approval.set_auto_for_tests(True)
    r = apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert r.ok
    assert p.read_text() == "hello\nearth\n"


def test_apply_patch_denied(ctx: ToolContext) -> None:
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = "@@ -1,2 +1,2 @@\n hello\n-world\n+earth\n"
    ctx.approval.set_auto_for_tests(False)
    r = apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert not r.ok
    assert p.read_text() == "hello\nworld\n"


def test_apply_patch_bad_diff_fails_cleanly(ctx: ToolContext) -> None:
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = "@@ -1,2 +1,2 @@\n not-in-file\n-world\n+earth\n"
    ctx.approval.set_auto_for_tests(True)
    with pytest.raises(Exception):
        apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert p.read_text() == "hello\nworld\n"