# Kernel-sync agent contract

The job: **keep VeloGuardOS's kernel current with Linus's latest stable, prove it
still builds with our delta, and ship it** — the "compare our kernel to Linus's"
agent. It works on the *delta* in this repo; it never commits kernel source.

## Inputs it reads
- `kernel/BASE` — the upstream tag we're pinned to (e.g. `v7.0`).
- `kernel/patches/*.patch` — our source deltas (none yet).
- `../veloguard/kernel/veloguardos-*.config` — our config fragments.
- Linus's tree at `/home/nodevortex/VeloGuardOS` (`origin = torvalds/linux`).

## The loop

1. **Compare.** Fetch Linus and find the latest stable tag:
   ```bash
   cd /home/nodevortex/VeloGuardOS && git fetch --tags --prune origin
   latest=$(git tag --list 'v*' --sort=-v:refname | grep -vE '\-rc' | head -1)
   ```
   If `latest` == `kernel/BASE`, nothing to do.

2. **Validate the delta against the new tag** (catches dropped config symbols and
   patch/build breaks *before* shipping). This is what `veloguard-kernel-sync`
   does — full compile, out-of-tree, non-destructive flags available:
   ```bash
   veloguard/bin/veloguard-kernel-sync --tag "$latest"        # checkout + config + full build
   # parse the trailing  VGKSYNC_JSON: {...}
   ```
   - `config:"dropped"` → our `CONFIG_` symbols didn't survive `olddefconfig`
     (unmet `depends`/`select` upstream). Inspect each in the new tree, explain,
     fix the fragment. **Don't ship a silently-degraded config.**
   - `build:"failed"` → read the first compile error; usually a renamed/removed
     upstream symbol or an API change a patch touches. Fix the fragment/patch.
   - `build:"ok"` → proceed.

3. **Bump + push** (this triggers `build-kernel.yml`):
   ```bash
   echo "$latest" > kernel/BASE          # in the veloguard-os repo
   # refresh kernel/patches/* if a rebase was needed
   git commit -am "kernel: track $latest"
   git push                               # CI builds the package, publishes a Release
   ```

4. **Hand off to the human for the trust step.** CI emits `out/kernel-manifest.json`
   (real sha256). Fold its block into `manifest.json`, then **sign with the
   offline release key** (`keys/SIGNING.md`) and push. The agent must **not** hold
   the signing key.

After that, users' `veloguard-update.timer` stages the new signed kernel in the
background and offers it on the next restart (opt-in checkbox → apply on reboot).

## Guardrails
- Never bypass `veloguard-kernel-sync`'s dirty-tree refusal or compile by hand.
- Never `git push` a `BASE` bump whose validation `build` wasn't `ok`.
- Never sign or fabricate `manifest.json.sig`.
