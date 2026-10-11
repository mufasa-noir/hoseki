"""Tool primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from hoseki.context import ToolContext


@dataclass
class ToolResult:
    ok: bool
    output: str = ""
    truncated: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        if self.ok:
            return {
                "ok": True,
                "output": self.output,
                "truncated": self.truncated,
            }
        return {"ok": False, "error": self.error}


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[BaseModel, ToolContext], ToolResult]

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_model.model_json_schema(),
        }