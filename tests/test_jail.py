from __future__ import annotations

from pathlib import Path

import pytest

from hoseki.errors import JailError
from hoseki.jail import PathJail


def test_root_must_exist(tmp_path):
    with pytest.raises(JailError):
        PathJail(tmp_path / "missing")


def test_root_must_be_dir(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    with pytest.raises(JailError):
        PathJail(f)


def test_basic_resolution(workspace):
    jail = PathJail(workspace)
    p = jail.resolve("src/app.py")
    assert p == (workspace / "src" / "app.py").resolve()


def test_dot_resolves_to_root(workspace):
    jail = PathJail(workspace)
    assert jail.resolve(".") == workspace.resolve()


@pytest.mark.parametrize("rel", [
    "../escape.txt",
    "../../etc/passwd",
    "src/../../etc/passwd",
    "src/../../../tmp",
    "/etc/passwd",
    "/tmp/whatever",
])
def test_escapes_rejected(workspace, rel):
    jail = PathJail(workspace)
    with pytest.raises(JailError):
        jail.resolve(rel)


def test_symlink_escape_rejected(workspace, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    link = workspace / "escape"
    link.symlink_to(outside)
    jail = PathJail(workspace)
    with pytest.raises(JailError):
        jail.resolve("escape/secret.txt")


def test_symlink_inside_allowed(workspace):
    target = workspace / "src" / "app.py"
    link = workspace / "link.py"
    link.symlink_to(target)
    jail = PathJail(workspace)
    resolved = jail.resolve("link.py")
    assert resolved == target.resolve()


def test_nul_byte_rejected(workspace):
    jail = PathJail(workspace)
    with pytest.raises(JailError):
        jail.resolve("bad\x00path")


def test_non_string_rejected(workspace):
    jail = PathJail(workspace)
    with pytest.raises(JailError):
        jail.resolve(None)  # type: ignore[arg-type]