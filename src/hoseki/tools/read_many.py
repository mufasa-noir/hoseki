from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.tools.base import ToolResult


class ReadSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start_line: int = Field(1, ge=1)
    end_line: int | None = Field(None, ge=1)


class ReadManyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    files: list[ReadSpec] = Field(..., min_length=1, max_length=20)


def read_many(args: ReadManyArgs, ctx: ToolContext) -> ToolResult:
    """Read multiple files (or line ranges) in one call.

    Concatenates the outputs with clear separators. Each file is subject to
    the same per-file caps as `read_file`; the combined output is capped at
    `limits.max_output_bytes`.
    """
    sections: list[str] = []
    total_bytes = 0
    any_truncated = False
    errors: list[str] = []

    for spec in args.files:
        try:
            target = ctx.check_path_allowed(spec.path)
        except Exception as e:
            errors.append(f"# {spec.path}\n[error: {e}]")
            continue

        if not target.exists():
            errors.append(f"# {spec.path}\n[error: not found]")
            continue
        if target.is_dir():
            errors.append(f"# {spec.path}\n[error: is a directory]")
            continue

        try:
            size = target.stat().st_size
        except OSError as e:
            errors.append(f"# {spec.path}\n[error: stat failed: {e}]")
            continue
        if size > ctx.limits.max_file_bytes:
            errors.append(
                f"# {spec.path}\n[error: too large ({size} bytes > "
                f"{ctx.limits.max_file_bytes})]"
            )
            continue

        try:
            raw = target.read_bytes()
        except OSError as e:
            errors.append(f"# {spec.path}\n[error: read failed: {e}]")
            continue
        if b"\x00" in raw[:8192]:
            errors.append(f"# {spec.path}\n[error: binary file refused]")
            continue

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        total_lines = len(lines)

        if spec.start_line > total_lines:
            errors.append(
                f"# {spec.path}\n[error: start_line {spec.start_line} "
                f"beyond EOF (total {total_lines})]"
            )
            continue
        end = total_lines if spec.end_line is None else min(
            spec.end_line, total_lines
        )
        if end < spec.start_line:
            errors.append(
                f"# {spec.path}\n[error: end_line before start_line]"
            )
            continue

        chunk = lines[spec.start_line - 1 : end]
        file_truncated = False
        if len(chunk) > ctx.limits.max_read_lines:
            chunk = chunk[: ctx.limits.max_read_lines]
            file_truncated = True

        last = spec.start_line + len(chunk) - 1 if chunk else spec.start_line - 1
        width = len(str(last))
        body = "\n".join(
            f"{i:>{width}}  {line}"
            for i, line in enumerate(chunk, start=spec.start_line)
        )
        header = (
            f"# {spec.path} (lines {spec.start_line}-{last} "
            f"of {total_lines})"
            f"{'  [truncated]' if file_truncated else ''}"
        )
        section = f"{header}\n{body}"
        total_bytes += len(section.encode("utf-8"))
        if total_bytes > ctx.limits.max_output_bytes:
            any_truncated = True
            sections.append(
                f"{section}\n\n# [combined output truncated — "
                f"remaining files not shown]"
            )
            break
        if file_truncated:
            any_truncated = True
        sections.append(section)

    if not sections and not errors:
        raise ToolError("no readable files in request")

    output = "\n\n".join(sections + (["\n\n".join(errors)] if errors else []))
    return ToolResult(ok=True, output=output, truncated=any_truncated)