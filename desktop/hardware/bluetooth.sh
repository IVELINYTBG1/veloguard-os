#!/usr/bin/env bash
# Enable Bluetooth. Derived from Omarchy install/hardware/bluetooth.sh (MIT).
# AutoEnable is left at its BlueZ default on purpose.
systemctl enable bluetooth.service 2>/dev/null || true
