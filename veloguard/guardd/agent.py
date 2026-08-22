"""Autonomous agent loop — give a brain a goal, it drives the kernel tools.

Provider-agnostic by design: the loop asks the active brain (claude/ollama) for
ONE JSON tool call at a time, runs it through the ONE guarded path
(dispatch.execute_tool) at the chosen autonomy, feeds the result back, and
repeats until the brain says it's done. Same registry (tools.py), same guard,
same audit as the CLI and MCP — there is no back door, and a remote/weak brain
still can't act on an IP the user never named or bypass a policy DENY.

The SNN planner (guardd/snn.py) will plug into the identical _exec path.
"""

from __future__ import annotations

import json

from . import dispatch
from .ai_adapter import _IP_RE, get_adapter, sanitize_text

SYSTEM = (
    "You are VeloGuard's autonomous operator for this machine. Achieve the "
    "user's goal by calling the provided tools. The guard enforces policy: if a "
    "tool is denied or needs approval, adapt or explain — never try to bypass "
    "it. Prefer the least-destructive action. When the goal is met, stop and "
    "summarize what you did."
)

_PROTOCOL = (
    "Each turn reply with ONLY one JSON object and no prose. To act: "
    "{\"tool\": <tool name>, \"args\": {...}}. When the goal is achieved: "
    "{\"done\": true, \"summary\": <what you did>}. Never invent an IP or "
    "target the user did not provide."
)


def _exec(name: str, args: dict, autonomy: str, apply: bool, steps: list) -> dict:
    """The ONE way any brain touches a tool — the guarded, audited path."""
    res = dispatch.execute_tool(name, args, apply=apply, autonomy=autonomy,
                                source="agent")
    steps.append({"tool": name, "args": args, "result": res})
    return res


def _parse_msg(text: str) -> dict:
    """Extract the JSON tool-call/done object from a model reply."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        i = t.find("{")
        if i != -1:
            t = t[i:]
    try:
        s = t.index("{")
        e = t.rindex("}") + 1
        obj = json.loads(t[s:e])
        return obj if isinstance(obj, dict) else {"done": True, "summary": text.strip()}
    except (ValueError, json.JSONDecodeError):
        return {"done": True, "summary": text.strip()}


def run(goal: str, provider: str, *, model=None, autonomy="guarded",
        apply=False, max_steps=8, **_legacy) -> dict:
    from . import state, tools as toolmod

    if provider == "mock":
        return {"final": "mock can't drive the agent loop — pick a reasoning "
                         "brain: guardd use claude|ollama", "steps": []}
    if provider == "snn":
        return {"final": "the SNN brain's planner isn't integrated yet — it "
                         "returns with the model code (guardd/snn.py) and drives "
                         "the same guarded tool path.", "steps": []}

    try:
        adapter = get_adapter(provider, **state.adapter_config(provider))
    except (ValueError, RuntimeError) as e:
        return {"final": f"cannot start the {provider} agent: {e}", "steps": []}

    tool_lines = "\n".join(
        f"- {t['name']}({', '.join(t['schema']['properties']) or ''}): {t['description']}"
        for t in toolmod.snn_tools())
    system = f"{SYSTEM}\n\nAvailable tools:\n{tool_lines}\n\n{_PROTOCOL}"
    convo = f"GOAL: {goal}\n\nReply with the first tool call as JSON."

    # Anti-hallucination for the agentic path too: block_ip/unblock_ip may only
    # target an IP that appears verbatim in the goal.
    allowed_ips = set(_IP_RE.findall(goal))
    steps: list = []

    for _ in range(max_steps):
        try:
            reply = adapter.complete(system, convo, max_tokens=400)
        except RuntimeError as e:
            return {"final": f"agent stopped: {e}", "steps": steps}

        msg = _parse_msg(reply)
        tool = msg.get("tool")
        if msg.get("done") or not tool or tool == "done":
            return {"final": msg.get("summary") or reply.strip(), "steps": steps}

        args = msg.get("args") or {}
        if tool in ("block_ip", "unblock_ip"):
            ip = str(args.get("ip", ""))
            if ip and ip not in allowed_ips:
                res = {"ok": False, "status": "rejected",
                       "reason": f"refusing {tool} on {ip}: not named in the goal"}
                steps.append({"tool": tool, "args": args, "result": res})
                convo += (f"\n\nTOOL {tool}({args}) -> "
                          f"{sanitize_text(json.dumps(res), 800)}\n\nNext JSON.")
                continue

        res = _exec(tool, args, autonomy, apply, steps)
        convo += (f"\n\nTOOL {tool}({args}) -> {sanitize_text(json.dumps(res), 800)}"
                  "\n\nNext tool call as JSON, or "
                  "{\"done\": true, \"summary\": ...} if the goal is met.")

    return {"final": "reached the step limit without an explicit finish.",
            "steps": steps}
