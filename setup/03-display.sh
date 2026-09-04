#!/usr/bin/env bash
# Stage 3: Waveshare 3.5" LCD (C) driver, fonts, and the pi-speakers services.
# App files must already be in /opt/pi-speakers (install.sh handles that).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG=/boot/firmware/config.txt
CMDLINE=/boot/firmware/cmdline.txt

install_packages() {
  apt-get install -y --no-install-recommends \
    python3-pil python3-numpy python3-evdev fonts-dejavu-core fonts-vlgothic unzip
}

install_fonts() {
  install -d /opt/pi-speakers/fonts

  if [ ! -f /opt/pi-speakers/fonts/VT323.ttf ]; then
    curl -sfL -o /opt/pi-speakers/fonts/VT323.ttf \
      "https://github.com/google/fonts/raw/main/ofl/vt323/VT323-Regular.ttf" \
      || echo "WARN: VT323 download failed - Retro TV theme falls back to DejaVu"
  fi

  [ -f /opt/pi-speakers/fonts/DotGothic16.ttf ] || curl -sfL \
    -o /opt/pi-speakers/fonts/DotGothic16.ttf \
    "https://github.com/google/fonts/raw/main/ofl/dotgothic16/DotGothic16-Regular.ttf" \
    || echo "WARN: DotGothic16 download failed - Retro TV Japanese falls back to DejaVu"

  for weight in Bold Medium; do
    [ -f "/opt/pi-speakers/fonts/Rajdhani-$weight.ttf" ] || curl -sfL \
      -o "/opt/pi-speakers/fonts/Rajdhani-$weight.ttf" \
      "https://github.com/google/fonts/raw/main/ofl/rajdhani/Rajdhani-$weight.ttf" \
      || echo "WARN: Rajdhani download failed - Neon theme falls back to DejaVu"
  done

  if [ ! -f /opt/pi-speakers/fonts/monofonto.otf ]; then
    curl -sfL -A "Mozilla/5.0" -o /tmp/monofonto.zip "https://dl.dafont.com/dl/?f=monofonto" \
      && unzip -o -q /tmp/monofonto.zip -d /tmp/monofonto \
      && find /tmp/monofonto -name "*.otf" -exec cp {} /opt/pi-speakers/fonts/monofonto.otf \; \
      || echo "WARN: Monofonto download failed - Terminal theme falls back to DejaVu"
  fi
}

install_display_driver() {
  if [ "${DISPLAY_KIND:-spi}" = "hdmi" ]; then
    # HDMI panel: KMS reads the mode from EDID; nothing to overlay.
    grep -q consoleblank "$CMDLINE" || sed -i "1s/$/ consoleblank=0/" "$CMDLINE"
    systemctl mask userconfig 2>/dev/null || true
    return
  fi

  install -m 644 "$HERE/../assets/overlays/waveshare35c.dtbo" /boot/firmware/overlays/

  grep -q "^dtparam=spi=on" "$CONFIG" || echo "dtparam=spi=on" >> "$CONFIG"
  grep -q "dtoverlay=waveshare35c" "$CONFIG" || {
    printf "\n# Waveshare 3.5in LCD (C) - 24MHz keeps the touch chip alive; rotate=270 for the case\ndtoverlay=waveshare35c:rotate=90,speed=24000000\n" >> "$CONFIG"
  }

  # never blank the panel, and silence the console first-boot wizard it exposes
  grep -q consoleblank "$CMDLINE" || sed -i "1s/$/ consoleblank=0/" "$CMDLINE"
  # panel is mounted upside-down in the case; the overlay cannot flip it
  grep -q "fbcon=rotate" "$CMDLINE" || sed -i "1s/$/ fbcon=rotate:2/" "$CMDLINE"
  systemctl mask userconfig 2>/dev/null || true
}

install_services() {
  echo "d /run/pi-speakers 0777 root root -" > /etc/tmpfiles.d/pi-speakers.conf
  systemd-tmpfiles --create
  install -d -m 777 /var/lib/pi-speakers

  cat > /etc/systemd/system/pi-speakers-web.service <<'EOF'
[Unit]
Description=Pi Speakers web control panel
After=network.target

[Service]
ExecStart=/usr/bin/python3 /opt/pi-speakers/webui.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/pi-speakers-nowplaying.service <<'EOF'
[Unit]
Description=Shairport metadata to nowplaying.json
After=shairport-sync.service

[Service]
ExecStart=/usr/bin/python3 /opt/pi-speakers/nowplaying.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/pi-speakers-display.service <<'EOF'
[Unit]
Description=Pi Speakers LCD dashboard
After=network.target

[Service]
ExecStartPre=/bin/sh -c "echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true"
ExecStart=/usr/bin/python3 /opt/pi-speakers/dashboard.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable pi-speakers-web pi-speakers-nowplaying pi-speakers-display
  systemctl restart pi-speakers-web pi-speakers-nowplaying
}

install_packages
install_fonts
install_display_driver
install_services

echo "Stage 3 done: display driver staged (takes effect after reboot), services enabled"
