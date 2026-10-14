from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.diff import render_append, render_new_file, render_unified_diff
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class WriteFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    content: str
    # "w" = overwrite (default), "a" = append.
    mode: Literal["w", "a"] = Field("w")


def write_file(args: WriteFileArgs, ctx: ToolContext) -> ToolResult:
    content_bytes = args.content.encode("utf-8")
    if len(content_bytes) > ctx.limits.max_output_bytes:
        raise LimitExceeded(
            f"content is {len(content_bytes)} bytes, over max_output_bytes "
            f"({ctx.limits.max_output_bytes})"
        )

    target = ctx.check_path_allowed(args.path)
    exists = target.exists()

    if exists:
        if not target.is_file():
            raise ToolError(f"not a regular file: {args.path}")

    if args.mode == "a":
        if not exists:
            # Appending to a nonexistent file creates it.
            diff = render_new_file(args.content, args.path)
            kind_desc = f"append to new file {args.path}"
        else:
            try:
                old_size = target.stat().st_size
            except OSError as e:
                raise ToolError(f"stat failed for {args.path}: {e}")
            diff = render_append(args.content, args.path)
            kind_desc = f"append {len(content_bytes)} bytes to {args.path} (was {old_size} bytes)"
    else:  # overwrite
        if exists:
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
            kind_desc = f"overwrite {args.path} ({len(content_bytes)} bytes)"
        else:
            diff = render_new_file(args.content, args.path)
            kind_desc = f"create {args.path} ({len(content_bytes)} bytes)"

    decision = ctx.approval.request(
        ApprovalRequest(
            kind="write_file",
            summary=kind_desc,
            body=diff,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="write denied by operator")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if args.mode == "a":
            with target.open("a", encoding="utf-8") as f:
                f.write(args.content)
        else:
            target.write_text(args.content, encoding="utf-8")
    except OSError as e:
        raise ToolError(f"write failed for {args.path}: {e}")

    verb = "appended to" if args.mode == "a" else "wrote"
    return ToolResult(
        ok=True,
        output=f"{verb} {args.path} ({len(content_bytes)} bytes)",
    )