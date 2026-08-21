#!/usr/bin/env python3
"""Pi Speakers control panel: bass/treble EQ + WiFi, served on port 80."""
import json
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FLAT_UNITS = 200 / 3          # amixer value for 0 dB (0-100 spans -48..+24 dB)
UNITS_PER_DB = 100 / 72
BASS_BANDS = ["00. 31 Hz", "01. 63 Hz", "02. 125 Hz"]
BASS_SHOULDER = "03. 250 Hz"
TREBLE_BANDS = ["07. 4 kHz", "08. 8 kHz", "09. 16 kHz"]
TREBLE_SHOULDER = "06. 2 kHz"
PAGE = (Path(__file__).parent / "index.html").read_bytes()
NOWPLAYING = Path("/run/pi-speakers/nowplaying.json")
THEME_MODE = Path("/var/lib/pi-speakers/theme")


def read_theme():
    try:
        mode = THEME_MODE.read_text().strip()
    except Exception:
        mode = "auto"
    return {"mode": mode if mode in ("auto", "light", "dark") else "auto"}


CHIME_FILE = Path("/var/lib/pi-speakers/chime")
QUIET_FILE = Path("/var/lib/pi-speakers/quiet")
QUIET_RANGE_FILE = Path("/var/lib/pi-speakers/quiet-range")


def read_flag(path):
    try:
        return path.read_text().strip() != "off"
    except OSError:
        return True


def read_quiet_range():
    try:
        start, end = QUIET_RANGE_FILE.read_text().strip().split("-")
        return int(start) % 24, int(end) % 24
    except (OSError, ValueError):
        return 0, 10


def read_chime():
    start, end = read_quiet_range()
    return {"on": read_flag(CHIME_FILE), "quiet": read_flag(QUIET_FILE),
            "quiet_start": start, "quiet_end": end}


def set_chime(body):
    CHIME_FILE.parent.mkdir(exist_ok=True)
    if "on" in body:
        CHIME_FILE.write_text("on" if body["on"] else "off")
    if "quiet" in body:
        QUIET_FILE.write_text("on" if body["quiet"] else "off")
    if "quiet_start" in body or "quiet_end" in body:
        start, end = read_quiet_range()
        start = int(body.get("quiet_start", start)) % 24
        end = int(body.get("quiet_end", end)) % 24
        QUIET_RANGE_FILE.write_text(f"{start}-{end}")


SKIN_FILE = Path("/var/lib/pi-speakers/skin")
SKINS = ("classic", "terminal", "neon", "retrotv")


def read_skin():
    try:
        skin = SKIN_FILE.read_text().strip()
    except Exception:
        skin = "classic"
    return {"skin": skin if skin in SKINS else "classic"}


def set_skin(skin):
    if skin not in SKINS:
        raise ValueError("unknown skin")
    SKIN_FILE.parent.mkdir(exist_ok=True)
    SKIN_FILE.write_text(skin)


def set_theme(mode):
    if mode not in ("auto", "light", "dark"):
        raise ValueError("mode must be auto, light or dark")
    THEME_MODE.parent.mkdir(exist_ok=True)
    THEME_MODE.write_text(mode)


def read_nowplaying():
    try:
        return json.loads(NOWPLAYING.read_text())
    except Exception:
        return {"playing": False, "title": "", "artist": "", "source": ""}


def amixer(*args):
    return subprocess.run(["amixer", "-D", "equal", *args],
                          capture_output=True, text=True, timeout=10).stdout


def nmcli(*args, timeout=30):
    return subprocess.run(["nmcli", *args], capture_output=True, text=True, timeout=timeout)


def clamp(value):
    return max(-10, min(10, int(value)))


def db_to_units(db):
    return str(round(FLAT_UNITS + db * UNITS_PER_DB))


def units_to_db(units):
    return round((units - FLAT_UNITS) / UNITS_PER_DB)


def read_band(name):
    match = re.search(r"Front Left: Playback (\d+)", amixer("sget", name))
    return int(match.group(1)) if match else round(FLAT_UNITS)


def read_eq():
    return {"bass": units_to_db(read_band(BASS_BANDS[0])),
            "treble": units_to_db(read_band(TREBLE_BANDS[0]))}


def set_band_group(bands, shoulder, db):
    for band in bands:
        amixer("sset", band, db_to_units(db))
    amixer("sset", shoulder, db_to_units(db / 2))


def set_eq(bass, treble):
    set_band_group(BASS_BANDS, BASS_SHOULDER, clamp(bass))
    set_band_group(TREBLE_BANDS, TREBLE_SHOULDER, clamp(treble))


def unescape_field(field):
    return field.replace("\\:", ":")


def wifi_networks(rescan):
    if rescan:
        nmcli("dev", "wifi", "rescan")
        time.sleep(4)

    out = nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list").stdout
    networks, seen = [], set()

    for line in out.splitlines():
        fields = [unescape_field(f) for f in re.split(r"(?<!\\):", line)]
        if len(fields) < 4:
            continue
        in_use, ssid, signal, security = fields[0], fields[1], fields[2], fields[3]

        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({"ssid": ssid,
                         "signal": int(signal or 0),
                         "secured": bool(security.strip()),
                         "connected": in_use == "*"})

    return networks


CONTROL_METHODS = {"play": "Play", "pause": "Pause", "next": "Next", "previous": "Previous"}


def control_airplay(action):
    if action == "playpause":
        action = "pause" if read_nowplaying().get("playing") else "play"

    method = CONTROL_METHODS.get(action)
    if not method:
        raise ValueError("unknown action")

    result = subprocess.run(["dbus-send", "--system", "--print-reply", "--type=method_call",
                             "--dest=org.gnome.ShairportSync", "/org/gnome/ShairportSync",
                             f"org.gnome.ShairportSync.RemoteControl.{method}"],
                            capture_output=True, text=True, timeout=10)

    return result.returncode == 0, result.stderr.strip()


def power(action):
    if action not in ("reboot", "shutdown"):
        raise ValueError("unknown action")

    command = "reboot" if action == "reboot" else "poweroff"
    subprocess.Popen(["sh", "-c", f"sleep 1; systemctl {command}"])


def join_wifi(ssid, psk):
    args = ["dev", "wifi", "connect", ssid]
    if psk:
        args += ["password", psk]

    result = nmcli(*args, timeout=60)
    message = (result.stdout + result.stderr).strip()

    return result.returncode == 0, message


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, payload, content_type="application/json", status=200):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self.reply(PAGE, "text/html; charset=utf-8")
        elif self.path.startswith("/api/eq"):
            self.reply(read_eq())
        elif self.path.startswith("/api/wifi"):
            self.reply({"networks": wifi_networks("rescan=1" in self.path)})
        elif self.path.startswith("/api/now"):
            self.reply(read_nowplaying())
        elif self.path.startswith("/api/theme"):
            self.reply(read_theme())
        elif self.path.startswith("/api/skin"):
            self.reply(read_skin())
        elif self.path.startswith("/api/chime"):
            self.reply(read_chime())
        else:
            self.reply({"error": "not found"}, status=404)

    def do_POST(self):
        try:
            body = self.read_body()

            if self.path.startswith("/api/eq"):
                set_eq(body.get("bass", 0), body.get("treble", 0))
                self.reply(read_eq())
            elif self.path.startswith("/api/wifi"):
                ok, message = join_wifi(str(body.get("ssid", "")), str(body.get("psk", "")))
                self.reply({"ok": ok, "message": message})
            elif self.path.startswith("/api/theme"):
                set_theme(str(body.get("mode", "")))
                self.reply(read_theme())
            elif self.path.startswith("/api/skin"):
                set_skin(str(body.get("skin", "")))
                self.reply(read_skin())
            elif self.path.startswith("/api/control"):
                ok, message = control_airplay(str(body.get("action", "")))
                self.reply({"ok": ok, "message": message})
            elif self.path.startswith("/api/power"):
                power(str(body.get("action", "")))
                self.reply({"ok": True})
            elif self.path.startswith("/api/chime"):
                set_chime(body)
                self.reply(read_chime())
            else:
                self.reply({"error": "not found"}, status=404)
        except Exception as error:
            self.reply({"error": str(error)}, status=500)


def main():
    ThreadingHTTPServer(("", 80), Handler).serve_forever()


if __name__ == "__main__":
    main()
