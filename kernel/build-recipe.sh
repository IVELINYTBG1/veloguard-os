#!/usr/bin/env bash
#
# build-recipe.sh — turn {BASE tag + our config fragments + patches} into a
# prebuilt VeloGuardOS kernel package. Runs in an Arch container (CI), where
# makepkg + the toolchain exist. Emits:
#   out/linux-veloguard-<ver>-1-x86_64.pkg.tar.zst   the installable package
#   out/kernel-manifest.json                          the 'kernel' block to sign
#
# It does NOT sign anything — signing the manifest uses the offline release key
# (see ../keys/SIGNING.md), done after this publishes the artifact.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
OUT="${OUT:-$REPO/out}"
FRAG="$REPO/veloguard/kernel"

BASE="$(tr -d ' \t\n\r' < "$HERE/BASE")"     # e.g. v7.0
[ -n "$BASE" ] || { echo "kernel/BASE is empty" >&2; exit 1; }
KVER="${BASE#v}"                              # 7.0
echo "==> VeloGuardOS kernel: base=$BASE  pkgver=$KVER"

for f in base desktop hardware; do
  [ -f "$FRAG/veloguardos-$f.config" ] || { echo "missing fragment veloguardos-$f.config" >&2; exit 1; }
done

mkdir -p "$OUT"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# --- stage the build context next to a version-injected PKGBUILD -----------
sed "s/__PKGVER__/${KVER}/g" "$HERE/PKGBUILD" > "$WORK/PKGBUILD"
cp "$FRAG/veloguardos-base.config"     "$WORK/"
cp "$FRAG/veloguardos-desktop.config"  "$WORK/"
cp "$FRAG/veloguardos-hardware.config" "$WORK/"
# our patch series (sorted) — none yet is fine
shopt -s nullglob
for p in "$HERE"/patches/*.patch; do cp "$p" "$WORK/"; done
shopt -u nullglob

# --- source tarball: shallow git archive of the BASE tag from Linus's tree --
# We pull from torvalds/linux (the tree the agent compares against), not the
# kernel.org tarball CDN — one source of truth, and the tag is guaranteed to
# exist there. --depth 1 keeps it to a single snapshot, not 6.4 GB of history.
echo "==> fetching upstream $BASE from torvalds/linux (shallow)…"
git clone --quiet --depth 1 --branch "$BASE" https://github.com/torvalds/linux "$WORK/linux-src"
( cd "$WORK/linux-src" && git archive --format=tar --prefix="linux-${KVER}/" HEAD ) > "$WORK/linux-${KVER}.tar"
rm -rf "$WORK/linux-src"

# --- build (this compiles the kernel — long) -------------------------------
cd "$WORK"
echo "==> makepkg…"
makepkg -f --noconfirm --skipinteg --nocheck

PKG="$(ls -1 "$WORK"/linux-veloguard-*.pkg.tar.zst 2>/dev/null | head -1)"
[ -n "$PKG" ] || { echo "makepkg produced no package" >&2; exit 1; }
cp -f "$PKG" "$OUT/"
PKGNAME="$(basename "$PKG")"
PKGOUT="$OUT/$PKGNAME"
SHA="$(sha256sum "$PKGOUT" | cut -d' ' -f1)"

echo "==> built  : $PKGOUT"
echo "==> sha256 : $SHA"

# --- emit the signed-updater 'kernel' manifest block -----------------------
cat > "$OUT/kernel-manifest.json" <<EOF
{
  "version": "${KVER}",
  "base_tag": "${BASE}",
  "package": "${PKGNAME}",
  "artifact": "https://github.com/IVELINYTBG1/veloguard-os/releases/latest/download/${PKGNAME}",
  "sha256": "${SHA}"
}
EOF
echo "==> wrote  : $OUT/kernel-manifest.json"
echo "==> next   : publish $PKGNAME to a Release, fold kernel-manifest.json into manifest.json, sign (offline key)"
