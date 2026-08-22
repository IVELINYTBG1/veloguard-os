#!/usr/bin/env bash
#
# VeloGuardOS — desktop userspace: Wayland + PipeWire + an Omarchy-derived
# Hyprland desktop (see ../../desktop/). Replaces the old GNOME/GDM stack.
#
# Userspace only. The kernel side (DRM/KMS, evdev, dmabuf, ALSA) comes from
# kernel/veloguardos-desktop.config. Kept "like Arch": a curated Hyprland set,
# not a full DE — add apps yourself (the "fully mutable" promise).
#
# Why this stack fits a security OS:
#   * Wayland isolates apps — no global keylogging / screen-scraping like X11.
#   * PipeWire captures screen/audio only through portals (per-app consent).
#
#   sudo ./install-desktop.sh
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
DESKTOP="$REPO/desktop"

say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo ./install-desktop.sh)"; exit 1; }

# --- install packages ------------------------------------------------------
install_arch() {                                  # the "lightweight" reference
  # Base Wayland/PipeWire + the Hyprland desktop set (single source of truth).
  local pkgs=(wayland wayland-protocols mesa vulkan-icd-loader \
              pipewire pipewire-pulse pipewire-alsa pipewire-jack wireplumber \
              polkit)
  if [ -f "$DESKTOP/packages.desktop" ]; then
    mapfile -t desk < <(grep -vE '^\s*(#|$)' "$DESKTOP/packages.desktop")
    pkgs+=("${desk[@]}")
  else
    warn "desktop/packages.desktop not found — installing a minimal Hyprland set"
    pkgs+=(hyprland waybar mako wofi swaybg swayosd sddm uwsm \
           xdg-desktop-portal-hyprland alacritty thunar polkit-gnome)
  fi
  pacman -Syu --noconfirm --needed "${pkgs[@]}"
}

# --- deploy the VeloGuard desktop config layer -----------------------------
deploy_config() {
  [ -d "$DESKTOP" ] || { warn "no desktop/ tree at $DESKTOP — skipping config deploy"; return; }
  install -d /usr/share/veloguard
  cp -r "$DESKTOP/defaults" /usr/share/veloguard/desktop
  cp -r "$DESKTOP/themes"   /usr/share/veloguard/themes
  cp -r "$DESKTOP/hardware" /usr/share/veloguard/hardware
  cp -r "$DESKTOP/agents"   /usr/share/veloguard/agents
  install -d /etc/skel/.config
  cp -r "$DESKTOP/skel/.config/." /etc/skel/.config/
  for b in "$DESKTOP/bin/"*; do
    install -Dm755 "$b" "/usr/local/bin/$(basename "$b")"
  done
  # Seed the active-theme symlink for new accounts.
  install -d /etc/skel/.config/veloguard
  ln -sfn /usr/share/veloguard/themes/veloguard /etc/skel/.config/veloguard/current
  say "Desktop config deployed to /usr/share/veloguard and /etc/skel."
}

# --- wire up display manager + audio ---------------------------------------
enable_services() {
  systemctl enable sddm 2>/dev/null || warn "could not enable sddm — enable a display manager manually"

  # PipeWire/WirePlumber are per-user services; enable them for every user.
  systemctl --global enable pipewire pipewire-pulse wireplumber 2>/dev/null \
    || warn "enable per user: systemctl --user enable pipewire pipewire-pulse wireplumber"

  # Hardware/driver setup (Omarchy-derived) on next boot, then a marker retires it.
  local hw_unit="$(dirname "$0")/veloguard-hardware.service"
  if [ -f "$hw_unit" ]; then
    install -Dm644 "$hw_unit" /etc/systemd/system/veloguard-hardware.service
    systemctl enable veloguard-hardware.service 2>/dev/null \
      || warn "enable it manually: systemctl enable veloguard-hardware.service"
  fi
}

main() {
  if command -v pacman >/dev/null; then
    say "Arch base → Hyprland (Omarchy-derived) + Wayland/PipeWire"
    install_arch
  else
    warn "VeloGuardOS's Hyprland desktop targets Arch. On other distros, install"
    warn "the Hyprland stack from your package manager, then re-run to deploy config."
  fi
  deploy_config
  enable_services
  say "Desktop ready. Reboot into the graphical session (SDDM → Hyprland)."
  say "Verify after login:  echo \$XDG_SESSION_TYPE   (expect: wayland)"
}

main "$@"
