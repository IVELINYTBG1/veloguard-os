"""Autonomous agent loop — give the brain a goal, it drives the kernel tools.

The cloud tool-calling loops (Claude/OpenAI/Ollama over HTTP) are gone with the
rest of the API plane. The agent loop returns when the local SNN brain lands:
its planner will emit tool calls against the same registry (tools.py), and
every call still goes through the one guarded path (dispatch.execute_tool) at
the chosen autonomy — that part is built, tested, and unchanged.
"""

from __future__ import annotations

from . import dispatch

SYSTEM = (
    "You are VeloGuard's autonomous operator for this machine. Achieve the "
    "user's goal by calling the provided tools. The guard enforces policy: if a "
    "tool is denied or needs approval, adapt or explain — never try to bypass "
    "it. Prefer the least-destructive action. When the goal is met, stop and "
    "summarize what you did."
)


def _exec(name: str, args: dict, autonomy: str, apply: bool, steps: list) -> dict:
    """The ONE way any brain touches a tool — kept as the integration point for
    the SNN planner."""
    res = dispatch.execute_tool(name, args, apply=apply, autonomy=autonomy,
                                source="agent")
    steps.append({"tool": name, "args": args, "result": res})
    return res


def run(goal: str, provider: str, *, model=None, autonomy="guarded",
        apply=False, max_steps=8, **_legacy) -> dict:
    if provider == "snn":
        return {"final": "the SNN brain's planner isn't integrated yet — the "
                         "agent loop comes back with the model code "
                         "(guardd/snn.py). The guarded tool path it will drive "
                         "is unchanged.", "steps": []}
    return {"final": f"provider '{provider}' can't drive the agent loop; the "
                     "agent returns with the local SNN brain", "steps": []}
