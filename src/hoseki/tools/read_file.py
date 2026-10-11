from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(None, ge=1)


def read_file(args: ReadFileArgs, ctx: ToolContext) -> ToolResult:
    target = ctx.check_path_allowed(args.path)

    if not target.exists():
        raise ToolError(f"not found: {args.path}")
    if target.is_dir():
        raise ToolError(f"is a directory: {args.path}")

    try:
        size = target.stat().st_size
    except OSError as e:
        raise ToolError(f"stat failed for {args.path}: {e}")

    if size > ctx.limits.max_file_bytes:
        raise LimitExceeded(
            f"file too large ({size} bytes > max_file_bytes "
            f"{ctx.limits.max_file_bytes})"
        )

    try:
        raw = target.read_bytes()
    except OSError as e:
        raise ToolError(f"read failed for {args.path}: {e}")

    if b"\x00" in raw[:8192]:
        raise ToolError(f"binary file refused: {args.path}")

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    total = len(lines)

    if total == 0:
        return ToolResult(ok=True, output=f"# {args.path} (empty file)")

    if args.start_line > total:
        return ToolResult(
            ok=True,
            output=(
                f"# {args.path}: start_line {args.start_line} is beyond EOF "
                f"(total {total})"
            ),
        )

    end = total if args.end_line is None else min(args.end_line, total)
    if end < args.start_line:
        raise ToolError(
            f"end_line ({end}) is before start_line ({args.start_line})"
        )

    chunk = lines[args.start_line - 1 : end]
    truncated = False
    if len(chunk) > ctx.limits.max_read_lines:
        chunk = chunk[: ctx.limits.max_read_lines]
        truncated = True

    if not chunk:
        body = ""
        last_line = args.start_line - 1
    else:
        last_line = args.start_line + len(chunk) - 1
        width = len(str(last_line))
        body = "\n".join(
            f"{i:>{width}}  {line}"
            for i, line in enumerate(chunk, start=args.start_line)
        )

    # Byte cap (approximate; keeps whole lines).
    encoded = body.encode("utf-8")
    if len(encoded) > ctx.limits.max_output_bytes:
        cut = body[: ctx.limits.max_output_bytes]
        last_nl = cut.rfind("\n")
        if last_nl > 0:
            cut = cut[:last_nl]
        body = cut
        truncated = True

    header = f"# {args.path} (lines {args.start_line}-{last_line} of {total})"
    if truncated:
        header += " [truncated]"

    output = header if not body else f"{header}\n{body}"
    return ToolResult(ok=True, output=output, truncated=truncated)