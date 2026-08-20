# Changelog

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
