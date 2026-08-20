#!/usr/bin/env bash
# One-shot installer. On a freshly imaged Pi (see sdcard/):
#
#   git clone https://github.com/psa1302/pi_airplay.git
#   cd pi_airplay && sudo bash install.sh
#   sudo reboot
#
# Idempotent - rerun any time to update. The Shairport build takes ~25 min.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

require_root() {
  [ "$(id -u)" -eq 0 ] || { echo "Run with sudo: sudo bash install.sh" >&2; exit 1; }
}

refuse_wrong_machine() {
  [ "$(hostname)" = "airplay-pi" ] && return
  [ "${FORCE:-0}" = "1" ] && return

  echo "This machine is '$(hostname)', not 'airplay-pi' - refusing to run." >&2
  echo "If this really is the speaker Pi, re-run with FORCE=1." >&2
  exit 1
}

deploy_app_files() {
  install -d /opt/pi-speakers
  install -m 644 "$HERE"/webui/webui.py "$HERE"/webui/index.html /opt/pi-speakers/
  install -m 644 "$HERE"/display/dashboard.py "$HERE"/display/nowplaying.py /opt/pi-speakers/
  install -m 755 "$HERE"/display/spotify-event.sh /opt/pi-speakers/

  install -m 644 "$HERE"/assets/spotify-logo.png /opt/pi-speakers/
  for mascot in "$HERE"/assets/mascots/*.png; do
    [ -f "$mascot" ] && install -m 644 "$mascot" "/opt/pi-speakers/$(basename "$mascot")"
  done
}

report() {
  echo
  echo "=== Install complete ==="
  echo "AirPlay:   $(systemctl is-active shairport-sync 2>/dev/null || true)  ($(shairport-sync -V 2>/dev/null || true))"
  echo "Spotify:   $(systemctl is-active raspotify 2>/dev/null || true)"
  echo "Bluetooth: $(systemctl is-active bluealsa-aplay 2>/dev/null || true)"
  echo "Web UI:    $(systemctl is-active pi-speakers-web 2>/dev/null || true)  ->  http://$(hostname).local/"
  echo
  echo "Reboot now to bring up the LCD:  sudo reboot"
  echo "Optional: drop a mascot image at /opt/pi-speakers/mascot.png (Terminal theme)."
}

require_root
refuse_wrong_machine
rfkill unblock wifi bluetooth 2>/dev/null || true
deploy_app_files
bash "$HERE/setup/01-airplay-build.sh"
bash "$HERE/setup/02-audio-stack.sh"
bash "$HERE/setup/03-display.sh"
report
