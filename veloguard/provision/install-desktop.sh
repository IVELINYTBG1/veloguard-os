#!/usr/bin/env bash
#
# VeloGuardOS — desktop userspace: Wayland + PipeWire + GNOME.
#
# Userspace only. The kernel side (DRM/KMS, evdev, dmabuf, ALSA) comes from
# kernel/veloguardos-desktop.config. Kept minimal on purpose ("like Arch"):
# GNOME *Shell* + GDM, not the full GNOME suite. Add apps yourself — that's the
# "fully mutable" promise.
#
# Why this stack fits a security OS:
#   * Wayland isolates apps — no global keylogging / screen-scraping like X11.
#   * PipeWire captures screen/audio only through portals (per-app consent).
#
#   sudo ./install-desktop.sh
#
set -euo pipefail

say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo ./install-desktop.sh)"; exit 1; }

# --- minimal package sets per base distro ----------------------------------
install_arch() {                                  # the "lightweight" reference
  pacman -Syu --noconfirm --needed \
    wayland wayland-protocols mesa vulkan-icd-loader \
    pipewire pipewire-pulse pipewire-alsa pipewire-jack wireplumber \
    gnome-shell gdm nautilus gnome-console \
    xdg-desktop-portal-gnome polkit
}

install_fedora() {
  dnf install -y \
    wayland-protocols-devel mesa-dri-drivers mesa-vulkan-drivers \
    pipewire pipewire-pulseaudio pipewire-alsa \
    pipewire-jack-audio-connection-kit wireplumber \
    gnome-shell gdm nautilus gnome-terminal \
    xdg-desktop-portal-gnome polkit
}

install_debian() {
  apt-get update
  apt-get install -y --no-install-recommends \
    wayland-protocols mesa-vulkan-drivers \
    pipewire pipewire-pulse pipewire-alsa wireplumber \
    gnome-shell gdm3 nautilus gnome-terminal \
    xdg-desktop-portal-gnome policykit-1
}

# --- wire up display manager + audio + Wayland session ---------------------
enable_services() {
  systemctl enable gdm 2>/dev/null || systemctl enable gdm3 2>/dev/null \
    || warn "could not enable a display manager — do it manually"

  # PipeWire/WirePlumber are per-user services; enable them for every user.
  systemctl --global enable pipewire pipewire-pulse wireplumber 2>/dev/null \
    || warn "enable per user: systemctl --user enable pipewire pipewire-pulse wireplumber"

  # GDM defaults to Wayland; make sure nobody disabled it.
  for conf in /etc/gdm/custom.conf /etc/gdm3/custom.conf /etc/gdm3/daemon.conf; do
    if [ -f "$conf" ] && grep -q '^WaylandEnable=false' "$conf"; then
      sed -i 's/^WaylandEnable=false/#WaylandEnable=false  # VeloGuardOS: Wayland on/' "$conf"
      say "re-enabled Wayland in $conf"
    fi
  done
}

main() {
  if   command -v pacman  >/dev/null; then say "Arch base → minimal GNOME/Wayland/PipeWire"; install_arch
  elif command -v dnf     >/dev/null; then say "Fedora base → GNOME/Wayland/PipeWire";      install_fedora
  elif command -v apt-get >/dev/null; then say "Debian/Ubuntu base → GNOME/Wayland/PipeWire"; install_debian
  else warn "unknown distro — install: wayland pipewire wireplumber gnome-shell gdm"; exit 1
  fi
  enable_services
  say "Desktop ready. Reboot into the graphical session."
  say "Verify after login:  echo \$XDG_SESSION_TYPE   (expect: wayland)"
}

main "$@"
