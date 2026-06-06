#!/usr/bin/env bash
#
# VeloGuardOS — automated data-broker opt-out (the user's OWN data only).
# Sends GDPR/CCPA-style deletion/opt-out requests on a 12h timer. Safe to run
# unconfigured: it no-ops until the user sets up their identity + broker list.
#
#   identity file (0600):   /etc/veloguard/privacy/identity      -> EMAIL=you@x.com
#   broker endpoints:       /etc/veloguard/privacy/brokers.list  -> name<TAB>url
#   log (redacted):         /var/log/veloguard/privacy-optout.log
#
set -uo pipefail
DIR="${VELOGUARD_PRIVACY_DIR:-/etc/veloguard/privacy}"
ID_FILE="$DIR/identity"
BROKERS="$DIR/brokers.list"
LOG="${VELOGUARD_PRIVACY_LOG:-/var/log/veloguard/privacy-optout.log}"
mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }

# Not configured yet → nothing to do (keeps the timer quiet by default).
[ -f "$ID_FILE" ] && [ -f "$BROKERS" ] || { log "not configured; skipping"; exit 0; }

# Refuse to read identity unless it is 0600 (don't leak via loose perms).
perm="$(stat -c '%a' "$ID_FILE" 2>/dev/null || echo 000)"
[ "$perm" = "600" ] || { log "REFUSED: $ID_FILE is $perm, must be 600"; exit 1; }

# shellcheck disable=SC1090
EMAIL=""; . "$ID_FILE"
[ -n "$EMAIL" ] || { log "no EMAIL in identity; skipping"; exit 0; }

# Offline? Fail gracefully (don't error the timer).
if ! curl -sf --max-time 8 -o /dev/null https://www.cloudflare.com/cdn-cgi/trace; then
  log "offline; will retry next run"; exit 0
fi

ok=0; fail=0
# brokers.list: "Name<TAB>https://endpoint"  (lines starting with # are ignored)
while IFS=$'\t' read -r name url; do
  [ -z "${name:-}" ] && continue
  case "$name" in \#*) continue;; esac
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 \
          -X POST --data-urlencode "email=${EMAIL}" \
          --data-urlencode "request=opt-out-and-delete" "$url" 2>/dev/null)"
  if [ "${code:-000}" -ge 200 ] && [ "${code:-000}" -lt 400 ]; then
    log "OK   $name (HTTP $code)"; ok=$((ok+1))
  else
    log "FAIL $name (HTTP ${code:-err})"; fail=$((fail+1))
  fi
done < "$BROKERS"

# Log a summary — note: the email is NEVER written to the log.
log "run complete: $ok ok, $fail failed across $(grep -cvE '^\s*#|^\s*$' "$BROKERS") brokers"
exit 0
