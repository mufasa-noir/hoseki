"""Configuration loading and defaults."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from hoseki.errors import ConfigError


DEFAULT_CONFIG_PATHS = [
    Path("./config.toml"),
    Path.home() / ".config" / "hoseki" / "config.toml",
]


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class LimitsConfig:
    max_file_bytes: int = 2_000_000
    max_read_lines: int = 2000
    max_output_bytes: int = 200_000
    max_calls_per_minute: int = 60
    max_list_depth: int = 5
    max_grep_results: int = 500
    max_find_results: int = 2000


DEFAULT_DENY_GLOBS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
    ".git/config", ".aws/credentials", ".netrc", ".npmrc",
    ".ssh/*", ".gnupg/*", "*.kdbx",
]


@dataclass
class SecretsConfig:
    deny_globs: list[str] = field(default_factory=lambda: list(DEFAULT_DENY_GLOBS))
    redact: bool = True


@dataclass
class IgnoreConfig:
    use_defaults: bool = True
    respect_gitignore: bool = True
    extra_dirs: list[str] = field(default_factory=list)
    extra_files: list[str] = field(default_factory=list)


@dataclass
class CommandsConfig:
    allowlist: list[str] = field(default_factory=list)
    unsafe_host_exec: bool = False
    default_timeout: int = 60
    max_timeout: int = 600
    max_output_bytes: int = 200_000


@dataclass
class SandboxConfig:
    mode: str = "auto"
    docker_image: str = "python:3.11-slim"
    network: bool = False
    workspace_read_only: bool = True
    memory: str = "512m"
    pids_limit: int = 256


@dataclass
class Config:
    workspace_root: Path
    server: ServerConfig
    limits: LimitsConfig
    secrets: SecretsConfig
    ignore: IgnoreConfig
    commands: CommandsConfig
    sandbox: SandboxConfig
    token_file: Path
    audit_log: Path
    allowed_origins: list[str]
    allow_missing_origin: bool = True
    config_path: Path | None = None

    @classmethod
    def load(
        cls,
        path: Path | None = None,
        overrides: dict | None = None,
    ) -> "Config":
        data: dict = {}
        chosen: Path | None = None

        if path is not None:
            path = Path(path).expanduser()
            if not path.exists():
                raise ConfigError(f"config file not found: {path}")
            chosen = path
        else:
            for candidate in DEFAULT_CONFIG_PATHS:
                if candidate.exists():
                    chosen = candidate
                    break

        if chosen is not None:
            with chosen.open("rb") as f:
                data = tomllib.load(f)

        server = ServerConfig(**data.get("server", {}))
        limits = LimitsConfig(**data.get("limits", {}))

        secrets_raw = data.get("secrets", {})
        secrets = SecretsConfig(
            deny_globs=secrets_raw.get("deny_globs", list(DEFAULT_DENY_GLOBS)),
            redact=bool(secrets_raw.get("redact", True)),
        )

        ignore = IgnoreConfig(**data.get("ignore", {}))
        commands = CommandsConfig(**data.get("commands", {}))
        sandbox = SandboxConfig(**data.get("sandbox", {}))
        if sandbox.mode not in ("auto", "docker", "host", "refuse"):
            raise ConfigError(
                f"sandbox.mode must be one of auto/docker/host/refuse, "
                f"got {sandbox.mode!r}"
            )

        root_str = data.get("workspace", {}).get("root")
        if overrides and overrides.get("workspace_root"):
            root_str = str(overrides["workspace_root"])
        if not root_str:
            raise ConfigError(
                "config: [workspace].root is required "
                "(or pass --workspace on the command line)"
            )
        workspace_root = Path(os.path.expanduser(root_str)).resolve()

        token_file = Path(os.path.expanduser(
            data.get("auth", {}).get("token_file", "~/.hoseki/token")
        ))
        audit_log = Path(os.path.expanduser(
            data.get("audit", {}).get("path", "~/.hoseki/audit.jsonl")
        ))

        extension = data.get("extension", {})
        allowed_origins = extension.get(
            "allowed_origins", ["chrome-extension://*", "moz-extension://*"]
        )
        allow_missing_origin = bool(extension.get("allow_missing_origin", True))

        if overrides:
            if overrides.get("host"):
                server.host = overrides["host"]
            if overrides.get("port"):
                server.port = int(overrides["port"])

        if server.host not in ("127.0.0.1", "::1", "localhost"):
            raise ConfigError(
                f"refusing to bind to {server.host!r}; only loopback is allowed"
            )

        return cls(
            workspace_root=workspace_root,
            server=server,
            limits=limits,
            secrets=secrets,
            ignore=ignore,
            commands=commands,
            sandbox=sandbox,
            token_file=token_file,
            audit_log=audit_log,
            allowed_origins=list(allowed_origins),
            allow_missing_origin=allow_missing_origin,
            config_path=chosen,
        )