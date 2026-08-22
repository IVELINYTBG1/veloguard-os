# Provenance — VeloGuardOS desktop layer ← Omarchy

The VeloGuardOS Hyprland desktop (`desktop/`) is **derived from Omarchy**, the
opinionated Arch/Hyprland setup by David Heinemeier Hansson / 37signals
(MIT, see [`OMARCHY-LICENSE`](OMARCHY-LICENSE)).

- **Upstream:** https://github.com/basecamp/omarchy
- **Branch:** `master`
- **Pinned commit:** `f4378f0de5b44d331ee943746a97872b718a6c18` (v3.8.5, 2026-08-14)

## What was taken, and how

These files reproduce Omarchy's Hyprland **keybinding scheme, window-management
behavior, and look-and-feel**, translated into a **self-contained** form: the
heavy `omarchy-*` helper-script dependency web is removed and replaced with
stock tools available in the official Arch repositories (so the VeloGuardOS ISO
stays hermetic — no AUR, no network at build). Where Omarchy branding appeared
it is rebranded to VeloGuard. This is a derivative work, not a verbatim copy.

| VeloGuard file | Derived from (Omarchy path @ f4378f0) | Nature of change |
|---|---|---|
| `desktop/defaults/hypr/bindings/hyprland-default.conf` | **NOT Omarchy** — the stock Hyprland default binding scheme | By request, keybindings are Hyprland's own defaults (SUPER+Q/C/M/E/V/R/P/J/S…), only the app vars point at VeloGuard apps |
| `desktop/defaults/hypr/bindings/veloguard.conf` | original (VeloGuard) | Guard/desktop additions under SUPER+SHIFT / SUPER+CTRL / fn-keys so nothing clobbers a Hyprland default |
| `desktop/defaults/hypr/looknfeel.conf` | `default/hypr/looknfeel.conf` | Kept faithfully — this is the Omarchy **UI/UX look** (gaps/border/shadow/blur/animations/dwindle) |
| `desktop/defaults/hypr/envs.conf` | `default/hypr/envs.conf` | Kept; theme `source` repointed to VeloGuard theme path |
| `desktop/defaults/hypr/windows.conf` | `default/hypr/windows.conf` | Adapted window rules |
| `desktop/defaults/hypr/autostart.conf` | `default/hypr/autostart.conf` | Rewired: hypridle/mako/waybar/swaybg kept; `omarchy-*` autostarts → VeloGuard equivalents + `veloguard-firstboot` |
| `desktop/skel/.config/hypr/*` | `config/hypr/*` | User-override stubs + top-level `hyprland.conf` that sources VeloGuard defaults |
| `desktop/skel/.config/waybar/config.jsonc` | `config/waybar/config.jsonc` | Omarchy-script modules removed; **`custom/guard`** module added; stock modules kept |
| `desktop/skel/.config/waybar/style.css` | `config/waybar/style.css` | Kept; theme import repointed; `.guard-*` classes added |
| `desktop/skel/.config/mako/config` | `default/mako/core.ini` + `default/themed/mako.ini.tpl` | Merged into one config; theme colors inlined via VeloGuard theme |
| `desktop/skel/.config/hypr/hyprlock.conf` | `config/hypr/hyprlock.conf` | Kept; theme/background paths repointed |
| `desktop/skel/.config/hypr/hypridle.conf` | `config/hypr/hypridle.conf` | Rewired lock/sleep to stock `hyprlock`/`loginctl` |
| `desktop/skel/.config/alacritty/alacritty.toml` | `default/alacritty/*` | Minimal terminal config, theme colors via include |
| `desktop/themes/*` | `themes/*` (color values) | Palettes reproduced as VeloGuard theme dirs |
| `iso/airootfs/.../sddm` + session | `default/sddm/*`, `default/wayland-sessions/omarchy.desktop` | SDDM autologin + `hyprland-uwsm` session, rebranded |
| `desktop/hardware/*` | `install/hardware/*` + `bin/omarchy-pkg-add`, `bin/omarchy-hw-nvidia-*` | Broadly-applicable driver/hardware scripts (network, nvidia, vulkan, bluetooth, wireless-regdom, fkeys, synaptic-touchpad, bcm43xx, input-group). Omarchy's `omarchy-*` helpers reimplemented as self-contained `vg_*` bash functions in `lib.sh`. Runs at **first boot** so it can fetch the drivers this machine needs. Niche device-family scripts (asus-rog, framework, apple-T2, surface, lenovo, intel-ptl camera) are **not** vendored — extensible later. |
| `desktop/agents/*`, `desktop/bin/veloguard-agent` | Modeled on Omarchy's agent plugin (`bin/omarchy-agent`, `omarchy-default-agent`, `default/agents/skills/*`) | VeloGuard's own agent launcher/skill following Omarchy's pattern (a persisted default brain, launched in a terminal); backends are the guard's restored **claude** + **ollama** brains driving the machine through the guard. |

## Not taken
Omarchy's installer pipeline (`install/`, except the hardware layer above), its
`bin/omarchy-*` helper scripts, `omarchy-menu`/walker, web-app launchers,
voxtype, quickshell, and its branding assets are **not** vendored. VeloGuardOS
provides its own guard-integrated equivalents.

## Deliberately NOT Omarchy
By request, two things use non-Omarchy sources:
- **Keybindings** are the **stock Hyprland defaults**
  (`desktop/defaults/hypr/bindings/hyprland-default.conf`), not Omarchy's scheme.
  Omarchy's **look & feel** (`looknfeel.conf`, Waybar, mako, theming) is kept.
- **Agent brains** (`claude`, `ollama`) live inside VeloGuard's own guard
  (`veloguard/guardd/ai_adapter.py`), not Omarchy's coding-agent runtime — but
  the launcher UX follows Omarchy's agent-plugin pattern.
