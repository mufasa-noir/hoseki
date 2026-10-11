from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.diff import render_new_file, render_unified_diff
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class WriteFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    content: str


def write_file(args: WriteFileArgs, ctx: ToolContext) -> ToolResult:
    # Sanity-check size before we do anything else.
    content_bytes = args.content.encode("utf-8")
    if len(content_bytes) > ctx.limits.max_output_bytes:
        raise LimitExceeded(
            f"content is {len(content_bytes)} bytes, over max_output_bytes "
            f"({ctx.limits.max_output_bytes})"
        )

    target = ctx.check_path_allowed(args.path)

    if target.exists():
        if not target.is_file():
            raise ToolError(f"not a regular file: {args.path}")
        try:
            old = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ToolError(f"cannot read existing file for diff: {e}")
        diff = render_unified_diff(old, args.content, args.path)
        if not diff:
            return ToolResult(
                ok=True,
                output=f"{args.path}: no changes (content identical)",
            )
    else:
        diff = render_new_file(args.content, args.path)

    decision = ctx.approval.request(
        ApprovalRequest(
            kind="write_file",
            summary=(
                f"write {args.path} "
                f"({len(content_bytes)} bytes, "
                f"{'new file' if not target.exists() else 'overwrite'})"
            ),
            body=diff,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="write denied by operator")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args.content, encoding="utf-8")
    except OSError as e:
        raise ToolError(f"write failed for {args.path}: {e}")

    return ToolResult(
        ok=True,
        output=f"wrote {args.path} ({len(content_bytes)} bytes)",
    )