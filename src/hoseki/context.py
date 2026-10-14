"""Tool execution context."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hoseki.approval import ApprovalGate
from hoseki.audit import AuditLog
from hoseki.config import (
    CommandsConfig,
    IgnoreConfig,
    LimitsConfig,
    SandboxConfig,
    SecretsConfig,
)
from hoseki.errors import SecretDenied
from hoseki.ignore import IgnoreRules
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
    ignore: IgnoreConfig

    def check_path_allowed(self, rel: str) -> Path:
        abs_path = self.jail.resolve(rel)
        rel_from_root = self.jail.relative(abs_path)
        if rel_from_root and is_denied(rel_from_root, self.secrets.deny_globs):
            raise SecretDenied(
                f"access to {rel_from_root!r} is denied by the secrets policy"
            )
        return abs_path

    def ignore_rules(self) -> IgnoreRules:
        """Build a fresh IgnoreRules for this call. Cheap (one file read)."""
        return IgnoreRules(self.jail.root, self.ignore)