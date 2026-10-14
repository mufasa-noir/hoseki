from __future__ import annotations

import shutil
import subprocess

from pydantic import BaseModel, ConfigDict

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ApplyPatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    unified_diff: str


def _run_patch(level: str, diff: str, cwd: str, dry_run: bool) -> subprocess.CompletedProcess:
    cmd = ["patch", level, "--forward", "--batch"]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        input=diff if diff.endswith("\n") else diff + "\n",
        capture_output=True,
        text=True,
        cwd=cwd,
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

    decision = ctx.approval.request(
        ApprovalRequest(
            kind="apply_patch",
            summary=f"apply patch to {args.path}",
            body=args.unified_diff,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="patch denied by operator")

    last_err = ""
    for level in ("-p0", "-p1", "-p2"):
        dry = _run_patch(level, args.unified_diff, str(ctx.jail.root), dry_run=True)
        if dry.returncode == 0:
            real = _run_patch(
                level, args.unified_diff, str(ctx.jail.root), dry_run=False
            )
            if real.returncode == 0:
                out = (real.stdout or "").strip() or "patch applied cleanly"
                return ToolResult(ok=True, output=f"{args.path}: {out}")
            last_err = real.stdout + real.stderr
            break
        last_err = dry.stdout + dry.stderr

    raise ToolError(f"patch did not apply cleanly: {last_err.strip()[:500]}")