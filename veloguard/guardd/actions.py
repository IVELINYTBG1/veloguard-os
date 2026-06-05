"""Structured actions — the contract between the AI plane and the kernel plane.

The AI never speaks to the kernel directly. It can only emit one of these
typed, validated actions. Adding a capability to VeloGuard means adding an
Action here, teaching the adapter to produce it, the policy engine to judge
it, and the executor to carry it out. Nothing else can reach the kernel.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from enum import Enum


class ActionType(str, Enum):
    BLOCK_IP = "block_ip"
    UNBLOCK_IP = "unblock_ip"
    LIST_BLOCKED = "list_blocked"
    # VPN — bring the encrypted tunnel up/down (WireGuard profile, or "tor").
    VPN_UP = "vpn_up"
    VPN_DOWN = "vpn_down"
    # Quarantine — isolate an unknown process in a RAM (tmpfs) sandbox, then
    # either release it (user trusts it) or kill+wipe it (user rejects it).
    QUARANTINE = "quarantine"
    RELEASE_QUARANTINE = "release_quarantine"
    KILL_QUARANTINE = "kill_quarantine"
    # Run an uncertain app in an isolated 'digital layer' (RAM, no net).
    SANDBOX_RUN = "sandbox_run"
    NOOP = "noop"  # adapter could not map the intent to anything


@dataclass
class Action:
    type: ActionType
    # Free-form parameters; validated per-type in `validate()`.
    params: dict = field(default_factory=dict)
    # Why the AI thinks this is the right action — surfaced to the user/audit.
    rationale: str = ""

    def validate(self) -> None:
        """Raise ValueError if params are malformed for this action type.

        This is *shape* validation only (is the IP a real IP?). Whether the
        action is *allowed* is the policy engine's job, not ours.
        """
        if self.type in (ActionType.BLOCK_IP, ActionType.UNBLOCK_IP):
            ip = self.params.get("ip")
            if not ip:
                raise ValueError(f"{self.type.value} requires an 'ip' param")
            # Raises ValueError on garbage; normalises e.g. trailing zeros.
            self.params["ip"] = str(ipaddress.ip_address(ip))
        if self.type in (ActionType.QUARANTINE, ActionType.RELEASE_QUARANTINE,
                         ActionType.KILL_QUARANTINE):
            if not self.params.get("target"):
                raise ValueError(f"{self.type.value} requires a 'target' "
                                 "(pid or process name)")
        if self.type == ActionType.SANDBOX_RUN and not self.params.get("target"):
            raise ValueError("sandbox_run requires a 'target' (command to run)")

    def describe(self) -> str:
        if self.type == ActionType.BLOCK_IP:
            return f"block traffic from {self.params.get('ip')}"
        if self.type == ActionType.UNBLOCK_IP:
            return f"unblock {self.params.get('ip')}"
        if self.type == ActionType.LIST_BLOCKED:
            return "list blocked addresses"
        if self.type == ActionType.VPN_UP:
            return f"bring up the VPN ({self.params.get('target') or 'default'})"
        if self.type == ActionType.VPN_DOWN:
            return f"take down the VPN ({self.params.get('target') or 'default'})"
        if self.type == ActionType.QUARANTINE:
            return f"quarantine {self.params.get('target')} in a RAM sandbox"
        if self.type == ActionType.RELEASE_QUARANTINE:
            return f"release {self.params.get('target')} from quarantine"
        if self.type == ActionType.KILL_QUARANTINE:
            return f"kill and wipe quarantined {self.params.get('target')}"
        if self.type == ActionType.SANDBOX_RUN:
            return f"run '{self.params.get('target')}' in an isolated layer"
        return "do nothing"
