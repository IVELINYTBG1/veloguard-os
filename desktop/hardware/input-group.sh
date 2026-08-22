#!/usr/bin/env bash
# Give the primary user privileged input access (dictation, game controllers).
# Derived from Omarchy install/hardware/input-group.sh (MIT).
user="${VELOGUARD_HW_USER:-veloguard}"
if getent passwd "$user" >/dev/null 2>&1; then
  usermod -aG input "$user" 2>/dev/null || true
fi
