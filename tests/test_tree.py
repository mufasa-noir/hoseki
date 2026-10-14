from __future__ import annotations

from hoseki.tools.tree import TreeArgs, tree


def test_tree_basic(ctx):
    r = tree(TreeArgs(path=".", depth=2), ctx)
    assert r.ok
    assert "src/" in r.output
    assert "app.py" in r.output
    assert "director" in r.output  # summary line


def test_tree_skips_ignored(ctx):
    r = tree(TreeArgs(path=".", depth=3), ctx)
    assert "node_modules" not in r.output
    assert "__pycache__" not in r.output
    assert "build" not in r.output
    assert "debug.log" not in r.output


def test_tree_depth_limit(ctx):
    r = tree(TreeArgs(path=".", depth=1), ctx)
    assert "src/" in r.output
    # app.py is at depth 2 from root, so with depth=1 it should not appear
    assert "app.py" not in r.output


def test_tree_summary_counts(ctx):
    r = tree(TreeArgs(path=".", depth=3), ctx)
    assert "director" in r.output
    assert "file" in r.output


def test_tree_ignore_disabled(ctx):
    r = tree(TreeArgs(path=".", depth=2, respect_ignore=False), ctx)
    assert "node_modules" in r.output