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

# dconf is needed to compile the default-wallpaper database (step 7.5)
command -v dconf >/dev/null || pacman -S --noconfirm --needed dconf

# 1. start from the official profile (correct syslinux/ + efiboot/ configs)
rm -rf "$PROFILE"
cp -r /usr/share/archiso/configs/releng "$PROFILE"

# 2. our identity
sed -i 's/^iso_name=.*/iso_name="veloguardos"/'  "$PROFILE/profiledef.sh"
sed -i 's/^iso_label=.*/iso_label="VELOGUARDOS"/' "$PROFILE/profiledef.sh"
sed -i 's#^iso_publisher=.*#iso_publisher="VeloGuardOS <https://github.com/IVELINYTBG1/veloguard-os>"#' "$PROFILE/profiledef.sh"
sed -i 's/^iso_application=.*/iso_application="VeloGuardOS Live"/' "$PROFILE/profiledef.sh"
# boot-menu titles: "Arch Linux" -> "VeloGuardOS"
sed -i 's/Arch Linux/VeloGuardOS/g' "$PROFILE"/syslinux/*.cfg 2>/dev/null || true
sed -i 's/Arch Linux/VeloGuardOS/g' "$PROFILE"/efiboot/loader/entries/*.conf 2>/dev/null || true

# 2.5 AUR: git + base-devel ship in the image (packages.extra), so the user has
#     full MANUAL AUR out of the box: git clone <aur-url> && (cd pkg && makepkg -si)
#     The auto-built 'yay' helper kept breaking the ISO build (local-repo/pacstrap
#     fragility), so it's deferred. Post-boot one-liner to add it:
#       git clone https://aur.archlinux.org/yay.git && (cd yay && makepkg -si)

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
         veloguard-netwatch veloguard-bulgarian-mode veloguard-mcp; do
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
# Wi-Fi: make NetworkManager the SOLE manager. archiso's base enables
# systemd-networkd + iwd; running them alongside NM leaves Wi-Fi 'unmanaged'/
# dead on the desktop. Mask them and let NM (via wpa_supplicant) own networking.
mkdir -p "$PROFILE/airootfs/etc/systemd/system/network-online.target.wants" \
         "$PROFILE/airootfs/etc/systemd/system/bluetooth.target.wants"
for svc in systemd-networkd.service systemd-networkd.socket iwd.service \
           systemd-networkd-wait-online.service; do
  ln -sf /dev/null "$PROFILE/airootfs/etc/systemd/system/$svc"     # mask
done
ln -sf /usr/lib/systemd/system/NetworkManager-wait-online.service \
  "$PROFILE/airootfs/etc/systemd/system/network-online.target.wants/NetworkManager-wait-online.service"
# Bluetooth: enable the service (and dbus-activated for GNOME's BT panel).
ln -sf /usr/lib/systemd/system/bluetooth.service \
  "$PROFILE/airootfs/etc/systemd/system/bluetooth.target.wants/bluetooth.service"
ln -sf /usr/lib/systemd/system/bluetooth.service \
  "$PROFILE/airootfs/etc/systemd/system/dbus-org.bluez.service"
install -Dm644 "$REPO/veloguard/provision/veloguard-update.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-update.service"
install -Dm644 "$REPO/veloguard/provision/veloguard-update.timer" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-update.timer"
ln -sf /etc/systemd/system/veloguard-update.timer \
  "$PROFILE/airootfs/etc/systemd/system/timers.target.wants/veloguard-update.timer"
# Privacy: data-broker opt-out timer (no-ops until the user configures identity).
chmod +x "$PROFILE/airootfs/opt/veloguard/provision/veloguard-privacy-optout.sh" 2>/dev/null || true
install -Dm644 "$REPO/veloguard/provision/veloguard-privacy.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-privacy.service"
install -Dm644 "$REPO/veloguard/provision/veloguard-privacy.timer" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-privacy.timer"
ln -sf /etc/systemd/system/veloguard-privacy.timer \
  "$PROFILE/airootfs/etc/systemd/system/timers.target.wants/veloguard-privacy.timer"

# 7.4 identity: override Arch's os-release at boot (filesystem pkg ships its own,
#     so an overlay file would be clobbered — do it as a boot-time service).
cat > "$PROFILE/airootfs/etc/systemd/system/veloguard-branding.service" <<'UNIT'
[Unit]
Description=VeloGuardOS identity branding
Before=gdm.service display-manager.service
ConditionPathExists=!/var/lib/veloguard/.branded
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/bash -c 'cp -f /opt/veloguard/branding/os-release /usr/lib/os-release; mkdir -p /var/lib/veloguard; touch /var/lib/veloguard/.branded'
[Install]
WantedBy=multi-user.target
UNIT
ln -sf /etc/systemd/system/veloguard-branding.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/veloguard-branding.service"

# 7.5 default wallpaper — system-wide via a dconf database, so every user
#     (including the live session) gets the VeloGuardOS wallpaper out of the box.
#     The PNG is already in airootfs from the overlay (step 5):
#       /usr/share/backgrounds/veloguard/default.png
WP="file:///usr/share/backgrounds/veloguard/default.png"
mkdir -p "$PROFILE/airootfs/etc/dconf/db/local.d" "$PROFILE/airootfs/etc/dconf/profile"
printf 'user-db:user\nsystem-db:local\n' > "$PROFILE/airootfs/etc/dconf/profile/user"
cat > "$PROFILE/airootfs/etc/dconf/db/local.d/01-veloguard-background" <<DCONF
[org/gnome/desktop/background]
picture-uri='$WP'
picture-uri-dark='$WP'
picture-options='zoom'
primary-color='#13203a'

[org/gnome/desktop/screensaver]
picture-uri='$WP'
picture-options='zoom'

[org/gnome/login-screen]
logo='/usr/share/pixmaps/veloguardos.png'

[org/gnome/shell]
disable-user-extensions=false
enabled-extensions=['veloguard@veloguardos']
DCONF
dconf compile "$PROFILE/airootfs/etc/dconf/db/local" \
              "$PROFILE/airootfs/etc/dconf/db/local.d"

# 7.6 graphical autologin — boot straight into GNOME as a passwordless live user.
#     (GDM refuses root logins, and releng defaults to a console; fix both.)
ln -sf /usr/lib/systemd/system/graphical.target \
  "$PROFILE/airootfs/etc/systemd/system/default.target"
# Create the live user AT BOOT so useradd gets home/perms right in the live system.
cat > "$PROFILE/airootfs/etc/systemd/system/veloguard-live-user.service" <<'UNIT'
[Unit]
Description=VeloGuardOS live user setup
Before=gdm.service display-manager.service
ConditionPathExists=!/home/veloguard
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/bash -c 'useradd -m -G wheel -s /usr/bin/bash veloguard && passwd -d veloguard'
[Install]
WantedBy=multi-user.target
UNIT
ln -sf /etc/systemd/system/veloguard-live-user.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/veloguard-live-user.service"
# Passwordless sudo for the live user.
mkdir -p "$PROFILE/airootfs/etc/sudoers.d"
printf '%%wheel ALL=(ALL:ALL) NOPASSWD: ALL\n' \
  > "$PROFILE/airootfs/etc/sudoers.d/10-wheel-nopasswd"
chmod 440 "$PROFILE/airootfs/etc/sudoers.d/10-wheel-nopasswd"
# GDM auto-login that user → straight to the GNOME desktop + our wallpaper.
mkdir -p "$PROFILE/airootfs/etc/gdm"
printf '[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=veloguard\nWaylandEnable=true\n' \
  > "$PROFILE/airootfs/etc/gdm/custom.conf"

# 7.7 boot + login ART generated from the wallpaper — replaces Arch's logo/splash.
IM="$(command -v magick || command -v convert || true)"
[ -n "$IM" ] || { pacman -S --noconfirm --needed imagemagick; \
                  IM="$(command -v magick || command -v convert)"; }
WALLSRC="$PROFILE/airootfs/usr/share/backgrounds/veloguard/default.png"
install -d "$PROFILE/airootfs/usr/share/pixmaps"
# BIOS (syslinux) boot-menu background — overwrite the Arch splash.
"$IM" "$WALLSRC" -resize 640x480^ -gravity center -extent 640x480 \
  "$PROFILE/syslinux/splash.png" || echo "  (splash gen skipped)"
# GDM login-screen / About logo.
"$IM" "$WALLSRC" -resize 480x \
  "$PROFILE/airootfs/usr/share/pixmaps/veloguardos.png" || echo "  (logo gen skipped)"
# Calamares installer branding logo.
install -d "$PROFILE/airootfs/etc/calamares/branding/veloguardos"
"$IM" "$WALLSRC" -resize 320x \
  "$PROFILE/airootfs/etc/calamares/branding/veloguardos/veloguard-logo.png" || true

# 8. build the ISO
mkdir -p "$WORK" "$OUT"
mkarchiso -v -w "$WORK" -o "$OUT" "$PROFILE"
echo "✅ ISO written to: $OUT"
ls -lh "$OUT"/*.iso
