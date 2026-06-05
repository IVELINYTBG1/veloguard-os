# VeloGuardOS ISO — live USB (archiso)

Builds a **live, bootable, mutable** VeloGuardOS ISO — boot it or `dd` it to a
USB stick and it runs live, with an "Install to Disk" option. Built by
[`build.sh`](build.sh), which layers our overlay on top of archiso's official
`releng` profile (so the BIOS+UEFI boot configs are always correct).

## What's in it

- Arch base + **GNOME on Wayland + PipeWire**, NetworkManager, GDM.
- The **VeloGuard guard** at `/opt/veloguard` with `veloguard`, `veloguard-vpn`,
  `veloguard-update`, `veloguard-install`, `veloguard-bulgarian-mode` on `PATH`.
- Security stack: `nftables`, `wireguard-tools`, `bubblewrap`, `tor`.
- `flatpak`, `mpv`/`ffmpeg`, broad filesystem tools.
- **Updater baked in**: `veloguard-update.timer` is enabled (signed, fail-closed;
  stays quiet until you add your release key — see `veloguard/keys/SIGNING.md`).
- Bulgarian Mode assets at `/opt/Bulgarian_Mode` + its launcher. 🇧🇬
- **Install to Disk** launcher → `archinstall` (guided). The live session *is*
  VeloGuardOS; a VeloGuardOS-aware graphical installer (Calamares with our
  modules) is the next polish.

## Build it

In CI: push a `v*` tag → `.github/workflows/build-iso.yml` builds it and attaches
the `.iso` to a Release. Locally, on Arch or in an Arch container (as root):

```bash
pacman -Sy --needed archiso
OUT=./out WORK=./work bash iso/build.sh        # → ./out/veloguardos-*.iso

# from any distro with podman/docker:
podman run --rm --privileged -v "$PWD":/repo -w /repo archlinux:latest \
  bash -c 'pacman -Sy --noconfirm archiso && OUT=/repo/out WORK=/repo/work bash iso/build.sh'
```

Write it to a USB stick (this erases the stick):

```bash
sudo dd if=out/veloguardos-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

## The custom kernel (upgrade path)

The ISO uses Arch's `linux` for a guaranteed-bootable base. To run the
**VeloGuardOS kernel** (Linus's tree + `veloguard/kernel/*.config`), build it and
install it on top — a `linux-veloguard` package + CI job is the clean next step.
