#!/usr/bin/env bash
# Persist the wireless regulatory domain from the timezone country (fixes weak/
# capped Wi-Fi). Derived from Omarchy install/hardware/set-wireless-regdom.sh.
regdom_file=/etc/conf.d/wireless-regdom
[[ -f $regdom_file ]] || : > "$regdom_file"

grep -q '^WIRELESS_REGDOM=' "$regdom_file" && exit 0

timezone=""
if [[ -e /etc/localtime ]]; then
  timezone=$(readlink -f /etc/localtime || true)
  timezone=${timezone#/usr/share/zoneinfo/}
fi

country="${timezone%%/*}"
zone_tab=/usr/share/zoneinfo/zone.tab
if [[ ! $country =~ ^[A-Z]{2}$ && -n $timezone && -f $zone_tab ]]; then
  country=$(awk -v tz="$timezone" '$3 == tz {print $1; exit}' "$zone_tab")
fi

if [[ $country =~ ^[A-Z]{2}$ ]]; then
  echo "WIRELESS_REGDOM=\"$country\"" >> "$regdom_file"
fi
