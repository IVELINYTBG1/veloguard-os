#!/usr/bin/env bash
#
# VeloGuardOS — default application set for the ISO.
#
# Browser: Brave (NOT Firefox). Plus the everyday basics, mostly as Flatpaks so
# they're identical across whatever base distro the image is built on:
#   Brave · Discord · Dolphin (files) · Viber · ZapZap (WhatsApp) · LibreOffice
#   · Transmission · Waydroid (Android apps) · GNOME Software + Flatpak
#
#   sudo ./install-default-apps.sh
#
# Waydroid needs the kernel's binder support — already enabled in
# kernel/veloguardos-base.config.
#
set -euo pipefail
say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }
priv() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }
[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo)"; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

# Run a command as the real desktop user (defaults are per-user, not root).
USER_NAME="${SUDO_USER:-$USER}"
as_user() { sudo -u "$USER_NAME" env XDG_RUNTIME_DIR="/run/user/$(id -u "$USER_NAME")" "$@"; }

# --- 1. Flatpak + Flathub --------------------------------------------------
ensure_flatpak() {
  command -v flatpak >/dev/null || {
    if   command -v dnf     >/dev/null; then priv dnf install -y flatpak
    elif command -v apt-get >/dev/null; then priv apt-get update && priv apt-get install -y flatpak
    elif command -v pacman  >/dev/null; then priv pacman -S --noconfirm --needed flatpak; fi
  }
  flatpak remote-add --if-not-exists flathub \
    https://flathub.org/repo/flathub.flatpakref
}

# --- 2. the app set, from Flathub (system-wide) ----------------------------
FLATPAKS=(
  com.brave.Browser              # default browser
  com.discordapp.Discord
  org.kde.dolphin                # file manager (user's pick)
  com.viber.Viber
  com.rtosta.zapzap              # ZapZap — WhatsApp client
  org.libreoffice.LibreOffice
  com.transmissionbt.Transmission
)
install_flatpaks() {
  say "installing Flatpak apps (Brave, Discord, Dolphin, Viber, ZapZap, LibreOffice, Transmission)…"
  flatpak install -y --system flathub "${FLATPAKS[@]}" \
    || warn "some Flatpaks failed — re-run; Flathub may be rate-limited"
}

# --- 3. native: GNOME Software (+Flatpak plugin) and Waydroid ---------------
install_store() {
  if   command -v dnf     >/dev/null; then priv dnf install -y gnome-software
  elif command -v apt-get >/dev/null; then priv apt-get install -y gnome-software gnome-software-plugin-flatpak
  elif command -v pacman  >/dev/null; then priv pacman -S --noconfirm --needed gnome-software; fi
}

install_waydroid() {
  if command -v waydroid >/dev/null; then say "waydroid already present"; return; fi
  if   command -v apt-get >/dev/null; then
    say "installing Waydroid (Android container)…"
    curl -fsSL https://repo.waydro.id | priv bash || { warn "waydroid repo add failed"; return; }
    priv apt-get install -y waydroid
  elif command -v dnf >/dev/null; then
    warn "Waydroid on Fedora: enable COPR  → sudo dnf copr enable aleasto/waydroid && sudo dnf install waydroid"
  elif command -v pacman >/dev/null; then
    warn "Waydroid on Arch: install 'waydroid' from the AUR (e.g. yay -S waydroid)"
  fi
  command -v waydroid >/dev/null && say "Waydroid installed — first run: 'waydroid init' (downloads ~1GB Android image)"
}

# --- 4. defaults: Brave browser + Dolphin file manager ---------------------
set_defaults() {
  say "setting Brave as the default browser, Dolphin as the file manager (for $USER_NAME)…"
  as_user xdg-settings set default-web-browser com.brave.Browser.desktop 2>/dev/null \
    || warn "set Brave default manually in Settings"
  as_user xdg-mime default org.kde.dolphin.desktop inode/directory 2>/dev/null || true
  as_user xdg-mime default com.brave.Browser.desktop x-scheme-handler/https x-scheme-handler/http 2>/dev/null || true
}

# --- 5. 🇧🇬 Bulgarian Mode easter egg (UI only) ----------------------------
install_bulgarian_mode() {
  install -m755 "$HERE/../bin/veloguard-bulgarian-mode" /usr/local/bin/ 2>/dev/null || return 0
  install -Dm644 "$HERE/../ui/bulgarian-mode.desktop" \
    /usr/share/applications/bulgarian-mode.desktop 2>/dev/null || true
  if [ -d "$HERE/../../Bulgarian_Mode" ]; then
    mkdir -p /usr/share/veloguard
    cp -r "$HERE/../../Bulgarian_Mode" /usr/share/veloguard/ 2>/dev/null || true
  fi
  # ffplay (ffmpeg) is the fallback player; mpv is nicer if present.
  command -v ffplay >/dev/null || command -v mpv >/dev/null \
    || warn "no mpv/ffplay — Bulgarian Mode music needs one (install ffmpeg)"
  say "Bulgarian Mode button installed 🇧🇬 (find it in the app grid)"
}

main() {
  ensure_flatpak
  install_flatpaks
  install_store
  install_waydroid
  set_defaults
  install_bulgarian_mode
  say "Done. Default apps installed; Brave is the default browser."
  say "GNOME Nautilus stays available too; Dolphin is the default file manager."
}

main "$@"
