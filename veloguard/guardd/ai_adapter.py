"""The AI plane — pluggable and swappable, exactly as the architecture demands.

Every adapter turns a human/AI natural-language *intent* into a structured
`Action`. The rest of VeloGuard neither knows nor cares whether that came from
Claude, Codex/OpenAI, a local llama, or a dumb regex. Swap the adapter, keep
the guard.

Two real choices, for two kinds of machine:
  * LOCAL  (ollama)         — private, free, needs a capable-ish PC
  * CLOUD  (claude/openai)  — works on a potato, needs an API key

Every cloud adapter here is STDLIB-ONLY (urllib) — no `pip install` required.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .actions import Action, ActionType

_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

# The structured shape every LLM is asked to emit. One enum + an optional IP.
_PROPERTIES = {
    "type": {"type": "string", "enum": [t.value for t in ActionType]},
    "ip": {"type": "string", "description": "IPv4 address copied from the request"},
    "target": {"type": "string",
               "description": "VPN profile name (or 'tor'), or a process pid/name"},
    "rationale": {"type": "string"},
}
_SYSTEM = (
    "You are the intent parser for VeloGuard, a security daemon. Map the user's "
    "request to exactly one action:\n"
    "- block_ip / unblock_ip: block or allow a host (put the IP in 'ip').\n"
    "- list_blocked: show the blocklist.\n"
    "- vpn_up / vpn_down: turn the VPN on/off ('target' = profile or 'tor').\n"
    "- quarantine: isolate a process ('target' = pid/name).\n"
    "- release_quarantine / kill_quarantine: free or kill a quarantined process.\n"
    "- noop: nothing fits.\n"
    "Copy any IP or target from the request verbatim; never invent one."
)


def _post(url: str, payload: dict, headers: dict, timeout: int = 60) -> dict:
    """Minimal stdlib JSON POST. Raises RuntimeError with a useful message."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} -> HTTP {e.code}: {e.read().decode()[:300]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"cannot reach {url}: {e.reason}") from e


def _resolve_ip(model_ip: str | None, intent: str) -> str | None:
    """Anti-hallucination: the only valid IP is one the user actually typed.
    Applies to *every* LLM adapter — the guard never acts on an invented host."""
    m = _IP_RE.search(intent)
    text_ip = m.group(1) if m else None
    if model_ip and model_ip != text_ip:
        model_ip = None  # model invented it — discard
    return model_ip or text_ip


def _build_action(data: dict, intent: str) -> Action:
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
    return Action(atype, params, rationale=data.get("rationale", ""))


def _heuristic_report(text: str) -> str:
    """Offline attack triage — pattern-match common signatures. The 'basic' tier
    when there's no LLM. Real diagnosis needs a model (ideally local + high-end)."""
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
            "Enable a local or cloud AI model for a full diagnosis.")


class AIAdapter(ABC):
    name = "abstract"

    @abstractmethod
    def parse(self, intent: str) -> Action:
        ...

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        """Free-form text in → text out. Used for attack analysis (not parsing)."""
        raise NotImplementedError


class MockAdapter(AIAdapter):
    """Zero-dependency keyword parser. Proves the pipeline, runs anywhere with
    no key and no model. Deterministic, offline, free."""

    name = "mock"

    def parse(self, intent: str) -> Action:
        text = intent.lower().strip()
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


class OllamaAdapter(AIAdapter):
    """LOCAL AI plane — no cloud, no key, nothing leaves the box. Needs Ollama
    running and a model pulled. Best for users with a capable PC who want
    privacy. Uses Ollama's JSON-schema mode so even small models stay structured.

    Env: VELOGUARD_OLLAMA_HOST (default http://localhost:11434),
         VELOGUARD_OLLAMA_MODEL (default llama3.2:1b)
    """

    name = "ollama"
    _SCHEMA = {"type": "object", "properties": _PROPERTIES,
               "required": ["type", "rationale"]}

    def __init__(self, host: str | None = None, model: str | None = None, **_) -> None:
        self.host = host or os.environ.get("VELOGUARD_OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.environ.get("VELOGUARD_OLLAMA_MODEL", "llama3.2:1b")

    def parse(self, intent: str) -> Action:
        body = _post(f"{self.host}/api/chat", {
            "model": self.model,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": intent}],
            "stream": False, "format": self._SCHEMA,
            "options": {"temperature": 0},
        }, headers={})
        content = body.get("message", {}).get("content", "").strip()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Ollama returned non-JSON: {content!r}") from e
        return _build_action(data, intent)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        body = _post(f"{self.host}/api/chat", {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }, headers={})
        return body.get("message", {}).get("content", "").strip()


class ClaudeAdapter(AIAdapter):
    """CLOUD AI plane via the Anthropic API — stdlib only, no SDK needed. Runs
    on the weakest machine; just needs ANTHROPIC_API_KEY. Uses Haiku (cheap
    intent classification) and tool-use to force structured output.

    Env: ANTHROPIC_API_KEY, VELOGUARD_CLAUDE_MODEL (default claude-haiku-4-5)
    """

    name = "claude"
    API = "https://api.anthropic.com/v1/messages"
    _TOOL = {"name": "emit_action",
             "description": "Translate the security intent into one VeloGuard action.",
             "input_schema": {"type": "object", "properties": _PROPERTIES,
                              "required": ["type", "rationale"]}}

    def __init__(self, key: str | None = None, model: str | None = None, **_) -> None:
        self.key = key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise RuntimeError(
                "no Claude API key — run:  guardd key claude <YOUR_KEY>  "
                "(or export ANTHROPIC_API_KEY)")
        self.model = model or os.environ.get("VELOGUARD_CLAUDE_MODEL", "claude-haiku-4-5")

    def parse(self, intent: str) -> Action:
        body = _post(self.API, {
            "model": self.model, "max_tokens": 512,
            "system": _SYSTEM, "tools": [self._TOOL],
            "tool_choice": {"type": "tool", "name": "emit_action"},
            "messages": [{"role": "user", "content": intent}],
        }, headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        for block in body.get("content", []):
            if block.get("type") == "tool_use":
                return _build_action(block["input"], intent)
        return Action(ActionType.NOOP, {}, rationale="model emitted no action")

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        body = _post(self.API, {
            "model": self.model, "max_tokens": max_tokens, "system": system,
            "messages": [{"role": "user", "content": user}],
        }, headers={"x-api-key": self.key, "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in body.get("content", [])
                       if b.get("type") == "text").strip()


class OpenAIAdapter(AIAdapter):
    """CLOUD AI plane via any OpenAI-compatible API — stdlib only. Covers OpenAI
    (Codex/GPT), plus Groq, Together, OpenRouter, or a local OpenAI server, by
    pointing the base URL wherever you like. Just needs OPENAI_API_KEY.

    Env: OPENAI_API_KEY,
         VELOGUARD_OPENAI_BASE_URL (default https://api.openai.com/v1),
         VELOGUARD_OPENAI_MODEL (default gpt-4o-mini)
    """

    name = "openai"
    _TOOL = {"type": "function", "function": {
        "name": "emit_action",
        "description": "Translate the security intent into one VeloGuard action.",
        "parameters": {"type": "object", "properties": _PROPERTIES,
                       "required": ["type", "rationale"]}}}

    def __init__(self, key: str | None = None, model: str | None = None,
                 base_url: str | None = None, **_) -> None:
        self.key = key or os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise RuntimeError(
                "no OpenAI API key — run:  guardd key openai <YOUR_KEY>  "
                "(or export OPENAI_API_KEY)")
        self.base = (base_url or os.environ.get(
            "VELOGUARD_OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.environ.get("VELOGUARD_OPENAI_MODEL", "gpt-4o-mini")

    def parse(self, intent: str) -> Action:
        body = _post(f"{self.base}/chat/completions", {
            "model": self.model, "temperature": 0,
            "messages": [{"role": "system", "content": _SYSTEM},
                         {"role": "user", "content": intent}],
            "tools": [self._TOOL],
            "tool_choice": {"type": "function", "function": {"name": "emit_action"}},
        }, headers={"Authorization": f"Bearer {self.key}"})
        try:
            call = body["choices"][0]["message"]["tool_calls"][0]
            data = json.loads(call["function"]["arguments"])
        except (KeyError, IndexError, json.JSONDecodeError):
            return Action(ActionType.NOOP, {}, rationale="model emitted no action")
        return _build_action(data, intent)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        body = _post(f"{self.base}/chat/completions", {
            "model": self.model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }, headers={"Authorization": f"Bearer {self.key}"})
        return body["choices"][0]["message"]["content"].strip()


_ADAPTERS = {
    "mock": MockAdapter,
    "ollama": OllamaAdapter,
    "claude": ClaudeAdapter,
    "openai": OpenAIAdapter,
}


def get_adapter(name: str, **cfg) -> AIAdapter:
    try:
        cls = _ADAPTERS[name]
    except KeyError:
        raise ValueError(
            f"unknown adapter: {name!r} (choices: {', '.join(_ADAPTERS)})") from None
    return cls(**cfg)
