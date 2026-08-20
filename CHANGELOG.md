# Changelog

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
