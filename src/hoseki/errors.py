"""Exception hierarchy for Hoseki."""
from __future__ import annotations


class HosekiError(Exception):
    """Base class for all Hoseki errors."""


class ConfigError(HosekiError):
    """Invalid or missing configuration."""


class JailError(HosekiError):
    """A path escaped the workspace root, or could not be resolved safely."""


class AuthError(HosekiError):
    """Authentication or origin check failed."""


class ToolError(HosekiError):
    """A tool failed in a way that should be reported back to the caller."""


class ToolNotFound(ToolError):
    """Unknown tool name."""


class ToolValidationError(ToolError):
    """Arguments did not match the tool schema."""


class LimitExceeded(ToolError):
    """A configured limit was hit."""


class SecretDenied(ToolError):
    """The requested path matches the secrets deny-list."""