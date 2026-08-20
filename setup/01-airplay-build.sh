#!/usr/bin/env bash
# Stage 1: build Shairport Sync (AirPlay 2 + metadata + D-Bus control) and NQPTP.
# Takes ~25-30 minutes on a Pi 3B. Idempotent - reruns just update and rebuild.
set -euo pipefail

SRC_DIR=/usr/local/src

install_dependencies() {
  apt-get update
  apt-get install -y --no-install-recommends \
    build-essential git autoconf automake libtool \
    libpopt-dev libconfig-dev libasound2-dev avahi-daemon libavahi-client-dev \
    libssl-dev libsoxr-dev libplist-dev libsodium-dev uuid-dev libgcrypt-dev \
    xxd libplist-utils libavutil-dev libavcodec-dev libavformat-dev \
    libglib2.0-dev alsa-utils curl
  apt-get install -y --no-install-recommends systemd-dev 2>/dev/null || true
}

fetch_source() {
  local url=$1 dir=$2

  if [ -d "$dir/.git" ]; then
    git -C "$dir" pull --ff-only
  else
    git clone "$url" "$dir"
  fi
}

build_nqptp() {
  fetch_source https://github.com/mikebrady/nqptp.git "$SRC_DIR/nqptp"
  cd "$SRC_DIR/nqptp"
  autoreconf -fi
  ./configure --with-systemd-startup
  make -j"$(nproc)"
  make install

  systemctl enable nqptp
  systemctl restart nqptp
}

build_shairport_sync() {
  fetch_source https://github.com/mikebrady/shairport-sync.git "$SRC_DIR/shairport-sync"
  cd "$SRC_DIR/shairport-sync"
  autoreconf -fi
  ./configure --sysconfdir=/etc --with-alsa --with-soxr --with-avahi \
    --with-ssl=openssl --with-systemd-startup --with-airplay-2 \
    --with-metadata --with-dbus-interface
  make -j"$(nproc)"
  make install

  systemctl enable shairport-sync
}

install_dependencies
build_nqptp
build_shairport_sync

echo "Stage 1 done: $(shairport-sync -V)"
