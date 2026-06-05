#!/usr/bin/env bash
# VeloGuard vertical-slice demo. Safe to run as a normal user: everything is
# dry-run unless you add --apply. Shows AI intent -> guard -> kernel path.
set -euo pipefail
cd "$(dirname "$0")"

run() { echo; echo "\$ python3 -m guardd $*"; python3 -m guardd "$@" || true; }

echo "### 1. Set up the nft table (dry-run shows the kernel ops)"
run --setup

echo; echo "### 2. A normal block — needs consent, so auto-approve with --yes"
run --yes "block the scanner at 203.0.113.10"

echo; echo "### 3. The guard refusing to lock you out of your own box"
run --yes "block 127.0.0.1"

echo; echo "### 4. The guard refusing your LAN gateway"
run --yes "block 192.168.1.1"

echo; echo "### 5. An intent it can't map to any action"
run "tell me a joke"

echo; echo "### 6. The audit trail (every decision, allowed or not)"
echo "\$ tail -n 6 audit.log"; tail -n 6 audit.log 2>/dev/null || echo "(no audit.log yet)"
