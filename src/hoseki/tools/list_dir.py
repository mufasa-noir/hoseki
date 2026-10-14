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
    respect_ignore: bool = True


_LINE_CAP = 5000


def list_dir(args: ListDirArgs, ctx: ToolContext) -> ToolResult:
    max_depth = min(args.depth, ctx.limits.max_list_depth)
    target = ctx.check_path_allowed(args.path)

    if not target.exists():
        raise ToolError(f"not found: {args.path}")
    if not target.is_dir():
        raise ToolError(f"not a directory: {args.path}")

    rules = ctx.ignore_rules() if args.respect_ignore else None
    lines: list[str] = []
    truncated = False
    ignored_count = 0

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal truncated, ignored_count
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

            # Symlinks: show target and don't follow.
            if entry.is_symlink():
                lines.append(f"{prefix}{_symlink_label(entry, ctx)}")
                continue

            try:
                rel = entry.relative_to(ctx.jail.root)
            except ValueError:
                lines.append(f"{prefix}{entry.name} (outside workspace)")
                continue

            if is_denied(str(rel), ctx.secrets.deny_globs):
                lines.append(f"{prefix}{entry.name} (hidden by secrets policy)")
                continue

            if rules is not None and entry.is_dir():
                if rules.is_ignored_dir(entry):
                    ignored_count += 1
                    continue
            if rules is not None and entry.is_file():
                if rules.is_ignored_file(entry):
                    ignored_count += 1
                    continue

            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                if depth < max_depth:
                    walk(entry, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}{entry.name}")

    walk(target, "", 1)

    if not lines:
        output = "(empty directory)"
    else:
        output = "\n".join(lines)

    if ignored_count:
        output += f"\n\n({ignored_count} entries skipped by ignore rules)"

    return ToolResult(ok=True, output=output, truncated=truncated)


def _symlink_label(entry: Path, ctx: ToolContext) -> str:
    """Format a symlink as `name@ -> target`, flagging escapes and breaks."""
    name = entry.name
    try:
        raw_target = entry.readlink()
    except OSError:
        return f"{name}@ -> (unreadable)"

    try:
        resolved = entry.resolve(strict=True)
    except (OSError, RuntimeError):
        return f"{name}@ -> {raw_target} (broken)"

    try:
        rel_target = resolved.relative_to(ctx.jail.root)
        return f"{name}@ -> {rel_target.as_posix()}"
    except ValueError:
        return f"{name}@ -> {resolved}  [ESCAPES WORKSPACE]"