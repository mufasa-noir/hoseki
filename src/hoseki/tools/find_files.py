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
    respect_ignore: bool = True


def find_files(args: FindFilesArgs, ctx: ToolContext) -> ToolResult:
    root = ctx.check_path_allowed(args.path)
    if not root.exists():
        raise ToolError(f"not found: {args.path}")
    if not root.is_dir():
        raise ToolError(f"not a directory: {args.path}")

    rules = ctx.ignore_rules() if args.respect_ignore else None
    max_results = min(args.max_results, ctx.limits.max_find_results)

    matches: list[str] = []
    truncated = False

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if rules is not None:
            keep: list[str] = []
            for d in dirnames:
                abs_d = Path(dirpath) / d
                if not rules.is_ignored_dir(abs_d):
                    keep.append(d)
            dirnames[:] = keep

        try:
            dir_rel = Path(dirpath).relative_to(ctx.jail.root)
        except ValueError:
            dirnames[:] = []
            continue

        for name in filenames:
            p = Path(dirpath) / name
            try:
                rel = p.relative_to(ctx.jail.root)
            except ValueError:
                continue
            if is_denied(str(rel), ctx.secrets.deny_globs):
                continue
            if rules is not None and rules.is_ignored_file(p):
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