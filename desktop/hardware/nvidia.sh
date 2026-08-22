#!/usr/bin/env bash
# NVIDIA drivers, matched to the GPU generation. Derived from Omarchy
# install/hardware/nvidia.sh (MIT). Uses the VeloGuard vg_* helpers.
if lspci | grep -qi 'nvidia'; then
  # Kernel headers for the DKMS build — match whatever kernel is installed
  # (VeloGuard ships linux-veloguard; linux/-zen/-lts also handled).
  KERNEL_PACKAGE=$(pacman -Qqs '^linux(-veloguard|-zen|-lts|-hardened)?$' | head -1 || true)
  [[ -n $KERNEL_PACKAGE ]] && vg_pkg_add "$KERNEL_PACKAGE-headers"

  if vg_hw_nvidia_gsp; then
    PACKAGES=(nvidia-open-dkms nvidia-utils lib32-nvidia-utils libva-nvidia-driver)
  elif vg_hw_nvidia_without_gsp; then
    # Legacy 580xx branch (Maxwell/Pascal/Volta) — AUR; vg_pkg_add falls back to
    # an AUR helper if one is installed.
    PACKAGES=(nvidia-580xx-dkms nvidia-580xx-utils lib32-nvidia-580xx-utils)
  fi

  if [[ -z ${PACKAGES+x} ]]; then
    echo "No matching VeloGuard NVIDIA driver package for this GPU."
    echo "See: https://wiki.archlinux.org/title/NVIDIA"
    exit 0
  fi

  vg_pkg_add "${PACKAGES[@]}"

  # Early KMS + modeset
  mkdir -p /etc/modprobe.d
  printf 'options nvidia_drm modeset=1\n' > /etc/modprobe.d/nvidia.conf

  mkdir -p /etc/mkinitcpio.conf.d
  printf 'MODULES+=(nvidia nvidia_modeset nvidia_uvm nvidia_drm)\n' \
    > /etc/mkinitcpio.conf.d/nvidia.conf

  # Hyprland NVIDIA session env (cursor + GBM) so Wayland comes up clean.
  install -d /usr/share/veloguard/desktop/hypr
  cat > /usr/share/veloguard/desktop/hypr/nvidia.conf <<'EOF'
# Loaded on NVIDIA hardware (sourced by hyprland.conf when present)
env = LIBVA_DRIVER_NAME,nvidia
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = NVD_BACKEND,direct
cursor {
  no_hardware_cursors = true
}
EOF
fi
