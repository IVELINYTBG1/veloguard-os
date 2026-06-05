<div align="center">

# VeloGuardOS 🛡️

**An AI-first, security-focused Linux — where an AI can run the machine, but only through a guard that keeps *you* in control.**

Lightweight like Arch. Fully mutable for the tinkerers. Built on Linus's kernel.

`GPL-2.0-only` · x86-64 + arm64 · [build an ISO](#-build-an-iso)

</div>

---

## What makes it different

Most "AI + OS" ideas bolt a chatbot onto root and hope for the best. VeloGuardOS
does the opposite: the AI is powerful **and** contained. Every action an AI (or
you) asks for becomes a **typed action → policy check → consent gate → audit
log** before it ever touches the kernel. That guard is the product.

```
  AI PLANE  (swappable: Claude · OpenAI/Codex · local Ollama · offline)
      │  natural-language intent ("block that scanner", "run this safely")
      ▼
  ★ VELOGUARD CONTROL PLANE ★   policy · consent · rate-limit · audit · memory
      │  only typed, validated actions get through
      ▼
  KERNEL PLANE   nftables · WireGuard · namespaces · LSM   (our custom kernel)
```

The AI never speaks to the kernel directly. A weak local model can be *wrong* but
it **cannot** make the guard block your own LAN, act on an IP you never named, or
do anything outside policy.

## Features

- **🧠 Pluggable AI plane** — run fully **local** (Ollama, private, free) or via
  **API** (Claude, OpenAI/Codex, Groq…). Hot-swap the brain at runtime; keys are
  stored `chmod 600` and never logged. First-boot **setup screen** picks for you.
- **🔒 Auto-VPN on untrusted Wi-Fi** — open/unknown network → WireGuard comes up
  automatically. Backends: ProtonVPN free tier, self-hosted, Mullvad/Surfshark,
  **Tor** fallback. *(No peer-relay — we won't make you liable for strangers' traffic.)*
- **🍯 Honeypot + AI diagnosis** — decoy services capture attackers; the AI writes
  the threat report. **Bonus:** a local high-end model gets the deepest analysis.
- **🧊 Process quarantine** — freeze an unknown process into a RAM (tmpfs) sandbox;
  release it or kill-and-wipe on your word.
- **📦 Virtualization layer** — unsure about an app? `run-safe` launches it in a
  read-only/RAM-overlay sandbox (bubblewrap → gVisor → microVM by risk). On disk
  one second, in a disposable digital layer the next.
- **🔄 Signed updater** — kernel + VeloGuard updates, **verified against a pinned
  key and fail-closed**. Agent-drivable (`update check --json`).
- **🧩 Universal apps** — Flatpak, Snap, AppImage, `.deb`/`.rpm` — one
  `veloguard-install <anything>`.
- **🐧 Custom kernel** — fetched from Linus's tree, re-merged with our config
  fragments, validated on **x86-64 (262 symbols) and arm64 (72 symbols)** with
  `make olddefconfig`. Broad hardware + firmware + codecs out of the box.
- **🖥️ Desktop** — Wayland + PipeWire + GNOME; Brave default browser; Discord,
  Dolphin, Viber, ZapZap, LibreOffice, Transmission, **Waydroid** (Android apps,
  binder baked into our kernel), GNOME Software.
- **🇧🇬 Bulgarian Mode** — an easter egg. You'll find it.

## Quick start (the guard)

```bash
cd veloguard
python3 -m guardd setup                 # pick your AI plane (local or API)
python3 -m guardd "block the ssh scanner at 203.0.113.10"   # dry-run by default
python3 -m guardd run-safe ./sketchy.AppImage               # isolate an app
python3 -m guardd honeypot --analyze --block                # decoy + AI report
python3 -m guardd help
```

Everything is **dry-run by default**; add `--apply` (and root) to enforce for
real. See [`veloguard/README.md`](veloguard/README.md) for the full guard docs
and [`veloguard/provision/README.md`](veloguard/provision/README.md) for the
desktop / hardware / apps / updater provisioning.

## 💿 Build an ISO

A real bootable ISO is large and needs root + image tooling, so it's built in
**CI, not committed**. Push a tag (or run the workflow) and GitHub Actions builds
it and attaches the `.iso` to a Release:

```bash
git tag v0.1.0 && git push origin v0.1.0     # → Actions builds → Releases/*.iso
```

The recipe lives in [`iso/`](iso/) (archiso profile) and
[`.github/workflows/build-iso.yml`](.github/workflows/build-iso.yml). It bakes in
our `veloguard/` tree, the guard, the default apps, and a first-boot setup. The
custom kernel (Linus's tree + `veloguard/kernel/*.config`) is the documented
upgrade path on top of the base ISO. See [`iso/README.md`](iso/README.md).

> **Status:** the ISO pipeline is a first cut — expect a round or two of fixes on
> the first CI run, as every ISO build does.

## 🔐 Security model

- The guard mediates **everything**; protective actions (VPN up, quarantine) are
  automatic, destructive ones (kill, VPN down, updates) require consent.
- **Updates are signed and fail-closed** — no valid signature, no update.
- **Wayland + PipeWire** isolate apps (no X11-style snooping); the desktop's
  consent model mirrors the guard's.
- It's a *security* OS, so we said no to the genuinely dangerous shortcuts
  (peer-relay VPN) even when asked.

## License

[`GPL-2.0-only`](LICENSE) — the same license as the Linux kernel it builds on.
VeloGuardOS components are GPL-2.0 © the VeloGuardOS authors; the kernel is
fetched at build time and remains GPL-2.0 © its own authors.

<div align="center"><sub>Built with Claude Code. For my brothers — the techies and experimenters. 🇧🇬</sub></div>
