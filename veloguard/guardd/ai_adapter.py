"""The AI plane — pluggable, exactly as the architecture demands.

Every adapter turns a human *intent* into a structured `Action`. The rest of
VeloGuard neither knows nor cares where that came from — and no matter the
brain, the action is still typed, IP-sanitized, policy-gated, consent-gated and
audited before it can reach the kernel. That structural guard is why a weak (or
remote) brain can be *wrong* but never *dangerous*.

Planes:
  * mock   — deterministic keyword parser; offline fallback that always works
  * snn    — VeloGuard's in-process spiking neural net (model code: guardd/snn.py)
  * claude — Anthropic Messages API (needs a key; nothing but the intent leaves)
  * ollama — a LOCAL model served by Ollama (private, free; no key, no cloud)

claude/ollama are OPT-IN: they only activate when the user selects them
(`guardd use claude|ollama`, or the setup wizard). The stdlib is the only
dependency — the adapters speak HTTP with urllib, so nothing new is vendored.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .actions import Action, ActionType

_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


def _resolve_ip(model_ip: str | None, intent: str) -> str | None:
    """Anti-hallucination: the only valid IP is one the user actually typed.
    Applies to *every* brain — the guard never acts on an invented host."""
    m = _IP_RE.search(intent)
    text_ip = m.group(1) if m else None
    if model_ip and model_ip != text_ip:
        model_ip = None  # model invented it — discard
    return model_ip or text_ip


def sanitize_text(text, limit: int = 4000) -> str:
    """Belt against prompt-injection / log-injection via untrusted text (SSIDs,
    filenames, log lines, AI rationale): cap length and strip NUL + control bytes
    (terminal-escape tricks) while keeping tab/newline. The real defense is
    structural — the AI can only emit a typed Action, every one gated by policy
    and sealed before it reaches the kernel — but untrusted bytes shouldn't ride
    into the audit log or the model unfiltered."""
    if not isinstance(text, str):
        text = str(text or "")
    text = text[:limit]
    return "".join(c for c in text if c in "\t\n" or ord(c) >= 0x20)


sanitize_intent = sanitize_text   # alias for readability at call sites


def _build_action(data: dict, intent: str) -> Action:
    intent = sanitize_intent(intent)
    try:
        atype = ActionType(data.get("type"))
    except ValueError:
        atype = ActionType.NOOP
    params = {}
    if atype in (ActionType.BLOCK_IP, ActionType.UNBLOCK_IP):
        ip = _resolve_ip(data.get("ip"), intent)
        if ip:
            params["ip"] = ip
    elif data.get("target"):
        params["target"] = data["target"]
    # rationale is free AI text that lands in the audit log — never executed,
    # but sanitize so it can't carry terminal escapes into logs.
    return Action(atype, params, rationale=sanitize_text(data.get("rationale", "")))


def _heuristic_report(text: str) -> str:
    """Offline attack triage — pattern-match common signatures. The 'basic' tier
    when the SNN isn't loaded. Real diagnosis needs the model."""
    t = text.lower()
    sigs = []
    if any(s in t for s in ("union select", "' or '1'='1", "sqlmap", " or 1=1")):
        sigs.append("SQL injection")
    if "../" in t or "%2e%2e" in t:
        sigs.append("path traversal")
    if any(s in t for s in ("/bin/sh", "wget ", "curl ", "chmod +x", "busybox")):
        sigs.append("remote code execution / dropper")
    if "${jndi:" in t:
        sigs.append("Log4Shell (CVE-2021-44228) probe")
    if any(s in t for s in ("nmap", "masscan", "zgrab", "nikto")):
        sigs.append("automated scanner")
    if any(s in t for s in ("authorization: basic", "admin:", "root:", "password=")):
        sigs.append("credential brute-force")
    if not sigs:
        sigs.append("unclassified probe")
    high = {"SQL injection", "remote code execution / dropper",
            "Log4Shell (CVE-2021-44228) probe"}
    sev = "HIGH" if high & set(sigs) else "MEDIUM"
    return (f"[heuristic triage] Likely: {', '.join(sigs)}. Severity: {sev}.\n"
            "The SNN brain will produce a full diagnosis once integrated.")


class AIAdapter:
    name = "abstract"

    def parse(self, intent: str) -> Action:
        raise NotImplementedError

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        """Free-form text in → text out. Used for attack analysis (not parsing)."""
        raise NotImplementedError


class MockAdapter(AIAdapter):
    """Zero-dependency keyword parser. Proves the pipeline, runs anywhere.
    Deterministic, offline, free — and the interim default until the SNN lands."""

    name = "mock"

    def parse(self, intent: str) -> Action:
        text = sanitize_intent(intent).lower().strip()
        ip = _resolve_ip(None, intent)
        pm = re.search(r"\bpid\s*(\d+)", text) or re.search(r"\b(\d{2,})\b", text)
        target = pm.group(1) if pm else None

        # VPN (checked first — "vpn off" must not be read as a block).
        if "vpn" in text or "tunnel" in text:
            tgt = "tor" if "tor" in text else None
            if any(w in text for w in ("off", "down", "disconnect", "stop", "disable")):
                return Action(ActionType.VPN_DOWN, {"target": tgt} if tgt else {},
                              rationale="user asked to turn the VPN off")
            return Action(ActionType.VPN_UP, {"target": tgt} if tgt else {},
                          rationale="user asked to turn the VPN on")

        # Quarantine family — kill/release checked before the bare verb so that
        # "kill quarantined 4321" isn't mis-read as a fresh quarantine.
        if (("kill" in text or "wipe" in text or "reject" in text)
                and ("process" in text or "quarantine" in text or target)):
            return Action(ActionType.KILL_QUARANTINE,
                          {"target": target} if target else {},
                          rationale="kill and wipe quarantined process")
        if "release" in text or ("trust" in text and "process" in text):
            return Action(ActionType.RELEASE_QUARANTINE,
                          {"target": target} if target else {},
                          rationale="release process from quarantine")
        if any(w in text for w in ("quarantine", "isolate", "suspicious")):
            return Action(ActionType.QUARANTINE, {"target": target} if target else {},
                          rationale="isolate an unknown process in RAM")

        # Virtualization layer — run something uncertain in isolation.
        if (any(w in text for w in ("sandbox", "virtual layer", "digital layer"))
                or ("run" in text and any(w in text for w in
                    ("safely", "uncertain", "not sure", "unsure", "risky")))):
            m2 = re.search(r"run\s+(\S+)", text) or re.search(r"sandbox\s+(\S+)", text)
            return Action(ActionType.SANDBOX_RUN,
                          {"target": m2.group(1)} if m2 else {},
                          rationale="run in an isolated layer")

        # IP blocklist.
        if any(w in text for w in ("unblock", "allow", "whitelist", "permit")):
            return Action(ActionType.UNBLOCK_IP, {"ip": ip} if ip else {},
                          rationale="user asked to unblock an address")
        if any(w in text for w in ("block", "ban", "drop", "deny", "kill")):
            return Action(ActionType.BLOCK_IP, {"ip": ip} if ip else {},
                          rationale="user asked to block an address")
        if any(w in text for w in ("list", "show", "what", "blocked")):
            return Action(ActionType.LIST_BLOCKED, {},
                          rationale="user asked to see the blocklist")
        return Action(ActionType.NOOP, {},
                      rationale="could not map intent to a known action")

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        return _heuristic_report(user)


class SNNAdapter(AIAdapter):
    """LOCAL SNN plane — an in-process spiking neural network. No API, no key,
    no HTTP. The model implementation lives in guardd/snn.py (pending: its
    methods raise NotImplementedError with a clear message until the code lands)."""

    name = "snn"

    def __init__(self, model_path: str | None = None, **_) -> None:
        from . import snn
        self.brain = snn.SNNBrain(model_path=model_path)

    def parse(self, intent: str) -> Action:
        # The brain proposes a dict; _build_action + _resolve_ip keep it honest,
        # and policy.py still has the only real say.
        return _build_action(self.brain.parse_intent(intent), intent)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        return self.brain.complete(system, user, max_tokens)


# --- pluggable reasoning brains (opt-in): Claude (API) and Ollama (local) -----

# Intent → single typed action, as strict JSON. The IP rule is belt-and-braces:
# _build_action/_resolve_ip discard any address the user didn't actually type.
_PARSE_SYSTEM = (
    "You map ONE security intent to ONE VeloGuard action. Reply with ONLY a JSON "
    "object and no prose: {\"type\": <one of block_ip, unblock_ip, list_blocked, "
    "vpn_up, vpn_down, quarantine, release_quarantine, kill_quarantine, "
    "sandbox_run, noop>, \"ip\": <IPv4 string or null>, \"target\": <string or "
    "null>, \"rationale\": <short reason>}. Only ever use an IP that appears "
    "verbatim in the intent; never invent one."
)


def _extract_json(text: str) -> dict:
    """Pull the first {...} object out of a model reply (tolerating code fences
    and surrounding prose). Falls back to NOOP so a chatty model is never fatal."""
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
        return obj if isinstance(obj, dict) else {"type": "noop"}
    except (ValueError, json.JSONDecodeError):
        return {"type": "noop", "rationale": "model did not return valid JSON"}


class ClaudeAdapter(AIAdapter):
    """Anthropic Messages API. Only the intent/prompt leaves the box; the key is
    read from state (chmod 600) or the environment and never logged."""

    name = "claude"
    API = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, model: str | None = None, api_key: str | None = None, **_) -> None:
        self.model = model or "claude-sonnet-5"
        self.api_key = api_key

    def _post(self, system: str, user: str, max_tokens: int) -> str:
        if not self.api_key:
            raise RuntimeError(
                "no Claude API key — run `guardd setup` or set ANTHROPIC_API_KEY")
        body = json.dumps({
            "model": self.model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(self.API, data=body, headers={
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Claude API error {e.code}") from None
        except OSError as e:
            raise RuntimeError(f"Claude API unreachable ({e})") from None
        parts = [b.get("text", "") for b in data.get("content", [])
                 if b.get("type") == "text"]
        return "".join(parts).strip()

    def parse(self, intent: str) -> Action:
        text = self._post(_PARSE_SYSTEM, sanitize_intent(intent), 300)
        return _build_action(_extract_json(text), intent)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        return self._post(system, sanitize_text(user, 8000), max_tokens)


class OllamaAdapter(AIAdapter):
    """A LOCAL model served by Ollama — private, free, offline. No key, and
    nothing leaves the machine (talks to 127.0.0.1:11434 by default)."""

    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None, **_) -> None:
        self.model = model or "llama3.1"
        self.host = (host or "http://127.0.0.1:11434").rstrip("/")

    def _post(self, system: str, user: str, max_tokens: int, fmt_json: bool = False) -> str:
        payload = {
            "model": self.model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "options": {"num_predict": max_tokens},
        }
        if fmt_json:
            payload["format"] = "json"
        req = urllib.request.Request(
            self.host + "/api/chat", data=json.dumps(payload).encode(),
            headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
        except OSError as e:
            raise RuntimeError(
                f"Ollama unreachable at {self.host} ({e}) — is `ollama serve` "
                "running and the model pulled?") from None
        return (data.get("message", {}) or {}).get("content", "").strip()

    def parse(self, intent: str) -> Action:
        text = self._post(_PARSE_SYSTEM, sanitize_intent(intent), 300, fmt_json=True)
        return _build_action(_extract_json(text), intent)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        return self._post(system, sanitize_text(user, 8000), max_tokens)


_ADAPTERS = {
    "mock": MockAdapter,
    "snn": SNNAdapter,
    "claude": ClaudeAdapter,
    "ollama": OllamaAdapter,
}


def get_adapter(name: str, **cfg) -> AIAdapter:
    try:
        cls = _ADAPTERS[name]
    except KeyError:
        raise ValueError(
            f"unknown adapter: {name!r} (choices: {', '.join(_ADAPTERS)})") from None
    return cls(**cfg)
