#!/usr/bin/env bash
#
# VeloGuardOS — gaming + Windows .exe layer (OPTIONAL, heavy; opt-in).
#
# Proton and Wine are USERSPACE compatibility layers — there is no such thing as
# an "exe translation layer in the kernel." The ONLY kernel piece is binfmt_misc
# (already enabled in kernel/veloguardos-base.config), which lets the system hand
# a Windows .exe straight to Wine so it "just runs."
#
#   sudo ./install-gaming.sh
#
set -euo pipefail
say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }
[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo)"; exit 1; }

if command -v pacman >/dev/null; then
  # Steam needs 32-bit libs → enable [multilib].
  if ! grep -q '^\[multilib\]' /etc/pacman.conf; then
    say "enabling [multilib] (Steam needs 32-bit)…"
    printf '\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n' >> /etc/pacman.conf
  fi
  pacman -Syu --noconfirm --needed \
    steam wine wine-mono wine-gecko winetricks lutris \
    gamemode lib32-gamemode mangohud lib32-mangohud \
    vulkan-icd-loader lib32-vulkan-icd-loader lib32-mesa
elif command -v dnf >/dev/null; then
  dnf install -y steam wine winetricks lutris gamemode mangohud || \
    warn "enable RPM Fusion for Steam on Fedora"
else
  warn "install steam/wine/lutris with your package manager"; exit 1
fi

# Register .exe with binfmt_misc via Wine's handler (kernel hook already on).
systemctl restart systemd-binfmt 2>/dev/null || true

say "Done. Proton: open Steam → Settings → Compatibility → 'Enable Steam Play for all titles'."
say "Windows apps: double-click a .exe (Wine via binfmt_misc), or 'wine app.exe'."
say "Tip: 'proton-ge-custom-bin' (AUR) gives newer Proton-GE for tougher games."
