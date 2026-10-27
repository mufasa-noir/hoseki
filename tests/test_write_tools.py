from __future__ import annotations

import pytest

from hoseki.errors import JailError, SecretDenied, ToolError
from hoseki.tools.apply_patch import ApplyPatchArgs, apply_patch
from hoseki.tools.write_file import WriteFileArgs, write_file


# ---------------------------------------------------------------- write_file

def test_write_new_file_approved(ctx):
    r = write_file(WriteFileArgs(path="hello.txt", content="hi\n"), ctx)
    assert r.ok
    assert (ctx.jail.root / "hello.txt").read_text() == "hi\n"


def test_write_new_file_denied(ctx):
    ctx.approval.set_auto_for_tests(False)
    r = write_file(WriteFileArgs(path="hello.txt", content="hi\n"), ctx)
    assert not r.ok
    assert not (ctx.jail.root / "hello.txt").exists()
    ctx.approval.set_auto_for_tests(True)


def test_write_overwrite(ctx):
    p = ctx.jail.root / "a.txt"
    p.write_text("old\n")
    r = write_file(WriteFileArgs(path="a.txt", content="new\n"), ctx)
    assert r.ok
    assert p.read_text() == "new\n"


def test_write_no_change(ctx):
    p = ctx.jail.root / "a.txt"
    p.write_text("same\n")
    r = write_file(WriteFileArgs(path="a.txt", content="same\n"), ctx)
    assert r.ok
    assert "no changes" in r.output


def test_write_append_mode(ctx):
    p = ctx.jail.root / "log.txt"
    p.write_text("line 1\n")
    r = write_file(
        WriteFileArgs(path="log.txt", content="line 2\n", mode="a"), ctx
    )
    assert r.ok
    assert p.read_text() == "line 1\nline 2\n"


def test_write_append_creates(ctx):
    r = write_file(
        WriteFileArgs(path="new.txt", content="first\n", mode="a"), ctx
    )
    assert r.ok
    assert (ctx.jail.root / "new.txt").read_text() == "first\n"


def test_write_secret_denied(ctx):
    with pytest.raises(SecretDenied):
        write_file(WriteFileArgs(path=".env", content="x=1\n"), ctx)


def test_write_escape_denied(ctx):
    with pytest.raises(JailError):
        write_file(WriteFileArgs(path="../escaped.txt", content="x\n"), ctx)


# --------------------------------------------------------------- apply_patch

def test_apply_patch_happy(ctx):
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
    r = apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert r.ok
    assert p.read_text() == "hello\nearth\n"


def test_apply_patch_denied(ctx):
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = "@@ -1,2 +1,2 @@\n hello\n-world\n+earth\n"
    ctx.approval.set_auto_for_tests(False)
    r = apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert not r.ok
    assert p.read_text() == "hello\nworld\n"
    ctx.approval.set_auto_for_tests(True)


def test_apply_patch_headerless_hunk(ctx):
    """A bare '@@' hunk with no ---/+++ header must still apply.

    patch cannot parse headerless hunks on its own; apply_patch synthesizes
    a header from the known target path. This case previously only passed
    under the denied-approval test, so the bug went unnoticed.
    """
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = "@@ -1,2 +1,2 @@\n hello\n-world\n+earth\n"
    r = apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert r.ok, r.error
    assert p.read_text() == "hello\nearth\n"


def test_apply_patch_basename_header_in_subdir(ctx):
    """Headers naming just the basename must apply to the file in args.path.

    patch is given the explicit target, so it ignores the ---/+++ paths and
    cannot strip its way to a different file.
    """
    # The workspace fixture already creates ws/src/, so don't mkdir() it.
    p = ctx.jail.root / "src" / "auth.py"
    p.write_text("x = 1\n")
    diff = "--- auth.py\n+++ auth.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    r = apply_patch(ApplyPatchArgs(path="src/auth.py", unified_diff=diff), ctx)
    assert r.ok, r.error
    assert p.read_text() == "x = 2\n"


def test_apply_patch_mismatched_hunk_fails_cleanly(ctx):
    """A hunk that doesn't match the file must fail without touching it."""
    p = ctx.jail.root / "greet.txt"
    p.write_text("hello\nworld\n")
    diff = "@@ -1,2 +1,2 @@\n hello\n-nonexistent\n+earth\n"
    with pytest.raises(ToolError):
        apply_patch(ApplyPatchArgs(path="greet.txt", unified_diff=diff), ctx)
    assert p.read_text() == "hello\nworld\n"