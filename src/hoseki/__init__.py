"""Hoseki — approval-gated filesystem and shell tools for LLM agents."""
from __future__ import annotations

__version__ = "0.3.1"

# Single source of truth for the tool registry lives in hoseki.tools.
from hoseki.tools import TOOLS, Tool, ToolResult

__all__ = ["__version__", "TOOLS", "Tool", "ToolResult"]