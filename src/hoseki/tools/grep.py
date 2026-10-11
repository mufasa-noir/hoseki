from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.secrets import is_denied
from hoseki.tools.base import ToolResult


class GrepArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str
    path: str = "."
    glob: str | None = None
    max_results: int = Field(100, ge=1, le=1000)


def grep(args: GrepArgs, ctx: ToolContext) -> ToolResult:
    try:
        re.compile(args.pattern)
    except re.error as e:
        raise ToolError(f"invalid regex: {e}")

    target = ctx.check_path_allowed(args.path)
    if not target.exists():
        raise ToolError(f"not found: {args.path}")

    max_results = min(args.max_results, ctx.limits.max_grep_results)
    rg = shutil.which("rg")
    if rg is not None:
        result = _grep_rg(rg, args.pattern, target, args.glob, max_results, ctx)
        if result is not None:
            return result

    return _grep_py(args.pattern, target, args.glob, max_results, ctx)


def _grep_rg(
    rg: str,
    pattern: str,
    target: Path,
    glob_pattern: str | None,
    max_results: int,
    ctx: ToolContext,
) -> ToolResult | None:
    cmd = [
        rg,
        "--no-heading",
        "--line-number",
        "--color",
        "never",
        "--with-filename",
        "--max-columns",
        "500",
        "--max-columns-preview",
        "-e",
        pattern,
    ]
    if glob_pattern:
        cmd += ["--glob", glob_pattern]
    cmd.append(str(target))

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, check=False
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if proc.returncode not in (0, 1):
        return None

    lines = proc.stdout.splitlines()
    truncated = False
    if len(lines) > max_results:
        lines = lines[:max_results]
        truncated = True

    root_str = str(ctx.jail.root)
    cleaned: list[str] = []
    for line in lines:
        if line.startswith(root_str):
            line = line[len(root_str):].lstrip("/\\")
        cleaned.append(line)

    if not cleaned:
        return ToolResult(ok=True, output="(no matches)")
    return ToolResult(ok=True, output="\n".join(cleaned), truncated=truncated)


def _grep_py(
    pattern: str,
    target: Path,
    glob_pattern: str | None,
    max_results: int,
    ctx: ToolContext,
) -> ToolResult:
    regex = re.compile(pattern)
    results: list[str] = []
    truncated = False

    def scan_file(p: Path) -> bool:
        """Return True if max_results hit."""
        nonlocal truncated
        try:
            rel = p.relative_to(ctx.jail.root)
        except ValueError:
            return False
        rel_str = str(rel)
        if is_denied(rel_str, ctx.secrets.deny_globs):
            return False
        if glob_pattern and not rel.match(glob_pattern):
            return False

        try:
            size = p.stat().st_size
        except OSError:
            return False
        if size > ctx.limits.max_file_bytes:
            return False

        try:
            raw = p.read_bytes()
        except OSError:
            return False
        if b"\x00" in raw[:8192]:
            return False

        text = raw.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                preview = line[:500]
                results.append(f"{rel_str}:{i}:{preview}")
                if len(results) >= max_results:
                    truncated = True
                    return True
        return False

    if target.is_file():
        scan_file(target)
    else:
        stop = False
        for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
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
                if scan_file(Path(dirpath) / name):
                    stop = True
                    break
            if stop:
                break

    if not results:
        return ToolResult(ok=True, output="(no matches)")
    return ToolResult(ok=True, output="\n".join(results), truncated=truncated)