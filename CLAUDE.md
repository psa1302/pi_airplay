# Pi Speakers — session notes

A Raspberry Pi 3B wireless speaker (AirPlay 2 + Spotify Connect + Bluetooth →
shared EQ → USB DAC) with a web UI and a themeable 3.5" LCD dashboard. Read
README.md for architecture and the hard-won gotchas; CHANGELOG.md for history.

## The devices

- Pi Speakers (3B): hostname `airplay-pi`, user `pi`, key auth
  (`ssh -o BatchMode=yes` works). mDNS usually resolves; when it doesn't, use
  the IP (192.168.31.199 as of Aug 2026, DHCP) with
  `-o HostKeyAlias=airplay-pi.local`.
- Pi Speakers 2 (4B): hostname `airplay-pi2` (192.168.31.178), 640x480 HDMI
  panel + USB capacitive touch, onboard jack or the shared USB DAC. Device
  differences live in `/boot/firmware/pi-speakers.conf` (written by
  sdcard/prepare-sd.sh, read by install.sh) - never hardcode them.
- **There is another Pi on this network (a printer server). Never touch it.**
- The Pi runs the code in `/opt/pi-speakers/` — the repo is the source of
  truth, but the device is updated by direct deploy, not git pull.

## Deploy loop (the workflow used for all iteration)

1. Patch the file locally (python heredoc with assert-guarded replaces),
   then `ast.parse` it (Python) or eyeball (HTML/JS).
2. `scp` to `pi@…:/tmp/`, then `sudo mv` into `/opt/pi-speakers/`.
3. `sudo systemctl restart <service>` and check `systemctl is-active`.

Services: `pi-speakers-display` (dashboard.py), `pi-speakers-web` (webui.py +
index.html, port 80), `pi-speakers-nowplaying` (nowplaying.py),
`pi-speakers-net-announce` (gratuitous-ARP beacon — the wifi firmware loses
broadcast RX; without it the IP goes dark for every device, see README),
`pi-speakers-dac-level` (oneshot: pins the USB DAC to 100% once it enumerates —
gain staging is DAC at full scale, speaker knob as the ceiling; alsactl alone
restores too early for USB), plus `shairport-sync`, `raspotify`,
`bluealsa-aplay`.

The user iterates live on the device — small change, deploy, they look at the
LCD or browser, next tweak. Reverts are common and expected. Be quick.

## Git / release conventions

- Work is committed in batches only when asked ("commit this much",
  "release cycle"): feature branch → conventional commit (no AI references,
  no Co-Authored-By) → CHANGELOG.md version entry → `merge --ff-only` into
  main → push both branches. See global CLAUDE.md for commit style.
- **The repo must stay private**: Monofonto's licence forbids redistribution,
  the mascots are game art, and the Spotify logo is bundled.

## Where things live

- State files (web UI ↔ dashboard): `/var/lib/pi-speakers/` — `theme`
  (auto/light/dark), `skin` (classic/terminal/neon/retrotv), `chime`,
  `quiet`, `quiet-range` ("start-end" hours), `announce-volume` (0–100),
  `vocab` (on/off), `vocab-interval` (15/30/60), `vocab-new-per-day`,
  `vocab-srs.json` (per-word step/due/seen). Missing file = default on.
- Runtime: `/run/pi-speakers/` — `nowplaying.json` (written by nowplaying.py,
  which arbitrates Shairport D-Bus vs `spotify.json` from the raspotify event
  hook), `chime.wav` (generated at dashboard startup), `announce` (write a
  wav path here and the dashboard plays it with the speech ripple),
  `vocab.json` (the current card, published by the dashboard), `vocab-cmd`
  (`again` / `next`, consumed by the dashboard).
- Vocabulary: `display/vocab.py` (schedule + SRS, imported by dashboard.py
  and webui.py — both live flat in /opt/pi-speakers/), data in
  `/opt/pi-speakers/vocab/n4.json` + `audio/NNNN.wav` (word, 3 s, sentence;
  22 kHz mono, ~180 MB, gitignored — rendered by `assets/vocab/generate.sh`
  and rsync'd, see README). Sentences are hand-authored in
  `assets/vocab/examples/part-NN.json` and must pass `build.py --lint`
  (N5 + list vocabulary, initial-N4 grammar only). Slots: 15 → :15/:30/:45,
  30 → :15/:45, 60 → :30 (never :00 — time signal); skipped in quiet hours,
  while anything streams to the DAC (/proc/asound status, catches Bluetooth),
  and during an announcement. New words pause while > 8 reviews are overdue.
- Hourly voice: `/opt/pi-speakers/voice/hour-NN.wav` — generated on the Mac
  by `assets/voice/generate.sh` (`say -v Kyoko` + ffmpeg; voice gained by
  measured mean level, tanh soft-clipped, lifted to -1.5 dBFS ≈ -10 LUFS —
  peak-normalizing speech next to a pure-tone chirp leaves it ~10 dB too
  quiet), committed in assets/voice/. Deploy: scp to /tmp, sudo mv into
  /opt/pi-speakers/voice/, test via the `announce` trigger.
- Fonts on the Pi: `/opt/pi-speakers/fonts/` — monofonto.otf (Terminal),
  Rajdhani-Bold/Medium (Neon Latin), DotGothic16 (ALL Retro TV text + its JP),
  VT323 (legacy); VL Gothic system font is Neon's Japanese.
- EQ: `amixer -D equal` (0–100 per band, flat = 66); webui maps ±10 dB.

## Display facts

- 480×320, framebuffer found by driver name (fb_ili9486, number changes per
  boot), RGB565, software 180° flip (`[::-1, ::-1]`), `fbcon=rotate:2`.
- Faux-bold = `stroke_width=1, stroke_fill=color`. Do NOT stroke dense kanji
  or small DotGothic (< ~18px) — it fills the counters into blobs.
- DotGothic16's "…" floats at JIS center height; use "..." (see truncate()).
- HUD icons must center on the text's optical midline — DotGothic leaves 6px
  of air above its caps (measure with font.getbbox, don't eyeball).
- Marquees baseline-align to their theme's anchor via
  `font.getmetrics()[0]`; each theme has intro animations keyed to
  `*_until` timestamps set on skin switch.

## Known parked issues

- AirPlay transport controls: Shairport's D-Bus accepts Play/Pause but most
  senders ignore it. Parked; noted in README.
- `display/spotify-event.sh` still contains a temporary event logger line
  (writes /run/pi-speakers/events.log).
- Design canvas artboards in `design/` are stale vs. the device.
