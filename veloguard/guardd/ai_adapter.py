"""The AI plane — local-only, exactly as the architecture demands.

Every adapter turns a human *intent* into a structured `Action`. The rest of
VeloGuard neither knows nor cares where that came from. The cloud-API adapters
(Claude/OpenAI) and the Ollama HTTP client are GONE by design: VeloGuardOS's
brain is a local spiking neural network (guardd/snn.py) running in-process —
no API, no key, no HTTP, nothing leaves the box.

Two planes:
  * snn   — the real brain (model code lands in guardd/snn.py; pending)
  * mock  — deterministic keyword parser; offline fallback that always works
"""

from __future__ import annotations

import re

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


_ADAPTERS = {
    "mock": MockAdapter,
    "snn": SNNAdapter,
}


def get_adapter(name: str, **cfg) -> AIAdapter:
    try:
        cls = _ADAPTERS[name]
    except KeyError:
        raise ValueError(
            f"unknown adapter: {name!r} (choices: {', '.join(_ADAPTERS)})") from None
    return cls(**cfg)
