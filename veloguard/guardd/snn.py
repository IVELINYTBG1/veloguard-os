"""The LOCAL SNN brain — VeloGuardOS's AI plane.

The product thesis is unchanged: an AI may run the machine, but ONLY through
the guard. What changed is the brain itself — no cloud APIs, no API keys, no
HTTP. The intelligence is a local spiking neural network running in-process;
nothing ever leaves the box.

════════════════════════════════════════════════════════════════════════════
 DROP-IN POINT — paste the SNN implementation into this file.
════════════════════════════════════════════════════════════════════════════

Implement the two methods on `SNNBrain` below. Everything else in VeloGuardOS
(CLI intents, voice, the honeypot analyst, status) already routes here through
`ai_adapter.get_adapter("snn")` — no other file needs touching when the model
lands.

The contract (the same one the guard has always enforced):

  parse_intent(intent: str) -> dict
      Natural language in, ONE structured action out:
        {
          "type":      one of guardd.actions.ActionType values —
                       block_ip | unblock_ip | list_blocked | vpn_up |
                       vpn_down | quarantine | release_quarantine |
                       kill_quarantine | sandbox_run | noop,
          "ip":        IPv4 string COPIED from the intent (block/unblock only),
          "target":    VPN profile / 'tor' / process pid or name (when relevant),
          "rationale": one short sentence explaining the mapping,
        }
      Anti-hallucination is enforced ABOVE this layer (`_resolve_ip` discards
      any IP the user didn't actually type), and the result still passes
      policy.py (allow / deny / needs-consent) before the executor ever runs.
      The model can suggest; only the guard decides.

  complete(system: str, user: str, max_tokens: int) -> str
      Free-form text generation — used by the honeypot analyst for attack
      diagnosis and by voice for spoken replies.

Model weights/config: `model_path` (set via `guardd model snn <path>`, default
~/.config/veloguard/snn/) — load lazily in `load()`, not at import time.
"""

from __future__ import annotations

_PENDING = (
    "the SNN model isn't wired in yet — this is the drop-in slot "
    "(guardd/snn.py). Until the model code lands, switch back with: "
    "guardd use mock"
)


class SNNBrain:
    """Skeleton awaiting the real spiking-network implementation."""

    name = "snn"

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path
        self._loaded = False

    def load(self) -> None:
        """Lazy-load weights from self.model_path. Called before first use."""
        raise NotImplementedError(_PENDING)

    def parse_intent(self, intent: str) -> dict:
        raise NotImplementedError(_PENDING)

    def complete(self, system: str, user: str, max_tokens: int = 600) -> str:
        raise NotImplementedError(_PENDING)
