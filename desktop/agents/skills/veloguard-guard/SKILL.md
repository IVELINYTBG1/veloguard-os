---
name: veloguard-guard
description: Drive VeloGuardOS through its guard — block IPs, raise the VPN, quarantine or sandbox processes, check signed updates — safely, via the guard's MCP tools or the built-in agent loop.
---

# Driving VeloGuardOS through the guard

VeloGuardOS exposes every kernel-level capability as a **typed, guarded tool**.
You (an AI agent) never touch the kernel directly: each tool call becomes an
Action that passes `validate → policy → consent → execute → audit`. A policy
`DENY` always blocks (you cannot block loopback or the local LAN, even at full
autonomy), the updater stays fail-closed, and every call is written to the audit
log. Work *with* that guard — never try to bypass it.

## Two ways to drive it

1. **MCP (recommended for coding agents like Claude Code / Codex / opencode).**
   Attach the guard's MCP server; add to your agent's MCP config (`./.mcp.json`):
   ```json
   { "mcpServers": { "veloguard": { "command": "veloguard-mcp",
       "env": { "VELOGUARD_AGENT_AUTONOMY": "guarded" } } } }
   ```
   or run `veloguard-agent mcp` to print it.

2. **The built-in agent loop** (local, no coding-agent needed):
   ```bash
   veloguard-agent set ollama          # or: claude   (local vs API brain)
   veloguard-agent "lock down: block 203.0.113.10 and raise the VPN"
   ```

## Tools

Mutating (go through policy + consent): `block_ip`, `unblock_ip`, `vpn_up`,
`vpn_down`, `quarantine`, `release_quarantine`, `kill_quarantine`, `sandbox_run`.
Read-only (always safe): `status`, `classify_network`, `check_update`, `recall`,
`list_blocked`.

## Autonomy

- `read` — mutating tools disabled.
- `guarded` (default) — protective actions run; destructive ones need a yes.
- `full` — destructive actions auto-approved (the session is standing consent);
  policy DENY still blocks and everything is still audited.

## Rules for a well-behaved agent

- Only act on an IP or target the **user actually named** — never invent one
  (the guard discards invented IPs, but don't rely on it).
- Prefer the least-destructive action; if a tool is denied or needs approval,
  adapt or explain — do not attempt a workaround.
- When the goal is met, stop and summarize what you did.
