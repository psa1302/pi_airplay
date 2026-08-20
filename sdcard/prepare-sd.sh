#!/usr/bin/env bash
# Run on the Mac AFTER flashing Raspberry Pi OS Lite (64-bit, Trixie) with
# Raspberry Pi Imager, while the card's "bootfs" volume is still mounted:
#
#   ./prepare-sd.sh "MyWifi" "wifi-password" [country] [timezone]
#
# Writes the cloud-init first-boot config: hostname airplay-pi, user `pi`
# (random password, printed below; SSH key auth from this machine), WiFi.
set -euo pipefail

SSID="${1:?usage: prepare-sd.sh SSID PSK [country] [timezone]}"
PSK="${2:?usage: prepare-sd.sh SSID PSK [country] [timezone]}"
COUNTRY="${3:-IN}"
TIMEZONE="${4:-Asia/Kolkata}"

HERE="$(cd "$(dirname "$0")" && pwd)"
BOOT=/Volumes/bootfs

[ -d "$BOOT" ] || { echo "No $BOOT - is the flashed card mounted?" >&2; exit 1; }

SSH_KEY="$(cat "$(ls ~/.ssh/id_*.pub | head -1)")"
PASSWORD="$(openssl rand -hex 8)"

sed -e "s|{{PASSWORD}}|$PASSWORD|" \
    -e "s|{{SSH_KEY}}|$SSH_KEY|" \
    -e "s|{{TIMEZONE}}|$TIMEZONE|" \
    "$HERE/user-data.template" > "$BOOT/user-data"

sed -e "s|{{WIFI_SSID}}|$SSID|" \
    -e "s|{{WIFI_PSK}}|$PSK|" \
    -e "s|{{WIFI_COUNTRY}}|$COUNTRY|" \
    "$HERE/network-config.template" > "$BOOT/network-config"

cat > "$BOOT/meta-data" <<EOF
dsmode: local
instance_id: airplay-pi-$(date +%s)
EOF

diskutil eject "$BOOT" >/dev/null || true

echo "Card ready. Boot the Pi (ethernet recommended for first boot), then:"
echo "  ssh pi@airplay-pi.local        # key auth; password fallback: $PASSWORD"
echo "  git clone https://github.com/psa1302/pi_airplay.git"
echo "  cd pi_airplay && sudo bash install.sh && sudo reboot"
echo
echo "Note: the Pi 3B only sees 2.4 GHz WiFi. WiFi may need one manual kick"
echo "after install if rfkill-blocked: sudo raspi-config nonint do_wifi_country $COUNTRY"
