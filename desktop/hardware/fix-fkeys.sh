#!/usr/bin/env bash
# Make F-keys behave as F-keys on Apple-like keyboards (Lofree Flow, etc.).
# Derived from Omarchy install/hardware/fix-fkeys.sh (MIT). Runs as root.
if [[ ! -f /etc/modprobe.d/hid_apple.conf ]]; then
  mkdir -p /etc/modprobe.d
  printf 'options hid_apple fnmode=2\n' > /etc/modprobe.d/hid_apple.conf
fi
