# VeloGuardOS agent plugin (Omarchy-style)

VeloGuard's **agentic workflows merged into Omarchy's agent model**: a default
"brain" you pick once and launch in a terminal — except the brain here drives
*the machine, through the guard*, not a code editor.

Installed to `/usr/share/veloguard/agents/`.

## Backends (both fully supported)

| Brain | What it is | Setup |
|---|---|---|
| **claude** | Anthropic API — most capable | `guardd key claude <KEY>` (or `$ANTHROPIC_API_KEY`) |
| **ollama** | a **local** model, private & free | `ollama serve` + `ollama pull <model>` |

Both are real in-guard brains (`guardd/ai_adapter.py`): the guard itself reasons
with them, and every action is still typed, policy-gated, consent-gated and
audited. Pick and launch Omarchy-style:

```bash
veloguard-agent set ollama            # persist the default brain
veloguard-agent                       # interactive agent console (Super+Shift+A)
veloguard-agent "raise the VPN and block 203.0.113.10"
```

## Driving from an external coding agent (Claude Code, Codex, opencode)

Attach the guard over MCP so your existing coding agent drives the machine
through the guard:

```bash
veloguard-agent mcp                   # prints the MCP config below
```
```json
{ "mcpServers": { "veloguard": { "command": "veloguard-mcp",
    "env": { "VELOGUARD_AGENT_AUTONOMY": "guarded" } } } }
```

## Files

- `veloguard-mcp.json` — the MCP server config template.
- `skills/veloguard-guard/SKILL.md` — an Omarchy-format skill teaching an agent
  how to drive the guard safely.

Launcher: `/usr/local/bin/veloguard-agent`. Keybind: `Super+Shift+A`.
