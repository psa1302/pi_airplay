#!/usr/bin/env bash
# Run on the Mac AFTER flashing Raspberry Pi OS Lite (64-bit, Trixie) with
# Raspberry Pi Imager, while the card's "bootfs" volume is still mounted:
#
#   ./prepare-sd.sh "MyWifi" "wifi-password" [country] [timezone] \
#                   [hostname] [speaker-name] [audio-card] [display]
#
# Writes the cloud-init first-boot config (hostname, user `pi` with a random
# printed password + SSH key auth, WiFi) and a device profile that install.sh
# reads. Defaults describe the original Pi 3B speaker; for the Pi 4B with the
# HDMI panel and onboard jack:
#
#   ./prepare-sd.sh "MyWifi" "pass" IN Asia/Kolkata \
#                   airplay-pi2 "Pi Speakers 2" Headphones hdmi
set -euo pipefail

SSID="${1:?usage: prepare-sd.sh SSID PSK [country] [timezone] [hostname] [speaker-name] [audio-card] [display]}"
PSK="${2:?usage: prepare-sd.sh SSID PSK [country] [timezone] [hostname] [speaker-name] [audio-card] [display]}"
COUNTRY="${3:-IN}"
TIMEZONE="${4:-Asia/Kolkata}"
SPEAKER_HOSTNAME="${5:-airplay-pi}"
SPEAKER_NAME="${6:-Pi Speakers}"
AUDIO_CARD="${7:-Creation}"
DISPLAY_KIND="${8:-spi}"

HERE="$(cd "$(dirname "$0")" && pwd)"
BOOT=/Volumes/bootfs

[ -d "$BOOT" ] || { echo "No $BOOT - is the flashed card mounted?" >&2; exit 1; }

SSH_KEY="$(cat "$(ls ~/.ssh/id_*.pub | head -1)")"
PASSWORD="$(openssl rand -hex 8)"

sed -e "s|{{PASSWORD}}|$PASSWORD|" \
    -e "s|{{SSH_KEY}}|$SSH_KEY|" \
    -e "s|{{TIMEZONE}}|$TIMEZONE|" \
    -e "s|{{HOSTNAME}}|$SPEAKER_HOSTNAME|" \
    "$HERE/user-data.template" > "$BOOT/user-data"

cat > "$BOOT/pi-speakers.conf" <<EOF
SPEAKER_HOSTNAME="$SPEAKER_HOSTNAME"
AIRPLAY_NAME="$SPEAKER_NAME"
AUDIO_CARD="$AUDIO_CARD"
DISPLAY_KIND="$DISPLAY_KIND"
EOF

sed -e "s|{{WIFI_SSID}}|$SSID|" \
    -e "s|{{WIFI_PSK}}|$PSK|" \
    -e "s|{{WIFI_COUNTRY}}|$COUNTRY|" \
    "$HERE/network-config.template" > "$BOOT/network-config"

# raspbian's own every-boot mechanism for enabling sshd - cloud-init's ssh
# module is per-instance and does not reliably run on these images
touch "$BOOT/ssh"

cat > "$BOOT/meta-data" <<EOF
dsmode: local
instance_id: $SPEAKER_HOSTNAME-$(date +%s)
EOF

diskutil eject "$BOOT" >/dev/null || true

echo "Card ready. Boot the Pi (ethernet recommended for first boot), then:"
echo "  ssh pi@$SPEAKER_HOSTNAME.local        # key auth; password fallback: $PASSWORD"
echo "  git clone https://github.com/psa1302/pi_airplay.git"
echo "  cd pi_airplay && sudo bash install.sh && sudo reboot"
echo
echo "Note: the Pi 3B only sees 2.4 GHz WiFi. WiFi may need one manual kick"
echo "after install if rfkill-blocked: sudo raspi-config nonint do_wifi_country $COUNTRY"
