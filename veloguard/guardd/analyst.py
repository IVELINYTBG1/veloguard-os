"""AI attack analyst — turns a raw honeypot capture into a human report.

Diagnosis runs entirely on this machine, like everything else: the SNN brain
produces the full report; without it (mock) you get offline heuristic triage.

  deep   the local SNN brain (guardd/snn.py)  → full diagnosis: technique,
         likely CVE, MITRE-style mapping, IOCs, step-by-step remediation.
  basic  no model (mock)                      → offline heuristic triage.
"""

from __future__ import annotations


def analysis_tier(provider: str, model: str | None) -> str:
    if provider == "snn":
        return "deep"
    return "basic"               # mock / no model


_SYSTEMS = {
    "deep": (
        "You are a senior incident-response analyst reading a honeypot capture. "
        "Produce a precise diagnosis: (1) attack class & technique, (2) the most "
        "likely CVE or named exploit if any, (3) MITRE ATT&CK tactic/technique, "
        "(4) indicators of compromise (IPs, payload hashes, URLs, user-agents), "
        "(5) severity with justification, (6) concrete step-by-step remediation. "
        "Be specific and technical; this reader is an expert."),
}

_MAXTOK = {"deep": 900}


def _format_capture(cap: dict) -> str:
    data = cap.get("data", "")
    if len(data) > 4000:
        data = data[:4000] + "…(truncated)"
    return (f"Honeypot service: {cap.get('service')} (port {cap.get('dst_port')})\n"
            f"Source: {cap.get('src_ip')}:{cap.get('src_port')}\n"
            f"Bytes received: {cap.get('bytes')}\n"
            f"--- payload begins ---\n{data}\n--- payload ends ---")


def analyze_capture(cap: dict, adapter, provider: str, model: str | None) -> dict:
    """Return {tier, report}. Falls back to heuristic if the model call fails."""
    tier = analysis_tier(provider, model)
    user = _format_capture(cap)
    if tier == "basic":
        report = adapter.complete("", user)   # mock → heuristic
    else:
        try:
            report = adapter.complete(_SYSTEMS[tier], user, _MAXTOK[tier])
        except Exception as e:
            from .ai_adapter import _heuristic_report
            report = (f"[AI analysis failed: {e}]\n" + _heuristic_report(user))
            tier = "basic"
    return {"tier": tier, "report": report, "model": model, "provider": provider}
