# VeloGuardOS ISO (archiso profile)

Builds a **live, mutable, Arch-based** VeloGuardOS ISO with the guard, desktop,
and tooling preloaded. Built in CI (`.github/workflows/build-iso.yml`) — push a
`v*` tag and the `.iso` lands in Releases.

## What goes in

- Arch base + **GNOME on Wayland + PipeWire** (minimal).
- The **VeloGuard guard** at `/opt/veloguard`, with `veloguard`, `veloguard-vpn`,
  `veloguard-update`, `veloguard-install`, `veloguard-bulgarian-mode` on `PATH`.
- Security stack: `nftables`, `wireguard-tools`, `bubblewrap`, `tor`.
- `flatpak` (for the default apps), `mpv`/`ffmpeg` (Bulgarian Mode), broad FS tools.
- Bulgarian Mode assets at `/opt/Bulgarian_Mode` + its launcher.

The CI workflow copies `veloguard/` and `Bulgarian_Mode/` into the profile's
`airootfs/` and runs `mkarchiso`.

## Build locally (on an Arch host, as root)

```bash
pacman -S --needed archiso
cp -r iso /tmp/profile
cp -r veloguard         /tmp/profile/airootfs/opt/veloguard
cp -r Bulgarian_Mode    /tmp/profile/airootfs/opt/Bulgarian_Mode
mkdir -p /tmp/profile/airootfs/usr/local/bin
for b in veloguard veloguard-install veloguard-vpn veloguard-update veloguard-bulgarian-mode; do
  ln -sf /opt/veloguard/bin/$b /tmp/profile/airootfs/usr/local/bin/$b
done
mkarchiso -v -w /tmp/work -o /tmp/out /tmp/profile     # → /tmp/out/veloguardos-*.iso
```

## The custom kernel (upgrade path)

The base ISO uses Arch's `linux` for a guaranteed-bootable image. To run the
**VeloGuardOS kernel** (Linus's tree + our fragments), build it and install the
package, then regenerate the boot image:

```bash
# fetch + configure + build (toolchain: base-devel bison flex bc openssl libelf)
git clone --depth 1 https://github.com/torvalds/linux
cd linux
../veloguard/... # merge:
./scripts/kconfig/merge_config.sh -m arch/x86/configs/x86_64_defconfig \
    ../veloguard/kernel/veloguardos-base.config \
    ../veloguard/kernel/veloguardos-desktop.config \
    ../veloguard/kernel/veloguardos-hardware.config
make -j"$(nproc)" && sudo make modules_install && sudo make install
```

(A `linux-veloguard` PKGBUILD that automates this is the natural next step, and a
matching CI job can publish it alongside the ISO.)

## Status

This profile is a **first cut**, written without an Arch/archiso host to test on.
The first CI run will likely need a tweak or two (package names, boot config) —
normal for any ISO pipeline. Once it's green, tags produce downloadable ISOs.
