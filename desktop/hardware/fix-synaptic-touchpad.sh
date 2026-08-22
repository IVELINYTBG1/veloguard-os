#!/usr/bin/env bash
# Enable Synaptics InterTouch for confirmed touchpads. Derived from Omarchy
# install/hardware/fix-synaptic-touchpad.sh (MIT).
if grep -qi synaptics /proc/bus/input/devices \
   && ! lsmod | grep -q '^psmouse'; then
  modprobe psmouse synaptics_intertouch=1 || true
fi
