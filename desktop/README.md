# VeloGuardOS desktop layer (Omarchy-style Hyprland)

This directory is the VeloGuardOS **desktop**: an Omarchy-derived Hyprland
(Wayland tiling) environment, re-branded and made **self-contained** so the ISO
builds hermetically from official Arch repos. It replaces the old GNOME/GDM
desktop while the VeloGuard **guard** (kernel, `guardd`, VPN, honeypot, updater,
installer) is unchanged and is wired into the desktop.

Derived from Omarchy (MIT, © David Heinemeier Hansson / 37signals). See
[`omarchy/OMARCHY-LICENSE`](omarchy/OMARCHY-LICENSE) and
[`omarchy/PROVENANCE.md`](omarchy/PROVENANCE.md).

## Layout

| Path | Installed to | What it is |
|---|---|---|
| `defaults/hypr/` | `/usr/share/veloguard/desktop/hypr/` | Shipped Hyprland defaults (envs, autostart, look'n'feel, window rules, keybindings). Read-only. |
| `skel/.config/` | `/etc/skel/.config/` → every user's `~/.config` | Per-user configs: Hyprland entry + overrides, Waybar, mako, wofi, alacritty, hyprlock, hypridle. |
| `themes/<name>/` | `/usr/share/veloguard/themes/<name>/` | Themes (colors for Hyprland/Waybar/mako/alacritty/hyprlock). Default: `veloguard`. |
| `hardware/` | `/usr/share/veloguard/hardware/` | Omarchy-derived driver/hardware setup, run once at first boot (see below). |
| `agents/` | `/usr/share/veloguard/agents/` | Agent plugin: MCP config + skill for driving the guard (see below). |
| `bin/` | `/usr/local/bin/` | Guard↔desktop helpers (see below). |
| `packages.desktop` | — | The desktop package set (official repos only). |

## Keybindings — stock Hyprland defaults

By request, VeloGuardOS uses the **default Hyprland keybindings** (not Omarchy's):
`defaults/hypr/bindings/hyprland-default.conf` (SUPER+Q terminal, SUPER+C close,
SUPER+E files, SUPER+R launcher, SUPER+V float, SUPER 1-0 workspaces, …). Only
the app variables point at VeloGuard's shipped apps. Omarchy's **look & feel**
(gaps/blur/animations, Waybar, mako, theming) is kept. VeloGuard's own additions
live in `veloguard.conf`, all under SUPER+SHIFT / SUPER+CTRL so they never
clobber a default.

## Hardware / drivers (Omarchy-derived)

`hardware/all.sh` runs once on **first boot** (`veloguard-hardware.service`) and
installs the drivers this machine actually needs — NVIDIA (matched to GPU gen),
Vulkan (Intel/AMD), Broadcom Wi-Fi, Bluetooth, wireless reg-domain, F-keys,
Synaptics touchpad — then regenerates the initramfs. Re-run any time with
`sudo veloguard-hardware`. Derived from Omarchy's `install/hardware/` with its
`omarchy-*` helpers reimplemented self-contained (`hardware/lib.sh`).

## AI agent plugin

`veloguard-agent` launches VeloGuard's guarded autonomous agent Omarchy-style
(`Super+Shift+A`, or the guard menu → "AI agent…"). Two brains, both restored in
the guard (`veloguard/guardd/ai_adapter.py`): **claude** (API) and **ollama**
(local). Everything the agent does still goes through the guard. External coding
agents (Claude Code, Codex) can drive the guard over MCP — see `agents/`.

## Guard ↔ desktop integration

The old GNOME Shell extension's behavior is ported to Hyprland/Waybar:

| Helper | Role |
|---|---|
| `veloguard-waybar-guard` | Waybar `custom/guard` module — read-only VPN / Wi-Fi-trust / staged-update / guard status, color-coded. |
| `veloguard-guard-menu` | `wofi` menu → VPN connect/import/Tor, Wi-Fi trust toggle, Bulgarian Mode. Wraps the existing `veloguard-vpn`, `veloguard-wifi-trust`, `veloguard-bulgarian-mode` helpers (polkit rules unchanged). |
| `veloguard-powermenu` | Power menu incl. **Reboot & Update** → `veloguard-arm-offline-update`. |
| `veloguard-theme` | Theme switcher (relinks `~/.config/veloguard/current`, live-reloads the session). |
| `veloguard-agent` | Launch the guarded autonomous agent (claude/ollama), Omarchy-style. |
| `veloguard-hardware` | Run the Omarchy-derived driver/hardware setup. |
| `veloguard-firstboot-desktop` | Runs `veloguard setup` once on first graphical login. |

VeloGuard keybindings (added on top of the Hyprland defaults): `Super+Shift+G`
guard menu · `Super+Shift+V` VPN · `Super+Shift+A` agent · `Super+Escape` power
menu · `Super+Shift+T` theme. Full set in `defaults/hypr/bindings/`.

## Theming

A theme is a directory of color files under `/usr/share/veloguard/themes/`. The
active theme is the symlink `~/.config/veloguard/current`; every desktop config
sources its colors *through* that symlink, so switching is a relink + reload:

```bash
veloguard-theme list          # veloguard, tokyo-night, catppuccin
veloguard-theme set tokyo-night
veloguard-theme menu          # pick with wofi (Super+Shift+Ctrl+Space)
```

## Not vendored

Omarchy's installer, its `omarchy-*` helper scripts, `omarchy-menu`/walker,
web-app launchers, and branding assets are **not** included — VeloGuardOS ships
its own guard-integrated equivalents from official-repo tools only.
