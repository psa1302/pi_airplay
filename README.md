# Pi Speakers

A Raspberry Pi 3B turned into a proper wireless speaker: **AirPlay 2**,
**Spotify Connect**, and **Bluetooth**, all flowing through a shared
**bass/treble equaliser**, controlled from a clean **web UI**, with a themeable
**3.5" LCD dashboard** (clock, weather, now playing) on the front.

## Hardware

- Raspberry Pi 3B (v1.2) + Raspberry Pi OS Lite 64-bit (Trixie)
- USB sound card (CableCreation / any C-Media class DAC) → powered speakers
  into its headphone jack
- Waveshare 3.5" RPi LCD (C) on GPIO pins 1–26 (SPI, XPT2046 touch)
- A solid 5V/2.5A+ power supply — undervoltage causes choppy USB audio

## Fresh install (three steps)

**1. Flash the SD card** with Raspberry Pi Imager (Raspberry Pi OS Lite
64-bit), no customisation needed. With the card still mounted:

```sh
cd sdcard && ./prepare-sd.sh "YourWifi" "wifi-password" [country] [timezone]
```

This writes the first-boot config (hostname `airplay-pi`, user `pi` with a
random printed password + your SSH key, WiFi). It uses cloud-init `bootcmd` —
see the template for why the obvious approach doesn't work on these images.

**2. Boot the Pi** (ethernet recommended for the first boot) and install:

```sh
ssh pi@airplay-pi.local
git clone https://github.com/psa1302/pi_airplay.git
cd pi_airplay && sudo bash install.sh     # ~30 min, mostly the AirPlay build
sudo reboot
```

**3. Done.** "Pi Speakers" appears in AirPlay and Spotify device lists and as
a Bluetooth speaker; the web UI is at `http://airplay-pi.local/`; the LCD
shows the dashboard. `install.sh` is idempotent — rerun it to update.

## What's inside

| Piece | What it does |
|---|---|
| `setup/01-airplay-build.sh` | Builds Shairport Sync (AirPlay 2 + metadata + D-Bus control) and NQPTP from source |
| `setup/02-audio-stack.sh` | ALSA pipeline (source → alsaequal EQ → dmix → USB DAC), Spotify Connect (raspotify), Bluetooth sink (bluez-alsa, auto-pairing) |
| `setup/03-display.sh` | LCD overlay + config, CRT fonts, systemd services |
| `webui/` | Control panel on port 80: EQ sliders, WiFi manager, theme picker, transport, now playing. Light/dark aware. |
| `display/` | LCD dashboard with four themes; hourly Japanese time announcements (pips + processed Kyoko voice from `assets/voice/`) with a speech-ripple animation; N4 vocabulary cards every quarter hour (`vocab.py`: passive spaced repetition, Kyoko clips from `assets/vocab/`) — Classic (auto day/night), Terminal (Fallout-style: scanlines, glitch, boot sequence, marquee now-playing with progress bar, vitals panel, per-theme mascots in `assets/mascots/`), Neon (glitch-storm intro, recolored glitching mascot), Retro TV (static tune-in intro, astronaut mascot). All themes share the HUD/music-box structure; now-playing state comes from Shairport's D-Bus (see CHANGELOG) |
| `sdcard/` | First-boot templates + the Mac-side prep script |
| `assets/vocab/` | The Shin Kanzen Master N4 list merged with hand-written, linted example sentences (`build.py` → `n4.json`); `generate.sh` renders the word + sentence clips on a Mac (kept out of git) |

## Hard-won gotchas (why this repo looks the way it does)

- **Trixie images ignore `custom.toml`** and don't reliably re-run cloud-init
  per-instance modules; the shipped `pi` account has a nologin shell. Hence
  the unconditional `bootcmd` user setup in `sdcard/user-data.template`.
- **WiFi and Bluetooth boot rfkill-blocked** until a regulatory country is
  set (`raspi-config nonint do_wifi_country XX`).
- **alsaequal needs a `plug` between it and dmix** or you get
  "Slave PCM not usable".
- **raspotify ships `ProtectSystem=strict`** — without the ReadWritePaths
  override it crashes trying to open the EQ.
- **The LCD (C) must run SPI at 24 MHz, not 115** — at high speed, a power-up
  latches the touch controller's interrupt line dead. Only a **cold power
  cycle** (not a reboot) resets the chip.
- **The LCD framebuffer number changes between boots** — the dashboard finds
  it by driver name.
- **`consoleblank=0`** or the kernel blanks the panel after 10 minutes with
  no way to wake it headlessly; `userconfig.service` is masked because its
  console wizard draws over the dashboard.
- Choppy audio = check `vcgencmd get_throttled` — it's the power supply, not
  the CPU.
- **WiFi power save makes the Pi unreachable over IPv4** from any device whose
  ARP cache expired — the napping radio misses broadcast ARP and mDNS while
  cached/unicast traffic (and IPv6 with a warm neighbor entry) keeps working.
  The installer now disables it (`wifi.powersave = 2`).
- **Even with power save off, the Pi 3B wifi stops *receiving* broadcast
  frames hours after association**: the in-firmware WPA supplicant botches
  the AP's group-key rekey, after which the chip can't decrypt
  broadcast/multicast (unicast keeps working — same symptom, all devices at
  once, ARP and mDNS dead). Fix: `options brcmfmac roamoff=1
  feature_disable=0x282000` in `/etc/modprobe.d/brcmfmac.conf` (what newer
  RPi firmware packages now ship by default). The
  `pi-speakers-net-announce` service (gratuitous ARP every 10s + avahi kick)
  stays as belt-and-braces.

## Everyday things

- **Rename the speaker:** `AIRPLAY_NAME="New Name" sudo -E bash setup/02-audio-stack.sh`
- **Logs:** `journalctl -u shairport-sync -u raspotify -u pi-speakers-display -f`
- **EQ from the shell:** `amixer -D equal scontrols` (0–100, flat = 66)
- **Vocabulary audio:** `assets/vocab/generate.sh` on the Mac (needs the Kyoko
  voice + ffmpeg, resumable), then rsync `assets/vocab/audio/` to
  `/opt/pi-speakers/vocab/audio/`. `echo next > /run/pi-speakers/vocab-cmd`
  shows the next card immediately; `again` replays the current one.
- **Known open issue:** AirPlay transport commands (play/pause/next from the
  web UI) reach Shairport's D-Bus interface but the sender ignores them on
  most sessions; parked.
