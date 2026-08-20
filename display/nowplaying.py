#!/usr/bin/env python3
"""Maintains /run/pi-speakers/nowplaying.json.

Track identity (title/artist/album) and progress come from Shairport's D-Bus
state, which tracks the ACTIVE item - the metadata pipe also carries prefetched
next-track bundles that would poison a naive reader. The pipe is still used for
what it does best: instant play/pause events and the sender's device name.
"""
import base64
import json
import re
import subprocess
import threading
import time
from pathlib import Path

PIPE = Path("/tmp/shairport-sync-metadata")
OUT = Path("/run/pi-speakers/nowplaying.json")
SPOTIFY = Path("/run/pi-speakers/spotify.json")
ITEM = re.compile(rb"<item><type>([0-9a-f]{8})</type><code>([0-9a-f]{8})</code>"
                  rb"<length>(\d+)</length>"
                  rb"(?:\s*<data encoding=\"base64\">\s*([A-Za-z0-9+/=\s]*?)</data>)?</item>")

state = {"playing": False, "source": "airplay", "title": "", "artist": "",
         "album": "", "device": "", "duration": 0, "elapsed": 0, "anchor": 0,
         "airplay_started": 0}
lock = threading.Lock()


PUBLIC_KEYS = ("playing", "source", "title", "artist", "album",
               "device", "duration", "elapsed", "anchor")


def write_state():
    """Publish whichever source is actually playing; Spotify's own state file
    wins while it plays and AirPlay is silent (or started earlier)."""
    snapshot = {key: state[key] for key in PUBLIC_KEYS}
    try:
        spotify = json.loads(SPOTIFY.read_text())
        spotify_at = SPOTIFY.stat().st_mtime
    except Exception:
        spotify = None

    if spotify and spotify.get("playing"):
        if not snapshot["playing"] or spotify_at > state["airplay_started"]:
            snapshot = spotify

    OUT.parent.mkdir(mode=0o777, exist_ok=True)
    OUT.write_text(json.dumps(snapshot))


def fourcc(hex_bytes):
    return bytes.fromhex(hex_bytes.decode()).decode("ascii", "replace")


def dbus_property(name):
    result = subprocess.run(
        ["dbus-send", "--system", "--print-reply",
         "--dest=org.gnome.ShairportSync", "/org/gnome/ShairportSync",
         "org.freedesktop.DBus.Properties.Get",
         "string:org.gnome.ShairportSync.RemoteControl", f"string:{name}"],
        capture_output=True, text=True, timeout=5)
    return result.stdout


def poll_active_track():
    while True:
        try:
            reply = dbus_property("Metadata")
            title = re.search(r'"xesam:title"\s*\n\s*variant\s+string "(.*)"', reply)
            album = re.search(r'"xesam:album"\s*\n\s*variant\s+string "(.*)"', reply)
            artist = re.search(r'"xesam:artist"\s*\n\s*variant\s+array \[\s*\n\s*string "(.*)"', reply)

            with lock:
                if title and title.group(1) != state["title"]:
                    print(f"active title -> {title.group(1)!r}", flush=True)
                    state["title"] = title.group(1)
                    state["source"] = "airplay"
                if artist:
                    state["artist"] = artist.group(1)
                if album:
                    state["album"] = album.group(1)

                player = re.search(r'variant\s+string "([A-Za-z ]+)"', dbus_property("PlayerState"))
                if player:
                    if player.group(1) == "Playing":
                        if not state["playing"]:
                            state["airplay_started"] = time.time()
                        state["playing"] = True
                    elif player.group(1) in ("Paused", "Stopped"):
                        state["playing"] = False

                progress = re.search(r'string "(\d+)/(\d+)/(\d+)"', dbus_property("ProgressString"))
                if progress:
                    start, current, end = (int(v) for v in progress.groups())
                    state.update(duration=max(0.0, (end - start) / 44100),
                                 elapsed=max(0.0, (current - start) / 44100),
                                 anchor=time.time())
                write_state()
        except Exception:
            pass
        time.sleep(2)


def handle(item_type, code, payload):
    text = payload.decode("utf-8", "replace").strip()

    with lock:
        if item_type == "ssnc" and code == "snam":
            state.update(device=text)
        elif item_type == "ssnc" and code in ("pbeg", "prsm"):
            state.update(playing=True, source="airplay", airplay_started=time.time())
        elif item_type == "ssnc" and code in ("pend", "pfls"):
            state.update(playing=False)
        else:
            return

        write_state()


def consume(buffer):
    end = 0
    for match in ITEM.finditer(buffer):
        item_type, code = fourcc(match.group(1)), fourcc(match.group(2))
        payload = base64.b64decode(match.group(4)) if match.group(4) else b""
        handle(item_type, code, payload)
        end = match.end()

    return buffer[end:] if end else buffer[-65536:]


def main():
    write_state()
    threading.Thread(target=poll_active_track, daemon=True).start()
    buffer = b""

    while True:
        if not PIPE.exists():
            time.sleep(2)
            continue
        with open(PIPE, "rb") as pipe:
            while chunk := pipe.read(4096):
                buffer = consume(buffer + chunk)


if __name__ == "__main__":
    main()
