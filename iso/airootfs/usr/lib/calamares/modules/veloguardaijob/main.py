#!/usr/bin/env python3
"""VeloGuardOS — Calamares job: apply the AI page's choices to the installed
system. Reads global storage set by the veloguardai QML page and configures the
guard (provider/model/key) for the new user, or pulls the chosen Ollama model.
Runs in the install target via target_env_call. Best-effort: failures warn, not
abort."""

import libcalamares

GUARD = "/opt/veloguard/bin/veloguard"


def _username():
    try:
        users = libcalamares.globalstorage.value("users")
        if isinstance(users, list) and users:
            return users[0].get("name")
    except Exception:
        pass
    return None


def run():
    gs = libcalamares.globalstorage
    provider = gs.value("veloguard_ai_provider")
    if not provider:
        return None
    key = gs.value("veloguard_ai_key") or ""
    model = gs.value("veloguard_ai_model") or ""
    user = _username()

    def in_target(args):
        cmd = (["runuser", "-u", user, "--"] + args) if user else args
        try:
            libcalamares.utils.target_env_call(cmd)
        except Exception as e:                       # never abort the install
            libcalamares.utils.warning("veloguardaijob: %s" % e)

    if provider in ("openai", "anthropic", "claude"):
        prov = "claude" if provider == "anthropic" else "openai"
        in_target([GUARD, "use", prov])
        if model:
            in_target([GUARD, "model", prov, model])
        if key:
            in_target([GUARD, "key", prov, key])
    elif provider == "ollama":
        in_target([GUARD, "use", "ollama"] + ([model] if model else []))
        if model:                                    # pull the model system-wide
            try:
                libcalamares.utils.target_env_call(["ollama", "pull", model])
            except Exception as e:
                libcalamares.utils.warning("veloguardaijob ollama: %s" % e)
    return None
