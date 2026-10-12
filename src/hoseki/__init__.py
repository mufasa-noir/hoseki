"""Tool registry."""
from __future__ import annotations

__version__ = "0.1.0"

from hoseki.tools.base import Tool, ToolResult
from hoseki.tools.find_files import FindFilesArgs, find_files
from hoseki.tools.grep import GrepArgs, grep
from hoseki.tools.list_dir import ListDirArgs, list_dir
from hoseki.tools.read_file import ReadFileArgs, read_file
from hoseki.tools.write_file import WriteFileArgs, write_file
from hoseki.tools.apply_patch import ApplyPatchArgs, apply_patch
from hoseki.tools.run_cmd import RunCmdArgs, run_cmd


TOOLS: dict[str, Tool] = {}


def _register(tool: Tool) -> None:
    TOOLS[tool.name] = tool


_register(Tool(
    name="list_dir",
    description="List directory entries under the workspace root. Symlinks "
                "are shown but never followed. Depth is capped by config.",
    args_model=ListDirArgs,
    handler=list_dir,
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
    name="grep",
    description="Regex search across files. Uses ripgrep when available, "
                "otherwise a pure-Python walker. Skips binary files, "
                "oversized files, and denied secret paths.",
    args_model=GrepArgs,
    handler=grep,
))

_register(Tool(
    name="find_files",
    description="Find files by PurePath.match-style glob (e.g. '**/*.py'). "
                "Never follows symlinks.",
    args_model=FindFilesArgs,
    handler=find_files,
))

_register(Tool(
    name="write_file",
    description="Write a UTF-8 text file. Requires human approval in the "
                "daemon terminal. Shows a unified diff before writing.",
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


__all__ = ["__version__", "TOOLS", "Tool", "ToolResult"]