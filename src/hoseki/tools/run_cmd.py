from __future__ import annotations

import shlex
import subprocess

from pydantic import BaseModel, ConfigDict, Field

from hoseki.approval import ApprovalRequest
from hoseki.context import ToolContext
from hoseki.errors import LimitExceeded, ToolError
from hoseki.sandbox import build_docker_plan, build_host_plan, docker_available
from hoseki.tools.base import ToolResult


class RunCmdArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cmd: str
    cwd: str = "."
    timeout: int = Field(60, ge=1, le=3600)


def _check_allowlist(cmd: str, allowlist: list[str]) -> None:
    """Deny unless the command starts with one of the allowlisted prefixes.

    Prefixes are matched against the *raw* command string, so multi-word
    prefixes like ``"git status"`` require an exact leading match.
    """
    if not allowlist:
        raise ToolError(
            "command allow-list is empty in config; refusing to run anything "
            "(add prefixes to [commands].allowlist)"
        )
    # Reject obvious shell-chaining that would smuggle past a prefix match.
    for token in (";", "&&", "||", "`", "$(", ">", "<", "\n"):
        if token in cmd:
            raise ToolError(
                f"command contains shell operator {token!r}; "
                "allow-listed commands must be single, un-chained invocations"
            )
    stripped = cmd.strip()
    for prefix in allowlist:
        if stripped == prefix or stripped.startswith(prefix + " "):
            return
    raise ToolError(
        f"command not in allow-list: {stripped!r} "
        f"(add an appropriate prefix to [commands].allowlist)"
    )


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text.encode("utf-8")) <= limit:
        return text, False
    cut = text[:limit]
    return cut + "\n…[truncated]", True


def run_cmd(args: RunCmdArgs, ctx: ToolContext) -> ToolResult:
    _check_allowlist(args.cmd, ctx.commands.allowlist)

    timeout = min(args.timeout, ctx.commands.max_timeout)
    cwd_abs = ctx.check_path_allowed(args.cwd)

    if not cwd_abs.is_dir():
        raise ToolError(f"cwd is not a directory: {args.cwd}")

    mode = ctx.sandbox.mode
    if mode == "refuse":
        raise ToolError("sandbox.mode = 'refuse'; run_cmd is disabled")

    if mode == "docker" and not docker_available():
        raise ToolError(
            "sandbox.mode = 'docker' but Docker is not available; refusing"
        )

    if mode == "auto":
        if docker_available():
            plan = build_docker_plan(
                ctx.jail.root, cwd_abs, args.cmd, ctx.sandbox
            )
        elif ctx.commands.unsafe_host_exec:
            plan = build_host_plan(args.cmd, cwd_abs)
        else:
            raise ToolError(
                "Docker is not available and unsafe_host_exec is false; "
                "refusing to run commands on the host"
            )
    elif mode == "docker":
        plan = build_docker_plan(ctx.jail.root, cwd_abs, args.cmd, ctx.sandbox)
    elif mode == "host":
        plan = build_host_plan(args.cmd, cwd_abs)
    else:  # pragma: no cover - guarded at config load
        raise ToolError(f"unknown sandbox.mode: {mode!r}")

    body = (
        f"mode:    {plan.mode}\n"
        f"cwd:     {args.cwd}\n"
        f"timeout: {timeout}s\n"
        f"argv:    {shlex.join(plan.argv)}\n"
    )
    decision = ctx.approval.request(
        ApprovalRequest(
            kind="run_cmd",
            summary=f"run {args.cmd!r} in {args.cwd} (mode={plan.mode})",
            body=body,
        )
    )
    if not decision.approved:
        return ToolResult(ok=False, error="command denied by operator")

    try:
        proc = subprocess.run(
            plan.argv,
            cwd=str(cwd_abs),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(
            ok=False,
            error=f"command timed out after {timeout}s",
        )
    except OSError as e:
        raise ToolError(f"failed to spawn command: {e}")

    out = proc.stdout or ""
    err = proc.stderr or ""
    combined = out
    if err:
        combined += ("\n" if combined else "") + "--- stderr ---\n" + err
    combined, trunc = _truncate(combined, ctx.commands.max_output_bytes)

    header = f"exit={proc.returncode}\n"
    return ToolResult(ok=True, output=header + combined, truncated=trunc)