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

# 3a. the Omarchy-style Hyprland desktop stack (single source of truth). Strip
#     comments/blank lines so only package names land in the archiso list.
grep -vE '^\s*(#|$)' "$REPO/desktop/packages.desktop" >> "$PROFILE/packages.x86_64"

# 3.5 local package repo: calamares (+ ckbcomp) — the GUI installer is not in
#     Arch's official repos and Chaotic-AUR dropped it, so we build it from AUR
#     once (container) and pin the package here. Hermetic: no AUR at ISO time.
if ls "$REPO/iso/pkgs/"*.pkg.tar.zst >/dev/null 2>&1; then
  printf '\n[veloguard]\nSigLevel = Optional TrustAll\nServer = file://%s\n' \
    "$REPO/iso/pkgs" >> "$PROFILE/pacman.conf"
  printf 'calamares\nckbcomp\n' >> "$PROFILE/packages.x86_64"
  echo "  local repo: $(ls "$REPO/iso/pkgs/"*.pkg.tar.zst | xargs -n1 basename | tr '\n' ' ')"
else
  echo "  (no iso/pkgs packages — GUI installer will be MISSING from this image)"
fi

# 4. our tree into the live root
mkdir -p "$PROFILE/airootfs/opt"
cp -r "$REPO/veloguard"      "$PROFILE/airootfs/opt/veloguard"
cp -r "$REPO/Bulgarian_Mode" "$PROFILE/airootfs/opt/Bulgarian_Mode"
rm -rf "$PROFILE/airootfs/opt/veloguard/.venv"
find "$PROFILE/airootfs/opt/veloguard" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# 5. our static overlay (desktop launchers, etc.)
[ -d "$REPO/iso/airootfs" ] && cp -r "$REPO/iso/airootfs/." "$PROFILE/airootfs/"

# 5a. the Omarchy-derived Hyprland desktop layer (see desktop/README.md):
#     - shipped defaults  -> /usr/share/veloguard/desktop
#     - themes            -> /usr/share/veloguard/themes
#     - per-user skel     -> /etc/skel/.config  (seeded into every account)
#     - helper scripts    -> /usr/local/bin     (guard <-> desktop integration)
mkdir -p "$PROFILE/airootfs/usr/share/veloguard" \
         "$PROFILE/airootfs/etc/skel/.config" \
         "$PROFILE/airootfs/usr/local/bin"
cp -r "$REPO/desktop/defaults" "$PROFILE/airootfs/usr/share/veloguard/desktop"
cp -r "$REPO/desktop/themes"   "$PROFILE/airootfs/usr/share/veloguard/themes"
cp -r "$REPO/desktop/hardware" "$PROFILE/airootfs/usr/share/veloguard/hardware"
cp -r "$REPO/desktop/agents"   "$PROFILE/airootfs/usr/share/veloguard/agents"
cp -r "$REPO/desktop/skel/.config/." "$PROFILE/airootfs/etc/skel/.config/"
for b in "$REPO/desktop/bin/"*; do
  install -Dm755 "$b" "$PROFILE/airootfs/usr/local/bin/$(basename "$b")"
done
# Seed the active-theme symlink so Waybar/mako/hyprland resolve a theme on the
# very first login (useradd copies /etc/skel, symlinks included).
mkdir -p "$PROFILE/airootfs/etc/skel/.config/veloguard"
ln -sfn /usr/share/veloguard/themes/veloguard \
  "$PROFILE/airootfs/etc/skel/.config/veloguard/current"

# 4b/5b. KEEP SCRIPTS EXECUTABLE: mkarchiso copies airootfs with
# --no-preserve=mode and restores ONLY the paths listed in profiledef.sh's
# file_permissions — anything else lands 0644. Without these entries every
# /opt/veloguard script (the veloguard CLI, veloguard-vpn, the netwatch
# dispatcher hook…) ships non-executable and silently no-ops on the live ISO.
{
  printf 'file_permissions+=(\n'
  for p in "$PROFILE/airootfs/opt/veloguard/bin/"* \
           "$PROFILE/airootfs/opt/veloguard/provision/"* \
           "$PROFILE/airootfs/opt/veloguard/"*.sh \
           "$PROFILE/airootfs/usr/local/bin/"veloguard-*; do
    [ -f "$p" ] || continue
    case "$p" in *.service|*.timer|*.md) continue ;; esac
    printf '  ["%s"]="0:0:755"\n' "${p#"$PROFILE/airootfs"}"
  done
  printf ')\n'
} >> "$PROFILE/profiledef.sh"

# 6. guard tools on PATH (the launcher cd's into /opt/veloguard)
mkdir -p "$PROFILE/airootfs/usr/local/bin"
for b in veloguard veloguard-install veloguard-vpn veloguard-vpn-ui \
         veloguard-wifi-doctor veloguard-wifi-autodetect veloguard-wifi-trust \
         veloguard-update veloguard-netwatch veloguard-bulgarian-mode veloguard-mcp; do
  ln -sf "/opt/veloguard/bin/$b" "$PROFILE/airootfs/usr/local/bin/$b"
done
install -Dm644 "$REPO/veloguard/ui/bulgarian-mode.desktop" \
  "$PROFILE/airootfs/usr/share/applications/bulgarian-mode.desktop"

# 6b. offline kernel updater (Fedora-style apply-on-reboot): the apply script
# runs during system-update.target; the restart prompt offers the opt-in.
ln -sf "/opt/veloguard/provision/veloguard-apply-staged-kernel" \
  "$PROFILE/airootfs/usr/local/bin/veloguard-apply-staged-kernel"
ln -sf "/opt/veloguard/provision/veloguard-restart-check" \
  "$PROFILE/airootfs/usr/local/bin/veloguard-restart-check"
ln -sf "/opt/veloguard/provision/veloguard-arm-offline-update" \
  "$PROFILE/airootfs/usr/local/bin/veloguard-arm-offline-update"
install -Dm644 "$REPO/veloguard/provision/veloguard-offline-update.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-offline-update.service"
mkdir -p "$PROFILE/airootfs/etc/systemd/system/system-update.target.wants"
ln -sf /etc/systemd/system/veloguard-offline-update.service \
  "$PROFILE/airootfs/etc/systemd/system/system-update.target.wants/veloguard-offline-update.service"

# 7. enable services: NetworkManager + SDDM, and BAKE IN the updater timer
mkdir -p "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants" \
         "$PROFILE/airootfs/etc/systemd/system/timers.target.wants"
ln -sf /usr/lib/systemd/system/NetworkManager.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/NetworkManager.service"
# Explicitly enable wpa_supplicant. NM is meant to D-Bus-activate it, but on the
# live ISO that activation wasn't firing — so NM got no WPA/RSN scan flags and
# every secured network showed as "open" (connects with no password prompt,
# then no traffic). Enabling the service guarantees the backend is up.
ln -sf /usr/lib/systemd/system/wpa_supplicant.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/wpa_supplicant.service"
ln -sf /usr/lib/systemd/system/sddm.service \
  "$PROFILE/airootfs/etc/systemd/system/display-manager.service"
# Wi-Fi: make NetworkManager the SOLE manager. archiso's base enables
# systemd-networkd + iwd; running them alongside NM leaves Wi-Fi 'unmanaged'/
# dead on the desktop. Mask them and let NM (via wpa_supplicant) own networking.
mkdir -p "$PROFILE/airootfs/etc/systemd/system/network-online.target.wants" \
         "$PROFILE/airootfs/etc/systemd/system/bluetooth.target.wants"
for svc in systemd-networkd.service systemd-networkd.socket iwd.service \
           systemd-networkd-wait-online.service ModemManager.service; do
  ln -sf /dev/null "$PROFILE/airootfs/etc/systemd/system/$svc"     # mask
done
# ModemManager mis-probes the Realtek USB Wi-Fi adapter and flaps its radio;
# there's no real WWAN here, so masking it is pure win for Wi-Fi stability.
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
# Hardware/driver setup (Omarchy-derived) — runs ONCE on first boot to install
# the drivers this machine actually needs (GPU/Wi-Fi/touchpad/…).
install -Dm644 "$REPO/veloguard/provision/veloguard-hardware.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-hardware.service"
ln -sf /etc/systemd/system/veloguard-hardware.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/veloguard-hardware.service"

# 7.4 identity: override Arch's os-release at boot (filesystem pkg ships its own,
#     so an overlay file would be clobbered — do it as a boot-time service).
cat > "$PROFILE/airootfs/etc/systemd/system/veloguard-branding.service" <<'UNIT'
[Unit]
Description=VeloGuardOS identity branding
Before=sddm.service display-manager.service
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

# 7.5 desktop wallpaper is now handled by the Hyprland session (swaybg, launched
#     from /usr/share/veloguard/desktop/hypr/autostart.conf) pointing at the
#     active theme's background, which falls back to the PNG already in airootfs:
#       /usr/share/backgrounds/veloguard/default.png
#     No dconf database to compile (that was the GNOME path). The SDDM Wayland
#     session `hyprland-uwsm.desktop` is shipped by the `hyprland` package itself
#     (uwsm-managed), and SDDM autologin (step 7.6) selects it by that name — so
#     we must NOT write our own copy here or pacstrap fails with a file conflict.

# 7.6 graphical autologin — boot straight into Hyprland as a passwordless live
#     user. (SDDM refuses root logins, and releng defaults to a console; fix both.)
ln -sf /usr/lib/systemd/system/graphical.target \
  "$PROFILE/airootfs/etc/systemd/system/default.target"
# Create the live user AT BOOT so useradd gets home/perms right in the live system.
cat > "$PROFILE/airootfs/etc/systemd/system/veloguard-live-user.service" <<'UNIT'
[Unit]
Description=VeloGuardOS live user setup
Before=sddm.service display-manager.service
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
# SDDM auto-login that user → straight into the Hyprland (uwsm) session.
mkdir -p "$PROFILE/airootfs/etc/sddm.conf.d"
cat > "$PROFILE/airootfs/etc/sddm.conf.d/10-veloguard-autologin.conf" <<'SDDM'
[Autologin]
User=veloguard
Session=hyprland-uwsm

[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=Hyprland
SDDM

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

# wifi-on-any-hardware: enable the boot-time autodetect service, and stock the
# offline driver depot (broadcom-wl can't be preinstalled — its blacklists
# would break b43/brcmfmac users — so autodetect installs it only when a
# wl-only Broadcom chip is actually present).
install -Dm644 "$REPO/veloguard/provision/veloguard-wifi-autodetect.service" \
  "$PROFILE/airootfs/etc/systemd/system/veloguard-wifi-autodetect.service"
ln -sf /etc/systemd/system/veloguard-wifi-autodetect.service \
  "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/veloguard-wifi-autodetect.service"
mkdir -p "$PROFILE/airootfs/opt/veloguard/drivers"
if pacman -Sw --noconfirm --cachedir "$PROFILE/airootfs/opt/veloguard/drivers" broadcom-wl >/dev/null 2>&1; then
  # -Sw downloads DEPENDENCIES too (incl. the 154MB 'linux' pkg) — keep only
  # the wl driver itself; everything it depends on is already in the image.
  find "$PROFILE/airootfs/opt/veloguard/drivers" -type f \
       ! -name 'broadcom-wl-*.pkg.tar.zst' -delete
  echo "  driver depot: $(ls "$PROFILE/airootfs/opt/veloguard/drivers")"
else
  echo "  (broadcom-wl depot skipped — package unavailable)"
fi

# build stamp — lets veloguard-wifi-doctor (and humans) tell stale ISOs apart
{ date -u +'%Y-%m-%dT%H:%MZ'
  git -C "$REPO" rev-parse --short HEAD 2>/dev/null || true
} > "$PROFILE/airootfs/etc/veloguard-build"

# 8. build the ISO
mkdir -p "$WORK" "$OUT"
mkarchiso -v -w "$WORK" -o "$OUT" "$PROFILE"
echo "✅ ISO written to: $OUT"
ls -lh "$OUT"/*.iso
