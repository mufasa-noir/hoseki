from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.secrets import is_denied
from hoseki.tools.base import ToolResult


class ListDirArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "."
    depth: int = Field(1, ge=1, le=10)


_LINE_CAP = 5000


def list_dir(args: ListDirArgs, ctx: ToolContext) -> ToolResult:
    max_depth = min(args.depth, ctx.limits.max_list_depth)
    target = ctx.check_path_allowed(args.path)

    if not target.exists():
        raise ToolError(f"not found: {args.path}")
    if not target.is_dir():
        raise ToolError(f"not a directory: {args.path}")

    lines: list[str] = []
    truncated = False

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal truncated
        if truncated:
            return
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except OSError as e:
            lines.append(f"{prefix}[error: {e}]")
            return

        for entry in entries:
            if len(lines) >= _LINE_CAP:
                truncated = True
                return

            try:
                rel = entry.relative_to(ctx.jail.root)
            except ValueError:
                lines.append(f"{prefix}{entry.name} (outside workspace)")
                continue

            if is_denied(str(rel), ctx.secrets.deny_globs):
                lines.append(f"{prefix}{entry.name} (hidden by secrets policy)")
                continue

            if entry.is_symlink():
                try:
                    entry.resolve(strict=True).relative_to(ctx.jail.root)
                    lines.append(f"{prefix}{entry.name}@")
                except (ValueError, OSError):
                    lines.append(
                        f"{prefix}{entry.name}@ (broken or escapes workspace)"
                    )
                continue

            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                if depth < max_depth:
                    walk(entry, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{entry.name}")

    walk(target, "", 1)
    output = "\n".join(lines) if lines else "(empty directory)"
    return ToolResult(ok=True, output=output, truncated=truncated)