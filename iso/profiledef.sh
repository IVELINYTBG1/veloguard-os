#!/usr/bin/env bash
# VeloGuardOS — archiso profile (live ISO). Builds an Arch-based, MUTABLE live
# system with the VeloGuard guard, desktop, and tooling preloaded at /opt/veloguard.
# shellcheck disable=SC2034
iso_name="veloguardos"
iso_label="VELOGUARDOS"
iso_publisher="VeloGuardOS <https://github.com/IVELINYTBG1/veloguard-os>"
iso_application="VeloGuardOS Live"
iso_version="$(date +%Y.%m.%d)"
install_dir="vgos"
buildmodes=('iso')
bootmodes=('bios.syslinux.mbr' 'bios.syslinux.eltorito'
           'uefi-x64.systemd-boot.esp' 'uefi-x64.systemd-boot.eltorito')
arch="x86_64"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19')
bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical')
file_permissions=(
  ["/etc/shadow"]="0:0:400"
  ["/root"]="0:0:750"
  ["/usr/local/bin/veloguard"]="0:0:755"
  ["/usr/local/bin/veloguard-install"]="0:0:755"
  ["/usr/local/bin/veloguard-vpn"]="0:0:755"
  ["/usr/local/bin/veloguard-update"]="0:0:755"
  ["/usr/local/bin/veloguard-bulgarian-mode"]="0:0:755"
  ["/opt/veloguard"]="0:0:755"
)
