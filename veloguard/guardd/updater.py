"""Built-in updater — merge kernel updates and signed VeloGuard releases, safely.

Two streams:
  veloguard — our userspace (guard, scripts, kernel fragments). SIGNED releases.
  kernel    — upstream Linux: fetch a new tag, re-merge our fragments, rebuild.

NON-NEGOTIABLE: every 'veloguard' update is verified against a PINNED public key
before anything touches disk. Unsigned or tampered → refused. The updater fails
CLOSED (missing key / missing openssl / bad signature all mean "do not apply").
An updater that skips this is a malware-delivery service, not a guard.

Agent-friendly: `check()` is read-only and JSON-able, so an external "keep it
updated" agent can poll, decide, and call apply (which re-verifies + audits).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

VELOGUARD_DIR = Path(__file__).resolve().parent.parent
KERNEL_TREE = VELOGUARD_DIR.parent
VERSION_FILE = VELOGUARD_DIR / "VERSION"
PUBKEY = VELOGUARD_DIR / "keys" / "veloguard-release.pem"
DEFAULT_MANIFEST = "https://raw.githubusercontent.com/IVELINYTBG1/veloguard-os/main/manifest.json"

# Prebuilt-kernel offline updates (Fedora-style: download in the background,
# apply on reboot). The staged package lives here; systemd enters
# system-update.target on the next boot iff SYSTEM_UPDATE_FLAG exists.
KERNEL_STAGE = Path("/var/lib/veloguard/staged-kernel")
SYSTEM_UPDATE_FLAG = Path("/system-update")


class UpdateError(Exception):
    pass


# --- versions --------------------------------------------------------------

def local_veloguard_version() -> str:
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return "0.0.0"


def local_kernel_version() -> str:
    try:
        mk = (KERNEL_TREE / "Makefile").read_text()[:600]
        v = {k: re.search(rf"^{k} = (.*)$", mk, re.M) for k in
             ("VERSION", "PATCHLEVEL", "SUBLEVEL")}
        return ".".join(v[k].group(1).strip() for k in
                        ("VERSION", "PATCHLEVEL", "SUBLEVEL") if v[k])
    except OSError:
        return "?"


# --- fetch + verify (the trust boundary) -----------------------------------

def _fetch(src: str) -> bytes:
    if src.startswith(("http://", "https://")):
        with urllib.request.urlopen(src, timeout=30) as r:
            return r.read()
    return Path(src).read_bytes()


def verify(data: bytes, sig: bytes) -> bool:
    """True only if `sig` is a valid signature of `data` under the pinned key.
    Any uncertainty (no key, no openssl, bad sig) returns False — fail closed."""
    if not PUBKEY.exists() or shutil.which("openssl") is None:
        return False
    with tempfile.TemporaryDirectory() as d:
        dp, sp = Path(d) / "data", Path(d) / "sig"
        dp.write_bytes(data)
        sp.write_bytes(sig)
        rc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", str(PUBKEY),
             "-signature", str(sp), str(dp)],
            capture_output=True).returncode
        return rc == 0


def load_manifest(source: str | None = None) -> dict:
    """Fetch the manifest and its detached signature; refuse if unverified."""
    source = source or os.environ.get("VELOGUARD_UPDATE_URL", DEFAULT_MANIFEST)
    data = _fetch(source)
    try:
        sig = _fetch(source + ".sig")
    except Exception as e:
        raise UpdateError(f"no signature alongside manifest: {e}") from e
    if not verify(data, sig):
        raise UpdateError("manifest signature INVALID — refusing (fail closed)")
    return json.loads(data)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# --- check (read-only; safe for the agent to poll) -------------------------

def check(source: str | None = None) -> dict:
    m = load_manifest(source)
    out = {"verified": True, "domains": {}}
    cur_v, lat_v = local_veloguard_version(), m.get("veloguard", {}).get("version")
    out["domains"]["veloguard"] = {
        "current": cur_v, "latest": lat_v,
        "update_available": bool(lat_v) and lat_v != cur_v}
    cur_k, lat_k = local_kernel_version(), m.get("kernel", {}).get("version")
    out["domains"]["kernel"] = {
        "current": cur_k, "latest": lat_k,
        "update_available": bool(lat_k) and lat_k != cur_k}
    return out


# --- apply (re-verifies; atomic with rollback for veloguard) ---------------

def apply_veloguard(source: str | None = None, dry_run: bool = True) -> str:
    m = load_manifest(source)                      # verifies the manifest
    info = m.get("veloguard", {})
    art, want = info.get("artifact"), info.get("sha256")
    if not art or not want:
        raise UpdateError("manifest has no veloguard artifact")
    if dry_run:
        return (f"[dry-run] would fetch {art}, verify sha256, back up "
                f"{VELOGUARD_DIR} → .bak, then swap in v{info.get('version')}")
    with tempfile.TemporaryDirectory() as d:
        tarball = Path(d) / "rel.tar.gz"
        tarball.write_bytes(_fetch(art))
        got = sha256(tarball)
        if got != want:                            # manifest is signed → chain of trust
            raise UpdateError(f"artifact sha256 mismatch (got {got[:12]}…)")
        backup = VELOGUARD_DIR.with_suffix(".bak")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(VELOGUARD_DIR, backup)
        try:
            shutil.unpack_archive(str(tarball), str(VELOGUARD_DIR.parent))
        except Exception as e:
            shutil.rmtree(VELOGUARD_DIR, ignore_errors=True)
            shutil.move(str(backup), str(VELOGUARD_DIR))
            raise UpdateError(f"apply failed, rolled back: {e}") from e
    return f"updated veloguard → v{info.get('version')} (backup at {VELOGUARD_DIR}.bak)"


def rollback_veloguard() -> str:
    backup = VELOGUARD_DIR.with_suffix(".bak")
    if not backup.exists():
        raise UpdateError("no backup to roll back to")
    shutil.rmtree(VELOGUARD_DIR, ignore_errors=True)
    shutil.move(str(backup), str(VELOGUARD_DIR))
    return "rolled back veloguard to the previous version"


def apply_kernel(source: str | None = None, build: bool = False,
                 dry_run: bool = True) -> str:
    """Fetch the target upstream tag, re-merge our fragments, olddefconfig, build.
    Upstream integrity comes from git (and optionally `git verify-tag`)."""
    m = load_manifest(source)
    tag = m.get("kernel", {}).get("tag")
    if not tag:
        raise UpdateError("manifest has no kernel tag")
    frags = [f"veloguard/kernel/veloguardos-{x}.config"
             for x in ("base", "desktop", "hardware")]
    steps = [
        ["git", "-C", str(KERNEL_TREE), "fetch", "--depth", "1", "origin", "tag", tag],
        ["git", "-C", str(KERNEL_TREE), "checkout", tag],
        ["scripts/kconfig/merge_config.sh", "-m",
         "arch/x86/configs/x86_64_defconfig", *frags],
        ["make", "olddefconfig"],
    ]
    if build:
        steps.append(["make", "-j", str(os.cpu_count() or 4)])
    if dry_run:
        return "[dry-run] kernel update steps:\n  " + "\n  ".join(
            " ".join(s) for s in steps)
    out = []
    for s in steps:
        cwd = str(KERNEL_TREE) if s[0] in ("scripts/kconfig/merge_config.sh", "make") else None
        r = subprocess.run(s, cwd=cwd, capture_output=True, text=True)
        if r.returncode != 0:
            raise UpdateError(f"kernel step failed: {' '.join(s)}\n{r.stderr[-400:]}")
        out.append(" ".join(s))
    return "kernel updated to " + tag + ":\n  " + "\n  ".join(out)


# --- kernel: prebuilt, offline, apply-on-reboot (the shippable path) --------
# Users don't compile. CI builds linux-veloguard once; the updater downloads the
# SIGNED, hash-pinned package in the background and stages it. Applying happens
# on the next reboot — and only if the user ticked the box on the restart dialog.

def kernel_update_pending() -> dict | None:
    """If a verified kernel package is staged, return {'version','package'};
    else None. Read-only — safe for the restart UI / agent to poll."""
    try:
        return json.loads((KERNEL_STAGE / "pending.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def stage_kernel(source: str | None = None, dry_run: bool = True) -> str:
    """Download + verify the prebuilt kernel named in the SIGNED manifest and
    stage it. Does NOT arm the reboot — that's the user's opt-in at restart
    (the checkbox → arm_reboot_update())."""
    m = load_manifest(source)                       # verifies the signature first
    k = m.get("kernel", {})
    art, want, ver, pkg = (k.get("artifact"), k.get("sha256"),
                           k.get("version"), k.get("package"))
    if not (art and want and pkg):
        raise UpdateError("manifest kernel block has no prebuilt artifact/sha256/"
                          "package — the prebuilt channel isn't published yet")
    if ver and ver == local_kernel_version():
        return f"kernel already at {ver} — nothing to stage"
    if dry_run:
        return (f"[dry-run] would fetch {pkg}, verify sha256, stage to "
                f"{KERNEL_STAGE}, mark pending v{ver}")
    KERNEL_STAGE.mkdir(parents=True, exist_ok=True)
    dest = KERNEL_STAGE / pkg
    dest.write_bytes(_fetch(art))
    got = sha256(dest)
    if got != want:                                  # manifest signed → trust chain
        dest.unlink(missing_ok=True)
        raise UpdateError(f"kernel artifact sha256 mismatch (got {got[:12]}…) — refused")
    (KERNEL_STAGE / "pending.json").write_text(
        json.dumps({"version": ver, "package": pkg}))
    return f"staged kernel v{ver} ({pkg}) — confirm at restart to install"


def arm_reboot_update() -> str:
    """Opt-in confirmed: flip systemd into offline-update mode for the next boot
    (it installs the staged package, then reboots normally)."""
    if kernel_update_pending() is None:
        raise UpdateError("nothing staged to apply")
    if SYSTEM_UPDATE_FLAG.is_symlink() or SYSTEM_UPDATE_FLAG.exists():
        SYSTEM_UPDATE_FLAG.unlink()
    SYSTEM_UPDATE_FLAG.symlink_to(KERNEL_STAGE)      # systemd.offline-updates(7)
    return "armed — VeloGuardOS will install the kernel on the next reboot"


def disarm_reboot_update() -> str:
    """Opt-out: keep the package staged but don't apply it on reboot."""
    if SYSTEM_UPDATE_FLAG.is_symlink() or SYSTEM_UPDATE_FLAG.exists():
        SYSTEM_UPDATE_FLAG.unlink()
    return "disarmed — staged kernel will not be applied on reboot"
