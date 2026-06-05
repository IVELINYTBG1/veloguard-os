#!/usr/bin/env bash
#
# VeloGuardOS — AI semantic memory on a COMPATIBLE Python.
#
# ChromaDB doesn't ship wheels for the newest Python yet, so instead of fighting
# the system interpreter we build a dedicated venv on a known-good Python
# (3.11–3.13) and install ChromaDB there. The `bin/veloguard` launcher then runs
# the whole guard under that venv automatically. The SQLite trust store works
# regardless; this just adds semantic recall.
#
#   ./install-ai-memory.sh
#
set -euo pipefail
say()  { printf '\033[1;36m[veloguard]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[veloguard]\033[0m %s\n' "$*" >&2; }

HOME_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VELOGUARD_VENV:-$HOME_DIR/.venv}"

# 1. find a ChromaDB-compatible interpreter; install one if none present.
PY=""
for v in python3.13 python3.12 python3.11; do
  command -v "$v" >/dev/null && { PY="$v"; break; }
done
if [ -z "$PY" ]; then
  say "no compatible Python (3.11–3.13) found — installing one"
  if   command -v dnf     >/dev/null; then sudo dnf install -y python3.12 && PY=python3.12
  elif command -v apt-get >/dev/null; then sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv && PY=python3.12
  elif command -v pacman  >/dev/null; then warn "install a 3.11–3.13 Python (pyenv/AUR), then re-run"; exit 1
  fi
fi
[ -n "$PY" ] || { warn "couldn't obtain a compatible Python"; exit 1; }
say "using $($PY --version 2>&1) → venv at $VENV"

# 2. build the venv and install ChromaDB into it.
"$PY" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
say "installing chromadb (this pulls a few hundred MB)…"
if "$VENV/bin/pip" install --quiet chromadb; then
  "$VENV/bin/python" -c "import chromadb; print('  chromadb', chromadb.__version__, 'OK')"
  say "semantic memory ready. Run the guard with:  bin/veloguard ..."
else
  warn "chromadb install failed; the SQLite trust store still works."
fi
