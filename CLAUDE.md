# Pi Speakers — session notes

A Raspberry Pi 3B wireless speaker (AirPlay 2 + Spotify Connect + Bluetooth →
shared EQ → USB DAC) with a web UI and a themeable 3.5" LCD dashboard. Read
README.md for architecture and the hard-won gotchas; CHANGELOG.md for history.

## The device

- Hostname `airplay-pi`, user `pi`, key auth (`ssh -o BatchMode=yes` works).
- mDNS `airplay-pi.local` usually resolves; when it doesn't, use the IP
  (192.168.31.199 as of Aug 2026, DHCP) with `-o HostKeyAlias=airplay-pi.local`.
- **There is another Pi on this network (a printer server). Never touch it.**
- The Pi runs the code in `/opt/pi-speakers/` — the repo is the source of
  truth, but the device is updated by direct deploy, not git pull.

## Deploy loop (the workflow used for all iteration)

1. Patch the file locally (python heredoc with assert-guarded replaces),
   then `ast.parse` it (Python) or eyeball (HTML/JS).
2. `scp` to `pi@…:/tmp/`, then `sudo mv` into `/opt/pi-speakers/`.
3. `sudo systemctl restart <service>` and check `systemctl is-active`.

Services: `pi-speakers-display` (dashboard.py), `pi-speakers-web` (webui.py +
index.html, port 80), `pi-speakers-nowplaying` (nowplaying.py), plus
`shairport-sync`, `raspotify`, `bluealsa-aplay`.

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
  `quiet`, `quiet-range` ("start-end" hours). Missing file = default on.
- Runtime: `/run/pi-speakers/` — `nowplaying.json` (written by nowplaying.py,
  which arbitrates Shairport D-Bus vs `spotify.json` from the raspotify event
  hook), `chime.wav` (generated at dashboard startup).
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
