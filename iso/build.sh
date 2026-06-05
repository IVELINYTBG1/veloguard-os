#!/usr/bin/env bash
# Build the VeloGuardOS live ISO = archiso's official 'releng' profile (which
# carries the correct BIOS+UEFI boot configs) + our overlay (packages, the guard
# at /opt/veloguard, enabled services, Bulgarian Mode). Run on Arch / an Arch
# container, as root. Same script used by CI and for local builds.
#
#   pacman -Sy --needed archiso
#   OUT=./out WORK=./work bash iso/build.sh     # → ./out/veloguardos-*.iso
#
set -eux
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${PROFILE:-/tmp/vgos-profile}"
WORK="${WORK:-$REPO/work}"
OUT="${OUT:-$REPO/out}"

# 1. start from the official profile (correct syslinux/ + efiboot/ configs)
rm -rf "$PROFILE"
cp -r /usr/share/archiso/configs/releng "$PROFILE"

# 2. our identity
sed -i 's/^iso_name=.*/iso_name="veloguardos"/'  "$PROFILE/profiledef.sh"
sed -i 's/^iso_label=.*/iso_label="VELOGUARDOS"/' "$PROFILE/profiledef.sh"
sed -i 's#^iso_publisher=.*#iso_publisher="VeloGuardOS <https://github.com/IVELINYTBG1/veloguard-os>"#' "$PROFILE/profiledef.sh"
sed -i 's/^iso_application=.*/iso_application="VeloGuardOS Live"/' "$PROFILE/profiledef.sh"

# 3. extra packages (appended to releng's base list)
cat "$REPO/iso/packages.extra" >> "$PROFILE/packages.x86_64"

# 4. our tree into the live root
mkdir -p "$PROFILE/airootfs/opt"
cp -r "$REPO/veloguard"      "$PROFILE/airootfs/opt/veloguard"
cp -r "$REPO/Bulgarian_Mode" "$PROFILE/airootfs/opt/Bulgarian_Mode"
rm -rf "$PROFILE/airootfs/opt/veloguard/.venv"
find "$PROFILE/airootfs/opt/veloguard" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 5. our static overlay (desktop launchers, etc.)
[ -d "$REPO/iso/airootfs" ] && cp -r "$REPO/iso/airootfs/." "$PROFILE/airootfs/"

# 6. guard tools on PATH (the launcher cd's into /opt/veloguard)
mkdir -p "$PROFILE/airootfs/usr/local/bin"
for b in veloguard veloguard-install veloguard-vpn veloguard-update \
         veloguard-netwatch veloguard-bulgarian-mode; do
  ln -sf "/opt/veloguard/bin/$b" "$PROFILE/airootfs/usr/local/bin/$b"
done
install -Dm644 "$REPO/veloguard/ui/bulgarian-mode.desktop" \
  "$PROFILE/airootfs/usr/share/applications/bulgarian-mode.desktop"

# 7. enable services: NetworkManager + GDM, and BAKE IN the updater timer
mkdir -p "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants" \
         "$PROFILE/airootfs/etc/systemd/system/timers.target.wants"
ln -sf /usr/lib/systemd/system/NetworkManager.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/NetworkManager.service"
ln -sf /usr/lib/systemd/system/gdm.service \
  "$PROFILE/airootfs/etc/systemd/system/display-manager.service"
install -Dm644 "$REPO/veloguard/provision/veloguard-update.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-update.service"
install -Dm644 "$REPO/veloguard/provision/veloguard-update.timer" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-update.timer"
ln -sf /etc/systemd/system/veloguard-update.timer \
  "$PROFILE/airootfs/etc/systemd/system/timers.target.wants/veloguard-update.timer"

# 8. build the ISO
mkdir -p "$WORK" "$OUT"
mkarchiso -v -w "$WORK" -o "$OUT" "$PROFILE"
echo "✅ ISO written to: $OUT"
ls -lh "$OUT"/*.iso
