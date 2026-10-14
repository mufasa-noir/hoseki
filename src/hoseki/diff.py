"""Unified-diff rendering for approval prompts."""
from __future__ import annotations

import difflib


def render_unified_diff(
    old: str,
    new: str,
    label: str,
    context: int = 3,
) -> str:
    """Return a unified diff between two strings, or "" if identical."""
    old_lines = old.splitlines(keepends=False)
    new_lines = new.splitlines(keepends=False)
    if old_lines == new_lines:
        return ""
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        n=context,
        lineterm="",
    )
    return "\n".join(diff)


def render_new_file(content: str, label: str) -> str:
    """Render a pseudo-diff for a brand-new file."""
    lines = content.splitlines()
    body = "\n".join("+" + line for line in lines)
    return f"--- /dev/null\n+++ b/{label}\n@@ -0,0 +1,{len(lines)} @@\n{body}"


def render_append(content: str, label: str) -> str:
    """Render a pseudo-diff for an append operation."""
    lines = content.splitlines()
    body = "\n".join("+" + line for line in lines)
    return f"--- a/{label}\n+++ b/{label}\n@@ append, +{len(lines)} lines @@\n{body}"