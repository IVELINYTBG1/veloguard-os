#!/usr/bin/env bash
#
# VeloGuardOS — firmware, CPU microcode, GPU video accel, and media codecs.
#
# The kernel modules (kernel/veloguardos-hardware.config) are useless without
# the firmware blobs most Wi-Fi/GPU/Bluetooth chips need. This installs those,
# plus CPU microcode (security + stability) and the codecs that make audio/video
# "just play" out of the box.
#
# Honest note on codecs: H.264/H.265/AAC and friends are patent-encumbered. On
# Fedora they live in RPM Fusion; on Debian in non-free. This script enables
# those repos so playback works for everyone — disable that if your distribution
# policy forbids it.
#
#   sudo ./install-firmware-codecs.sh
#
set -euo pipefail

say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

[ "$(id -u)" -eq 0 ] || { warn "run as root (sudo ./install-firmware-codecs.sh)"; exit 1; }

# ---------------------------------------------------------------------------
# Arch
# ---------------------------------------------------------------------------
do_arch() {
  pacman -Syu --noconfirm --needed \
    linux-firmware sof-firmware \
    intel-ucode amd-ucode \
    mesa libva-mesa-driver mesa-vdpau \
    intel-media-driver libva-intel-driver \
    libva-utils vdpauinfo \
    gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly \
    gst-libav ffmpeg
  say "regenerating initramfs (mkinitcpio)…"; mkinitcpio -P || warn "run mkinitcpio -P yourself"
}

# ---------------------------------------------------------------------------
# Fedora — enable RPM Fusion so restricted codecs + freeworld VA-API exist.
# ---------------------------------------------------------------------------
do_fedora() {
  if ! rpm -q rpmfusion-free-release >/dev/null 2>&1; then
    say "enabling RPM Fusion (free + nonfree) for full codec support…"
    local v; v="$(rpm -E %fedora)"
    dnf install -y \
      "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${v}.noarch.rpm" \
      "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${v}.noarch.rpm" \
      || warn "could not add RPM Fusion — restricted codecs may be unavailable"
  fi
  dnf install -y \
    linux-firmware alsa-sof-firmware \
    amd-gpu-firmware intel-gpu-firmware nvidia-gpu-firmware \
    microcode_ctl \
    mesa-va-drivers mesa-vdpau-drivers intel-media-driver libva-utils \
    gstreamer1-plugins-base gstreamer1-plugins-good \
    gstreamer1-plugins-bad-free gstreamer1-plugins-ugly gstreamer1-libav
  # Swap the codec-stripped Mesa/ffmpeg for the freeworld builds (H.264/H.265).
  dnf swap -y mesa-va-drivers mesa-va-drivers-freeworld 2>/dev/null || true
  dnf swap -y mesa-vdpau-drivers mesa-vdpau-drivers-freeworld 2>/dev/null || true
  dnf swap -y ffmpeg-free ffmpeg --allowerasing 2>/dev/null || \
    dnf install -y ffmpeg --allowerasing 2>/dev/null || true
  say "regenerating initramfs (dracut)…"; dracut -f || warn "run dracut -f yourself"
}

# ---------------------------------------------------------------------------
# Debian / Ubuntu — needs non-free + non-free-firmware components.
# ---------------------------------------------------------------------------
do_debian() {
  warn "ensure your apt sources include: contrib non-free non-free-firmware"
  apt-get update
  apt-get install -y \
    firmware-linux firmware-sof-signed \
    intel-microcode amd64-microcode \
    mesa-va-drivers mesa-vdpau-drivers va-driver-all vdpau-driver-all \
    intel-media-va-driver-non-free vainfo \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav ffmpeg \
    || warn "some packages need contrib/non-free enabled"
  say "regenerating initramfs…"; update-initramfs -u || warn "run update-initramfs -u yourself"
}

main() {
  if   command -v pacman  >/dev/null; then say "Arch base";          do_arch
  elif command -v dnf     >/dev/null; then say "Fedora base";        do_fedora
  elif command -v apt-get >/dev/null; then say "Debian/Ubuntu base"; do_debian
  else warn "unknown distro — install: linux-firmware, CPU microcode, VA-API drivers, gstreamer + ffmpeg"; exit 1
  fi
  say "Done. Firmware + microcode + codecs installed. Reboot to load microcode early."
  say "Verify GPU video decode after reboot:  vainfo"
}

main "$@"
