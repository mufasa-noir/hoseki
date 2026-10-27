from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ApplyPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    unified_diff: str


def _ensure_header(diff: str, rel: str) -> str:
    """Make sure the diff has a ---/+++ header.

    GNU patch needs a header to parse the input, even when the target file
    is passed explicitly on the command line. Models frequently emit bare
    '@@' hunks, so synthesize a header from the known target path when it's
    missing. Existing headers are left untouched.
    """
    body = diff.lstrip("\n")
    head = body.splitlines()[:4]
    if any(line.startswith("--- ") for line in head):
        return diff
    return f"--- a/{rel}\n+++ b/{rel}\n" + body


def _run_patch(target: Path, diff: str, dry_run: bool) -> subprocess.CompletedProcess:
    """Run GNU patch against an explicit target file.

    Passing the original file as an argument means patch applies the hunks
    to that file and ignores the ---/+++ paths, so strip-level (-pN)
    guessing is unnecessary and cannot retarget the patch elsewhere.
    """
    cmd = ["patch", "--forward", "--batch", "--reject-file=-"]
    if dry_run:
        cmd.append("--dry-run")
    cmd.append(str(target))
    if not diff.endswith("\n"):
        diff += "\n"
    return subprocess.run(
        cmd,
        input=diff,
        capture_output=True,
        text=True,
        cwd=str(target.parent),
        timeout=30,
        check=False,
    )


def apply_patch(args: ApplyPatchArgs, ctx: ToolContext) -> ToolResult:
    if len(args.unified_diff.encode("utf-8")) > ctx.limits.max_output_bytes:
        raise LimitExceeded("unified_diff exceeds max_output_bytes")

    target = ctx.check_path_allowed(args.path)
    if not target.exists():
        raise ToolError(f"file does not exist: {args.path}")
    if not target.is_file():
        raise ToolError(f"not a regular file: {args.path}")

    if shutil.which("patch") is None:
        raise ToolError("the 'patch' utility was not found on PATH")

    rel = ctx.jail.relative(target)
    diff = _ensure_header(args.unified_diff, rel)

    decision = ctx.approval.request(
        ApprovalRequest(
            kind="apply_patch",
            summary=f"apply patch to {rel}",
            body=diff,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="patch denied by operator")

    # Snapshot the file so a partial multi-hunk application can be rolled back.
    original = target.read_bytes()

    dry = _run_patch(target, diff, dry_run=True)
    if dry.returncode != 0:
        msg = (dry.stdout + dry.stderr).strip()
        raise ToolError(f"patch did not apply cleanly: {msg[:500]}")

    real = _run_patch(target, diff, dry_run=False)
    if real.returncode != 0:
        try:
            target.write_bytes(original)
        except OSError:
            pass
        msg = (real.stdout + real.stderr).strip()
        raise ToolError(
            f"patch failed after dry-run succeeded; file restored. {msg[:500]}"
        )

    out = (real.stdout or "").strip() or "patch applied cleanly"
    return ToolResult(ok=True, output=f"{rel}: {out}")