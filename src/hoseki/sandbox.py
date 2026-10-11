"""Docker sandbox for run_cmd."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hoseki.config import SandboxConfig
from hoseki.errors import ToolError


@dataclass
class SandboxPlan:
    argv: list[str]
    container_workspace: str  # path *inside* the container
    mode: str                 # "docker" | "host"


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def build_docker_plan(
    workspace: Path,
    cwd_abs: Path,
    cmd: str,
    cfg: SandboxConfig,
) -> SandboxPlan:
    container_root = "/workspace"
    try:
        cwd_rel = cwd_abs.relative_to(workspace)
    except ValueError as e:
        raise ToolError(f"cwd escapes workspace: {cwd_abs}") from e

    container_cwd = container_root
    if str(cwd_rel) != ".":
        container_cwd = f"{container_root}/{cwd_rel.as_posix()}"

    mount = f"{workspace}:{container_root}"
    if cfg.workspace_read_only:
        mount += ":ro"

    argv: list[str] = [
        "docker", "run", "--rm",
        "--network", "none" if not cfg.network else "bridge",
        "-v", mount,
        "-w", container_cwd,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", cfg.memory,
        "--pids-limit", str(cfg.pids_limit),
        cfg.docker_image,
        "/bin/sh", "-lc", cmd,
    ]
    return SandboxPlan(argv=argv, container_workspace=container_cwd, mode="docker")


def build_host_plan(cmd: str, cwd_abs: Path) -> SandboxPlan:
    return SandboxPlan(
        argv=["/bin/sh", "-lc", cmd],
        container_workspace=str(cwd_abs),
        mode="host",
    )