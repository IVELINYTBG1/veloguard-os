"""The hot-swappable core — runtime brain selection + credentials.

VeloGuard's "which AI, which model, which key" is mutated ONLY by explicit user
commands (`guardd use|model|key`). Nothing here ever changes on its own. The run
pipeline reads this state fresh on every action, so a swap takes effect on the
very next command — that is the "hot swap, only when the user types it" rule.

Two stores, on purpose:
  * state.json        — active provider + chosen model per provider (no secrets)
  * credentials.json  — API keys, chmod 600, NEVER logged or printed in full

Resolution order (so power users and scripts keep working):
  model:  $VELOGUARD_<PROVIDER>_MODEL  >  stored model  >  built-in default
  key:    $ANTHROPIC_API_KEY / $OPENAI_API_KEY  >  stored key  >  (none)
  active: --adapter flag  >  stored active  >  config.json default  >  mock
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

# The four AI planes. KEYED ones need an API key; the rest don't.
PROVIDERS = ("mock", "ollama", "claude", "openai")
KEYED = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
DEFAULT_MODELS = {
    "ollama": "llama3.2:1b",
    "claude": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
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


def _cred_file() -> Path:
    return state_dir() / "credentials.json"


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
    s = _load(_state_file())
    s.setdefault("models", {})[provider] = model
    _state_file().write_text(json.dumps(s, indent=2))


def set_base_url(provider: str, url: str) -> None:
    s = _load(_state_file())
    s.setdefault("base_urls", {})[provider] = url
    _state_file().write_text(json.dumps(s, indent=2))


def set_key(provider: str, key: str) -> None:
    """Store a credential with restrictive perms. The value never leaves here
    except to the provider's own API."""
    c = _load(_cred_file())
    c[provider] = key
    f = _cred_file()
    f.write_text(json.dumps(c, indent=2))
    f.chmod(0o600)


# --- resolution (the run pipeline reads through these) ----------------------

def active_provider(cli: str | None = None, config_default: str | None = None) -> str:
    return cli or _load(_state_file()).get("active") or config_default or "mock"


def model_for(provider: str) -> str | None:
    env = os.environ.get(f"VELOGUARD_{provider.upper()}_MODEL")
    stored = _load(_state_file()).get("models", {}).get(provider)
    return env or stored or DEFAULT_MODELS.get(provider)


def key_for(provider: str) -> str | None:
    env_name = KEYED.get(provider)
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return _load(_cred_file()).get(provider)


def base_url_for(provider: str) -> str | None:
    if provider == "openai" and os.environ.get("VELOGUARD_OPENAI_BASE_URL"):
        return os.environ["VELOGUARD_OPENAI_BASE_URL"]
    return _load(_state_file()).get("base_urls", {}).get(provider)


def adapter_config(provider: str) -> dict:
    """Concrete kwargs to construct the adapter for `provider`."""
    if provider == "mock":
        return {}
    cfg: dict = {"model": model_for(provider)}
    if provider in KEYED:
        cfg["key"] = key_for(provider)
    if provider == "ollama":
        cfg["host"] = os.environ.get("VELOGUARD_OLLAMA_HOST")
    if provider == "openai":
        cfg["base_url"] = base_url_for("openai")
    return cfg


# --- introspection (status / models) ---------------------------------------

def mask(key: str | None) -> str | None:
    if not key:
        return None
    return f"…{key[-4:]}" if len(key) >= 4 else "set"


def key_source(provider: str) -> str | None:
    """Where the active key comes from — for honest status output."""
    if provider not in KEYED:
        return None
    if os.environ.get(KEYED[provider]):
        return "env"
    if _load(_cred_file()).get(provider):
        return "stored"
    return None


def list_ollama_models(host: str | None = None) -> list[str]:
    """What's actually pulled locally — answers 'they might have multiple models'."""
    host = host or os.environ.get("VELOGUARD_OLLAMA_HOST", "http://localhost:11434")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as r:
            data = json.loads(r.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []
