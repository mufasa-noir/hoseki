from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hoseki.context import ToolContext
from hoseki.errors import ToolError
from hoseki.ignore import DEFAULT_IGNORE_DIRS
from hoseki.secrets import is_denied
from hoseki.tools.base import ToolResult


class GrepArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str
    path: str = "."
    glob: str | None = None
    max_results: int = Field(100, ge=1, le=1000)
    context: int = Field(0, ge=0, le=10,
                        description="Lines of context before/after each match")
    mode: Literal["content", "files", "count"] = Field(
        "content",
        description="content = matching lines; files = only paths; "
                    "count = per-file match counts",
    )
    respect_ignore: bool = True


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
        result = _grep_rg(rg, args, target, max_results, ctx)
        if result is not None:
            return result
    return _grep_py(args, target, max_results, ctx)


def _build_rg_cmd(rg: str, args: GrepArgs, target: Path,
                  ctx: ToolContext) -> list[str]:
    cmd = [rg, "--color", "never", "--no-heading", "--with-filename"]
    if args.mode == "files":
        cmd.append("--files-with-matches")
    elif args.mode == "count":
        cmd.append("--count-matches")
    else:
        cmd.extend(["--line-number", "--max-columns", "500",
                    "--max-columns-preview"])
        if args.context > 0:
            cmd.extend(["-C", str(args.context)])

    cmd.extend(["-e", args.pattern])

    if args.respect_ignore:
        for d in DEFAULT_IGNORE_DIRS:
            cmd.extend(["--glob", f"!{d}/**"])
        for d in ctx.ignore.extra_dirs:
            cmd.extend(["--glob", f"!{d}/**"])
        for f in ctx.ignore.extra_files:
            cmd.extend(["--glob", f"!{f}"])
    else:
        cmd.append("--no-ignore")

    if args.glob:
        cmd.extend(["--glob", args.glob])
    cmd.append(str(target))
    return cmd


def _grep_rg(rg: str, args: GrepArgs, target: Path,
             max_results: int, ctx: ToolContext) -> ToolResult | None:
    cmd = _build_rg_cmd(rg, args, target, ctx)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            check=False, stdin=subprocess.DEVNULL,
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
    cleaned = []
    for line in lines:
        if line.startswith(root_str):
            line = line[len(root_str):].lstrip("/\\")
        cleaned.append(line)

    if not cleaned:
        return ToolResult(ok=True, output="(no matches)")
    return ToolResult(ok=True, output="\n".join(cleaned), truncated=truncated)


def _grep_py(args: GrepArgs, target: Path, max_results: int,
             ctx: ToolContext) -> ToolResult:
    regex = re.compile(args.pattern)
    rules = ctx.ignore_rules() if args.respect_ignore else None

    # For "files" mode, dedupe by path.
    files_hit: list[str] = []
    content_lines: list[str] = []
    count_lines: list[str] = []
    truncated = False

    def emit(file_rel: str, line_no: int, line: str,
             file_lines: list[str]) -> None:
        nonlocal truncated
        if args.mode == "files":
            if file_rel not in files_hit:
                files_hit.append(file_rel)
        elif args.mode == "count":
            # handled per-file below; nothing here
            pass
        else:
            if args.context == 0:
                content_lines.append(f"{file_rel}:{line_no}:{line[:500]}")
            else:
                lo = max(0, line_no - 1 - args.context)
                hi = min(len(file_lines), line_no + args.context)
                content_lines.append(f"{file_rel}-{line_no}- (context)")
                for i in range(lo, hi):
                    marker = ":" if i == line_no - 1 else "-"
                    content_lines.append(
                        f"{file_rel}{marker}{i + 1}{marker}{file_lines[i][:500]}"
                    )
                content_lines.append("")

    def scan(p: Path) -> bool:
        nonlocal truncated
        try:
            rel = p.relative_to(ctx.jail.root)
        except ValueError:
            return False
        if is_denied(str(rel), ctx.secrets.deny_globs):
            return False
        if rules is not None and rules.is_ignored_file(p):
            return False
        if args.glob and not rel.match(args.glob):
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
        file_lines = text.splitlines()
        matches = 0
        for i, line in enumerate(file_lines, start=1):
            if regex.search(line):
                matches += 1
                emit(str(rel), i, line, file_lines)
        if matches and args.mode == "count":
            count_lines.append(f"{rel}:{matches}")
        if args.mode == "files":
            return len(files_hit) >= max_results
        if args.mode == "content":
            return len(content_lines) >= max_results
        return False

    if target.is_file():
        scan(target)
    else:
        for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
            if rules is not None:
                dirnames[:] = [
                    d for d in dirnames
                    if not rules.is_ignored_dir(Path(dirpath) / d)
                ]
            try:
                dir_rel = Path(dirpath).relative_to(ctx.jail.root)
            except ValueError:
                dirnames[:] = []
                continue
            dirnames[:] = [
                d for d in dirnames
                if not is_denied(str(dir_rel / d), ctx.secrets.deny_globs)
            ]
            for name in filenames:
                if scan(Path(dirpath) / name):
                    truncated = True
                    break
            if truncated:
                break

    if args.mode == "files":
        lines = files_hit
    elif args.mode == "count":
        lines = count_lines
    else:
        lines = content_lines

    if not lines:
        return ToolResult(ok=True, output="(no matches)")
    if len(lines) > max_results:
        lines = lines[:max_results]
        truncated = True
    return ToolResult(ok=True, output="\n".join(lines), truncated=truncated)