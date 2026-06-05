"""The control plane — VeloGuard's whole reason to exist.

An AI with root is a liability. An AI whose every move must pass a policy
engine, get logged, and (when it matters) get the user's explicit consent is
a *guard*. This module is that gate. It answers one question about an Action:
allow it, deny it, or stop and ask the human first.
"""

from __future__ import annotations

import ipaddress
import json
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .actions import Action, ActionType


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class Decision:
    verdict: Verdict
    reason: str


DEFAULT_POLICY = {
    # Actions the AI plane is permitted to request at all.
    "allowed_actions": ["block_ip", "unblock_ip", "list_blocked",
                        "vpn_up", "vpn_down", "quarantine",
                        "release_quarantine", "kill_quarantine", "sandbox_run"],
    # Actions that always require a human "yes". Protective actions (vpn_up,
    # quarantine) are deliberately NOT here — they fire automatically. Undoing
    # protection (vpn_down) or acting destructively (kill) needs consent.
    "require_approval": ["block_ip", "unblock_ip", "vpn_down",
                        "release_quarantine", "kill_quarantine"],
    # CIDRs the AI may never block — blocking these is how you brick a box.
    "protected_cidrs": [
        "127.0.0.0/8", "::1/128",        # loopback
        "10.0.0.0/8", "172.16.0.0/12",   # RFC1918 private
        "192.168.0.0/16",
        "169.254.0.0/16",                # link-local
    ],
    # Sliding-window rate limit on state-changing actions.
    "rate_limit": {"max_actions": 20, "window_seconds": 60},
}


class PolicyEngine:
    def __init__(self, policy: dict):
        self.policy = policy
        self._recent: list[float] = []  # timestamps of state-changing actions

    @classmethod
    def load(cls, path: Path | None) -> "PolicyEngine":
        if path and path.exists():
            return cls(json.loads(path.read_text()))
        return cls(DEFAULT_POLICY)

    def _is_protected(self, ip: str) -> str | None:
        addr = ipaddress.ip_address(ip)
        for cidr in self.policy.get("protected_cidrs", []):
            if addr in ipaddress.ip_network(cidr):
                return cidr
        return None

    def _rate_ok(self) -> bool:
        rl = self.policy.get("rate_limit")
        if not rl:
            return True
        now = time.time()
        window = rl["window_seconds"]
        self._recent = [t for t in self._recent if now - t < window]
        return len(self._recent) < rl["max_actions"]

    def evaluate(self, action: Action) -> Decision:
        if action.type == ActionType.NOOP:
            return Decision(Verdict.DENY, "no actionable intent")

        if action.type.value not in self.policy.get("allowed_actions", []):
            return Decision(Verdict.DENY,
                            f"action {action.type.value} not in allowed_actions")

        # Blocking a protected range is refused outright — the AI cannot
        # talk the guard into locking the user out of their own machine.
        if action.type == ActionType.BLOCK_IP:
            protected = self._is_protected(action.params["ip"])
            if protected:
                return Decision(
                    Verdict.DENY,
                    f"{action.params['ip']} is in protected range {protected}")

        if action.type in (ActionType.BLOCK_IP, ActionType.UNBLOCK_IP):
            if not self._rate_ok():
                return Decision(Verdict.DENY, "rate limit exceeded")

        if action.type.value in self.policy.get("require_approval", []):
            return Decision(Verdict.NEEDS_APPROVAL,
                            "policy requires user consent for this action")

        return Decision(Verdict.ALLOW, "permitted by policy")

    def record(self, action: Action) -> None:
        """Call after a state-changing action actually executes (for rate limit)."""
        if action.type in (ActionType.BLOCK_IP, ActionType.UNBLOCK_IP):
            self._recent.append(time.time())
