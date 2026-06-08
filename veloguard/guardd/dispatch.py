"""One guarded road to the kernel — used by the MCP server and the agent loop.

Every mutating tool call becomes an Action that passes the SAME guard the CLI
uses: validate → policy → consent (by autonomy) → execute → audit. There is no
back door. Read tools never mutate and are always allowed.

Autonomy levels:
  read    — mutating tools disabled entirely.
  guarded — protective actions run; destructive ones need an interactive yes.
  full    — destructive actions auto-approved (the session is standing consent);
            policy DENY still blocks, everything is still audited.
"""

from __future__ import annotations

from pathlib import Path

from . import memory, netclass, state, tools as toolmod, updater
from .actions import Action, ActionType
from .audit import record
from .executor import NftExecutor
from .policy import PolicyEngine, Verdict

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policy.json"
AUTONOMY = ("read", "guarded", "full")


def _run_on_executor(action: Action, ex: NftExecutor) -> str:
    t = action.type
    if t == ActionType.BLOCK_IP:           return ex.block_ip(action.params["ip"])
    if t == ActionType.UNBLOCK_IP:         return ex.unblock_ip(action.params["ip"])
    if t == ActionType.LIST_BLOCKED:       return ex.list_blocked()
    if t == ActionType.VPN_UP:             return ex.vpn_up(action.params.get("target"))
    if t == ActionType.VPN_DOWN:           return ex.vpn_down(action.params.get("target"))
    if t == ActionType.QUARANTINE:         return ex.quarantine(action.params["target"])
    if t == ActionType.RELEASE_QUARANTINE: return ex.release_quarantine(action.params["target"])
    if t == ActionType.KILL_QUARANTINE:    return ex.kill_quarantine(action.params["target"])
    if t == ActionType.SANDBOX_RUN:
        return ex.sandbox_run(action.params["target"],
                              action.params.get("tier", "light"),
                              action.params.get("net", False))
    return "noop"


def _read_tool(name: str, args: dict) -> dict:
    if name == "status":
        active = state.active_provider()
        return {"ok": True, "data": {
            "active": active,
            "model": state.model_for(active) if active != "mock" else None}}
    if name == "classify_network":
        v, reason = netclass.classify(args.get("ssid"), args.get("bssid"),
                                      args.get("security"))
        return {"ok": True, "data": {"verdict": v, "reason": reason}}
    if name == "check_update":
        if not updater.PUBKEY.exists():
            return {"ok": True, "data": {"configured": False}}
        try:
            return {"ok": True, "data": updater.check()}
        except updater.UpdateError as e:
            return {"ok": False, "status": "refused", "error": str(e)}
    if name == "recall":
        return {"ok": True, "data": {
            "matches": memory.SemanticMemory().recall(args.get("query", ""))}}
    return {"ok": False, "error": f"no read handler for {name}"}


def execute_tool(name: str, args: dict, *, apply: bool = False,
                 autonomy: str = "guarded", interactive: bool = False,
                 confirm=None, source: str = "agent") -> dict:
    spec = toolmod.get(name)
    if not spec:
        return {"ok": False, "error": f"unknown tool: {name}"}
    if spec["kind"] == "read":
        return _read_tool(name, args)

    if autonomy == "read":
        return {"ok": False, "status": "read_only",
                "reason": "autonomy=read: mutating tools are disabled"}

    try:
        action = Action(toolmod.action_type(name), dict(args))
        action.validate()
    except ValueError as e:
        return {"ok": False, "status": "invalid", "error": str(e)}

    engine = PolicyEngine.load(DEFAULT_POLICY_PATH)
    decision = engine.evaluate(action)
    base = {"source": source, "tool": name, "params": action.params,
            "verdict": decision.verdict.value, "reason": decision.reason,
            "autonomy": autonomy, "apply": apply}

    if decision.verdict == Verdict.DENY:
        record({**base, "result": "denied"})
        return {"ok": False, "status": "denied", "reason": decision.reason}

    if decision.verdict == Verdict.NEEDS_APPROVAL:
        approved = (autonomy == "full") or bool(
            interactive and confirm and confirm(action, decision))
        if not approved:
            record({**base, "result": "needs_approval"})
            return {"ok": False, "status": "needs_approval",
                    "reason": "destructive — needs autonomy=full or an interactive yes"}

    try:
        out = _run_on_executor(action, NftExecutor(apply=apply))
    except RuntimeError as e:
        # Executor failed or self-protected (e.g. vpn_up refused/rolled back a
        # black-holing tunnel). Audit the failure too — the guard logs every
        # decision — and hand callers (MCP/agent/CLI) a clean error, not a crash.
        record({**base, "result": "failed", "error": str(e)})
        return {"ok": False, "status": "failed", "error": str(e)}
    engine.record(action)
    record({**base, "result": "executed", "output": out})
    return {"ok": True, "status": "executed", "output": out}
