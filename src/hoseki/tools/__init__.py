"""Tool registry."""
from __future__ import annotations

from hoseki.tools.base import Tool, ToolResult
from hoseki.tools.find_files import FindFilesArgs, find_files
from hoseki.tools.grep import GrepArgs, grep
from hoseki.tools.list_dir import ListDirArgs, list_dir
from hoseki.tools.read_file import ReadFileArgs, read_file
from hoseki.tools.read_many import ReadManyArgs, read_many
from hoseki.tools.tree import TreeArgs, tree
from hoseki.tools.write_file import WriteFileArgs, write_file
from hoseki.tools.apply_patch import ApplyPatchArgs, apply_patch
from hoseki.tools.run_cmd import RunCmdArgs, run_cmd

TOOLS: dict[str, Tool] = {}


def _register(tool: Tool) -> None:
    TOOLS[tool.name] = tool


_register(Tool(
    name="list_dir",
    description="Shallow directory listing. Symlinks are shown with their "
                "target but never followed. Ignored entries are skipped "
                "unless respect_ignore=false.",
    args_model=ListDirArgs,
    handler=list_dir,
))

_register(Tool(
    name="tree",
    description="Recursive directory tree with box-drawing characters. "
                "Skips .gitignore'd paths and common build/cache dirs by "
                "default, and prints a count summary. Prefer this over "
                "multiple list_dir calls when exploring a repo layout.",
    args_model=TreeArgs,
    handler=tree,
))

_register(Tool(
    name="read_file",
    description="Read a UTF-8 text file as numbered lines, with optional "
                "start_line/end_line. Capped by max_read_lines and "
                "max_output_bytes. Binary files and denied secret paths "
                "are refused.",
    args_model=ReadFileArgs,
    handler=read_file,
))

_register(Tool(
    name="read_many",
    description="Read multiple files or line ranges in a single call "
                "(up to 20). Concatenates outputs with clear separators. "
                "Use this instead of multiple read_file calls when you "
                "already know which files you need.",
    args_model=ReadManyArgs,
    handler=read_many,
))

_register(Tool(
    name="grep",
    description="Regex search across files. Uses ripgrep when available, "
                "otherwise a pure-Python walker. Skips .gitignore'd paths, "
                "common build/cache dirs, binary files, oversized files, "
                "and denied secret paths.",
    args_model=GrepArgs,
    handler=grep,
))

_register(Tool(
    name="find_files",
    description="Find files by PurePath.match-style glob (e.g. '**/*.py'). "
                "Skips .gitignore'd paths and common build/cache dirs. "
                "Never follows symlinks.",
    args_model=FindFilesArgs,
    handler=find_files,
))

_register(Tool(
    name="write_file",
    description=(
        "Write or append to a UTF-8 text file. Requires human approval in "
        "the daemon terminal; shows a unified diff before writing. "
        "mode='w' (default) overwrites; mode='a' appends. Use mode='a' to "
        "build a large file across multiple calls."
    ),
    args_model=WriteFileArgs,
    handler=write_file,
))

_register(Tool(
    name="apply_patch",
    description="Apply a unified diff to an existing file. Requires human "
                "approval. Fails cleanly if the patch does not apply.",
    args_model=ApplyPatchArgs,
    handler=apply_patch,
))

_register(Tool(
    name="run_cmd",
    description="Run a shell command, subject to the command allow-list. "
                "Requires human approval. Prefers Docker sandbox with no "
                "network; refuses to run on the host unless explicitly "
                "enabled in config.",
    args_model=RunCmdArgs,
    handler=run_cmd,
))


__all__ = ["TOOLS", "Tool", "ToolResult"]