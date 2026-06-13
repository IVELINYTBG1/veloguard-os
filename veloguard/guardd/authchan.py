"""Authenticated AI→kernel channel (anti-prompt-injection).

The AI plane only ever *proposes* a typed Action; the guard (policy engine)
approves it; and ONLY then does the guard seal the action with a per-boot HMAC.
The kernel executor refuses to act on a sealed channel unless the seal matches.

So a prompt-injected or otherwise compromised AI cannot forge a privileged
kernel operation that skipped the policy gate — the seal can only be produced
by code holding the in-process key, which is the guard itself. The key is
random per boot, lives only in this process's memory, and is never logged or
written to disk.

This is integrity + authenticity (a tamper-proof channel), which is what
defends against forged/injected commands. It is NOT confidentiality — within a
single process that's meaningless; for a future *remote* AI plane the seal can
be upgraded to an AEAD (encrypt-then-MAC) over the same boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets

# Per-process, per-boot. Regenerated every start; never persisted or logged.
_KEY = secrets.token_bytes(32)


def _canonical(action) -> bytes:
    """Deterministic bytes for an Action: its type + sorted params. Params are
    JSON-safe because Action.validate() ran before we ever sign."""
    atype = getattr(action, "type", None)
    payload = {
        "type": getattr(atype, "value", str(atype)),
        "params": getattr(action, "params", {}) or {},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def seal(action) -> str:
    """Guard-only: stamp a policy-approved action with the channel HMAC."""
    return hmac.new(_KEY, _canonical(action), hashlib.sha256).hexdigest()


def verify(action, token: str | None) -> bool:
    """Executor side: True iff `token` is this guard's seal for exactly `action`."""
    if not token:
        return False
    try:
        return hmac.compare_digest(str(token), seal(action))
    except Exception:
        return False
