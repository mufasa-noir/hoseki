from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.secrets import is_denied
from hoseki.tools.base import ToolResult


class TreeArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = "."
    depth: int = Field(3, ge=1, le=20)
    max_lines: int = Field(500, ge=10, le=10000)
    show_sizes: bool = Field(True, description="Append human-readable file sizes")
    respect_ignore: bool = True


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def tree(args: TreeArgs, ctx: ToolContext) -> ToolResult:
    root = ctx.check_path_allowed(args.path)
    if not root.exists():
        raise ToolError(f"not found: {args.path}")
    if not root.is_dir():
        raise ToolError(f"not a directory: {args.path}")

    rules = ctx.ignore_rules() if args.respect_ignore else None

    lines: list[str] = [args.path if args.path != "." else "."]
    truncated = False
    dir_count = 0
    file_count = 0
    ignored_count = 0

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal truncated, dir_count, file_count, ignored_count
        if truncated or depth > args.depth:
            return
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except OSError as e:
            lines.append(f"{prefix}[error: {e}]")
            return

        visible: list[Path] = []
        for entry in entries:
            try:
                rel = entry.relative_to(ctx.jail.root)
            except ValueError:
                continue
            if is_denied(str(rel), ctx.secrets.deny_globs):
                ignored_count += 1
                continue
            if rules is not None:
                if entry.is_dir() and rules.is_ignored_dir(entry):
                    ignored_count += 1
                    continue
                if entry.is_file() and rules.is_ignored_file(entry):
                    ignored_count += 1
                    continue
            visible.append(entry)

        for idx, entry in enumerate(visible):
            if len(lines) >= args.max_lines:
                truncated = True
                return
            last = idx == len(visible) - 1
            branch = "└── " if last else "├── "
            next_prefix = prefix + ("    " if last else "│   ")

            if entry.is_symlink():
                lines.append(f"{prefix}{branch}{_symlink_label(entry, ctx)}")
                continue

            if entry.is_dir():
                dir_count += 1
                lines.append(f"{prefix}{branch}{entry.name}/")
                walk(entry, next_prefix, depth + 1)
            else:
                file_count += 1
                suffix = ""
                if args.show_sizes:
                    try:
                        suffix = f" [{_human_size(entry.stat().st_size)}]"
                    except OSError:
                        suffix = " [?]"
                lines.append(f"{prefix}{branch}{entry.name}{suffix}")

    walk(root, "", 1)
    if truncated:
        lines.append("…[truncated]")

    summary: list[str] = [
        f"{dir_count} director{'y' if dir_count == 1 else 'ies'}",
        f"{file_count} file{'s' if file_count != 1 else ''}",
    ]
    if ignored_count:
        summary.append(f"{ignored_count} ignored")
    lines.append("")
    lines.append(", ".join(summary))

    return ToolResult(ok=True, output="\n".join(lines), truncated=truncated)


def _symlink_label(entry: Path, ctx: ToolContext) -> str:
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