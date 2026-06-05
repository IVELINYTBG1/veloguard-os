# VeloGuardOS provisioning — setup screen, local AI + GPU

The installer lays the **infrastructure** (Ollama + the right GPU acceleration);
the **setup screen** lets the user choose their AI plane — local or API — and is
where keys and models get configured.

```bash
sudo ./install-ai-stack.sh        # installs Ollama + GPU accel, then runs the wizard
```

## The setup screen

`guardd setup` is an interactive wizard over the same `use`/`key`/`model`
commands. It asks one question — **local or cloud?** — and configures the rest:

```
┌────────────────────────────────────────────────┐
│  VeloGuardOS  ·  setup                          │
└────────────────────────────────────────────────┘
Choose your AI plane:
   1) Local   — Ollama on this machine. Private, free, needs a capable PC.
   2) Cloud   — Claude or OpenAI/Codex. Runs on a potato, needs an API key.
   3) Skip    — offline keyword mode (mock); set it up later.
```

- **Local** → lists pulled Ollama models (offers to pull one if none), you pick.
- **Cloud** → pick Claude or OpenAI-compatible, paste the key (hidden, stored
  `chmod 600`), choose a model; OpenAI path also asks for a base URL so Groq /
  OpenRouter / a local server work.
- Offers to **test the connection** (validates a local model or an API key) and
  to **initialize the firewall table**.

Run it again any time to reconfigure: `python3 -m guardd setup`.

### Running it on first boot (the actual "setup screen")

`veloguard-firstboot` + `veloguard-firstboot.service` drive the wizard on the
console (tty1) the first time the machine boots, then bow out via a marker file:

```bash
install -m755 veloguard-firstboot         /usr/local/bin/veloguard-firstboot
install -m644 veloguard-firstboot.service /etc/systemd/system/
systemctl enable veloguard-firstboot.service
# delete /var/lib/veloguard/.setup-done to make it run again
```

## How Ollama is "connected to the kernel"

It isn't — and shouldn't be. Ollama is a userspace program; it lives in the
**AI plane**. "Connected" means it plugs into VeloGuard's existing spine as a
swappable adapter:

```
Ollama (local LLM)  ->  OllamaAdapter  ->  guard (policy/consent/audit)  ->  nftables
   localhost:11434      stdlib HTTP        the part that protects you       kernel
```

Same guard, same audit log, same protected-range refusals as the cloud
adapters. Going local changes *who answers*, not *what's allowed*.

## The CUDA / GPU truth (important)

**CUDA is not part of the kernel and is not "all drivers you can install."**
CUDA is NVIDIA-only userspace (libcuda + the CUDA toolkit) plus the proprietary
NVIDIA kernel module. So VeloGuardOS handles acceleration by hardware class,
and the provisioner picks the right one automatically:

| GPU in the machine | What we install | Ollama uses |
|--------------------|-----------------|-------------|
| **NVIDIA** | proprietary driver + CUDA runtime (distro layer) | CUDA |
| **AMD** | ROCm / Vulkan | ROCm/Vulkan — **CUDA does nothing here** |
| **Intel iGPU / VM / none** | nothing extra | CPU (or Intel Vulkan) — **CUDA does nothing here** |

Installing "all the CUDA drivers" on a non-NVIDIA box (like this dev machine's
Intel Iris Xe) is wasted space and won't accelerate anything. The script
detects this and stays CPU-only instead.

### For the actual VeloGuardOS image (kernel side)

The kernel binary stays GPU-agnostic. What the **image** does:

- ships `nouveau`/`amdgpu`/`i915` in-tree modules (already in the kernel we cloned),
- on first boot or via this script, layers the NVIDIA proprietary driver +
  CUDA toolkit **only if** an NVIDIA card is present (akmod/DKMS so it rebuilds
  against our kernel),
- enables the `ollama` systemd unit so the local AI plane is up at boot.

That keeps the kernel lightweight (your "like Arch" goal) while still giving
GPU users full CUDA acceleration.

## Picking the local model

Default is `llama3.2:1b` — small and fast. In testing it reliably handles clear
commands ("ban 203.0.113.10") but **misclassifies nuanced phrasings** (e.g.
"let X back in" as a block) and sometimes invents an IP. For real local use a
3B+ model is the sweet spot:

```bash
export VELOGUARD_OLLAMA_MODEL=llama3.2:3b     # or qwen2.5:3b — much better classification
export VELOGUARD_OLLAMA_MODEL=qwen2.5:7b      # if you have the VRAM
export VELOGUARD_OLLAMA_HOST=http://localhost:11434
```

### Why a weak model is still safe here

This is the whole point of the guard. The `OllamaAdapter` only lets the model
*classify intent* — the IP it acts on must appear verbatim in your request
(hallucinated addresses are discarded), and every action still passes the
policy engine, protected-range refusals, consent gate, and audit log. A dumb
local model can be wrong, but it **cannot** make VeloGuard block an address you
never mentioned or lock you out of your own LAN.

---

# Desktop — Wayland + PipeWire + GNOME

Two halves, because the desktop is userspace but the kernel must support it.

## 1. Kernel side — `../kernel/veloguardos-desktop.config`

A verified Kconfig fragment (DRM/KMS, GPU drivers as modules, dmabuf + sync_file,
evdev input, ALSA for PipeWire, plus seccomp/Landlock). Merge it into a base
defconfig in the kernel tree:

```bash
cd <kernel-tree>
./scripts/kconfig/merge_config.sh -m arch/x86/configs/x86_64_defconfig \
    veloguard/kernel/veloguardos-desktop.config
make olddefconfig
```

GPU drivers are modules so only your card loads; DRM core + virtio-gpu are
built in so VeloGuardOS always reaches a graphical session (bare metal *or* VM).

## 2. Userspace side — `install-desktop.sh`

```bash
sudo ./install-desktop.sh        # detects Arch / Fedora / Debian base
```

Minimal on purpose ("like Arch"): GNOME **Shell** + GDM, PipeWire +
WirePlumber, the GNOME portal — not the full GNOME suite. Add what you want;
that's the "fully mutable" promise. It enables GDM, turns on PipeWire as a
per-user service, and makes sure GDM is serving **Wayland**.

## Why this stack suits a *security* OS

- **Wayland** isolates apps — one app can't keylog or screen-scrape another, the
  way any X11 client can snoop the whole session.
- **PipeWire** grants screen/audio capture only through **portals** (per-app,
  per-use consent) — the same consent philosophy as the VeloGuard guard.

Verify after reboot: `echo $XDG_SESSION_TYPE` → `wayland`.

---

# Hardware support — "works for everyone out of the box"

Same two halves: the kernel must *contain* the drivers, and userspace must
supply the *firmware* that makes them run.

## 1. Kernel side — `../kernel/veloguardos-hardware.config`

A broad driver fragment: Intel/AMD/NVIDIA GPUs, Intel/Realtek/Atheros/MediaTek/
Broadcom Wi-Fi, common Ethernet, Bluetooth, NVMe/SATA/USB/SD/RAID storage,
HDA + USB + SOF audio, UVC webcams, every mainstream filesystem, and
virtio/Hyper-V/VMware so it boots in any VM.

**How they avoid conflicting:** every driver is a **module** (`=m`). udev loads
only the one matching your hardware — an Intel laptop never touches the AMD GPU
module. Only the must-boot-early bits stay built in. All **177 symbols are
verified to exist in the tree**, and the fragment merges cleanly with the
desktop one:

**Canonical merge — all three fragments, `base` first:**

```bash
cd <kernel-tree>
./scripts/kconfig/merge_config.sh -m arch/x86/configs/x86_64_defconfig \
    veloguard/kernel/veloguardos-base.config \
    veloguard/kernel/veloguardos-desktop.config \
    veloguard/kernel/veloguardos-hardware.config
make olddefconfig          # final dependency resolution (needs bison + flex)
```

- **base** — boot/UEFI, systemd prerequisites, namespaces + cgroups, app-sandbox
  filesystems, **nftables (VeloGuard's guard needs it)**, **WireGuard** (built-in
  VPN), TUN, suspend/cpufreq/backlight.
- **desktop** — DRM/KMS, dmabuf/sync_file, evdev, ALSA, Landlock.
- **hardware** — broad GPU/Wi-Fi/NIC/BT/storage/audio/webcam/FS drivers as modules.

Want *literally every* driver? `make allmodconfig` builds them all as modules;
these fragments are the curated mainstream subset (no staging/debug bloat).

> **Validated, not hoped.** The three x86_64 fragments merge onto
> `x86_64_defconfig` and pass `make olddefconfig` with **259/259 requested
> symbols landing exactly** (0 mismatches) — every dependency chain resolved.

### ARM / arm64 — don't exclude ARM users

ARM is a **separate architecture** (Raspberry Pi, Apple Silicon, Snapdragon
laptops, Rockchip/Allwinner SBCs, Ampere/Graviton servers) — its own defconfig
and its own GPUs (Mali/Adreno/VideoCore). So there's a dedicated profile,
`../kernel/veloguardos-arm64.config`, layering the VeloGuardOS essentials
(nftables guard, WireGuard, sandbox FS, app-format support) plus ARM desktop
GPUs (Panfrost/Panthor/Lima, MSM/Adreno, VC4/V3D, Tegra, Etnaviv) on top of the
kernel's broad arm64 defconfig.

```bash
./scripts/kconfig/merge_config.sh -m -O build-arm64 \
    arch/arm64/configs/defconfig veloguard/kernel/veloguardos-arm64.config
make ARCH=arm64 O=build-arm64 olddefconfig          # config: no cross-compiler needed
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc)   # full build
```

Validated the same way: **72/72 symbols land, 0 mismatches.** All VeloGuard
*userspace* (guard daemon, setup wizard, provisioning, `veloguard-install`) is
architecture-independent and runs unchanged on ARM. Apple Silicon note: display
works via SIMPLEDRM today; the dedicated Asahi GPU driver isn't upstream yet.

## 2. Userspace side — `install-firmware-codecs.sh`

```bash
sudo ./install-firmware-codecs.sh    # firmware + microcode + VA-API + codecs
```

- **`linux-firmware` + SOF firmware** — the blobs Wi-Fi/GPU/Bluetooth/audio
  need; without these the modules load but the hardware stays dark.
- **CPU microcode** (`intel-ucode`/`amd-ucode`) — applied early at boot; then
  the initramfs is regenerated so it actually takes effect.
- **GPU video decode** — VA-API/VDPAU (Intel media driver, Mesa freeworld on
  AMD) so the GPU does the heavy lifting for video.
- **Codecs** — GStreamer (base/good/bad/ugly + libav) and ffmpeg.

**Codec licensing, honestly:** H.264/H.265/AAC are patent-encumbered. The
script enables RPM Fusion (Fedora) / non-free (Debian) so playback works for
everyone — drop that if your distribution policy forbids it.

Verify after reboot: `vainfo` (GPU decode), `lsmod` (loaded drivers).

---

# Universal application formats — install anything

VeloGuardOS aims to run software in **every** common form, so nobody is locked
out by packaging. Kernel support (user namespaces, FUSE, squashfs, overlayfs,
binfmt_misc) is in `kernel/veloguardos-base.config`; userspace is two scripts.

## Enable the runtimes — `install-app-formats.sh`

```bash
sudo ./install-app-formats.sh
```

Installs **Flatpak** (+ Flathub), **Snap** (snapd), **AppImage** support (FUSE +
bubblewrap + portals), and **alien** for `.deb`⇄`.rpm` conversion. Native
`.deb`/`.rpm`/`.pkg` work through the base distro's own package manager.

## Install any file — `bin/veloguard-install`

One command, dispatches by type (downloads URLs first):

```bash
veloguard-install ./Foo.AppImage            # → ~/Applications, runnable
veloguard-install ./app.flatpakref          # → flatpak install
veloguard-install ./tool_1.2_amd64.deb      # → apt, or alien-convert off-distro
veloguard-install https://x.com/thing.rpm   # → dnf/rpm, or alien-convert
veloguard-install ./game.snap               # → snap install
veloguard-install ./pkg-1-x86_64.pkg.tar.zst# → pacman -U
veloguard-install ./blob.tar.gz             # → extracted to /opt
```

Cross-distro reality, stated plainly: `.deb` is native only on Debian-based and
`.rpm` only on RPM-based systems. Off their home distro, `veloguard-install`
falls back to **alien** conversion — which works for many simple packages but
not ones with complex maintainer scripts. The portable answer remains
Flatpak/Snap/AppImage, which run anywhere.

---

# Default applications (shipped on the ISO)

`install-default-apps.sh` — **Brave is the default browser (not Firefox)**, plus
the everyday basics, mostly Flatpaks for cross-distro consistency:

| App | Source | Role |
|-----|--------|------|
| **Brave** | `com.brave.Browser` | default browser |
| Discord | `com.discordapp.Discord` | chat |
| **Dolphin** | `org.kde.dolphin` | default file manager |
| Viber | `com.viber.Viber` | messaging |
| ZapZap | `com.rtosta.zapzap` | WhatsApp client |
| LibreOffice | `org.libreoffice.LibreOffice` | office suite |
| Transmission | `com.transmissionbt.Transmission` | torrents |
| Waydroid | native (binder in our kernel) | Android apps |
| GNOME Software | native (+ Flatpak plugin) | graphical app store |

Brave is set as default browser and `https`/`http` handler; Dolphin is the
default file manager (GNOME's Nautilus stays available). **Waydroid** needs the
kernel `binder` support we enabled in `kernel/veloguardos-base.config`, and a
one-time `waydroid init` (downloads ~1 GB Android image) on first run.

# Built-in updater

`veloguard-update check|apply|rollback` (or `guardd update`). Signed and
fail-closed — see the main `veloguard/README.md`. The systemd timer
(`veloguard-update.{service,timer}`) polls `check` every 12 h; applying is
deliberate (user or update-agent). Sign releases per `keys/SIGNING.md`.
