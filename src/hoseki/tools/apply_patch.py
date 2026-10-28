from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ApplyPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    unified_diff: str


@dataclass
class _Hunk:
    old_start: int
    new_start: int
    old_lines: list[str]
    new_lines: list[str]


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_hunks(diff: str) -> list[_Hunk]:
    """Parse a unified diff into hunks.

    File headers (---/+++ lines) are optional; only '@@' hunks are required,
    so headerless hunks produced by many models apply without synthesis.
    """
    lines = diff.splitlines(keepends=False)
    hunks: list[_Hunk] = []
    i = 0
    n = len(lines)
    while i < n:
        m = _HUNK_RE.match(lines[i])
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        new_start = int(m.group(3))
        i += 1
        old_lines: list[str] = []
        new_lines: list[str] = []
        while i < n:
            ln = lines[i]
            if _HUNK_RE.match(ln) or ln.startswith("--- ") or ln.startswith("+++ "):
                break
            if ln.startswith("\\"):
                i += 1
                continue
            if ln == "":
                old_lines.append("")
                new_lines.append("")
            elif ln[0] == " ":
                old_lines.append(ln[1:])
                new_lines.append(ln[1:])
            elif ln[0] == "-":
                old_lines.append(ln[1:])
            elif ln[0] == "+":
                new_lines.append(ln[1:])
            else:
                raise ToolError(f"unparseable diff line inside hunk: {ln[:80]!r}")
            i += 1
        hunks.append(_Hunk(old_start, new_start, old_lines, new_lines))
    if not hunks:
        raise ToolError("no @@ hunks found in unified_diff")
    return hunks


def _find_block(src: list[str], block: list[str], expected: int) -> int | None:
    """Locate `block` in `src`, preferring the occurrence nearest `expected`.

    Mirrors GNU patch's fuzzy offset search so hunks with stale line numbers
    (a common LLM output failure) still apply to the correct location.
    """
    if not block:
        return min(max(expected, 0), len(src))
    limit = len(src) - len(block)
    if limit < 0:
        return None
    best: int | None = None
    best_dist: int | None = None
    for idx in range(limit + 1):
        if src[idx:idx + len(block)] == block:
            dist = abs(idx - expected)
            if best_dist is None or dist < best_dist:
                best, best_dist = idx, dist
    return best


def _apply_hunks(original: str, hunks: list[_Hunk]) -> str:
    had_final_newline = original.endswith("\n")
    src = original.splitlines(keepends=False)
    out: list[str] = []
    pos = 0
    for hunk in hunks:
        if hunk.old_lines:
            expected = max(hunk.old_start - 1, 0)
            idx = _find_block(src, hunk.old_lines, expected)
            if idx is None:
                preview = "\n".join(hunk.old_lines[:3])
                raise ToolError(
                    "hunk did not match the file at or near line "
                    f"{hunk.old_start} (context: {preview[:120]!r})"
                )
        else:
            # Pure insertion: '-N,0' means "after line N" (index N);
            # '-0,0' means "before line 1" (index 0).
            idx = min(max(hunk.old_start, 0), len(src))
        if idx < pos:
            raise ToolError(
                f"overlapping or out-of-order hunk at line {hunk.old_start}"
            )
        out.extend(src[pos:idx])
        out.extend(hunk.new_lines)
        pos = idx + len(hunk.old_lines)
    out.extend(src[pos:])
    text = "\n".join(out)
    if had_final_newline:
        text += "\n"
    return text


def apply_patch(args: ApplyPatchArgs, ctx: ToolContext) -> ToolResult:
    if len(args.unified_diff.encode("utf-8")) > ctx.limits.max_output_bytes:
        raise LimitExceeded("unified_diff exceeds max_output_bytes")

    target = ctx.check_path_allowed(args.path)
    if not target.exists():
        raise ToolError(f"file does not exist: {args.path}")
    if not target.is_file():
        raise ToolError(f"not a regular file: {args.path}")

    rel = ctx.jail.relative(target)
    try:
        original = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError(f"file is not valid UTF-8: {args.path}") from exc

    hunks = _parse_hunks(args.unified_diff)

    decision = ctx.approval.request(
        ApprovalRequest(
            kind="apply_patch",
            summary=f"apply patch to {rel}",
            body=args.unified_diff,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="patch denied by operator")

    patched = _apply_hunks(original, hunks)
    if patched == original:
        return ToolResult(ok=True, output=f"{rel}: no changes")

    original_bytes = original.encode("utf-8")
    try:
        target.write_text(patched, encoding="utf-8")
    except OSError:
        try:
            target.write_bytes(original_bytes)
        except OSError:
            pass
        raise ToolError(f"failed to write patched file: {args.path}")

    return ToolResult(ok=True, output=f"{rel}: applied {len(hunks)} hunk(s)")