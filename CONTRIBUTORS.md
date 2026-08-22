# Contributors & Acknowledgments

## VeloGuardOS

VeloGuardOS — the guard (kernel plane, `guardd`, VPN/honeypot/updater, ISO
recipe, provisioning) — is `GPL-2.0-only` © the VeloGuardOS authors and
contributors. See [`COPYRIGHT`](COPYRIGHT) and [`LICENSE`](LICENSE).

## Omarchy — the desktop, hardware & agent-plugin foundations

The VeloGuardOS **desktop** ([`desktop/`](desktop/)) — the Hyprland environment,
its look & feel (Waybar, mako, theming), the first-boot **hardware/driver
layer**, and the **agent-plugin** pattern — is **derived from
[Omarchy](https://github.com/basecamp/omarchy)**, and we gratefully credit its
authors:

- **David Heinemeier Hansson** and the **37signals / Omarchy team**

Omarchy is MIT-licensed; the MIT license is compatible with VeloGuardOS's
GPL-2.0-only distribution. The upstream MIT notice is retained verbatim in
[`desktop/omarchy/OMARCHY-LICENSE`](desktop/omarchy/OMARCHY-LICENSE), and a
file-by-file record of what was derived and how lives in
[`desktop/omarchy/PROVENANCE.md`](desktop/omarchy/PROVENANCE.md) (pinned to
Omarchy commit `f4378f0`).

> This is an acknowledgment of authorship and license, not a claim that the
> Omarchy team endorses or maintains VeloGuardOS.

## The Linux kernel

VeloGuardOS builds on the Linux kernel, fetched at build time from Linus
Torvalds' tree and remaining `GPL-2.0` © its own authors. VeloGuardOS's kernel
changes are the config fragments under [`veloguard/kernel/`](veloguard/kernel/).
