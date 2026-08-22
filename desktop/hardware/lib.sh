#!/usr/bin/env bash
# VeloGuardOS hardware layer — shared helpers.
# Derived from Omarchy's install/hardware helpers + bin/omarchy-pkg-add and the
# omarchy-hw-nvidia-* detectors (MIT). See desktop/omarchy/PROVENANCE.md.
#
# These replace Omarchy's omarchy-* commands with self-contained bash functions
# so the hardware scripts run without Omarchy's helper-script web. Exported with
# `export -f` by all.sh so the per-device scripts can call them.

# Install packages if missing: official repos first, then an AUR helper (for the
# handful of AUR-only driver packages, e.g. nvidia-580xx). Best-effort: a missing
# package logs a warning but never aborts the whole hardware pass.
vg_pkg_add() {
  local p missing=()
  for p in "$@"; do pacman -Q "$p" &>/dev/null || missing+=("$p"); done
  ((${#missing[@]})) || return 0
  if pacman -S --noconfirm --needed "${missing[@]}" 2>/dev/null; then return 0; fi
  local helper
  for helper in yay paru; do
    if command -v "$helper" >/dev/null 2>&1; then
      "$helper" -S --noconfirm --needed "${missing[@]}" && return 0
    fi
  done
  echo "vg-hardware: could not install: ${missing[*]}" >&2
  return 1
}

# NVIDIA GSP firmware present (Turing / RTX 20-series or newer): device id >= 0x1e00.
# Reads cached sysfs IDs (not lspci, which resumes runtime-suspended GPUs).
vg_hw_nvidia_gsp() {
  local dev pci="${VELOGUARD_PCI_DEVICES_PATH:-/sys/bus/pci/devices}"
  shopt -s nullglob
  for dev in "$pci"/*; do
    [[ $(< "$dev/vendor") == "0x10de" ]] || continue
    [[ $(< "$dev/class")  == 0x03*    ]] || continue
    (( $(< "$dev/device") >= 0x1e00 )) && return 0
  done
  return 1
}

# NVIDIA without GSP (Maxwell/Pascal/Volta): 0x1340 <= device id < 0x1e00.
vg_hw_nvidia_without_gsp() {
  local dev id pci="${VELOGUARD_PCI_DEVICES_PATH:-/sys/bus/pci/devices}"
  shopt -s nullglob
  for dev in "$pci"/*; do
    [[ $(< "$dev/vendor") == "0x10de" ]] || continue
    [[ $(< "$dev/class")  == 0x03*    ]] || continue
    id=$(< "$dev/device")
    (( id >= 0x1340 && id < 0x1e00 )) && return 0
  done
  return 1
}
