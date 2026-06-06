"""Autonomous agent loop — give an AI a goal, it drives the kernel tools to it.

The other half of "full agentic control via API": instead of an external agent
attaching over MCP, this runs the *active* AI plane (Claude / OpenAI / Ollama)
in a tool-calling loop until the goal is met. Every tool call goes through the
same guard (dispatch.execute_tool) at the chosen autonomy. Mock has no tools.
"""

from __future__ import annotations

import json

from . import dispatch, tools
from .ai_adapter import _post

SYSTEM = (
    "You are VeloGuard's autonomous operator for this machine. Achieve the "
    "user's goal by calling the provided tools. The guard enforces policy: if a "
    "tool is denied or needs approval, adapt or explain — never try to bypass "
    "it. Prefer the least-destructive action. When the goal is met, stop and "
    "summarize what you did."
)


def _exec(name: str, args: dict, autonomy: str, apply: bool, steps: list) -> dict:
    res = dispatch.execute_tool(name, args, apply=apply, autonomy=autonomy,
                                source="agent")
    steps.append({"tool": name, "args": args, "result": res})
    return res


def run(goal: str, provider: str, *, model=None, key=None, base_url=None,
        host=None, autonomy="guarded", apply=False, max_steps=8) -> dict:
    if provider == "ollama":
        return _ollama(goal, model, host, autonomy, apply, max_steps)
    if provider == "claude":
        return _claude(goal, model, key, autonomy, apply, max_steps)
    if provider == "openai":
        return _openai(goal, model, key, base_url, autonomy, apply, max_steps)
    return {"final": f"provider '{provider}' has no tool-calling; "
            "use ollama, claude, or openai", "steps": []}


def _ollama(goal, model, host, autonomy, apply, max_steps) -> dict:
    host = host or "http://localhost:11434"
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": goal}]
    steps = []
    for _ in range(max_steps):
        body = _post(f"{host}/api/chat", {"model": model or "llama3.2:1b",
                     "messages": msgs, "tools": tools.ollama_tools(),
                     "stream": False, "options": {"temperature": 0}},
                     headers={}, timeout=240)
        m = body.get("message", {})
        msgs.append(m)
        tcs = m.get("tool_calls") or []
        if not tcs:
            return {"final": m.get("content", ""), "steps": steps}
        for tc in tcs:
            fn = tc.get("function", {})
            res = _exec(fn.get("name", ""), fn.get("arguments", {}) or {},
                        autonomy, apply, steps)
            msgs.append({"role": "tool", "content": json.dumps(res)})
    return {"final": "(max steps reached)", "steps": steps}


def _claude(goal, model, key, autonomy, apply, max_steps) -> dict:
    api = "https://api.anthropic.com/v1/messages"
    hdr = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    msgs = [{"role": "user", "content": goal}]
    steps = []
    for _ in range(max_steps):
        body = _post(api, {"model": model or "claude-haiku-4-5", "max_tokens": 1024,
                     "system": SYSTEM, "tools": tools.anthropic_tools(),
                     "messages": msgs}, headers=hdr, timeout=240)
        content = body.get("content", [])
        msgs.append({"role": "assistant", "content": content})
        tus = [b for b in content if b.get("type") == "tool_use"]
        if not tus:
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            return {"final": text.strip(), "steps": steps}
        results = []
        for tu in tus:
            res = _exec(tu.get("name", ""), tu.get("input", {}) or {},
                        autonomy, apply, steps)
            results.append({"type": "tool_result", "tool_use_id": tu.get("id"),
                            "content": json.dumps(res)})
        msgs.append({"role": "user", "content": results})
    return {"final": "(max steps reached)", "steps": steps}


def _openai(goal, model, key, base_url, autonomy, apply, max_steps) -> dict:
    base = (base_url or "https://api.openai.com/v1").rstrip("/")
    hdr = {"Authorization": f"Bearer {key}"}
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": goal}]
    steps = []
    for _ in range(max_steps):
        body = _post(f"{base}/chat/completions", {"model": model or "gpt-4o-mini",
                     "messages": msgs, "tools": tools.openai_tools(),
                     "tool_choice": "auto", "temperature": 0}, headers=hdr, timeout=240)
        m = body["choices"][0]["message"]
        msgs.append(m)
        tcs = m.get("tool_calls") or []
        if not tcs:
            return {"final": m.get("content", "") or "", "steps": steps}
        for tc in tcs:
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            res = _exec(fn.get("name", ""), args, autonomy, apply, steps)
            msgs.append({"role": "tool", "tool_call_id": tc.get("id"),
                         "content": json.dumps(res)})
    return {"final": "(max steps reached)", "steps": steps}
