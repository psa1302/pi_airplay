# Changelog

## [0.7.1] - 2026-09-04

### Changed
- The hourly signal is the voice announcement alone - the Casio pips are
  retired from the top of the hour (they remain the fallback when voice
  files are absent, and the chime toggle still gates everything).
- Announcement volume normalized: every voice file now peaks at -1.5 dB
  (they sat ~10 dB low).

## [0.7.0] - 2026-09-04

### Added
- Japanese time announcements: at the top of each hour the Casio pips are
  followed by a spoken 「時刻、午後4時」-style readout (Kyoko voice, comms
  chirp intro, light chorus/echo processing; 24 pre-generated WAVs in
  assets/voice/, no runtime TTS). Rides the chime toggle and quiet hours.
  A small speech ripple animates in every theme while the voice plays, and
  /run/pi-speakers/announce lets anything trigger an announcement.
- Second speaker support: sdcard/prepare-sd.sh takes hostname, speaker
  name, audio card, and display kind, and writes a pi-speakers.conf device
  profile that install.sh reads - "Pi Speakers 2" runs on a Pi 4B with a
  640x480 HDMI panel and the onboard jack or the USB DAC (one-line switch).
- The dashboard renders on any framebuffer: size and depth are detected,
  non-native panels get stretch scaling (16 and 32 bit paths), USB
  capacitive touchscreens work alongside the SPI panel.
- The web UI is a home-screen app: web manifest, generated icons, Apple
  meta tags, standalone display on iOS/Android.

### Fixed
- The Pi 3B wifi went deaf to broadcast (ARP/mDNS) hours after
  association even with power save off: the in-firmware WPA supplicant
  mishandles the AP group-key rekey. Fixed with
  `brcmfmac roamoff=1 feature_disable=0x282000`; a net-announce service
  (gratuitous ARP + avahi kick) stays as belt-and-braces.
- SD prep now writes the `ssh` boot flag - cloud-init's ssh module does
  not reliably run on Trixie images.
- The audio-stage pipeline check no longer aborts the install when
  bcm2835 hangs in the final drain (timeout exit tolerated).

## [0.6.0] - 2026-08-21

### Added
- Hourly chime, Casio style: a double pip (2730 Hz piezo timbre) at the top
  of every hour, mixed through the EQ so it plays over music. Toggle in the
  web UI; quiet hours silence it (default 00:00-10:00, adjustable with a
  dual-thumb range slider, overnight spans supported). During quiet hours
  every LCD theme shows a crescent moon between the wifi and source icons,
  in the theme's accent color.
- Power menu in the web UI: a top-right icon opens a popover with Restart
  and Shut down (two-tap confirm). Restart reloads the page when the
  speaker returns; new /api/power endpoint.
- Settings menu (gear icon): sectioned popover holding the page appearance
  toggle and the chime/quiet-hours controls; new /api/chime endpoint.
- Farewell screens: on a real reboot or shutdown the dashboard paints a
  theme-styled goodbye (Retro TV: PLEASE STAND BY with color bars; Terminal:
  SYSTEM HALTED; Neon: 再起動中/またね; Classic: plain words) so the frozen
  panel no longer masquerades as a hang. Plain service restarts skip it.

### Changed
- Web UI desktop layout: explicit grid placement, equal-height rows, and
  the wifi list scrolls inside its card instead of stretching the page.
- The installer now disables wifi power save, pins the CPU governor to
  performance, and turns off USB autosuspend for the DAC.

### Fixed
- WiFi power save made the Pi unreachable over IPv4 once a device's ARP
  cache expired (the napping radio misses broadcast ARP/mDNS); documented
  in the README and prevented by the installer change above.

## [0.5.2] - 2026-08-21

### Fixed
- Neon vitals kanji (稼働, 音量) lost their faux-bold stroke - dense kanji
  blob at 15px with any thickening - and grew a point instead.
- The 音量 label is vertically centered on the volume bar in Neon and
  Retro TV.

## [0.5.1] - 2026-08-20

### Fixed
- Terminal: the song line's baseline lands on the VU bars' bottom edge.
- Retro TV: the track title lost its faux-bold stroke - at 16px the stroke
  closed the gaps of DotGothic16's dot matrix and smeared the glyphs.

### Changed
- Bigger clocks: Retro TV 82px → 96px, Neon 96px → 104px.

## [0.5.0] - 2026-08-20

### Changed (Retro TV theme)
- All text now set in DotGothic16 (fetched at install time), Latin and
  Japanese alike, replacing VT323: HUD, clock, date, weather, music box,
  and vitals.
- Japanese ambient elements on the Neon pattern: 8月20日（水）date readout
  with the weekday in phosphor green, katakana city names, 稼働/音量 vitals
  labels. Song info stays untouched.
- Clock (82px), temperature (20px, phosphor green), date, city, and track
  title carry a 1px faux-bold stroke; the chromatic clock ghosts keep their
  offsets around the heavier face.
- HUD icons realigned to the text midline: DotGothic leaves 6px of air above
  its caps, so the wifi fan and source badge sat visibly high.
- The SSID truncates with baseline dots - DotGothic16's ellipsis glyph
  floats at the JIS center height.

## [0.4.0] - 2026-08-20

### Fixed
- Spotify Connect now shows track info everywhere: its event hook writes a
  dedicated state file and the now-playing daemon arbitrates between sources
  (whichever actually plays wins) instead of clobbering it every poll. Events
  without metadata merge with the previous state rather than blanking it.
- Metadata text is sanitized before rendering - a track title containing a
  newline crashed the dashboard's text renderer in a restart loop.
- The Spotify badge renders from the official logo (bundled, theme-tinted);
  the previous hand-drawn arcs sat outside the circle.
- The song line's baseline now aligns exactly with the playing-indicator
  bars in all four themes, using real font metrics.

### Changed (Neon theme)
- Latin text set in Rajdhani (the Cyberpunk 2077 UI face; fetched at install
  time): clock, temperature, HUD, marquee, and progress times.
- Japanese ambient text: bracket-style date readout with weekday accent,
  katakana city names, vitals labels; VL Gothic installed for kanji.
- Temperature in Rich Lemon; date and city in Blushing Purple.

## [0.3.0] - 2026-08-20

### Added
- Theme mascots, now bundled and auto-deployed by install.sh: Terminal
  renders any image at /opt/pi-speakers/mascot.png as phosphor-green line art
  (white-canvas keying and dark-line inversion handled automatically), Neon
  recolors mascot-neon.png into theme magenta/cyan with an ambient RGB-tear
  glitch, Retro TV shows mascot-tv.png in its original colors.
- Theme intros: Retro TV tunes in through analog static that resolves into
  the picture; Neon locks its signal through a decaying glitch storm.
- All four themes share the layout structure: top HUD (IP, SSID, WiFi,
  playback source badge), icon + °C weather, and a music box with animated
  bars, a title·artist marquee, and a live progress bar (vitals when idle).

### Fixed
- Display orientation is now global: fbcon=rotate:2 flips the console (the
  overlay's rotate parameter cannot flip this panel - its init sequence pins
  the scan direction) while the dashboard flips its own frames.
- Source badge color matches each theme's WiFi icon.

## [0.2.0] - 2026-08-20

### Fixed
- Now-playing data no longer poisoned by the sender's next-track prefetch:
  track identity (title/artist/album), progress, and play state now come from
  Shairport Sync's D-Bus `RemoteControl` properties, which track the active
  item. The metadata pipe remains only for instant play/pause events and the
  sender's device name. This also fixes the progress bar running out while a
  song was still playing, and the play state being lost after a reader restart.
- Spotify events now carry album, duration, and position into the shared
  now-playing state.

### Changed (Terminal theme)
- Music box redesigned: three animated playing-indicator bars, a single
  title `·` artist line (bright/dim, Apple Music style) that scrolls with a
  hold-scroll-hold-reset marquee when it overflows, and a progress bar whose
  width is measured against the time readout so they can never collide.
- Source badge (AirPlay / Spotify) moved to the top-right HUD next to the
  WiFi icon, shown only during playback; the HUD hugs the corner when idle.
- Sender device name shown under the date during playback.

## [0.1.0] - 2026-08-20

Initial release: AirPlay 2 + Spotify Connect + Bluetooth through a shared
bass/treble EQ, web control panel (EQ, WiFi, themes, transport), themeable
LCD dashboard (Classic / Terminal / Neon / Retro TV) with weather, vitals,
and mascot support, one-shot installer, and SD-card first-boot tooling.
