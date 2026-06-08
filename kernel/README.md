# VeloGuardOS kernel update-tree

This directory is **our kernel expressed as a delta on Linus's tree** — never the
full 6.4 GB source (GitHub can't host that, and nobody should pull it per update).
The full source is fetched from kernel.org at build time; here we keep only:

| File | What it is |
|------|------------|
| `BASE` | the upstream tag we're pinned to (e.g. `v7.0`). The agent bumps this. |
| `PKGBUILD` | Arch recipe: upstream source + our config + our patches → `linux-veloguard` package |
| `build-recipe.sh` | CI entry point: stages context, runs `makepkg`, emits the artifact + sha256 + manifest block |
| `patches/*.patch` | our source patches on top of upstream (none yet — config-only so far) |

The config fragments themselves live in `../veloguard/kernel/veloguardos-*.config`
(single source of truth, also used by the ISO + `veloguard-kernel-sync`); the
recipe copies them into the build context.

## The pipeline

```
Linus stable tag ─┐
                  ├─[agent] bump BASE + rebase patches + validate → commit & push
our patches+config┘                         │
                              [CI build-kernel.yml] makepkg in an Arch container
                                            │
                          linux-veloguard-X.Y-1-x86_64.pkg.tar.zst → GitHub Release
                                            │
                              sign manifest.json (kernel version + sha256)   ← offline key
                                            │
                    [user's updater] background download → stage → apply on reboot (opt-in)
```

- **Compare our kernel to Linus's** = compare `BASE` + `patches/` against Linus's
  latest stable. The agent does the merge and updates this tree (see the
  `kernel-sync` agent contract).
- **Deliver to users** = the built-in updater (`guardd update`) downloads the
  signed, prebuilt package in the background and stages it for an
  apply-on-reboot, Fedora-style (opt-in checkbox on the restart dialog).

## Bump the kernel by hand (what the agent automates)

```bash
echo v7.1 > kernel/BASE          # pin a newer upstream stable tag
# (add/refresh kernel/patches/*.patch if our deltas need rebasing)
git commit -am "kernel: bump to v7.1"   # CI builds + publishes; then sign the manifest
```
