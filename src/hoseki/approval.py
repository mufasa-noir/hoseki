"""Terminal approval gate.

The decision is made only by a human at the daemon's own terminal.
Nothing in the model's output, a file's contents, or an HTTP header can
pre-approve, bypass, or mutate this.
"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass


@dataclass
class ApprovalRequest:
    kind: str          # "write_file" | "apply_patch" | "run_cmd"
    summary: str       # one-line description
    body: str          # full diff or command, shown verbatim


@dataclass
class ApprovalDecision:
    approved: bool
    reason: str = ""


class ApprovalGate:
    """Serialises approval prompts; one human, one prompt at a time."""

    def __init__(self, audit=None, stdin=None, stderr=None):
        self._lock = threading.Lock()
        self._audit = audit
        self._stdin = stdin if stdin is not None else sys.stdin
        self._stderr = stderr if stderr is not None else sys.stderr
        # Bypass hook for tests only. Never set from config or network input.
        self._auto: bool | None = None

    def set_auto_for_tests(self, decision: bool | None) -> None:
        """Test-only. Passing None restores interactive behaviour."""
        self._auto = decision

    def request(self, req: ApprovalRequest) -> ApprovalDecision:
        with self._lock:
            if self._auto is not None:
                decision = ApprovalDecision(
                    approved=bool(self._auto),
                    reason="auto (tests)",
                )
                self._log(req, decision)
                return decision

            e = self._stderr
            e.write("\n" + "=" * 72 + "\n")
            e.write(f"HOSEKI APPROVAL REQUIRED — {req.kind}\n")
            e.write(f"  {req.summary}\n")
            e.write("-" * 72 + "\n")
            e.write(req.body.rstrip("\n") + "\n")
            e.write("-" * 72 + "\n")
            e.write("Approve? [y/N] ")
            e.flush()

            try:
                line = self._stdin.readline()
            except (EOFError, KeyboardInterrupt):
                line = ""
            answer = (line or "").strip().lower()
            approved = answer in ("y", "yes")
            decision = ApprovalDecision(
                approved=approved,
                reason="approved by operator" if approved else "denied by operator",
            )
            self._log(req, decision)
            e.write("  -> " + ("APPROVED" if approved else "DENIED") + "\n\n")
            e.flush()
            return decision

    def _log(self, req: ApprovalRequest, d: ApprovalDecision) -> None:
        if self._audit is not None:
            self._audit.append(
                "approval",
                kind=req.kind,
                summary=req.summary,
                approved=d.approved,
                reason=d.reason,
            )