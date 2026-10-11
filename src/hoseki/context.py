"""Tool execution context."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hoseki.approval import ApprovalGate
from hoseki.audit import AuditLog
from hoseki.config import (
    CommandsConfig,
    LimitsConfig,
    SandboxConfig,
    SecretsConfig,
)
from hoseki.errors import SecretDenied
from hoseki.jail import PathJail
from hoseki.secrets import is_denied


@dataclass
class ToolContext:
    jail: PathJail
    limits: LimitsConfig
    secrets: SecretsConfig
    audit: AuditLog
    approval: ApprovalGate
    commands: CommandsConfig
    sandbox: SandboxConfig

    def check_path_allowed(self, rel: str) -> Path:
        """Resolve a path inside the jail and enforce the secrets deny-list."""
        abs_path = self.jail.resolve(rel)
        rel_from_root = self.jail.relative(abs_path)
        if rel_from_root and is_denied(rel_from_root, self.secrets.deny_globs):
            raise SecretDenied(
                f"access to {rel_from_root!r} is denied by the secrets policy"
            )
        return abs_path