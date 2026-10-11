from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.secrets import is_denied
from hoseki.tools.base import ToolResult


class FindFilesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    glob: str
    path: str = "."
    max_results: int = Field(500, ge=1, le=5000)


def find_files(args: FindFilesArgs, ctx: ToolContext) -> ToolResult:
    root = ctx.check_path_allowed(args.path)
    if not root.exists():
        raise ToolError(f"not found: {args.path}")
    if not root.is_dir():
        raise ToolError(f"not a directory: {args.path}")

    max_results = min(args.max_results, ctx.limits.max_find_results)
    matches: list[str] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        try:
            dir_rel = Path(dirpath).relative_to(ctx.jail.root)
        except ValueError:
            dirnames[:] = []
            continue

        dirnames[:] = [
            d
            for d in dirnames
            if not is_denied(str(dir_rel / d), ctx.secrets.deny_globs)
        ]

        for name in filenames:
            p = Path(dirpath) / name
            try:
                rel = p.relative_to(ctx.jail.root)
            except ValueError:
                continue
            if is_denied(str(rel), ctx.secrets.deny_globs):
                continue
            if rel.match(args.glob):
                matches.append(str(rel))
                if len(matches) >= max_results:
                    truncated = True
                    break

        if truncated:
            break

    matches.sort()
    if not matches:
        return ToolResult(ok=True, output="(no matches)")
    return ToolResult(ok=True, output="\n".join(matches), truncated=truncated)