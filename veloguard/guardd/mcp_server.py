"""VeloGuard MCP server — exposes the kernel-tool actions to any MCP agent.

This is how Claude Code, Codex, or a custom agent get "full agentic control via
API": they connect over MCP (stdio, JSON-RPC 2.0, newline-delimited) and call
the tools in tools.py. Every mutating call still goes through the guard
(dispatch.execute_tool) — policy, consent-by-autonomy, audit.

Autonomy + enforcement come from the environment (set by whoever launches it):
  VELOGUARD_AGENT_AUTONOMY = read | guarded | full   (default: guarded)
  VELOGUARD_APPLY          = 1 to actually touch the kernel (default: dry-run)

Add to Claude Code (.mcp.json):
  {"mcpServers": {"veloguard": {"command": "veloguard-mcp"}}}
"""

from __future__ import annotations

import json
import os
import sys

from . import __version__, dispatch, tools

PROTOCOL = "2024-11-05"


def _autonomy() -> str:
    a = os.environ.get("VELOGUARD_AGENT_AUTONOMY", "guarded")
    return a if a in dispatch.AUTONOMY else "guarded"


def _apply() -> bool:
    return os.environ.get("VELOGUARD_APPLY", "0") in ("1", "true", "yes")


def _handle(req: dict) -> dict | None:
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "veloguard", "version": __version__,
                           "autonomy": _autonomy(), "apply": _apply()}}}

    if method in ("notifications/initialized", "initialized"):
        return None                       # notification — no response

    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": tools.mcp_tools()}}

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        result = dispatch.execute_tool(name, args, apply=_apply(),
                                       autonomy=_autonomy(), source="mcp")
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "isError": not result.get("ok", False)}}

    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve() -> None:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = _handle(req)
        if resp is not None:
            out.write(json.dumps(resp) + "\n")
            out.flush()


if __name__ == "__main__":
    serve()
