# VeloGuardOS kernel patches

Drop `*.patch` files here (one per logical change, `git format-patch` style).
They are applied with `patch -Np1` in the upstream source tree, in **sorted
order**, by `../PKGBUILD`'s `prepare()` — before the config merge.

There are **none yet**: VeloGuardOS currently customizes the kernel purely
through config fragments (`../../veloguard/kernel/veloguardos-*.config`), not
source changes. When we start carrying real source deltas (a custom LSM, the
VeloGuard guard hooks, etc.), they live here as a numbered series:

```
0001-veloguard-lsm-skeleton.patch
0002-binfmt-misc-default-on.patch
```

Keep them rebased on the tag named in `../BASE`. The kernel-sync agent's job is
to re-apply (and, on conflict, fix) this series whenever `BASE` moves forward.
