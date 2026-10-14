"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from hoseki import __version__
from hoseki.approval import ApprovalGate
from hoseki.audit import AuditLog
from hoseki.auth import (
    check_host,
    check_origin,
    get_or_create_token,
    verify_token,
)
from hoseki.config import Config
from hoseki.context import ToolContext
from hoseki.errors import (
    HosekiError,
    JailError,
    LimitExceeded,
    SecretDenied,
    ToolError,
    ToolNotFound,
    ToolValidationError,
)
from hoseki.jail import PathJail
from hoseki.secrets import redact
from hoseki.tools import TOOLS


class _RateLimiter:
    """In-memory sliding-window limiter. Single-process only."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self._hits: deque[float] = deque()

    def check(self) -> bool:
        now = time.monotonic()
        cutoff = now - 60.0
        while self._hits and self._hits[0] < cutoff:
            self._hits.popleft()
        if len(self._hits) >= self.per_minute:
            return False
        self._hits.append(now)
        return True


def _summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Short, log-safe summary of a tool result for the audit log."""
    if result.get("ok"):
        out = result.get("output", "")
        return {
            "ok": True,
            "output_bytes": len(out.encode("utf-8")),
            "truncated": bool(result.get("truncated")),
            "preview": out[:200],
        }
    return {"ok": False, "error": str(result.get("error", ""))[:300]}


def create_app(config: Config) -> FastAPI:
    token = get_or_create_token(config.token_file)
    jail = PathJail(config.workspace_root)
    audit = AuditLog(config.audit_log)
    limiter = _RateLimiter(config.limits.max_calls_per_minute)
    approval = ApprovalGate(audit=audit)

    ctx = ToolContext(
        jail=jail,
        limits=config.limits,
        secrets=config.secrets,
        audit=audit,
        approval=approval,
        commands=config.commands,
        sandbox=config.sandbox,
    )

    app = FastAPI(
        title="Hoseki",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # -------- middleware: Host, Origin, CORS --------
    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host")
        if not check_host(host, config.server):
            audit.append(
                "request_rejected",
                reason="bad_host",
                host=host,
                path=request.url.path,
            )
            return JSONResponse(
                {"ok": False, "error": "invalid Host header"}, status_code=400
            )

        origin = request.headers.get("origin")
        if not check_origin(
            origin, config.allowed_origins, config.allow_missing_origin
        ):
            audit.append(
                "request_rejected",
                reason="bad_origin",
                origin=origin,
                path=request.url.path,
            )
            return JSONResponse(
                {"ok": False, "error": "origin not allowed"}, status_code=403
            )

        if request.method == "OPTIONS":
            response: Response = Response(status_code=204)
        else:
            response = await call_next(request)

        if origin is not None:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )
            response.headers["Access-Control-Max-Age"] = "600"
            response.headers["Vary"] = "Origin"
        return response

    # -------- auth helper --------
    def require_auth(request: Request) -> None:
        if not verify_token(token, request.headers.get("authorization")):
            audit.append(
                "request_rejected",
                reason="bad_token",
                path=request.url.path,
            )
            raise HTTPException(status_code=401, detail="invalid bearer token")

    # -------- endpoints --------
    @app.get("/v1/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "hoseki", "version": __version__}

    @app.get("/v1/status")
    def status(request: Request) -> dict[str, Any]:
        require_auth(request)
        return {
            "ok": True,
            "service": "hoseki",
            "version": __version__,
            "workspace_root": str(config.workspace_root),
            "host": config.server.host,
            "port": config.server.port,
            "tools": sorted(TOOLS.keys()),
            "limits": {
                "max_file_bytes": config.limits.max_file_bytes,
                "max_read_lines": config.limits.max_read_lines,
                "max_output_bytes": config.limits.max_output_bytes,
                "max_calls_per_minute": config.limits.max_calls_per_minute,
            },
            "sandbox_mode": config.sandbox.mode,
            "command_allowlist_size": len(config.commands.allowlist),
        }

    @app.post("/v1/call")
    async def call(
        request: Request,
        payload: dict[str, Any] = Body(...),
    ) -> JSONResponse:
        require_auth(request)

        if not limiter.check():
            audit.append(
                "tool_call",
                name=payload.get("name"),
                id=payload.get("id"),
                ok=False,
                error="rate limit",
            )
            return JSONResponse(
                {
                    "id": payload.get("id"),
                    "ok": False,
                    "error": (
                        "rate limit exceeded "
                        f"({config.limits.max_calls_per_minute}/min)"
                    ),
                },
                status_code=200,
            )

        call_id = payload.get("id")
        name = payload.get("name")
        args_in = payload.get("args") or {}

        if not isinstance(name, str) or not name:
            return JSONResponse(
                {
                    "id": call_id,
                    "ok": False,
                    "error": "field 'name' is required and must be a string",
                },
                status_code=200,
            )

        tool = TOOLS.get(name)
        if tool is None:
            audit.append(
                "tool_call", id=call_id, name=name, ok=False,
                error="unknown tool",
            )
            return JSONResponse(
                {
                    "id": call_id,
                    "ok": False,
                    "error": f"unknown tool: {name!r}",
                },
                status_code=200,
            )

        # Strict validation.
        try:
            args = tool.args_model.model_validate(args_in)
        except ValidationError as e:
            audit.append(
                "tool_call",
                id=call_id,
                name=name,
                args=args_in,
                ok=False,
                error="validation",
            )
            return JSONResponse(
                {
                    "id": call_id,
                    "ok": False,
                    "error": (
                        "invalid arguments: "
                        + "; ".join(
                            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                            for err in e.errors()
                        )
                    ),
                },
                status_code=200,
            )

        started = time.monotonic()
        try:
            # Run the handler in a worker thread so blocking terminal
            # approvals do not stall the event loop.
            result = await asyncio.to_thread(tool.handler, args, ctx)
        except (JailError, SecretDenied, LimitExceeded, ToolValidationError,
                ToolNotFound, ToolError) as e:
            payload_out = {"id": call_id, "ok": False, "error": str(e)}
        except HosekiError as e:
            payload_out = {"id": call_id, "ok": False, "error": str(e)}
        except Exception as e:  # pragma: no cover - defensive
            payload_out = {
                "id": call_id,
                "ok": False,
                "error": f"internal error: {type(e).__name__}: {e}",
            }
        else:
            d = result.to_dict()
            if d.get("ok") and config.secrets.redact:
                d["output"] = redact(d.get("output", ""), config.secrets)
            payload_out = {"id": call_id, **d}

        elapsed_ms = int((time.monotonic() - started) * 1000)
        audit.append(
            "tool_call",
            id=call_id,
            name=name,
            args=args.model_dump(),
            duration_ms=elapsed_ms,
            result=_summarize(payload_out),
        )

        return JSONResponse(payload_out, status_code=200)

    audit.append(
        "daemon_start",
        version=__version__,
        workspace_root=str(config.workspace_root),
        host=config.server.host,
        port=config.server.port,
    )

    return app