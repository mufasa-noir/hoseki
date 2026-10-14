from __future__ import annotations

import pytest

from hoseki.errors import JailError, SecretDenied, ToolError
from hoseki.tools.find_files import FindFilesArgs, find_files
from hoseki.tools.grep import GrepArgs, grep
from hoseki.tools.list_dir import ListDirArgs, list_dir
from hoseki.tools.read_file import ReadFileArgs, read_file


# ---------------------------------------------------------------- list_dir

def test_list_dir_root(ctx):
    r = list_dir(ListDirArgs(path=".", depth=1), ctx)
    assert r.ok
    assert "src/" in r.output
    assert "README.md" in r.output


def test_list_dir_missing(ctx):
    with pytest.raises(ToolError):
        list_dir(ListDirArgs(path="nope"), ctx)


def test_list_dir_skip_secrets(ctx):
    r = list_dir(ListDirArgs(path="."), ctx)
    # .env and id_rsa are hidden by the secrets policy
    assert "hidden by secrets policy" in r.output


def test_list_dir_shows_symlink_target(ctx, workspace):
    (workspace / "alias.py").symlink_to(workspace / "src" / "app.py")
    r = list_dir(ListDirArgs(path="."), ctx)
    assert "alias.py@ -> src/app.py" in r.output


# --------------------------------------------------------------- read_file

def test_read_file_range(ctx):
    r = read_file(ReadFileArgs(path="src/app.py", start_line=1, end_line=3), ctx)
    assert r.ok
    assert "1  import os" in r.output
    assert "3  def main():" in r.output


def test_read_file_missing(ctx):
    with pytest.raises(ToolError):
        read_file(ReadFileArgs(path="nope.py"), ctx)


def test_read_file_binary_refused(ctx, workspace):
    (workspace / "bin.dat").write_bytes(b"\x00\x01\x02")
    with pytest.raises(ToolError):
        read_file(ReadFileArgs(path="bin.dat"), ctx)


def test_read_file_secret_denied(ctx):
    with pytest.raises(SecretDenied):
        read_file(ReadFileArgs(path=".env"), ctx)


def test_read_file_escape_denied(ctx):
    with pytest.raises(JailError):
        read_file(ReadFileArgs(path="../etc/passwd"), ctx)


# --------------------------------------------------------------------- grep

def test_grep_finds_todo(ctx):
    r = grep(GrepArgs(pattern="TODO", path="."), ctx)
    assert r.ok
    assert "src/app.py" in r.output


def test_grep_skips_ignored(ctx):
    (ctx.jail.root / "node_modules" / "lib.js").write_text("// TODO\n")
    r = grep(GrepArgs(pattern="TODO", path="."), ctx)
    assert "node_modules" not in r.output


def test_grep_bad_regex(ctx):
    with pytest.raises(ToolError):
        grep(GrepArgs(pattern="(", path="."), ctx)


# -------------------------------------------------------------- find_files

def test_find_files_py(ctx):
    r = find_files(FindFilesArgs(glob="**/*.py", path="."), ctx)
    assert r.ok
    assert "src/app.py" in r.output
    assert "src/util.py" in r.output


def test_find_files_skips_node_modules(ctx):
    r = find_files(FindFilesArgs(glob="**/*.js", path="."), ctx)
    assert "node_modules" not in r.output