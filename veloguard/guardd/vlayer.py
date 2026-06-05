"""The virtualization layer — run an uncertain app in a 'digital layer' instantly.

When the AI or the user is unsure about a program but wants to run it anyway,
VeloGuard launches it isolated: the real filesystem is read-only and every write
goes to RAM (tmpfs), inside Linux namespaces. The app runs from disk but its
whole writable world is ephemeral — on exit it evaporates. Namespace setup is
milliseconds, so it's "on disk one second, in a digital layer the next."

Tiered by risk (degrades to the strongest tier actually installed):
  light  — bubblewrap + RAM writable layer, no network. Instant. The default.
  strong — gVisor (runsc): a userspace kernel intercepting syscalls.
  vm     — Firecracker/cloud-hypervisor microVM with its own kernel (VeloGuardOS
           can be that guest kernel). Strongest; still boots in ~125 ms.
"""

from __future__ import annotations

import os
import shutil

ORDER = ["light", "strong", "vm"]
TIER_FOR_RISK = {"low": "light", "medium": "strong", "high": "vm"}


def available_tiers() -> list[str]:
    av = []
    if shutil.which("bwrap"):
        av.append("light")
    if shutil.which("runsc"):
        av.append("strong")
    if shutil.which("firecracker") or shutil.which("cloud-hypervisor"):
        av.append("vm")
    return av or ["none"]


def resolve_tier(requested: str, available: list[str] | None = None) -> tuple[str, bool]:
    """Return (tier, degraded?). Falls back to the best *installed* tier."""
    available = available or available_tiers()
    if requested in available:
        return requested, False
    idx = ORDER.index(requested) if requested in ORDER else len(ORDER) - 1
    for t in reversed(ORDER[:idx + 1]):       # best available at-or-below request
        if t in available:
            return t, True
    for t in ORDER:                            # else anything we have
        if t in available:
            return t, True
    return "none", True


def build_argv(cmd: list[str], tier: str, allow_net: bool = False,
               persist: str | None = None) -> list[str]:
    if tier == "light":
        return _bwrap(cmd, allow_net, persist)
    if tier == "strong":
        return ["runsc", "--network", "host" if allow_net else "none", "do", *cmd]
    if tier == "vm":
        # Real launch needs a kernel + rootfs image; VeloGuardOS's own kernel can
        # be the guest. Shown for transparency; executor dry-runs it.
        return ["firecracker", "--no-api",
                "--config-file", "/etc/veloguard/microvm.json", "--", *cmd]
    return cmd  # "none" — no isolation available (shouldn't happen if bwrap present)


def _bwrap(cmd: list[str], allow_net: bool, persist: str | None) -> list[str]:
    home = os.path.expanduser("~")
    args = [
        "bwrap",
        "--ro-bind", "/", "/",            # whole system visible, READ-ONLY
        "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--tmpfs", "/run", "--tmpfs", "/var/tmp",
        "--tmpfs", home,                  # ephemeral RAM home — writes vanish
        "--unshare-user", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--unshare-cgroup",
        "--die-with-parent", "--new-session",
    ]
    if not allow_net:
        args += ["--unshare-net"]          # uncertain → no network by default
    if persist:                            # optional single rw escape hatch
        args += ["--bind", persist, persist]
    return [*args, "--", *cmd]


# --- risk assessment: the AI (or a heuristic) decides how hard to sandbox -----

def _heuristic_risk(app: str) -> tuple[str, str]:
    p = app.lower()
    if (any(d in p for d in ("/tmp/", "/download", "/dev/shm"))
            or p.endswith((".sh", ".appimage", ".bin", ".run", ".deb", ".rpm"))):
        return "high", "downloaded / unknown executable"
    if p.startswith(("/usr/bin/", "/bin/", "/usr/sbin/", "/sbin/")):
        return "low", "installed system binary"
    return "medium", "unrecognised program"


def assess_risk(app: str, adapter, provider: str, model: str | None) -> tuple[str, str]:
    """Ask the active AI to rate run-risk (low/medium/high); heuristic fallback.
    Mock has no real judgement (its complete() is the attack-triage tool), so it
    uses the run-risk heuristic directly."""
    if adapter is None or provider == "mock":
        return _heuristic_risk(app)
    sys_p = ("You are a security advisor. Rate the risk of running the named "
             "program in ONE word — low, medium, or high — then a brief reason.")
    try:
        out = adapter.complete(sys_p, f"Program: {app}", 80).lower()
    except Exception:
        return _heuristic_risk(app)
    for r in ("high", "medium", "low"):
        if r in out:
            return r, out.strip()[:160]
    return _heuristic_risk(app)
