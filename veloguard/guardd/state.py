"""The hot-swappable core — runtime brain selection.

VeloGuard's "which brain" is mutated ONLY by explicit user commands
(`guardd use|model`). Nothing here ever changes on its own. The run pipeline
reads this state fresh on every action, so a swap takes effect on the very
next command — that is the "hot swap, only when the user types it" rule.

Per-provider settings:
  * snn    — a filesystem path to the model weights
  * claude — a model id + an API key (stored in credentials.json, chmod 600, or
             read from ANTHROPIC_API_KEY / VELOGUARD_CLAUDE_KEY; never logged)
  * ollama — a model id + a host URL (default 127.0.0.1:11434; nothing leaves)

Resolution order (so power users and scripts keep working):
  model:  $VELOGUARD_<PROVIDER>_MODEL  >  stored model  >  built-in default
  host:   $VELOGUARD_<PROVIDER>_HOST   >  stored host   >  built-in default
  key:    $VELOGUARD_CLAUDE_KEY / $ANTHROPIC_API_KEY  >  credentials.json
  active: --adapter flag  >  stored active  >  config.json default  >  mock
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# AI planes: offline keywords, the local SNN brain, and the opt-in pluggable
# reasoning brains (Claude via API, Ollama locally).
PROVIDERS = ("mock", "snn", "claude", "ollama")
DEFAULT_MODELS: dict[str, str] = {
    "claude": "claude-sonnet-5",
    "ollama": "llama3.1",
    # snn: model path; default resolved lazily (~/.config/veloguard/snn/)
}
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


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
    """For 'snn' the model is a filesystem path; for claude/ollama a model id."""
    s = _load(_state_file())
    s.setdefault("models", {})[provider] = model
    _state_file().write_text(json.dumps(s, indent=2))


def set_host(provider: str, host: str) -> None:
    """The API/base URL for a provider (used by ollama)."""
    s = _load(_state_file())
    s.setdefault("hosts", {})[provider] = host
    _state_file().write_text(json.dumps(s, indent=2))


def _cred_file() -> Path:
    return state_dir() / "credentials.json"


def set_key(provider: str, key: str) -> None:
    """Store an API key (claude), chmod 600. Never printed or logged."""
    f = _cred_file()
    creds = _load(f)
    creds[provider] = key
    f.write_text(json.dumps(creds, indent=2))
    try:
        f.chmod(0o600)
    except OSError:
        pass


def get_key(provider: str) -> str | None:
    if provider == "claude":
        env = os.environ.get("VELOGUARD_CLAUDE_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if env:
            return env
    return _load(_cred_file()).get(provider)


# --- resolution (the run pipeline reads through these) ----------------------

def active_provider(cli: str | None = None, config_default: str | None = None) -> str:
    return cli or _load(_state_file()).get("active") or config_default or "mock"


def model_for(provider: str) -> str | None:
    env = os.environ.get(f"VELOGUARD_{provider.upper()}_MODEL")
    stored = _load(_state_file()).get("models", {}).get(provider)
    return env or stored or DEFAULT_MODELS.get(provider)


def host_for(provider: str) -> str | None:
    env = os.environ.get(f"VELOGUARD_{provider.upper()}_HOST")
    stored = _load(_state_file()).get("hosts", {}).get(provider)
    default = DEFAULT_OLLAMA_HOST if provider == "ollama" else None
    return env or stored or default


def adapter_config(provider: str) -> dict:
    """Concrete kwargs to construct the adapter for `provider`."""
    if provider == "snn":
        return {"model_path": model_for("snn")}
    if provider == "claude":
        return {"model": model_for("claude"), "api_key": get_key("claude")}
    if provider == "ollama":
        return {"model": model_for("ollama"), "host": host_for("ollama")}
    return {}
