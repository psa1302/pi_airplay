#!/bin/sh
# librespot --onevent hook: mirrors Spotify playback into spotify.json
# (nowplaying.py arbitrates between this and the AirPlay state)
echo "$(date +%T) event=$PLAYER_EVENT name=$NAME pos=$POSITION_MS dur=$DURATION_MS" >> /run/pi-speakers/events.log
python3 - <<'PY'
import json, os, time

event = os.environ.get("PLAYER_EVENT", "")
path = "/run/pi-speakers/spotify.json"

previous = {}
try:
    with open(path) as handle:
        previous = json.load(handle)
except Exception:
    pass

if event in ("track_changed", "playing", "started", "seeked"):
    data = {"playing": True, "source": "spotify",
            "title": os.environ.get("NAME") or previous.get("title", ""),
            "artist": os.environ.get("ARTISTS") or previous.get("artist", ""),
            "album": os.environ.get("ALBUM") or previous.get("album", ""),
            "device": ""}
    duration = os.environ.get("DURATION_MS")
    data["duration"] = int(duration) / 1000 if duration else previous.get("duration", 0)
    position = os.environ.get("POSITION_MS")
    if position:
        data["elapsed"] = int(position) / 1000
        data["anchor"] = time.time()
    else:
        data["elapsed"] = previous.get("elapsed", 0)
        data["anchor"] = previous.get("anchor", time.time())
elif event in ("paused", "stopped", "session_disconnected"):
    data = dict(previous, playing=False, source="spotify")
else:
    raise SystemExit

os.makedirs("/run/pi-speakers", mode=0o777, exist_ok=True)
with open(path, "w") as handle:
    json.dump(data, handle)
PY
