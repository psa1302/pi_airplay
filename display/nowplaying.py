#!/usr/bin/env python3
"""Reads Shairport Sync's metadata pipe into /run/pi-speakers/nowplaying.json."""
import base64
import json
import re
import time
from pathlib import Path

PIPE = Path("/tmp/shairport-sync-metadata")
OUT = Path("/run/pi-speakers/nowplaying.json")
ITEM = re.compile(rb"<item><type>([0-9a-f]{8})</type><code>([0-9a-f]{8})</code>"
                  rb"<length>(\d+)</length>"
                  rb"(?:\s*<data encoding=\"base64\">\s*([A-Za-z0-9+/=\s]*?)</data>)?</item>")

state = {"playing": False, "source": "airplay", "title": "", "artist": ""}


def write_state():
    OUT.parent.mkdir(mode=0o777, exist_ok=True)
    OUT.write_text(json.dumps(state))


def fourcc(hex_bytes):
    return bytes.fromhex(hex_bytes.decode()).decode("ascii", "replace")


def handle(item_type, code, payload):
    text = payload.decode("utf-8", "replace").strip()

    if item_type == "core" and code == "minm":
        state.update(title=text, playing=True, source="airplay")
    elif item_type == "core" and code == "asar":
        state.update(artist=text, source="airplay")
    elif item_type == "ssnc" and code in ("pbeg", "prsm"):
        state.update(playing=True, source="airplay")
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
