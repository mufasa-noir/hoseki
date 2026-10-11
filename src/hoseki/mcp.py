"""Minimal MCP (Model Context Protocol) server over stdio.

Reuses the same TOOLS registry and ToolContext as the HTTP daemon, so the
path jail, secrets policy, limits, and approval gate are identical. Writes
and commands still block on the terminal.

Transport: newline-delimited JSON-RPC 2.0 on stdin/stdout. No external
dependencies.
"""
from __future__ import annotations

import json
import sys
import traceback
from typing import Any, IO

from hoseki import __version__
from hoseki.config import Config
from hoseki.errors import HosekiError
from hoseki.tools import TOOLS


PROTOCOL_VERSION = "2024-11-05"


def _read_message(stdin: IO[str]) -> dict[str, Any] | None:
    line = stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def _write_message(stdout: IO[str], obj: dict[str, Any]) -> None:
    stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stdout.flush()


def _result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.args_model.model_json_schema(),
        }
        for t in TOOLS.values()
    ]


def _call_tool(name: str, arguments: dict[str, Any], ctx) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        return {
            "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
            "isError": True,
        }
    try:
        args = tool.args_model.model_validate(arguments or {})
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"invalid arguments: {e}"}],
            "isError": True,
        }
    try:
        result = tool.handler(args, ctx)
    except HosekiError as e:
        return {
            "content": [{"type": "text", "text": str(e)}],
            "isError": True,
        }
    except Exception as e:  # pragma: no cover
        return {
            "content": [{"type": "text", "text": f"internal error: {e}"}],
            "isError": True,
        }
    if not result.ok:
        return {
            "content": [{"type": "text", "text": result.error}],
            "isError": True,
        }
    return {
        "content": [{"type": "text", "text": result.output}],
        "isError": False,
    }


def serve_stdio(config: Config) -> int:
    # Reuse the app factory to get the fully-wired ToolContext (jail,
    # approval gate, audit log, secrets, limits).
    from hoseki.app import create_app  # local import to avoid a cycle

    app = create_app(config)
    # Pull the ctx out of the closure by rebuilding it here instead of
    # reaching into the app object. Keeps create_app honest about its API.
    from hoseki.approval import ApprovalGate
    from hoseki.audit import AuditLog
    from hoseki.context import ToolContext
    from hoseki.jail import PathJail

    audit = AuditLog(config.audit_log)
    gate = ApprovalGate(audit=audit)
    ctx = ToolContext(
        jail=PathJail(config.workspace_root),
        limits=config.limits,
        secrets=config.secrets,
        audit=audit,
        approval=gate,
        commands=config.commands,
        sandbox=config.sandbox,
    )

    stdin = sys.stdin
    stdout = sys.stdout
    while True:
        try:
            msg = _read_message(stdin)
        except json.JSONDecodeError as e:
            _write_message(stdout, _error(None, -32700, f"parse error: {e}"))
            continue
        if msg is None:
            return 0

        method = msg.get("method")
        req_id = msg.get("id")

        try:
            if method == "initialize":
                _write_message(stdout, _result(req_id, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "hoseki", "version": __version__},
                }))
            elif method == "notifications/initialized":
                # Notification: no response.
                continue
            elif method == "tools/list":
                _write_message(stdout, _result(req_id, {"tools": _tool_list()}))
            elif method == "tools/call":
                params = msg.get("params") or {}
                out = _call_tool(
                    str(params.get("name") or ""),
                    params.get("arguments") or {},
                    ctx,
                )
                _write_message(stdout, _result(req_id, out))
            elif method == "shutdown":
                _write_message(stdout, _result(req_id, None))
                return 0
            elif method is None and req_id is not None:
                _write_message(stdout, _error(req_id, -32600, "no method"))
            else:
                if req_id is not None:
                    _write_message(stdout, _error(
                        req_id, -32601, f"method not found: {method!r}"
                    ))
        except Exception as e:  # pragma: no cover - defensive
            tb = traceback.format_exc(limit=3)
            if req_id is not None:
                _write_message(stdout, _error(
                    req_id, -32603, f"internal error: {e}", data=tb
                ))
    return 0