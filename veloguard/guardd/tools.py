"""The agentic tool surface — every kernel-tool capability, as callable tools.

This is the single source of truth for "what an AI agent can do to the system."
It renders to whatever a consumer expects (the SNN planner / MCP tool
schemas, or MCP `inputSchema`), and maps each tool back to a guard action or a
read handler. Mutating tools ALWAYS run through the guard (policy + consent +
audit) — see dispatch.py. Read tools never mutate.

Adding a capability = add one entry here. Nothing else gets to the kernel.
"""

from __future__ import annotations

from .actions import ActionType

# kind: "action" → goes through the guard (mutating). "read" → query only.
# params: JSON-schema properties (names match Action.params for action tools).
TOOLS: list[dict] = [
    {"name": "block_ip", "kind": "action", "mutating": True,
     "description": "Block all traffic from an IP via the firewall.",
     "params": {"ip": {"type": "string", "description": "IPv4 address"}},
     "required": ["ip"]},
    {"name": "unblock_ip", "kind": "action", "mutating": True,
     "description": "Remove an IP from the firewall blocklist.",
     "params": {"ip": {"type": "string"}}, "required": ["ip"]},
    {"name": "list_blocked", "kind": "action", "mutating": False,
     "description": "List currently blocked addresses.",
     "params": {}, "required": []},
    {"name": "vpn_up", "kind": "action", "mutating": True,
     "description": "Bring the VPN up (WireGuard profile name, or 'tor').",
     "params": {"target": {"type": "string", "description": "profile or 'tor'"}},
     "required": []},
    {"name": "vpn_down", "kind": "action", "mutating": True,
     "description": "Take the VPN down.",
     "params": {"target": {"type": "string"}}, "required": []},
    {"name": "quarantine", "kind": "action", "mutating": True,
     "description": "Freeze an unknown process into a RAM sandbox.",
     "params": {"target": {"type": "string", "description": "pid or process name"}},
     "required": ["target"]},
    {"name": "release_quarantine", "kind": "action", "mutating": True,
     "description": "Release a process from quarantine (you trust it).",
     "params": {"target": {"type": "string"}}, "required": ["target"]},
    {"name": "kill_quarantine", "kind": "action", "mutating": True,
     "description": "Kill and wipe a quarantined process (you reject it).",
     "params": {"target": {"type": "string"}}, "required": ["target"]},
    {"name": "sandbox_run", "kind": "action", "mutating": True,
     "description": "Run an uncertain app in an isolated, RAM-overlay layer.",
     "params": {"target": {"type": "string", "description": "command to run"},
                "tier": {"type": "string", "enum": ["light", "strong", "vm"]},
                "net": {"type": "boolean"}}, "required": ["target"]},
    # --- read-only tools (safe at any autonomy level) ---
    {"name": "status", "kind": "read", "mutating": False,
     "description": "Active AI plane and its model path.",
     "params": {}, "required": []},
    {"name": "classify_network", "kind": "read", "mutating": False,
     "description": "Judge a Wi-Fi network: trusted / untrusted / unknown.",
     "params": {"ssid": {"type": "string"}, "bssid": {"type": "string"},
                "security": {"type": "string"}}, "required": []},
    {"name": "check_update", "kind": "read", "mutating": False,
     "description": "Signed update check (read-only; fail-closed).",
     "params": {}, "required": []},
    {"name": "recall", "kind": "read", "mutating": False,
     "description": "Recall similar past decisions from the AI's memory.",
     "params": {"query": {"type": "string"}}, "required": ["query"]},
]

_BY_NAME = {t["name"]: t for t in TOOLS}
ACTION_TOOLS = {t["name"] for t in TOOLS if t["kind"] == "action"}


def get(name: str) -> dict | None:
    return _BY_NAME.get(name)


def action_type(name: str) -> ActionType:
    return ActionType(name)            # tool names mirror ActionType values


def _schema(t: dict) -> dict:
    return {"type": "object", "properties": t["params"],
            "required": t.get("required", [])}


# The cloud renderers (anthropic/openai/ollama tool shapes) are gone with the
# API plane. The registry itself is brain-agnostic: the SNN planner consumes
# this plain shape, and MCP keeps its own rendering below.

def snn_tools() -> list[dict]:
    """The registry in plain shape — what the SNN planner will read."""
    return [{"name": t["name"], "description": t["description"],
             "schema": _schema(t)} for t in TOOLS]


def mcp_tools() -> list[dict]:
    return [{"name": t["name"], "description": t["description"],
             "inputSchema": _schema(t)} for t in TOOLS]
