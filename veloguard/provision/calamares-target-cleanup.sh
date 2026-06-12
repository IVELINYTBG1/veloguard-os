#!/usr/bin/env bash
#
# calamares-target-cleanup — runs INSIDE the freshly-installed system (chroot)
# during install, before the initramfs is regenerated. The install copies the
# live squashfs 1:1, so everything that makes the live ISO "live" must be
# stripped here or the installed system boots like (or fails like) the ISO.
set -u

# 1. archiso initramfs machinery → stock Arch initramfs
rm -f /etc/mkinitcpio.conf.d/archiso.conf
cat > /etc/mkinitcpio.d/linux.preset <<'EOF'
# mkinitcpio preset file for the 'linux' package (restored by VeloGuardOS installer)
ALL_kver="/boot/vmlinuz-linux"

PRESETS=('default' 'fallback')

default_image="/boot/initramfs-linux.img"

fallback_image="/boot/initramfs-linux-fallback.img"
fallback_options="-S autodetect"
EOF

# 2. live-session autologin (tty + GDM) must not reach the installed system
rm -rf /etc/systemd/system/getty@tty1.service.d
rm -f  /etc/gdm/custom.conf

# 3. live-only units + their activation links
for u in pacman-init.service choose-mirror.service veloguard-live-user.service \
         reflector.service reflector.timer; do
    rm -f "/etc/systemd/system/$u" \
          "/etc/systemd/system/"*.wants/"$u" 2>/dev/null
done
systemctl disable --no-reload reflector.service reflector.timer >/dev/null 2>&1 || true

# 4. live NOPASSWD sudo: the users module writes proper %wheel sudoers
rm -f /etc/sudoers.d/10-wheel-nopasswd

# 5. installer entry points make no sense on an installed system
rm -f /usr/share/applications/install-to-disk.desktop \
      /usr/share/applications/install-to-disk-advanced.desktop \
      /etc/polkit-1/rules.d/49-veloguard-live-calamares.rules

# 6. archiso login cosmetics
rm -f /root/.automated_script.sh /root/.zlogin /etc/motd 2>/dev/null

exit 0
