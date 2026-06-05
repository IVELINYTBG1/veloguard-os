#!/usr/bin/env bash
#
# VeloGuardOS — universal application format support.
#
# Make the system able to install software in every common form:
#   * Flatpak  (+ Flathub)   — cross-distro, sandboxed
#   * Snap     (snapd)        — cross-distro
#   * AppImage (FUSE)         — single-file, no install
#   * native .deb / .rpm / .pkg — via the base package manager
#   * alien                   — convert .deb <-> .rpm where native won't do
#
# Kernel prerequisites (USER_NS, FUSE, SQUASHFS, OVERLAY, BINFMT_MISC) come from
# kernel/veloguardos-base.config. The per-file installer is bin/veloguard-install.
#
#   sudo ./install-app-formats.sh
#
set -euo pipefail

say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo ./install-app-formats.sh)"; exit 1; }

do_arch() {
  pacman -Syu --noconfirm --needed \
    flatpak fuse2 bubblewrap \
    xdg-desktop-portal xdg-desktop-portal-gtk
  warn "snapd is not in Arch's official repos — install from the AUR (e.g. 'yay -S snapd')"
  warn "alien is also AUR if you need .deb/.rpm conversion"
}

do_fedora() {
  dnf install -y \
    flatpak snapd fuse fuse-libs bubblewrap \
    xdg-desktop-portal xdg-desktop-portal-gtk || true
  dnf install -y alien 2>/dev/null || warn "alien unavailable on this Fedora — .deb conversion limited"
}

do_debian() {
  apt-get update
  apt-get install -y \
    flatpak snapd libfuse2 bubblewrap gdebi-core alien \
    xdg-desktop-portal xdg-desktop-portal-gtk
}

post_common() {
  # Flathub — the de-facto Flatpak app store.
  if command -v flatpak >/dev/null; then
    flatpak remote-add --if-not-exists flathub \
      https://flathub.org/repo/flathub.flatpakref || warn "could not add Flathub"
    say "Flatpak + Flathub ready."
  fi
  # snapd socket + the /snap symlink classic snaps expect.
  if command -v snap >/dev/null || [ -d /var/lib/snapd ]; then
    systemctl enable --now snapd.socket 2>/dev/null || warn "enable snapd.socket manually"
    [ -e /snap ] || ln -s /var/lib/snapd/snap /snap 2>/dev/null || true
    say "Snap ready (you may need to log out/in for PATH)."
  fi
  say "AppImage: just 'chmod +x foo.AppImage && ./foo.AppImage' (FUSE handles the rest)."
}

main() {
  if   command -v pacman  >/dev/null; then say "Arch base";          do_arch
  elif command -v dnf     >/dev/null; then say "Fedora base";        do_fedora
  elif command -v apt-get >/dev/null; then say "Debian/Ubuntu base"; do_debian
  else warn "unknown distro — install: flatpak snapd fuse bubblewrap"; exit 1
  fi
  post_common
  say "Done. Install any file with:  veloguard-install <file-or-URL>"
}

main "$@"
