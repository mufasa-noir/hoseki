from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ReadFileArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(None, ge=1)
    mode: Literal["full", "outline"] = Field(
        "full",
        description="full = numbered lines; outline = declarations only",
    )
    compact: bool = Field(
        False,
        description="Drop the line-number prefix (smaller output, "
                    "but no line numbers for later patches)",
    )


# Language-agnostic declaration patterns. Order matters: more specific first.
_OUTLINE_PATTERNS = [
    # Python
    re.compile(r"^\s*(?:async\s+)?def\s+\w+"),
    re.compile(r"^\s*class\s+\w+"),
    re.compile(r"^\s*@\w+"),
    # JS / TS / Java / C# / Go / Rust
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+\w+"),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?class\s+\w+"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+\w+\s*=\s*(?:async\s*)?\("),
    re.compile(r"^\s*(?:export\s+)?interface\s+\w+"),
    re.compile(r"^\s*(?:export\s+)?type\s+\w+\s*="),
    re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+\w+"),
    re.compile(r"^\s*(?:pub\s+)?struct\s+\w+"),
    re.compile(r"^\s*(?:pub\s+)?enum\s+\w+"),
    re.compile(r"^\s*(?:pub\s+)?trait\s+\w+"),
    re.compile(r"^\s*impl\s+"),
    re.compile(r"^\s*func\s+\w+"),
    re.compile(r"^\s*type\s+\w+\s+(?:struct|interface)"),
    # PHP
    re.compile(r"^\s*(?:public|private|protected|static|abstract|final|\s)*function\s+\w+"),
    # Ruby
    re.compile(r"^\s*def\s+\w+"),
    re.compile(r"^\s*(?:class|module)\s+[A-Z]\w*"),
    # Shell
    re.compile(r"^\s*function\s+\w+"),
    re.compile(r"^\s*[a-zA-Z_]\w*\s*\(\)\s*\{"),
    # Imports (useful for dependency scanning, small cost)
    re.compile(r"^\s*(?:import|from|require|use|include)\s+"),
]


def _is_declaration(line: str) -> bool:
    for pat in _OUTLINE_PATTERNS:
        if pat.match(line):
            return True
    return False


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

    if args.mode == "outline":
        return _outline(args, lines, total)

    # --- full mode ---
    if args.start_line > total:
        return ToolResult(
            ok=True,
            output=f"# {args.path}: start_line {args.start_line} is beyond EOF "
                   f"(total {total})",
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
        if args.compact:
            body = "\n".join(chunk)
        else:
            width = len(str(last_line))
            body = "\n".join(
                f"{i:>{width}}  {line}"
                for i, line in enumerate(chunk, start=args.start_line)
            )

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


def _outline(args: ReadFileArgs, lines: list[str], total: int) -> ToolResult:
    """Return only declaration lines with their line numbers."""
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        if _is_declaration(line):
            hits.append((i, line))

    if not hits:
        return ToolResult(
            ok=True,
            output=f"# {args.path} (outline, {total} lines): "
                   f"no declarations found — try mode='full'",
        )

    outline_hard_cap = 500
    truncated = False
    if len(hits) > outline_hard_cap:
        hits = hits[:outline_hard_cap]
        truncated = True

    width = len(str(hits[-1][0]))
    body = "\n".join(f"{i:>{width}}  {line[:200]}" for i, line in hits)
    header = (
        f"# {args.path} (outline: {len(hits)} of {total} lines)"
        f"{'  [truncated]' if truncated else ''}"
    )
    return ToolResult(ok=True, output=f"{header}\n{body}", truncated=truncated)