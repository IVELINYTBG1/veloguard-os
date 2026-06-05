"""Network trust classifier — the AI's 'is this a safe network?' judgement.

Memory is the source of truth: once you've judged a network, we remember it.
For first-time networks we fall back to a safe heuristic (open Wi-Fi = untrusted)
and let the user (or, non-interactively, the safe default) decide.

Verdicts:
  trusted    — known-good; do nothing.
  untrusted  — known-bad OR open/public; AUTO bring the VPN up, no questions.
  unknown    — never seen, but encrypted; ask the user.
"""

from __future__ import annotations

from . import memory

OPEN = ("", "none", "open", "--", None)


def classify(ssid: str | None, bssid: str | None,
             security: str | None) -> tuple[str, str]:
    stored = memory.get_network_trust(ssid, bssid)
    if stored == "trusted":
        return "trusted", "you trusted this network before"
    if stored in ("untrusted", "blocked"):
        return "untrusted", f"you marked this network {stored} before"

    sec = (security or "").strip().lower()
    if sec in OPEN:
        return "untrusted", "open network with no encryption — high risk"
    return "unknown", "first time on this network"
