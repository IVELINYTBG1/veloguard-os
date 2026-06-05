# VeloGuard — control plane (prototype)

The piece that makes VeloGuardOS *AI-first* without making it *AI-owned*.

An AI with root is a liability. VeloGuard puts a **guard** between the AI and
the kernel: every intent must become a typed action, pass a policy engine, get
the user's consent when it matters, and land in an audit log. The guard is the
product.

```
  intent (NL)        Action            Decision           kernel
  "block that    ->  block_ip      ->  allow / deny  ->   nftables
   ssh scanner"      {ip: …}           / ask user         (in-kernel netfilter)
       │                │                  │                  │
   ai_adapter.py    actions.py        policy.py          executor.py
   (swappable:      (the only         (the GUARD:        (only code that
    mock/claude/    contract the      consent, rate      touches the
    codex/local)    AI can speak)     limit, protect)    kernel; dry-run
                                                          by default)
```

## This is the vertical slice

One capability, proven end to end: **"block an IP."** It exercises the whole
spine so every later feature (honeypots, VPN toggles, LSM policy) just plugs in
as another `Action` + adapter case + policy rule + executor method.

## Try it (safe — dry-run by default, no root needed)

```bash
cd veloguard
./demo.sh                                    # full guided tour
python3 -m guardd --setup                    # show the nft table it manages
python3 -m guardd "block 203.0.113.10"       # parse + guard + consent prompt
python3 -m guardd --yes "ban 203.0.113.10"   # skip the prompt
```

Real enforcement (touches the live firewall — needs root):

```bash
sudo python3 -m guardd --apply --setup
sudo python3 -m guardd --apply --yes "block 203.0.113.10"
```

## Two AI planes — pick what your machine can handle

Not everyone has a GPU rig, and not everyone wants to depend on the cloud. Both
paths go through the exact same guard, so the safety story is identical.

**Local** (private, free, needs a capable-ish PC) — see `provision/`:

```bash
python3 -m guardd --adapter ollama "kill the host hammering my ssh, 203.0.113.10"
```

**Cloud API** (runs on a potato, needs a key) — *no pip install, stdlib only*:

```bash
# Anthropic
export ANTHROPIC_API_KEY=...
python3 -m guardd --adapter claude "block 203.0.113.10"

# Any OpenAI-compatible API (OpenAI/Codex, Groq, OpenRouter, local server…)
export OPENAI_API_KEY=...
# export VELOGUARD_OPENAI_BASE_URL=https://api.groq.com/openai/v1   # optional
python3 -m guardd --adapter openai "block 203.0.113.10"
```

**Set your default once** in `config.json` (`"adapter": "ollama" | "claude" |
"openai" | "mock"`) and drop the `--adapter` flag. The CLI flag always
overrides the config.

## Hot-swapping the core — runtime commands

The active brain (provider + model + key) is **hot-swappable, but only when you
type a command**. Nothing switches on its own. A swap takes effect on the *very
next* intent.

```bash
guardd use claude                 # switch active brain
guardd use ollama llama3.2:3b     # switch brain AND pick its model in one go
guardd key claude  sk-ant-...     # store an API key  (chmod 600, never logged)
guardd key openai  sk-...
guardd model openai gpt-4o        # pick a model for a provider
guardd model ollama qwen2.5:3b    # ollama users often have several models
guardd status                     # what's active; keys shown masked (…1234)
guardd models                     # list the ollama models you've pulled
```

(`guardd` = `python3 -m guardd`.) Where things live and who wins:

| Setting | Resolution order (first found wins) |
|---------|-------------------------------------|
| active provider | `--adapter` flag → stored (`guardd use`) → `config.json` → `mock` |
| model | `$VELOGUARD_<P>_MODEL` → stored (`guardd model`) → built-in default |
| API key | `$ANTHROPIC_API_KEY`/`$OPENAI_API_KEY` → stored (`guardd key`) → none |

Runtime state is written to `~/.config/veloguard/` (override with
`$VELOGUARD_STATE`): `state.json` holds the non-secret selection, and
`credentials.json` holds keys at `chmod 600`. **Keys are never written to the
audit log or printed in full** — only `…last4`. Setting a key is itself audited
(masked), so you can see *when* a brain's credentials changed.

## What the guard guarantees today

- **Protected ranges** — the AI can never block loopback, RFC1918, or
  link-local. It cannot be talked into locking you out of your own box.
- **Consent gate** — state-changing actions stop and ask, unless `--yes`.
- **Rate limit** — sliding window caps runaway action storms.
- **Audit** — every decision (allowed, denied, aborted) is one JSON line in
  `audit.log`.
- **Dry-run default** — nothing touches the kernel without `--apply`.

## Layout

| File | Plane | Role |
|------|-------|------|
| `guardd/ai_adapter.py` | AI | intent → Action; swap Claude / Codex / local |
| `guardd/actions.py`    | — | the typed contract the AI is limited to |
| `guardd/policy.py`     | control | allow / deny / needs-approval |
| `guardd/executor.py`   | kernel | nftables today, netlink → VeloGuard LSM later |
| `guardd/audit.py`      | — | append-only decision log |
| `guardd/__main__.py`   | — | wires the pipeline; the CLI |
| `policy.json`          | control | editable policy ("fully mutable") |

## Roadmap from here

1. Replace `nft` shell-out with direct **netlink** (no fork per action).
2. Run as a **daemon** with a local socket; the CLI becomes a thin client.
3. New actions: honeypot spin-up, WireGuard up/down, seccomp/landlock profiles.
4. Move enforcement into a real **`security/veloguard/` LSM** in the kernel tree.

## VPN, auto-protect, quarantine & AI memory

New guard actions (same pipeline: AI/intent → policy → consent → executor → audit):

| Action | Consent? | What it does |
|--------|----------|--------------|
| `vpn_up` | **auto** (protective) | WireGuard tunnel up (profile, or `tor`) |
| `vpn_down` | needs consent | tunnel down — undoing protection |
| `quarantine` | **auto** (protective) | freeze an unknown process, stash its exe in a RAM (tmpfs) sandbox |
| `release_quarantine` | needs consent | unfreeze + clear (you trust it) |
| `kill_quarantine` | needs consent | SIGKILL + wipe the RAM stash (you reject it) |

**Auto-protect on Wi-Fi** — the network brain:

```bash
guardd net --ssid "Airport_Free_WiFi" --security open   # → untrusted → auto VPN
guardd net --ssid HomeNet --bssid de:ad:.. --security wpa2   # → ask, then remember
```

`guardd/netclass.py` classifies (memory first, then heuristics: open = untrusted),
and on a real box `bin/veloguard-netwatch` runs it automatically on every Wi-Fi
connect (NetworkManager dispatcher `provision/veloguard-nm-dispatcher`).

**The VPN exit is a real endpoint, not peer-relay.** Routing users through each
other (the Hola model) makes every user liable for strangers' traffic — we don't
do that. Set a backend with `bin/veloguard-vpn` (Proton free tier, self-hosted,
Mullvad/Surfshark), with **Tor** as the fallback.

**AI memory** (`guardd/memory.py`) — SQLite trust store (networks, processes,
prefs; always on) + optional **ChromaDB** for semantic recall of past decisions
(`provision/install-ai-memory.sh`; degrades to off if not installed).

## Honeypot + AI attack diagnosis

A decoy honeypot (`guardd/honeypot.py`) opens fake services (SSH/HTTP/Telnet/FTP),
baits attackers with real-looking banners, and records every session to a RAM
(tmpfs) capture log. The active AI then diagnoses each attack and reports to you.

```bash
veloguard honeypot --ports 2222,8080,2323 --analyze --block
```

- captures the attacker's payload (creds, commands, exploit strings)
- the AI summarizes: attack class, severity, IOCs, remediation
- `--block` auto-blocks the source through the guard (protected ranges stay safe)
- analyze a saved capture later:  `veloguard analyze <captures.jsonl>`

### The bonus for the tech community: depth scales with your model

| Tier | When | What you get |
|------|------|--------------|
| **deep** ★ | local (ollama) **+ high-end** model (70B, mixtral…) | full IR report: technique, likely CVE, MITRE mapping, IOCs, step-by-step fix |
| standard | any other LLM (small local / cloud) | classification, severity, IOCs, one recommendation |
| basic | no model (mock) | offline heuristic triage |

Run a beefy **local** model → deepest diagnosis, entirely on your own hardware,
nothing leaving the box. (Verified live: ollama diagnosed a Log4Shell+traversal
payload; the heuristic flagged a sqlmap+dropper attack as HIGH.)

## Running the guard on a compatible Python

ChromaDB lags the newest Python. Instead of pinning the whole system,
`provision/install-ai-memory.sh` builds a venv on a known-good Python (3.11–3.13)
and installs ChromaDB there; `bin/veloguard` runs the guard under that venv
automatically (falling back to system `python3`). Semantic memory just works.

```bash
./provision/install-ai-memory.sh     # one-time: venv + chromadb
bin/veloguard "block 203.0.113.10"   # uses the venv if present
```

## Virtualization layer — run uncertain apps in a "digital layer"

When the AI or you are unsure about a program but you still want to run it, the
guard launches it **isolated**: the real filesystem is read-only and every write
goes to RAM (tmpfs), inside Linux namespaces. It runs from disk but its writable
world is ephemeral — on exit it evaporates. Setup is milliseconds.

```bash
veloguard run-safe ./sketchy.AppImage        # AI rates risk → picks the tier
veloguard run-safe --tier light --apply foo  # force a tier and actually run it
veloguard "run /usr/bin/xterm in a sandbox"  # also via natural language
```

Tiered by risk (degrades to the strongest tier installed — `install-sandbox.sh`):

| Tier | Tech | Isolation | When |
|------|------|-----------|------|
| **light** (default) | bubblewrap + RAM tmpfs, no network | namespaces, ephemeral writes | low risk / installed apps |
| **strong** | gVisor `runsc` | userspace syscall kernel | medium risk |
| **vm** | Firecracker microVM (VeloGuardOS kernel as guest) | separate kernel | high risk / downloaded binaries |

The AI assesses run-risk (`vlayer.assess_risk` — local high-end models reason
deepest, per the [model bonus](#the-bonus-for-the-tech-community-depth-scales-with-your-model));
no-model falls back to a heuristic (downloaded/`.AppImage` → high). **Verified
live**: a write to `~/vproof.txt` inside the layer was readable *inside* and
**absent on the real host** — it stayed in RAM and vanished.

## Built-in updater (signed, fail-closed, agent-drivable)

VeloGuardOS updates in two streams, and **every `veloguard` update is verified
against a pinned key before anything touches disk — it fails closed** (no key,
no openssl, or a bad/absent signature all mean "do not apply").

```bash
veloguard-update check --json     # read-only — what the update-agent polls
veloguard-update apply --domain veloguard --apply --yes
veloguard-update rollback         # restore the previous version
```

- **veloguard** — our signed release: a manifest (detached signature) carrying
  the artifact's sha256, so the artifact is trusted transitively. Atomic swap
  with automatic rollback on failure.
- **kernel** — fetch a new upstream tag, re-merge our fragments, `olddefconfig`,
  rebuild. Upstream integrity from git.

Sign releases with the offline key (`keys/SIGNING.md`). `check` emits JSON so the
"keep VeloGuardOS updated" agent can poll, decide, and call apply (which
re-verifies + audits). A systemd timer (`provision/veloguard-update.timer`)
polls `check` every 12 h — **check only; applying is always deliberate**.
Verified live: valid signature passes; tampered manifest and missing key both
refuse.

## 🇧🇬 Bulgarian Mode (easter egg — UI only, no kernel)

A toggle button for fellow Bulgarians. ON: the wallpaper becomes a **random
slideshow** of `Bulgarian_Mode/wallpapers/` and `Bulgarian_Mode/Music/` plays on
**shuffle** — both loop **until you turn it off**, which stops the music and
restores your original wallpaper.

```bash
veloguard-bulgarian-mode on | off | toggle | status
```

Ships as a **"Bulgarian Mode" launcher** (`ui/bulgarian-mode.desktop`) that
appears as a button in the app grid and toggles the mode. Purely userspace —
`gsettings` for the wallpaper, `mpv`/`ffplay` for the music. Assets install to
`/usr/share/veloguard/Bulgarian_Mode` (override with `$VELOGUARD_BG_DIR`).
Честито! 🎉
