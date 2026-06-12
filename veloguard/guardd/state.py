"""The hot-swappable core — runtime brain selection.

VeloGuard's "which brain" is mutated ONLY by explicit user commands
(`guardd use|model`). Nothing here ever changes on its own. The run pipeline
reads this state fresh on every action, so a swap takes effect on the very
next command — that is the "hot swap, only when the user types it" rule.

There are no credentials anymore: the cloud-API planes are gone. The brain is
local (guardd/snn.py) — the only per-provider setting left is the SNN's
model path. (credentials.json from older installs is simply ignored.)

Resolution order (so power users and scripts keep working):
  model:  $VELOGUARD_<PROVIDER>_MODEL  >  stored model  >  built-in default
  active: --adapter flag  >  stored active  >  config.json default  >  mock
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# The two AI planes: the local SNN brain, and the offline keyword fallback.
PROVIDERS = ("mock", "snn")
DEFAULT_MODELS: dict[str, str] = {
    # snn: model path; default resolved lazily (~/.config/veloguard/snn/)
}


def state_dir() -> Path:
    """~/.config/veloguard (or $VELOGUARD_STATE). Created 0700 if missing."""
    d = os.environ.get("VELOGUARD_STATE")
    base = Path(d) if d else (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "veloguard")
    base.mkdir(parents=True, exist_ok=True)
    try:
        base.chmod(0o700)
    except OSError:
        pass
    return base


def _state_file() -> Path:
    return state_dir() / "state.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


# --- mutations (the command verbs write through these) ----------------------

def set_active(provider: str) -> None:
    s = _load(_state_file())
    s["active"] = provider
    _state_file().write_text(json.dumps(s, indent=2))


def set_model(provider: str, model: str) -> None:
    """For 'snn' the model is a filesystem path to the network's weights."""
    s = _load(_state_file())
    s.setdefault("models", {})[provider] = model
    _state_file().write_text(json.dumps(s, indent=2))


# --- resolution (the run pipeline reads through these) ----------------------

def active_provider(cli: str | None = None, config_default: str | None = None) -> str:
    return cli or _load(_state_file()).get("active") or config_default or "mock"


def model_for(provider: str) -> str | None:
    env = os.environ.get(f"VELOGUARD_{provider.upper()}_MODEL")
    stored = _load(_state_file()).get("models", {}).get(provider)
    return env or stored or DEFAULT_MODELS.get(provider)


def adapter_config(provider: str) -> dict:
    """Concrete kwargs to construct the adapter for `provider`."""
    if provider == "snn":
        return {"model_path": model_for("snn")}
    return {}
