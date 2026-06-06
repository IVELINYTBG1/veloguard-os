"""VeloGuard daemon CLI — run security intents, and hot-swap the AI core.

Two kinds of command:

  RUN an intent (goes through AI -> guard -> kernel):
    python3 -m guardd "block 203.0.113.10"
    python3 -m guardd --apply --yes "block 203.0.113.10"     # for real, no prompt

  CONTROL the core (hot-swap — takes effect on the very next intent):
    python3 -m guardd use claude                 # switch active brain
    python3 -m guardd use ollama llama3.2:3b      # switch brain AND pick its model
    python3 -m guardd key claude sk-ant-...       # store an API key (chmod 600)
    python3 -m guardd key openai sk-...
    python3 -m guardd model openai gpt-4o          # pick a model for a provider
    python3 -m guardd status                       # what's active, keys (masked)
    python3 -m guardd models                       # local ollama models available

  PROTECT:
    python3 -m guardd net --ssid Cafe --security open   # classify wifi, auto-VPN
    python3 -m guardd honeypot --analyze --block        # decoy + AI diagnosis
    python3 -m guardd analyze <captures.jsonl>          # diagnose a saved capture
    python3 -m guardd run-safe ./sketchy.AppImage       # run isolated (AI picks tier)
    python3 -m guardd update check --json               # signed update check (agent)
    python3 -m guardd update apply --domain veloguard --apply

  AGENTIC (full control via API, through the guard):
    python3 -m guardd agent --autonomy full "lock down: block 203.0.113.10, vpn up"
    python3 -m guardd mcp                                # MCP server for Claude Code/Codex
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from . import (__version__, agent, analyst, honeypot, memory, netclass, state,
               updater, vlayer, voice)
from .actions import Action, ActionType
from .ai_adapter import get_adapter
from .audit import record
from .executor import NftExecutor
from .policy import Decision, PolicyEngine, Verdict

VELOGUARD_DIR = Path(__file__).resolve().parent.parent
DEFAULT_POLICY_PATH = VELOGUARD_DIR / "policy.json"
CONFIG_PATH = VELOGUARD_DIR / "config.json"

CONTROL_VERBS = {"setup", "use", "key", "model", "status", "models",
                 "providers", "net", "honeypot", "analyze", "run-safe",
                 "update", "agent", "mcp", "voice", "help"}


def _configured_adapter() -> str:
    """Factory-default adapter from config.json (runtime state overrides it)."""
    try:
        return json.loads(CONFIG_PATH.read_text()).get("adapter", "mock")
    except (OSError, json.JSONDecodeError):
        return "mock"


# ===========================================================================
# SETUP SCREEN — first-boot wizard (a friendly front-end over use/key/model)
# ===========================================================================

_BANNER = """
\033[1;36m┌────────────────────────────────────────────────┐
│  VeloGuardOS  ·  setup                          │
│  AI-first. Local or cloud. You stay in control. │
└────────────────────────────────────────────────┘\033[0m"""


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" \033[2m[{default}]\033[0m" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        val = ""
    return val or (default or "")


def _ask_secret(prompt: str) -> str:
    import getpass
    try:
        return getpass.getpass(f"{prompt}: ").strip()
    except Exception:          # no tty (e.g. piped) — fall back to plain read
        return _ask(prompt)


def _choose(prompt: str, options: list[tuple[str, str]], default: int = 1) -> str:
    """Numbered menu. Returns the chosen option key. Accepts the number or key."""
    print(prompt)
    for i, (_, label) in enumerate(options, 1):
        print(f"   \033[1m{i}\033[0m) {label}")
    keys = {k for k, _ in options}
    while True:
        raw = _ask("  >", str(default))
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][0]
        if raw.lower() in keys:
            return raw.lower()
        print("  please pick a number from the list.")


def _test_connection(provider: str) -> bool:
    from .ai_adapter import get_adapter
    print(f"  testing {provider} …")
    try:
        adapter = get_adapter(provider, **state.adapter_config(provider))
        action = adapter.parse("block 203.0.113.10")
        print(f"  \033[1;32m✓\033[0m ok — test intent parsed as: {action.type.value}")
        return True
    except Exception as e:
        print(f"  \033[1;31m✗\033[0m failed: {e}")
        return False


def _setup_local() -> None:
    models = state.list_ollama_models()
    if not models:
        print("\n  No local models found yet.")
        if _ask("  Pull a recommended model now (~2 GB)? [Y/n]", "Y").lower() in ("y", "yes"):
            name = _ask("  model to pull", "llama3.2:3b")
            print(f"  pulling {name} … (this can take a while)")
            import subprocess
            subprocess.run(["ollama", "pull", name])
            models = state.list_ollama_models()
    if models:
        choice = _choose("\n  Pick the model to use:", [(m, m) for m in models])
    else:
        choice = _ask("\n  model name to use", "llama3.2:3b")
    state.set_active("ollama")
    state.set_model("ollama", choice)
    record({"control": "setup", "plane": "local", "provider": "ollama",
            "model": choice, "result": "ok"})
    print(f"\n  → local plane ready (ollama · {choice}) — nothing leaves this machine.")


def _setup_api() -> None:
    provider = _choose("\n  Which API?", [
        ("claude", "Claude  (Anthropic)"),
        ("openai", "OpenAI / Codex-compatible  (also Groq, OpenRouter, local servers)"),
    ])
    key = _ask_secret(f"  paste your {provider} API key (hidden)")
    if key:
        state.set_key(provider, key)
    if provider == "openai":
        base = _ask("  API base URL", "https://api.openai.com/v1")
        if base and base != "https://api.openai.com/v1":
            state.set_base_url("openai", base)
        model = _ask("  model", "gpt-4o-mini")
    else:
        model = _choose("  model:", [
            ("claude-haiku-4-5", "Haiku  — fast & cheap (recommended for intent parsing)"),
            ("claude-sonnet-4-6", "Sonnet — stronger"),
            ("claude-opus-4-8", "Opus   — strongest"),
        ])
    state.set_model(provider, model)
    state.set_active(provider)
    # The key VALUE is never recorded — only that setup stored one.
    record({"control": "setup", "plane": "api", "provider": provider,
            "model": model, "key": state.mask(key), "result": "ok"})
    print(f"\n  → cloud plane ready ({provider} · {model} · key {state.mask(key) or '—'})")


def _setup_wizard() -> int:
    print(_BANNER)
    if not sys.stdin.isatty():
        print("\033[2m(non-interactive input — reading answers from stdin)\033[0m")

    plane = _choose("\nChoose your AI plane:", [
        ("local", "Local   — Ollama on this machine. Private, free, needs a capable PC."),
        ("api",   "Cloud   — Claude or OpenAI/Codex. Runs on a potato, needs an API key."),
        ("none",  "Skip    — offline keyword mode (mock); set it up later."),
    ])

    if plane == "none":
        state.set_active("mock")
        record({"control": "setup", "plane": "none", "result": "ok"})
        print("\n  → offline mock mode. Run 'guardd setup' again any time.")
    elif plane == "local":
        _setup_local()
    else:
        _setup_api()

    active = state.active_provider(config_default=_configured_adapter())
    if active != "mock" and _ask("\nTest the connection now? [Y/n]", "Y").lower() in ("y", "yes"):
        _test_connection(active)

    # Voice assistant wake word (optional; engines via provision/install-voice.sh)
    ww = _ask("\nVoice assistant wake word (blank to skip)", "hey guard")
    if ww:
        memory.set_pref("wake_word", ww)
        print(f"  wake word: '{ww}'  (install voice engines: sudo provision/install-voice.sh)")

    if _ask("\nInitialize the VeloGuard firewall table now? [y/N]", "N").lower() in ("y", "yes"):
        as_root = os.geteuid() == 0
        if not as_root:
            print("  (not root — showing what it WOULD do; re-run with sudo to apply)")
        for line in NftExecutor(apply=as_root).setup():
            print("  " + line)

    print("\n\033[1;32m── setup complete ──\033[0m")
    _control(["status"])
    return 0


# ===========================================================================
# NETWORK AUTO-PROTECT — classify the Wi-Fi, bring the VPN up if untrusted
# ===========================================================================

def _vpn_up_through_guard(ex: NftExecutor, profile: str, note: str) -> str:
    """Run VPN_UP through the policy engine (auto-allowed) + audit it."""
    action = Action(ActionType.VPN_UP, {"target": profile} if profile else {})
    decision = PolicyEngine.load(DEFAULT_POLICY_PATH).evaluate(action)
    if decision.verdict == Verdict.DENY:
        return f"VPN blocked by policy: {decision.reason}"
    out = ex.vpn_up(profile)
    record({"control": "net", "action": "vpn_up", "target": profile,
            "result": "executed", "output": out, "note": note})
    return out


def _net(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="guardd net",
                                description="classify a network and auto-protect")
    p.add_argument("--ssid")
    p.add_argument("--bssid")
    p.add_argument("--security", help="e.g. wpa2, wpa3, open")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--yes", action="store_true", help="non-interactive: safe default")
    args = p.parse_args(rest)

    verdict, reason = netclass.classify(args.ssid, args.bssid, args.security)
    label = args.ssid or args.bssid or "(unknown)"
    print(f"network '{label}': {verdict} — {reason}")
    memory.log_decision("network", label, verdict, reason)
    ex = NftExecutor(apply=args.apply)
    profile = memory.get_pref("vpn_profile", "veloguard")

    if verdict == "trusted":
        print("  trusted — no VPN needed.")
        return 0
    if verdict == "untrusted":
        print("  untrusted → auto-protecting (no questions).")
        print("  " + _vpn_up_through_guard(ex, profile, f"auto on {label}"))
        return 0

    # unknown: ask the human if we can; otherwise fail safe (protect).
    if sys.stdin.isatty() and not args.yes:
        ans = input(f"  trust '{label}'? [y/N] ").strip().lower()
        if ans in ("y", "yes"):
            memory.set_network_trust(args.ssid, args.bssid, args.security, "trusted")
            print("  remembered as trusted — no VPN.")
            return 0
        memory.set_network_trust(args.ssid, args.bssid, args.security, "untrusted")
    else:
        print("  non-interactive → failing safe.")
    print("  " + _vpn_up_through_guard(ex, profile, f"unknown net {label}"))
    return 0


# ===========================================================================
# HONEYPOT — decoy listeners + AI attack diagnosis
# ===========================================================================

def _active_adapter():
    """Build the currently-active AI plane; (None, provider, model) on failure."""
    provider = state.active_provider(config_default=_configured_adapter())
    cfg = state.adapter_config(provider)
    try:
        return get_adapter(provider, **cfg), provider, cfg.get("model")
    except (ValueError, RuntimeError) as e:
        print(f"  (AI analysis disabled: {e})", file=sys.stderr)
        return None, provider, cfg.get("model")


def _auto_block(ex: NftExecutor, ip: str) -> str:
    """Protective auto-block of a confirmed attacker (the --block flag is consent)."""
    action = Action(ActionType.BLOCK_IP, {"ip": ip})
    try:
        action.validate()
    except ValueError as e:
        return f"not blocked: {e}"
    decision = PolicyEngine.load(DEFAULT_POLICY_PATH).evaluate(action)
    if decision.verdict == Verdict.DENY:
        return f"not blocked: {decision.reason}"
    out = ex.block_ip(ip)
    record({"control": "honeypot", "action": "block_ip", "params": {"ip": ip},
            "result": "executed", "output": out})
    return out


def _honeypot(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="guardd honeypot")
    p.add_argument("--ports", default="2222,8080,2323",
                   help="comma-separated decoy ports (default high ports, no root)")
    p.add_argument("--analyze", action="store_true",
                   help="have the active AI diagnose each captured attack")
    p.add_argument("--block", action="store_true",
                   help="auto-block the attacker's IP (protective)")
    p.add_argument("--apply", action="store_true",
                   help="actually touch nftables for --block (needs root)")
    args = p.parse_args(rest)
    sys.stdout.reconfigure(line_buffering=True)  # live output for a long-runner
    ports = [int(x) for x in args.ports.split(",") if x.strip()]

    adapter = provider = model = None
    if args.analyze:
        adapter, provider, model = _active_adapter()
        if adapter:
            tier = analyst.analysis_tier(provider, model)
            print(f"  AI analysis: {provider}/{model or '-'} → '{tier}' tier"
                  + ("  ★ local high-end bonus" if tier == "deep" else ""))
    ex = NftExecutor(apply=args.apply)

    def on_capture(cap: dict) -> None:
        print(f"\n[capture] {cap['service']} from {cap['src_ip']}:{cap['src_port']}"
              f"  {cap['bytes']}B")
        memory.log_decision("honeypot", cap["src_ip"], "captured",
                            f"{cap['service']} {cap['bytes']}B")
        if adapter:
            rep = analyst.analyze_capture(cap, adapter, provider, model)
            print(f"  ── AI diagnosis ({rep['tier']}) ──\n  "
                  + rep["report"].replace("\n", "\n  "))
        if args.block:
            print("  " + _auto_block(ex, cap["src_ip"]))

    print(f"VeloGuard honeypot starting on ports {ports}")
    honeypot.run(ports, on_capture)
    return 0


def _analyze(rest: list[str]) -> int:
    p = argparse.ArgumentParser(prog="guardd analyze")
    p.add_argument("capture", help="a capture .json or .jsonl file from the honeypot")
    args = p.parse_args(rest)
    text = Path(args.capture).read_text().strip()
    last = [ln for ln in text.splitlines() if ln.strip()][-1] if text else "{}"
    try:
        cap = json.loads(last)
    except json.JSONDecodeError as e:
        print(f"bad capture file: {e}", file=sys.stderr)
        return 2
    adapter, provider, model = _active_adapter()
    if not adapter:
        return 2
    rep = analyst.analyze_capture(cap, adapter, provider, model)
    print(f"── AI diagnosis ({rep['tier']} · {provider}/{model or '-'}) ──")
    print(rep["report"])
    return 0


# ===========================================================================
# AGENT — autonomous loop: give the active AI a goal, it drives the tools
# ===========================================================================

def _agent(rest: list[str]) -> int:
    autonomy, apply, max_steps = "guarded", False, 8
    if "--apply" in rest:
        apply = True; rest = [a for a in rest if a != "--apply"]
    if "--autonomy" in rest:
        i = rest.index("--autonomy")
        autonomy = rest[i + 1] if i + 1 < len(rest) else "guarded"
        del rest[i:i + 2]
    if "--max-steps" in rest:
        i = rest.index("--max-steps")
        max_steps = int(rest[i + 1]) if i + 1 < len(rest) else 8
        del rest[i:i + 2]
    if autonomy not in ("read", "guarded", "full"):
        autonomy = "guarded"
    goal = " ".join(rest).strip()
    if not goal:
        print('usage: guardd agent [--autonomy read|guarded|full] [--apply] '
              '[--max-steps N] "<goal>"', file=sys.stderr)
        return 2

    provider = state.active_provider(config_default=_configured_adapter())
    if provider == "mock":
        print("agent needs a tool-capable AI plane — run: guardd use ollama|claude|openai",
              file=sys.stderr)
        return 2
    cfg = state.adapter_config(provider)
    print(f"agent: {provider}/{cfg.get('model') or '-'} · autonomy={autonomy} · "
          f"{'APPLY' if apply else 'dry-run'}")
    try:
        result = agent.run(goal, provider, model=cfg.get("model"), key=cfg.get("key"),
                           base_url=cfg.get("base_url"),
                           host=os.environ.get("VELOGUARD_OLLAMA_HOST"),
                           autonomy=autonomy, apply=apply, max_steps=max_steps)
    except (RuntimeError, KeyError, ValueError) as e:
        print(f"agent error: {e}", file=sys.stderr)
        return 1
    for s in result["steps"]:
        print(f"  → {s['tool']}({s['args']}) :: {s['result'].get('status', '?')}")
    print("\n" + (result["final"] or "(no summary)"))
    record({"control": "agent", "goal": goal, "autonomy": autonomy,
            "steps": len(result["steps"]), "result": "done"})
    return 0


# ===========================================================================
# UPDATER — signed VeloGuard releases + kernel re-merge (agent-drivable)
# ===========================================================================

def _update(rest: list[str]) -> int:
    sub = rest[0] if rest and not rest[0].startswith("-") else "check"
    flags = [a for a in rest if a.startswith("-")]
    as_json = "--json" in flags
    do_apply = "--apply" in flags
    yes = "--yes" in flags
    build = "--build" in flags
    domain = "all"
    if "--domain" in rest:
        i = rest.index("--domain")
        domain = rest[i + 1] if i + 1 < len(rest) else "all"

    try:
        if sub in ("check", "apply") and not updater.PUBKEY.exists():
            print("updater: not configured yet — add your release key to "
                  "veloguard/keys/veloguard-release.pem and set VELOGUARD_UPDATE_URL "
                  "(see keys/SIGNING.md). Nothing to do.")
            record({"control": "update", "sub": sub, "result": "not_configured"})
            return 0
        if sub == "check":
            res = updater.check()
            if as_json:
                print(json.dumps(res))
            else:
                print(f"signature: verified ✓   (root of trust: keys/veloguard-release.pem)")
                for dom, d in res["domains"].items():
                    flag = "UPDATE" if d["update_available"] else "up to date"
                    print(f"  {dom:<9} {d['current']} → {d['latest']}   [{flag}]")
            record({"control": "update", "sub": "check", "result": "ok"})
            return 0

        if sub == "rollback":
            print(updater.rollback_veloguard())
            record({"control": "update", "sub": "rollback", "result": "ok"})
            return 0

        if sub == "apply":
            # Verification happens inside the updater regardless of consent.
            if not do_apply:
                if domain in ("all", "veloguard"):
                    print(updater.apply_veloguard(dry_run=True))
                if domain in ("all", "kernel"):
                    print(updater.apply_kernel(build=build, dry_run=True))
                print("\n(preview only — add --apply to execute)")
                return 0
            if not yes:
                sys.stderr.write(f"\n  Apply VeloGuard updates ({domain})? Signature is "
                                 "verified. This is privileged. [y/N] ")
                if input().strip().lower() not in ("y", "yes"):
                    print("aborted by user", file=sys.stderr)
                    return 1
            out = []
            if domain in ("all", "veloguard"):
                out.append(updater.apply_veloguard(dry_run=False))
            if domain in ("all", "kernel"):
                out.append(updater.apply_kernel(build=build, dry_run=False))
            for line in out:
                print(line)
            record({"control": "update", "sub": "apply", "domain": domain,
                    "build": build, "result": "executed"})
            return 0

        print(f"unknown update subcommand {sub!r} (check | apply | rollback)",
              file=sys.stderr)
        return 2
    except updater.UpdateError as e:
        print(f"update refused (fail-closed): {e}", file=sys.stderr)
        record({"control": "update", "sub": sub, "result": "refused", "error": str(e)})
        return 1


# ===========================================================================
# VIRTUALIZATION LAYER — run an uncertain app in an isolated 'digital layer'
# ===========================================================================

def _run_safe(rest: list[str]) -> int:
    apply = "--apply" in rest; rest = [a for a in rest if a != "--apply"]
    allow_net = "--net" in rest; rest = [a for a in rest if a != "--net"]
    tier = None
    if "--tier" in rest:
        i = rest.index("--tier")
        tier = rest[i + 1] if i + 1 < len(rest) else None
        del rest[i:i + 2]
    if not rest:
        print("usage: guardd run-safe [--tier light|strong|vm] [--net] [--apply] "
              "<command...>", file=sys.stderr)
        return 2

    cmd, app = rest, rest[0]
    if not tier:                       # let the AI judge how hard to sandbox
        adapter, provider, model = _active_adapter()
        risk, why = vlayer.assess_risk(app, adapter, provider, model)
        tier = vlayer.TIER_FOR_RISK[risk]
        print(f"  risk: {risk} — {why}")
    chosen, degraded = vlayer.resolve_tier(tier)
    print(f"  isolation tier: {chosen}"
          + (f"  (degraded from '{tier}' — not installed)" if degraded else ""))

    action = Action(ActionType.SANDBOX_RUN,
                    {"target": " ".join(shlex.quote(c) for c in cmd),
                     "tier": tier, "net": allow_net})
    try:
        action.validate()
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    decision = PolicyEngine.load(DEFAULT_POLICY_PATH).evaluate(action)
    if decision.verdict == Verdict.DENY:
        print(f"DENIED: {decision.reason}", file=sys.stderr)
        return 1
    ex = NftExecutor(apply=apply)
    out = ex.sandbox_run(action.params["target"], tier, allow_net)
    print(out)
    record({"control": "run-safe", "target": action.params["target"],
            "tier": chosen, "net": allow_net, "apply": apply, "result": "executed"})
    return 0


# ===========================================================================
# CONTROL PLANE — the hot-swap commands
# ===========================================================================

def _control(argv: list[str]) -> int:
    verb, rest = argv[0], argv[1:]

    if verb == "help" or not argv:
        print(__doc__)
        return 0

    if verb == "setup":
        return _setup_wizard()

    if verb == "net":
        return _net(rest)

    if verb == "honeypot":
        return _honeypot(rest)

    if verb == "analyze":
        return _analyze(rest)

    if verb == "run-safe":
        return _run_safe(rest)

    if verb == "update":
        return _update(rest)

    if verb == "agent":
        return _agent(rest)

    if verb == "mcp":
        from .mcp_server import serve
        serve()
        return 0

    if verb == "voice":
        return voice.run()

    if verb == "providers":
        for p in state.PROVIDERS:
            tag = " (needs API key)" if p in state.KEYED else (
                " (local)" if p == "ollama" else "")
            print(f"  {p}{tag}")
        return 0

    if verb == "use":
        if not rest:
            print("usage: guardd use <provider> [model]", file=sys.stderr)
            return 2
        provider = rest[0]
        if provider not in state.PROVIDERS:
            print(f"unknown provider {provider!r} "
                  f"(choices: {', '.join(state.PROVIDERS)})", file=sys.stderr)
            return 2
        state.set_active(provider)
        msg = f"active AI plane → {provider}"
        if len(rest) > 1:
            state.set_model(provider, rest[1])
            msg += f"  (model: {rest[1]})"
        print(msg)
        # Friendly nudges, not errors.
        if provider in state.KEYED and not state.key_for(provider):
            print(f"  ⚠ no API key yet — run:  guardd key {provider} <YOUR_KEY>")
        if provider == "ollama":
            _warn_if_model_missing(state.model_for("ollama"))
        record({"control": "use", "provider": provider,
                "model": state.model_for(provider) if provider != "mock" else None,
                "result": "ok"})
        return 0

    if verb == "key":
        if len(rest) < 2:
            print("usage: guardd key <claude|openai> <API_KEY>", file=sys.stderr)
            return 2
        provider, api_key = rest[0], rest[1]
        if provider not in state.KEYED:
            print(f"{provider!r} does not use an API key "
                  f"(keyed providers: {', '.join(state.KEYED)})", file=sys.stderr)
            return 2
        state.set_key(provider, api_key)
        print(f"stored {provider} API key ({state.mask(api_key)}) → "
              f"{state.state_dir()}/credentials.json (chmod 600)")
        # The key VALUE is never recorded — only that one was set.
        record({"control": "key", "provider": provider,
                "key": state.mask(api_key), "result": "stored"})
        return 0

    if verb == "model":
        if len(rest) < 2:
            print("usage: guardd model <provider> <model>", file=sys.stderr)
            return 2
        provider, model = rest[0], rest[1]
        if provider not in state.PROVIDERS or provider == "mock":
            print(f"cannot set a model for {provider!r}", file=sys.stderr)
            return 2
        state.set_model(provider, model)
        print(f"{provider} model → {model}")
        if provider == "ollama":
            _warn_if_model_missing(model)
        record({"control": "model", "provider": provider,
                "model": model, "result": "ok"})
        return 0

    if verb == "models":
        models = state.list_ollama_models()
        if not models:
            print("no local ollama models found (is ollama running? try: ollama pull llama3.2:3b)")
        else:
            current = state.model_for("ollama")
            for m in models:
                print(f"  {'*' if m == current else ' '} {m}")
        return 0

    if verb == "status":
        active = state.active_provider(config_default=_configured_adapter())
        print(f"active AI plane : {active}")
        print("providers:")
        for p in state.PROVIDERS:
            line = f"  {'➤' if p == active else ' '} {p:<7}"
            if p != "mock":
                line += f" model={state.model_for(p)}"
            if p in state.KEYED:
                src = state.key_source(p)
                key = state.key_for(p)
                line += f"  key={state.mask(key)} ({src})" if key else "  key=—"
            print(line)
        local = state.list_ollama_models()
        if local:
            print(f"local ollama models: {', '.join(local)}")
        return 0

    print(f"unknown command {verb!r}. Try: guardd help", file=sys.stderr)
    return 2


def _warn_if_model_missing(model: str | None) -> None:
    if model and model not in state.list_ollama_models():
        print(f"  ⚠ '{model}' not pulled yet — run:  ollama pull {model}")


# ===========================================================================
# RUN PLANE — execute one security intent
# ===========================================================================

def _confirm(action: Action, decision: Decision) -> bool:
    sys.stderr.write(
        f"\n  VeloGuard wants to: {action.describe()}\n"
        f"  reason: {action.rationale or '(none)'}\n"
        f"  policy: {decision.reason}\n"
        f"  approve? [y/N] ")
    sys.stderr.flush()
    return input().strip().lower() in ("y", "yes")


def _execute(action: Action, ex: NftExecutor) -> str:
    t = action.type
    if t == ActionType.BLOCK_IP:
        return ex.block_ip(action.params["ip"])
    if t == ActionType.UNBLOCK_IP:
        return ex.unblock_ip(action.params["ip"])
    if t == ActionType.LIST_BLOCKED:
        return ex.list_blocked()
    if t == ActionType.VPN_UP:
        return ex.vpn_up(action.params.get("target"))
    if t == ActionType.VPN_DOWN:
        return ex.vpn_down(action.params.get("target"))
    if t == ActionType.QUARANTINE:
        return ex.quarantine(action.params["target"])
    if t == ActionType.RELEASE_QUARANTINE:
        return ex.release_quarantine(action.params["target"])
    if t == ActionType.KILL_QUARANTINE:
        return ex.kill_quarantine(action.params["target"])
    if t == ActionType.SANDBOX_RUN:
        return ex.sandbox_run(action.params["target"],
                              action.params.get("tier", "light"),
                              action.params.get("net", False))
    return "noop"


def _run(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        prog="guardd", description="VeloGuard — run a security intent")
    p.add_argument("intent", nargs="?", help="natural-language security intent")
    p.add_argument("--adapter", default=None,
                   help="override the active AI plane for this one command")
    p.add_argument("--apply", action="store_true",
                   help="actually touch nftables (needs root); default is dry-run")
    p.add_argument("--yes", action="store_true",
                   help="auto-approve actions that need consent (USE CAREFULLY)")
    p.add_argument("--setup", action="store_true",
                   help="create the veloguard nft table/set/rule, then exit")
    p.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    p.add_argument("--version", action="version", version=f"VeloGuard {__version__}")
    args = p.parse_args(argv)

    ex = NftExecutor(apply=args.apply)

    if args.setup:
        for line in ex.setup():
            print(line)
        return 0

    if not args.intent:
        p.error("provide an intent, or a control command (try: guardd help)")

    # 1. AI plane: resolve the *currently active* brain (hot-swappable state),
    #    unless this one command overrides it with --adapter.
    provider = state.active_provider(cli=args.adapter,
                                     config_default=_configured_adapter())
    cfg = state.adapter_config(provider)
    try:
        adapter = get_adapter(provider, **cfg)
        action = adapter.parse(args.intent)
    except (ValueError, RuntimeError) as e:
        print(f"AI plane error: {e}", file=sys.stderr)
        return 2

    try:
        action.validate()
    except ValueError as e:
        print(f"rejected (malformed): {e}", file=sys.stderr)
        record({"intent": args.intent, "provider": provider,
                "action": action.type.value, "result": "malformed", "error": str(e)})
        return 2

    # 2. Control plane: judge it
    engine = PolicyEngine.load(args.policy)
    decision = engine.evaluate(action)
    base = {"intent": args.intent, "provider": provider,
            "model": cfg.get("model"), "action": action.type.value,
            "params": action.params, "rationale": action.rationale,
            "verdict": decision.verdict.value, "reason": decision.reason,
            "apply": args.apply}

    if decision.verdict == Verdict.DENY:
        print(f"DENIED: {action.describe()} — {decision.reason}", file=sys.stderr)
        record({**base, "result": "denied"})
        return 1

    # 3. Consent gate ("when the user demands it")
    if decision.verdict == Verdict.NEEDS_APPROVAL and not args.yes:
        if not _confirm(action, decision):
            print("aborted by user", file=sys.stderr)
            record({**base, "result": "aborted_by_user"})
            return 1

    # 4. Kernel plane: do it
    out = _execute(action, ex)
    engine.record(action)
    print(out)
    record({**base, "result": "executed", "output": out})
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 0
    if argv[0] in CONTROL_VERBS:
        return _control(argv)
    return _run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
