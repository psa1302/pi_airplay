#!/bin/sh
# librespot --onevent hook: mirrors Spotify playback into nowplaying.json
python3 - <<'PY'
import json, os

event = os.environ.get("PLAYER_EVENT", "")
path = "/run/pi-speakers/nowplaying.json"

if event in ("track_changed", "playing", "started"):
    import time
    data = {"playing": True, "source": "spotify",
            "title": os.environ.get("NAME", ""),
            "artist": os.environ.get("ARTISTS", ""),
            "album": os.environ.get("ALBUM", ""),
            "device": "",
            "duration": int(os.environ.get("DURATION_MS", 0) or 0) / 1000,
            "elapsed": int(os.environ.get("POSITION_MS", 0) or 0) / 1000,
            "anchor": time.time()}
elif event in ("paused", "stopped", "session_disconnected"):
    data = {"playing": False, "source": "spotify", "title": "", "artist": ""}
else:
    raise SystemExit

os.makedirs("/run/pi-speakers", mode=0o777, exist_ok=True)
with open(path, "w") as handle:
    json.dump(data, handle)
PY
