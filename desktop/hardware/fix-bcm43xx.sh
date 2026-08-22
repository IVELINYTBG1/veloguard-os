#!/usr/bin/env bash
# Broadcom BCM4360/BCM4331 Wi-Fi (some MacBooks + other systems). Derived from
# Omarchy install/hardware/fix-bcm43xx.sh (MIT). Uses vg_pkg_add.
pci_info=$(lspci -nn)
if echo "$pci_info" | grep -q "14e4:43a0" || echo "$pci_info" | grep -q "14e4:4331"; then
  echo "BCM4360 / BCM4331 detected — installing broadcom-wl"
  vg_pkg_add broadcom-wl dkms linux-headers
fi
