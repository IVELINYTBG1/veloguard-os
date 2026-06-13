#!/usr/bin/env bash
#
# calamares-stage-kernel — runs on the LIVE system (Calamares dontChroot),
# BEFORE the initcpio module. archiso keeps the kernel on the boot medium, NOT
# in the squashfs, so the freshly-unpacked target has no /boot/vmlinuz-linux and
# mkinitcpio aborts ("'/boot/vmlinuz-linux' must be readable"). Copy it in.
#
# $1 = the target root mount point (Calamares substitutes ${ROOT}).
set -e
ROOT="${1:?target root path required}"
[ -d "$ROOT" ] || { echo "ERROR: target root '$ROOT' is not a directory" >&2; exit 1; }

for src in /run/archiso/bootmnt/arch/boot/x86_64/vmlinuz-linux \
           /run/archiso/bootmnt/arch/boot/*/vmlinuz-linux \
           /run/archiso/airootfs/boot/vmlinuz-linux; do
  if [ -f "$src" ]; then
    install -Dm644 "$src" "$ROOT/boot/vmlinuz-linux"
    echo "staged kernel: $src -> $ROOT/boot/vmlinuz-linux"
    exit 0
  fi
done

echo "ERROR: vmlinuz-linux not found on the live medium" >&2
exit 1
