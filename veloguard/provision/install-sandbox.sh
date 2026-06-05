#!/usr/bin/env bash
#
# VeloGuardOS — virtualization layer tiers.
#
# The default 'light' tier (bubblewrap + RAM overlay) needs only bubblewrap and
# is already pulled by install-app-formats.sh. This adds the optional stronger
# tiers the AI can escalate to for riskier apps.
#
#   ./install-sandbox.sh              # ensure bubblewrap (light tier)
#   ./install-sandbox.sh --gvisor     # + gVisor runsc (strong tier)
#   ./install-sandbox.sh --all        # + notes for Firecracker (vm tier)
#
set -euo pipefail
say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }
priv() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# light tier — bubblewrap
if ! command -v bwrap >/dev/null; then
  if   command -v dnf     >/dev/null; then priv dnf install -y bubblewrap
  elif command -v apt-get >/dev/null; then priv apt-get update && priv apt-get install -y bubblewrap
  elif command -v pacman  >/dev/null; then priv pacman -S --noconfirm --needed bubblewrap
  else warn "install 'bubblewrap' manually"; fi
fi
command -v bwrap >/dev/null && say "light tier ready (bubblewrap)"

# strong tier — gVisor (runsc)
if [ "${1:-}" = "--gvisor" ] || [ "${1:-}" = "--all" ]; then
  say "installing gVisor (runsc) for the 'strong' tier…"
  arch="$(uname -m)"
  url="https://storage.googleapis.com/gvisor/releases/release/latest/${arch}"
  if ( cd /tmp && curl -fsSL "${url}/runsc" -o runsc \
        && curl -fsSL "${url}/runsc.sha512" -o runsc.sha512 \
        && sha512sum -c runsc.sha512 && chmod +x runsc \
        && priv mv runsc /usr/local/bin/ ); then
    say "gVisor installed (strong tier)"
  else
    warn "gVisor install failed — strong tier will keep degrading to light"
  fi
fi

# vm tier — Firecracker (separate kernel)
if [ "${1:-}" = "--firecracker" ] || [ "${1:-}" = "--all" ]; then
  say "Firecracker 'vm' tier needs a guest kernel + rootfs image."
  say "VeloGuardOS's own kernel build can serve as that guest kernel."
  say "Binary: https://github.com/firecracker-microvm/firecracker/releases"
fi

say "tiers available now:"
python3 - <<'PY' 2>/dev/null || true
import shutil
print("  light :", "yes" if shutil.which("bwrap") else "no")
print("  strong:", "yes" if shutil.which("runsc") else "no  (re-run with --gvisor)")
print("  vm    :", "yes" if (shutil.which("firecracker") or shutil.which("cloud-hypervisor")) else "no  (see --firecracker)")
PY
