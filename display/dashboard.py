#!/usr/bin/env python3
"""Glanceable panel for the Waveshare 3.5" LCD: clock, weather, WiFi, EQ, themes."""
import json
import random
import re
import signal
import subprocess
import threading
import time
import wave
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SIZE = (480, 320)


def find_display_fb():
    for node in sorted(Path("/sys/class/graphics").glob("fb*")):
        try:
            if "ili9486" in (node / "name").read_text():
                return Path("/dev") / node.name, True
        except OSError:
            continue
    return Path("/dev/fb0"), False


def fb_geometry(fb):
    node = Path("/sys/class/graphics") / fb.name
    width, height = map(int, (node / "virtual_size").read_text().split(","))
    return width, height, int((node / "bits_per_pixel").read_text())


NIGHT_HOURS = range(0, 7)          # plus 21-23, see is_night()

DAY = {"bg": (255, 255, 255), "ink": (17, 17, 20),
       "muted": (107, 111, 118), "card": (242, 243, 245)}
NIGHT = {"bg": (8, 8, 10), "ink": (225, 227, 231),
         "muted": (110, 114, 122), "card": (24, 25, 28)}

GREEN = (47, 158, 95)
AMBER = (209, 154, 47)
RED = (209, 88, 58)
SUN = (224, 166, 60)
MOON = (139, 163, 199)
CLOUD = (125, 136, 153)
FOG = (154, 160, 168)
RAIN = (74, 144, 196)
SNOW = (127, 181, 214)
STORM = (129, 104, 184)

TERM_BG = (5, 16, 6)
TERM_FG = (38, 245, 74)
TERM_DIM = (18, 130, 42)

NEON_PANEL = (18, 8, 31)
NEON_MAGENTA = (255, 45, 120)
NEON_CYAN = (0, 229, 255)
NEON_YELLOW = (253, 245, 0)        # rich lemon
NEON_INK = (242, 238, 252)
NEON_MUTED = (138, 127, 168)

TV_BEZEL = (22, 23, 26)
TV_BG = (10, 12, 16)
TV_INK = (244, 246, 242)
TV_MUTED = (154, 163, 173)
TV_GREEN = (157, 255, 157)
TV_BOX = (14, 17, 20)
TV_EDGE = (42, 47, 54)
TV_BARS = [(200, 200, 200), (200, 200, 50), (50, 200, 200), (50, 200, 50),
           (200, 50, 200), (200, 50, 50), (50, 50, 200)]

WEATHER = {0: ("Clear", "sun", SUN), 1: ("Mostly clear", "sun", SUN),
           2: ("Partly cloudy", "cloud", CLOUD), 3: ("Overcast", "cloud", CLOUD),
           45: ("Fog", "fog", FOG), 48: ("Fog", "fog", FOG),
           51: ("Drizzle", "rain", RAIN), 53: ("Drizzle", "rain", RAIN), 55: ("Drizzle", "rain", RAIN),
           61: ("Rain", "rain", RAIN), 63: ("Rain", "rain", RAIN), 65: ("Heavy rain", "rain", RAIN),
           66: ("Freezing rain", "rain", RAIN), 67: ("Freezing rain", "rain", RAIN),
           71: ("Snow", "snow", SNOW), 73: ("Snow", "snow", SNOW), 75: ("Heavy snow", "snow", SNOW),
           80: ("Showers", "rain", RAIN), 81: ("Showers", "rain", RAIN), 82: ("Heavy showers", "rain", RAIN),
           95: ("Thunderstorm", "storm", STORM), 96: ("Thunderstorm", "storm", STORM),
           99: ("Thunderstorm", "storm", STORM)}

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_MONOFONTO = "/opt/pi-speakers/fonts/monofonto.otf"
FONT_VT323 = "/opt/pi-speakers/fonts/VT323.ttf"
FONT_JP = "/usr/share/fonts/truetype/vlgothic/VL-PGothic-Regular.ttf"
FONT_RAJ_BOLD = "/opt/pi-speakers/fonts/Rajdhani-Bold.ttf"
FONT_RAJ_MED = "/opt/pi-speakers/fonts/Rajdhani-Medium.ttf"
FONT_DOT = "/opt/pi-speakers/fonts/DotGothic16.ttf"

WEEKDAY_KANJI = "月火水木金土日"
KATAKANA_CITIES = {"New Delhi": "ニューデリー", "Delhi": "デリー", "Gurugram": "グルガオン",
                   "Gurgaon": "グルガオン", "Noida": "ノイダ", "Mumbai": "ムンバイ",
                   "Bengaluru": "ベンガルール", "Bangalore": "ベンガルール"}
MASCOT_FILE = Path("/opt/pi-speakers/mascot.png")
NEON_MASCOT_FILE = Path("/opt/pi-speakers/mascot-neon.png")
TV_MASCOT_FILE = Path("/opt/pi-speakers/mascot-tv.png")
SPOTIFY_LOGO = Path("/opt/pi-speakers/spotify-logo.png")

BOOT_LINES = ["PI-OS(R) V3.0 - PERSONAL AUDIO TERMINAL",
              "COPYRIGHT 2286 PI-TUNE INDUSTRIES",
              "LOADER V1.1",
              "EXEC AUDIO SUBSYSTEM ............ OK",
              "EXEC EQUALIZER [31Hz-16kHz] ..... OK",
              "EXEC AIRPLAY / SPOTIFY / BT ..... OK",
              "",
              "> WELCOME, OVERSEER"]
BOOT_SECONDS = 4.2
TV_INTRO_SECONDS = 2.8
NEON_INTRO_SECONDS = 3.2

_fonts = {}


def is_night(hour):
    return hour >= 21 or hour in NIGHT_HOURS


def font(size, bold=False):
    weight = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(f"{FONT_DIR}/{weight}", size)


def face(path, size):
    key = (path, size)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype(path, size)
        except OSError:
            _fonts[key] = font(size, bold=True)
    return _fonts[key]


def fetch_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def locate():
    place = fetch_json("http://ip-api.com/json/?fields=lat,lon,city")
    return place["lat"], place["lon"], place["city"]


def fetch_weather(lat, lon):
    data = fetch_json("https://api.open-meteo.com/v1/forecast"
                      f"?latitude={lat}&longitude={lon}"
                      "&current=temperature_2m,weather_code&timezone=auto")
    current = data["current"]
    return round(current["temperature_2m"]), current["weather_code"]


def run(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=10).stdout


CHIME_FILE = Path("/var/lib/pi-speakers/chime")
ANNOUNCE_TRIGGER = Path("/run/pi-speakers/announce")
VOICE_DIR = Path("/opt/pi-speakers/voice")
QUIET_FILE = Path("/var/lib/pi-speakers/quiet")
QUIET_RANGE_FILE = Path("/var/lib/pi-speakers/quiet-range")
CHIME_WAV = Path("/run/pi-speakers/chime.wav")


def write_chime_wav():
    rate = 44100
    t = np.arange(int(rate * 0.06)) / rate
    pip = np.sin(2 * np.pi * 2730 * t) + 0.25 * np.sin(2 * np.pi * 8190 * t)
    attack, release = int(rate * 0.004), int(rate * 0.015)
    pip[:attack] *= np.linspace(0, 1, attack)
    pip[-release:] *= np.linspace(1, 0, release)
    tone = np.concatenate([pip, np.zeros(int(rate * 0.06)), pip]) * 0.36
    samples = (tone * 32767).astype("<i2")

    with wave.open(str(CHIME_WAV), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples.tobytes())


ANNOUNCE_VOLUME_FILE = Path("/var/lib/pi-speakers/announce-volume")
SCALED_WAV = Path("/run/pi-speakers/announce-scaled.wav")


def announce_gain():
    try:
        percent = min(100, max(0, int(ANNOUNCE_VOLUME_FILE.read_text().strip())))
    except (OSError, ValueError):
        percent = 100
    return (percent / 100) ** 2      # square law: slider steps sound roughly even


def play_announcement(path):
    """Scale the clip by the announcement volume and play it; returns its length."""
    try:
        with wave.open(str(path), "rb") as clip:
            params = clip.getparams()
            frames = clip.readframes(params.nframes)
    except (OSError, wave.Error, EOFError):
        return 2.5

    scaled = (np.frombuffer(frames, dtype="<i2") * announce_gain()).astype("<i2")
    with wave.open(str(SCALED_WAV), "wb") as out:
        out.setparams(params)
        out.writeframes(scaled.tobytes())
    subprocess.Popen(["aplay", "-q", "-D", "equal", str(SCALED_WAV)])

    return params.nframes / params.framerate


def chime_enabled():
    try:
        return CHIME_FILE.read_text().strip() != "off"
    except OSError:
        return True


def quiet_pref():
    try:
        return QUIET_FILE.read_text().strip() != "off"
    except OSError:
        return True


def quiet_range():
    try:
        start, end = QUIET_RANGE_FILE.read_text().strip().split("-")
        return int(start) % 24, int(end) % 24
    except (OSError, ValueError):
        return 0, 10


def in_quiet_range(hour):
    start, end = quiet_range()
    if start <= end:
        return start <= hour < end
    return hour >= start or hour < end


def quiet_hours(hour):
    return quiet_pref() and in_quiet_range(hour)


FAREWELL = {
    "reboot": {"classic": ("Restarting…", "back in a moment"),
               "terminal": ("> REBOOT INITIATED", "PLEASE STAND BY_"),
               "neon": ("REBOOTING", "再起動中…"),
               "retrotv": ("PLEASE STAND BY", "再起動中…")},
    "shutdown": {"classic": ("Goodbye", "unplug and replug to restart"),
                 "terminal": ("> SYSTEM HALTED", "SAFE TO POWER OFF_"),
                 "neon": ("POWER OFF", "またね…"),
                 "retrotv": ("SIGN OFF", "電源オフ")},
}


def shutdown_kind():
    jobs = run(["systemctl", "list-jobs"])
    if "reboot.target" in jobs:
        return "reboot"
    if "poweroff.target" in jobs or "halt.target" in jobs:
        return "shutdown"
    return None


def install_farewell(panel):
    def on_sigterm(signum, frame):
        kind = shutdown_kind()
        if kind:
            panel.blit(panel.draw_farewell(kind))
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, on_sigterm)


def read_eq_db(band):
    match = re.search(r"Front Left: Playback (\d+)", run(["amixer", "-D", "equal", "sget", band]))
    return round((int(match.group(1)) - 200 / 3) * 72 / 100) if match else 0


def read_wifi():
    for line in run(["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL", "dev", "wifi", "list"]).splitlines():
        fields = re.split(r"(?<!\\):", line)
        if fields[0] == "*" and len(fields) >= 3:
            return fields[1].replace("\\:", ":"), int(fields[2] or 0)
    return "No WiFi", 0


def read_cpu_temp():
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000)
    except Exception:
        return None


def read_uptime():
    try:
        seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return "—"
    days, rest = divmod(seconds, 86400)
    hours, minutes = rest // 3600, rest % 3600 // 60
    return f"{days}D {hours}:{minutes:02d}" if days else f"{hours}:{minutes:02d}"


def read_volume():
    match = re.search(r"\[(\d+)%\]", run(["amixer", "-D", "hw:CARD=Creation", "sget", "Speaker"]))
    return int(match.group(1)) if match else None


def read_ip():
    addresses = run(["hostname", "-I"]).split()
    return addresses[0] if addresses else "—"


NOWPLAYING = Path("/run/pi-speakers/nowplaying.json")
THEME_MODE = Path("/var/lib/pi-speakers/theme")
SKIN_FILE = Path("/var/lib/pi-speakers/skin")


def theme_mode():
    try:
        mode = THEME_MODE.read_text().strip()
        return mode if mode in ("auto", "light", "dark") else "auto"
    except Exception:
        return "auto"


def read_skin():
    try:
        skin = SKIN_FILE.read_text().strip()
        return skin if skin in ("classic", "terminal", "neon", "retrotv") else "classic"
    except Exception:
        return "classic"


def read_nowplaying():
    try:
        data = json.loads(NOWPLAYING.read_text())
        if not (data.get("playing") and data.get("title")):
            return None
        for key in ("title", "artist", "album", "device"):
            data[key] = " ".join(str(data.get(key, "")).split())
        return data if data["title"] else None
    except Exception:
        return None


def send_remote(method):
    subprocess.run(["dbus-send", "--system", "--type=method_call",
                    "--dest=org.gnome.ShairportSync", "/org/gnome/ShairportSync",
                    f"org.gnome.ShairportSync.RemoteControl.{method}"],
                   capture_output=True, timeout=5)


# Measured via corner taps at rotate=90. The panel is mounted upside-down in
# its case; the overlay's rotate param cannot flip it (fixed init sequence),
# so the frame is flipped in software and fbcon=rotate:2 flips the console.
# If touch is re-enabled, both axes of this mapping must be mirrored.
RAW_Y_TO_COL = (470, 3700)
RAW_X_TO_ROW = (575, 3610)


def touch_to_screen(raw_x, raw_y):
    lo, hi = RAW_Y_TO_COL
    x = (hi - raw_y) / (hi - lo) * SIZE[0]

    lo, hi = RAW_X_TO_ROW
    y = (raw_x - lo) / (hi - lo) * SIZE[1]

    return min(max(x, 0), SIZE[0]), min(max(y, 0), SIZE[1])


def find_touch_device():
    import evdev

    devices = [evdev.InputDevice(p) for p in evdev.list_devices()]
    for dev in devices:
        if "ADS7846" in dev.name:
            return dev, "spi"
    for dev in devices:
        if evdev.ecodes.BTN_TOUCH in dev.capabilities().get(evdev.ecodes.EV_KEY, []):
            return dev, "usb"
    return None, None


def touch_loop(panel):
    import evdev

    device = kind = None
    raw_x = raw_y = None
    touching = False
    last_tap = 0.0

    while True:
        try:
            if device is None:
                device, kind = find_touch_device()
                if device is None:
                    time.sleep(5)
                    continue

            for event in device.read_loop():
                if event.type == evdev.ecodes.EV_ABS:
                    if event.code in (evdev.ecodes.ABS_X, evdev.ecodes.ABS_MT_POSITION_X):
                        raw_x = event.value
                    elif event.code in (evdev.ecodes.ABS_Y, evdev.ecodes.ABS_MT_POSITION_Y):
                        raw_y = event.value
                elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                    touching = event.value == 1
                elif (event.type == evdev.ecodes.EV_SYN and touching
                      and raw_x is not None and raw_y is not None
                      and time.time() - last_tap > 0.4):
                    last_tap = time.time()
                    x, y = (touch_to_screen(raw_x, raw_y) if kind == "spi"
                            else panel.absolute_to_design(device, raw_x, raw_y))
                    panel.on_tap(x, y)
        except Exception:
            device = None
            time.sleep(3)


def truncate(text, limit, dots="…"):
    return text if len(text) <= limit else text[:limit - 1] + dots


def signed(db):
    return f"+{db}" if db > 0 else str(db)


def signal_color(signal):
    if signal >= 70:
        return GREEN
    if signal >= 45:
        return AMBER
    if signal >= 20:
        return RED
    return None


def draw_moon_icon(image, cx, cy, color):
    tile = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    tile_pen = ImageDraw.Draw(tile)
    tile_pen.ellipse((4, 0, 18, 14), fill=color)
    tile_pen.ellipse((9, -5, 23, 9), fill=(0, 0, 0, 0))
    image.paste(tile, (cx - 9, cy - 9), tile)


def draw_wifi_icon(pen, cx, cy, signal, ink, muted, strength_colors=True):
    bars = 3 if signal >= 70 else 2 if signal >= 45 else 1 if signal >= 20 else 0
    active = (signal_color(signal) or muted) if strength_colors else (ink if bars else muted)

    for i, radius in enumerate((5, 9, 13)):
        color = active if i < bars else muted
        pen.arc((cx - radius, cy - radius, cx + radius, cy + radius), 225, 315, fill=color, width=2)
    pen.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=active)


_spotify_logo = [None]
_spotify_tints = {}


def spotify_logo_tinted(color):
    if _spotify_logo[0] is None:
        try:
            source = Image.open(SPOTIFY_LOGO).convert("RGBA")
            source.thumbnail((18, 18))
            _spotify_logo[0] = source
        except OSError:
            _spotify_logo[0] = False
    if not _spotify_logo[0]:
        return None

    if color not in _spotify_tints:
        tinted = Image.new("RGBA", _spotify_logo[0].size, color)
        tinted.putalpha(_spotify_logo[0].getchannel("A"))
        _spotify_tints[color] = tinted
    return _spotify_tints[color]


def draw_source_badge(image, x, y, source, ink, bg):
    pen = ImageDraw.Draw(image)

    if source == "spotify":
        logo = spotify_logo_tinted(tuple(ink))
        if logo:
            image.paste(logo, (x - 1, y - 1), logo)
        else:
            pen.ellipse((x, y, x + 16, y + 16), fill=ink)
            for radius, apex in ((9, y + 4), (6, y + 9)):
                pen.arc((x + 8 - radius, apex, x + 8 + radius, apex + 2 * radius),
                        238, 302, fill=bg, width=2)
        return

    pen.rounded_rectangle((x, y, x + 16, y + 11), radius=3, outline=ink, width=1)
    pen.polygon(((x + 8, y + 5), (x + 15, y + 17), (x + 1, y + 17)), fill=bg)
    pen.polygon(((x + 8, y + 7), (x + 13, y + 16), (x + 3, y + 16)), fill=ink)


def draw_cloud(pen, cx, cy, color):
    pen.ellipse((cx - 14, cy - 4, cx - 2, cy + 8), fill=color)
    pen.ellipse((cx - 8, cy - 10, cx + 6, cy + 4), fill=color)
    pen.ellipse((cx, cy - 4, cx + 14, cy + 8), fill=color)
    pen.rectangle((cx - 8, cy + 2, cx + 7, cy + 8), fill=color)


def draw_weather_icon(pen, cx, cy, kind, color, night, moon_fill=MOON, moon_bg=None, bolt_fill=AMBER):
    if kind == "sun" and night:
        pen.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), fill=moon_fill)
        pen.ellipse((cx - 3, cy - 13, cx + 15, cy + 5), fill=moon_bg or NIGHT["card"])
    elif kind == "sun":
        pen.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=color)
        for angle in range(0, 360, 45):
            dx, dy = np.cos(np.radians(angle)), np.sin(np.radians(angle))
            pen.line((cx + 11 * dx, cy + 11 * dy, cx + 15 * dx, cy + 15 * dy), fill=color, width=2)
    elif kind == "cloud":
        draw_cloud(pen, cx, cy, color)
    elif kind == "fog":
        for offset in (-6, 0, 6):
            pen.line((cx - 13, cy + offset, cx + 13, cy + offset), fill=color, width=3)
    elif kind == "rain":
        draw_cloud(pen, cx, cy - 5, color)
        for offset in (-8, 0, 8):
            pen.line((cx + offset, cy + 10, cx + offset - 3, cy + 16), fill=color, width=2)
    elif kind == "snow":
        draw_cloud(pen, cx, cy - 5, color)
        for offset in (-8, 0, 8):
            pen.ellipse((cx + offset - 2, cy + 11, cx + offset + 2, cy + 15), fill=color)
    elif kind == "storm":
        draw_cloud(pen, cx, cy - 5, color)
        pen.polygon((cx + 2, cy + 6, cx - 5, cy + 15, cx - 1, cy + 15, cx - 4, cy + 22,
                     cx + 5, cy + 12, cx + 1, cy + 12), fill=bolt_fill)


def draw_clock(pen, cx, cy, clock_font, now, ink, colon_ink=None, show_colon=None, stroke=0):
    if show_colon is None:
        show_colon = now.second % 2 == 0
    half = pen.textlength(":", font=clock_font) / 2

    pen.text((cx - half, cy), now.strftime("%H"), font=clock_font, fill=ink, anchor="rm",
             stroke_width=stroke, stroke_fill=ink)
    pen.text((cx + half, cy), now.strftime("%M"), font=clock_font, fill=ink, anchor="lm",
             stroke_width=stroke, stroke_fill=ink)
    if show_colon:
        pen.text((cx, cy), ":", font=clock_font, fill=colon_ink or ink, anchor="mm",
                 stroke_width=stroke, stroke_fill=colon_ink or ink)


def chamfer(x1, y1, x2, y2, cut=10):
    return ((x1 + cut, y1), (x2, y1), (x2, y2 - cut), (x2 - cut, y2), (x1, y2), (x1, y1 + cut))


def scanlines(arr, t, y0=0, y1=320, dark=0.74, speed=8):
    phase = int(t * speed) % 4
    rows = np.arange(y0, y1)
    marked = rows[((rows + phase) % 4) < 2]
    arr[marked] *= dark


def glitch(arr, t, period=4.5, burst=0.28):
    if t % period > burst:
        return
    for _ in range(4):
        y = random.randint(0, 300)
        h = random.randint(4, 14)
        arr[y:y + h] = np.roll(arr[y:y + h], random.randint(-38, 38), axis=1)

    y = random.randint(0, 290)
    h = random.randint(8, 20)
    arr[y:y + h, :, 0] = np.roll(arr[y:y + h, :, 0], random.randint(-14, 14), axis=1)


def light_band(arr, center, half, add, y0=0, y1=320):
    lo, hi = max(y0, int(center - half)), min(y1, int(center + half))
    if lo >= hi:
        return
    profile = 1 - np.abs(np.arange(lo, hi) - center) / half
    arr[lo:hi] += (add * profile)[:, None, None]


class Panel:
    def __init__(self):
        self.city = self.temperature = None
        self.condition = ("—", "cloud", CLOUD)
        self.coords = None
        self.weather_at = 0
        self.slow_at = 0
        self.wifi = ("", 0)
        self.ip = "—"
        self.eq = (0, 0)
        self.vu = [8, 13, 6]
        self.buttons = {}
        self.dirty = threading.Event()
        self.fb, self.spi_panel = find_display_fb()
        self.fb_w, self.fb_h, self.fb_bpp = fb_geometry(self.fb)
        self.skin = "classic"
        self.skin_prev = None
        self.chimed_hour = None
        self.announcing_until = 0.0
        self.boot_until = 0
        self.cpu_temp = None
        self.uptime = "—"
        self.volume = None
        self.buzz_rect = None
        self._neon_bg = None
        self._mascot = None
        self._neon_mascot = None
        self.neon_mascot_rect = None
        self._tv_mascot = None
        self.tv_intro_until = 0
        self.neon_intro_until = 0

    def refresh_weather(self):
        try:
            if not self.coords:
                lat, lon, self.city = locate()
                self.coords = (lat, lon)
            self.temperature, code = fetch_weather(*self.coords)
            self.condition = WEATHER.get(code, ("—", "cloud", CLOUD))
            self.weather_at = time.time()
        except Exception:
            self.weather_at = time.time() - 840        # retry in a minute

    def refresh_slow(self):
        self.wifi = read_wifi()
        self.ip = read_ip()
        self.eq = (read_eq_db("00. 31 Hz"), read_eq_db("07. 4 kHz"))
        self.cpu_temp = read_cpu_temp()
        self.uptime = read_uptime()
        self.volume = read_volume()
        self.slow_at = time.time()

    def tick(self):
        if time.time() - self.weather_at > 900:
            self.refresh_weather()
        if time.time() - self.slow_at > 30:
            self.refresh_slow()

        try:
            announce_wav = ANNOUNCE_TRIGGER.read_text().strip()
            ANNOUNCE_TRIGGER.unlink()
        except OSError:
            announce_wav = ""
        if announce_wav:
            self.announcing_until = time.time() + play_announcement(announce_wav)

        now = datetime.now()
        if now.minute == 0 and self.chimed_hour != now.hour:
            self.chimed_hour = now.hour
            if chime_enabled() and not quiet_hours(now.hour):
                voice = VOICE_DIR / f"hour-{now.hour:02d}.wav"
                if voice.exists():
                    self.announcing_until = time.time() + play_announcement(voice)
                else:
                    play_announcement(CHIME_WAV)

        self.skin = read_skin()
        if self.skin == "terminal" and self.skin_prev != "terminal":
            self.boot_until = time.time() + BOOT_SECONDS
        if self.skin == "retrotv" and self.skin_prev != "retrotv":
            self.tv_intro_until = time.time() + TV_INTRO_SECONDS
        if self.skin == "neon" and self.skin_prev != "neon":
            self.neon_intro_until = time.time() + NEON_INTRO_SECONDS
        self.skin_prev = self.skin

    def marquee_offset(self, key, overflow):
        if getattr(self, "_marquee_key", None) != key:
            self._marquee_key = key
            self._marquee_start = time.time()
        if overflow <= 0:
            return 0

        pause_in, speed, pause_out = 2.0, 30.0, 1.5
        cycle = pause_in + overflow / speed + pause_out
        t = (time.time() - self._marquee_start) % cycle

        if t < pause_in:
            return 0
        if t < pause_in + overflow / speed:
            return (t - pause_in) * speed
        return overflow

    def step_vu(self):
        self.vu = [max(4, min(18, v + random.randint(-4, 4))) for v in self.vu]

    def weather_line(self):
        text, _, _ = self.condition
        return text, self.city or ""

    def status_lines(self):
        ssid, signal = self.wifi
        bass, treble = self.eq
        return ssid, signal, f"Bass {signed(bass)} dB  ·  Treble {signed(treble)} dB", self.ip

    # ---------- classic ----------

    def draw_classic(self, now):
        night = theme_mode() == "dark" or (theme_mode() == "auto" and is_night(now.hour))
        theme = NIGHT if night else DAY
        image = Image.new("RGB", SIZE, theme["bg"])
        pen = ImageDraw.Draw(image)

        track = read_nowplaying()
        ssid, signal, _, ip = self.status_lines()
        pen.text((20, 8), ip, font=font(13), fill=theme["muted"])
        moon = quiet_hours(now.hour)
        wifi_cx = (398 if moon else 420) if track else (420 if moon else 442)
        pen.text((wifi_cx - 18, 8), truncate(ssid, 18), font=font(13), fill=theme["muted"], anchor="ra")
        draw_wifi_icon(pen, wifi_cx, 20, signal, theme["ink"], theme["muted"])
        if moon:
            draw_moon_icon(image, wifi_cx + 26, 15, theme["ink"])
        if track:
            draw_source_badge(image, 440, 8, track.get("source"), theme["ink"], theme["bg"])

        draw_clock(pen, 240, 118, font(96, bold=True), now, theme["ink"])
        pen.text((240, 182), now.strftime("%A, %-d %B"), font=font(17), fill=theme["muted"], anchor="ma")
        self.draw_speech_ripple(pen, 154, 220, theme["muted"])

        pen.rounded_rectangle((20, 220, 235, 300), radius=16, fill=theme["card"])
        if self.temperature is not None:
            _, kind, color = self.condition
            draw_weather_icon(pen, 52, 258, kind, color, night)
            pen.text((84, 236), f"{self.temperature}°C", font=font(30, bold=True), fill=theme["ink"])
            pen.text((86, 272), self.city or "", font=font(13), fill=theme["muted"])
        else:
            pen.text((40, 250), "Weather unavailable", font=font(14), fill=theme["muted"])

        pen.rounded_rectangle((245, 220, 460, 300), radius=16, fill=theme["card"])
        if track:
            self.step_vu()
            for i, height in enumerate(self.vu):
                x = 262 + i * 8
                pen.rectangle((x, 254 - height, x + 5, 254), fill=theme["ink"])

            artist = track.get("artist", "")
            title = track["title"]
            title_font, sub_font = font(16, bold=True), font(13)
            region_w = 150

            strip = Image.new("RGB", (region_w, 24), theme["card"])
            strip_pen = ImageDraw.Draw(strip)
            title_w = strip_pen.textlength(title, font=title_font)
            sep_w = 15 if artist else 0
            artist_w = strip_pen.textlength(artist, font=sub_font) if artist else 0

            offset = self.marquee_offset(title + artist, title_w + sep_w + artist_w - region_w)
            sx = -int(offset)
            ascent = title_font.getmetrics()[0]
            sub_ascent = sub_font.getmetrics()[0]
            strip_pen.text((sx, 0), title, font=title_font, fill=theme["ink"])
            if artist:
                dot_x = sx + int(title_w) + 6
                strip_pen.ellipse((dot_x, ascent - 5, dot_x + 3, ascent - 2), fill=theme["muted"])
                strip_pen.text((dot_x + 9, ascent - sub_ascent), artist, font=sub_font, fill=theme["muted"])
            image.paste(strip, (292, 254 - ascent))

            duration = track.get("duration") or 0
            if duration:
                elapsed = min(duration, (track.get("elapsed") or 0)
                              + max(0.0, time.time() - (track.get("anchor") or time.time())))
                clock = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}/{int(duration // 60)}:{int(duration % 60):02d}"
                small_font = font(12)
                bar_end = int(442 - pen.textlength(clock, font=small_font) - 8)
                pen.rectangle((262, 274, bar_end, 282), outline=theme["muted"], width=1)
                pen.rectangle((264, 276, 264 + int((bar_end - 266) * elapsed / duration), 280), fill=theme["ink"])
                pen.text((442, 278), clock, font=small_font, fill=theme["muted"], anchor="rm")
        else:
            temp = f"{self.cpu_temp}°C" if self.cpu_temp is not None else "—"
            pen.text((262, 234), f"CPU {temp} · Up {self.uptime}", font=font(14), fill=theme["ink"])
            pen.text((262, 264), "Vol", font=font(12), fill=theme["muted"])
            pen.rectangle((300, 262, 442, 276), outline=theme["muted"], width=1)
            if self.volume is not None:
                pen.rectangle((302, 264, 302 + int(138 * self.volume / 100), 274), fill=theme["ink"])

        return image

    # ---------- terminal ----------

    def draw_boot(self, progress):
        image = Image.new("RGB", SIZE, TERM_BG)
        pen = ImageDraw.Draw(image)
        line_font = face(FONT_MONOFONTO, 22)

        budget = int(progress * sum(len(line) + 1 for line in BOOT_LINES))
        y = 26
        for line in BOOT_LINES:
            take = min(len(line), budget)
            pen.text((28, y), line[:take], font=line_font, fill=TERM_FG)
            budget -= take + 1
            if budget <= 0:
                break
            y += 30

        if int(time.time() * 2) % 2 == 0:
            pen.text((28, min(y + 30, 280)), "▮", font=line_font, fill=TERM_FG)

        return image

    def draw_terminal(self, now):
        if time.time() < self.boot_until:
            return self.draw_boot(1 - (self.boot_until - time.time()) / BOOT_SECONDS)

        image = Image.new("RGB", SIZE, TERM_BG)
        pen = ImageDraw.Draw(image)

        mascot = self.mascot_image()
        if mascot:
            image.paste(mascot, (20 + (118 - mascot.width) // 2, 210 - mascot.height), mascot)

        track = read_nowplaying()
        ssid, signal, _, ip = self.status_lines()
        moon = quiet_hours(now.hour)
        wifi_cx = (400 if moon else 422) if track else (422 if moon else 444)
        pen.text((20, 6), ip, font=face(FONT_MONOFONTO, 17), fill=TERM_DIM)
        pen.text((wifi_cx - 18, 6), truncate(ssid.upper(), 16), font=face(FONT_MONOFONTO, 17),
                 fill=TERM_DIM, anchor="ra")
        draw_wifi_icon(pen, wifi_cx, 19, signal, TERM_FG, TERM_DIM, strength_colors=False)
        if moon:
            draw_moon_icon(image, wifi_cx + 26, 14, TERM_FG)

        if track:
            draw_source_badge(image, 442, 6, track.get("source"), TERM_FG, TERM_BG)

        clock_font = face(FONT_MONOFONTO, 118)
        half = pen.textlength(":", font=clock_font) / 2
        clock_cx = 452 - half - pen.textlength(now.strftime("%M"), font=clock_font)
        draw_clock(pen, clock_cx, 92, clock_font, now, TERM_FG)
        self.draw_speech_ripple(pen, 272, 185, TERM_DIM)
        pen.text((452, 158), now.strftime("%A, %-d %B").upper(), font=face(FONT_MONOFONTO, 22),
                 fill=TERM_DIM, anchor="ra")

        if track and track.get("device"):
            pen.text((452, 190), truncate(f"FROM {track['device']}", 26).upper(),
                     font=face(FONT_MONOFONTO, 15), fill=TERM_DIM, anchor="ra")

        for box in ((20, 222, 225, 302), (237, 222, 460, 302)):
            pen.rectangle(box, outline=TERM_DIM, width=1)

        if self.temperature is not None:
            _, city = self.weather_line()
            _, kind, _ = self.condition
            draw_weather_icon(pen, 48, 258, kind, TERM_FG, is_night(now.hour),
                              moon_fill=TERM_FG, moon_bg=TERM_BG, bolt_fill=TERM_FG)
            pen.text((82, 232), f"{self.temperature}°C", font=face(FONT_MONOFONTO, 44), fill=TERM_FG)
            pen.text((84, 276), city.upper(), font=face(FONT_MONOFONTO, 17), fill=TERM_DIM)

        if track:
            self.step_vu()
            for i, height in enumerate(self.vu):
                x = 254 + i * 8
                pen.rectangle((x, 256 - height, x + 5, 256), fill=TERM_FG)

            artist = track.get("artist", "").upper()
            title = track["title"].upper()
            title_font, artist_font = face(FONT_MONOFONTO, 18), face(FONT_MONOFONTO, 16)
            region_w = 166

            strip = Image.new("RGB", (region_w, 24), TERM_BG)
            strip_pen = ImageDraw.Draw(strip)
            title_w = strip_pen.textlength(title, font=title_font)
            sep_w = 17 if artist else 0
            artist_w = strip_pen.textlength(artist, font=artist_font) if artist else 0

            total = int(title_w + sep_w + artist_w)
            overflow = total - region_w
            offset = self.marquee_offset(title + artist, overflow)

            ascent = title_font.getmetrics()[0]
            sub_ascent = artist_font.getmetrics()[0]
            sx = -int(offset)
            strip_pen.text((sx, 0), title, font=title_font, fill=TERM_FG)
            if artist:
                dot_x = sx + int(title_w) + 7
                strip_pen.ellipse((dot_x, ascent - 5, dot_x + 3, ascent - 2), fill=TERM_DIM)
                strip_pen.text((dot_x + 10, ascent - sub_ascent), artist, font=artist_font, fill=TERM_DIM)
            image.paste(strip, (282, 256 - ascent))

            duration = track.get("duration") or 0
            if duration:
                elapsed = (track.get("elapsed") or 0) + max(0.0, time.time() - (track.get("anchor") or time.time()))
                elapsed = min(duration, elapsed)
                clock = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}/{int(duration // 60)}:{int(duration % 60):02d}"
                clock_font = face(FONT_MONOFONTO, 15)
                bar_end = int(444 - pen.textlength(clock, font=clock_font) - 10)
                pen.rectangle((252, 272, bar_end, 280), outline=TERM_DIM, width=1)
                pen.rectangle((254, 274, 254 + int((bar_end - 256) * elapsed / duration), 278), fill=TERM_FG)
                pen.text((444, 276), clock, font=clock_font, fill=TERM_DIM, anchor="rm")
        else:
            temp = f"{self.cpu_temp}°C" if self.cpu_temp is not None else "—"
            pen.text((252, 232), f"CPU {temp}  ·  UP {self.uptime}",
                     font=face(FONT_MONOFONTO, 18), fill=TERM_FG)
            pen.text((252, 260), "VOL", font=face(FONT_MONOFONTO, 17), fill=TERM_DIM)
            pen.rectangle((296, 262, 444, 276), outline=TERM_DIM, width=1)
            if self.volume is not None:
                pen.rectangle((298, 264, 298 + int(144 * self.volume / 100), 274), fill=TERM_FG)

        return image

    def mascot_image(self):
        try:
            stamp = MASCOT_FILE.stat().st_mtime
        except OSError:
            return None
        if self._mascot and self._mascot[0] == stamp:
            return self._mascot[1]

        source = Image.open(MASCOT_FILE).convert("LA").transpose(Image.FLIP_LEFT_RIGHT)
        source.thumbnail((118, 168))
        pixels = np.asarray(source, dtype=np.float32)
        gray, alpha = pixels[..., 0], pixels[..., 1]

        if alpha.min() >= 250 and gray.mean() > 170:
            # opaque line art on white: key out the white, lines glow green
            alpha = 255 - gray
            shade = np.ones_like(gray)[..., None]
        else:
            shade = (gray / 255)[..., None]
            opaque = alpha > 128
            if opaque.any() and gray[opaque].mean() < 100:
                # dark line art on transparency: invert so lines glow
                shade = 1 - shade

        rgb = (np.array(TERM_BG) + (np.array(TERM_FG) - np.array(TERM_BG)) * shade).astype(np.uint8)
        rgba = np.dstack([rgb, alpha.astype(np.uint8)])

        image = Image.fromarray(rgba, "RGBA")
        self._mascot = (stamp, image)
        return image

    def neon_mascot_image(self):
        try:
            stamp = NEON_MASCOT_FILE.stat().st_mtime
        except OSError:
            return None
        if self._neon_mascot and self._neon_mascot[0] == stamp:
            return self._neon_mascot[1]

        image = Image.open(NEON_MASCOT_FILE).convert("RGBA")
        pixels = np.asarray(image, dtype=np.uint8).copy()
        if pixels[..., 3].min() >= 250:
            # opaque art on a white canvas: key the white out, soft-edged
            whiteness = pixels[..., :3].min(axis=2).astype(np.int16)
            pixels[..., 3] = np.clip((225 - whiteness) * 6, 0, 255).astype(np.uint8)
            image = Image.fromarray(pixels, "RGBA")

        # recolor into the theme: warm tones become magenta, cool tones cyan
        pixels = np.asarray(image, dtype=np.uint8).copy()
        rgb = pixels[..., :3].astype(np.float32)
        value = (rgb.max(axis=2) / 255) ** 0.8
        warm = rgb[..., 0] > rgb[..., 2]
        palette = np.where(warm[..., None],
                           np.array(NEON_MAGENTA, np.float32),
                           np.array(NEON_CYAN, np.float32))
        pixels[..., :3] = np.clip(palette * value[..., None], 0, 255).astype(np.uint8)
        image = Image.fromarray(pixels, "RGBA")

        image.thumbnail((150, 190))
        self._neon_mascot = (stamp, image)
        return image

    # ---------- neon ----------

    def neon_background(self):
        if self._neon_bg is None:
            top, bottom = np.array((7, 2, 15)), np.array((21, 7, 50))
            ramp = np.linspace(0, 1, SIZE[1])[:, None]
            rows = (top + (bottom - top) * ramp).astype(np.uint8)
            self._neon_bg = Image.fromarray(np.repeat(rows[:, None, :], SIZE[0], axis=1))
        return self._neon_bg.copy()

    def neon_panel(self, pen, box, color, dim):
        x1, y1, x2, y2 = box
        pen.polygon(chamfer(x1 - 2, y1 - 2, x2 + 2, y2 + 2, cut=11), outline=dim, width=1)
        pen.polygon(chamfer(x1, y1, x2, y2), fill=NEON_PANEL, outline=color, width=1)

    def draw_neon(self, now):
        image = self.neon_background()
        pen = ImageDraw.Draw(image)

        track = read_nowplaying()
        ssid, signal, _, ip = self.status_lines()
        pen.text((22, 6), ip, font=face(FONT_RAJ_MED, 15), fill=NEON_MUTED)
        moon = quiet_hours(now.hour)
        wifi_cx = (396 if moon else 418) if track else (418 if moon else 440)
        pen.text((wifi_cx - 18, 6), truncate(ssid, 18), font=face(FONT_RAJ_MED, 15), fill=NEON_MUTED, anchor="ra")
        draw_wifi_icon(pen, wifi_cx, 20, signal, NEON_CYAN, NEON_MUTED, strength_colors=False)
        if moon:
            draw_moon_icon(image, wifi_cx + 26, 15, NEON_CYAN)
        if track:
            draw_source_badge(image, 438, 8, track.get("source"), NEON_CYAN, image.getpixel((446, 16)))

        self.neon_mascot_rect = None
        mascot = self.neon_mascot_image()
        if mascot:
            left = 18 + (150 - mascot.width) // 2
            image.paste(mascot, (left, 224 - mascot.height), mascot)
            self.neon_mascot_rect = (left, 224 - mascot.height, left + mascot.width, 224)

        glow = 0.82 + 0.18 * (np.sin(time.time() * 1.8) * 0.5 + 0.5)
        cyan = tuple(int(c * glow) for c in NEON_CYAN)
        clock_font = face(FONT_RAJ_BOLD, 104)
        half_colon = pen.textlength(":", font=clock_font) / 2
        clock_cx = 452 - half_colon - pen.textlength(now.strftime("%M"), font=clock_font)
        draw_clock(pen, clock_cx, 96, clock_font, now, cyan, colon_ink=NEON_MAGENTA)
        self.draw_speech_ripple(pen, 272, 200, NEON_MAGENTA)
        date_font = face(FONT_JP, 19)
        segments = (("【", (0, 150, 170)),
                    (f"{now.month}月{now.day}日", (147, 112, 219)),
                    ("・", NEON_CYAN),
                    (WEEKDAY_KANJI[now.weekday()], NEON_MAGENTA),
                    ("】", (0, 150, 170)))
        seg_x = 452 - sum(pen.textlength(text, font=date_font) + 2 for text, _ in segments)
        for text, color in segments:
            pen.text((seg_x, 154), text, font=date_font, fill=color,
                     stroke_width=1, stroke_fill=color)
            seg_x += pen.textlength(text, font=date_font) + 2

        self.neon_panel(pen, (20, 230, 225, 302), NEON_MAGENTA, (120, 25, 60))
        self.buzz_rect = (20, 230, 225, 302)
        if self.temperature is not None:
            _, kind, color = self.condition
            draw_weather_icon(pen, 48, 262, kind, color, is_night(now.hour), moon_bg=NEON_PANEL)
            pen.text((82, 238), f"{self.temperature}°C", font=face(FONT_RAJ_BOLD, 32), fill=NEON_YELLOW)
            city = KATAKANA_CITIES.get(self.city or "", self.city or "")
            pen.text((84, 274), city, font=face(FONT_JP, 16), fill=(147, 112, 219))

        self.neon_panel(pen, (237, 230, 460, 302), NEON_CYAN, (20, 90, 105))
        if track:
            self.step_vu()
            for i, height in enumerate(self.vu):
                x = 254 + i * 8
                pen.rectangle((x, 262 - height, x + 5, 262), fill=NEON_CYAN)

            artist = track.get("artist", "")
            title = track["title"]
            title_font, sub_font = face(FONT_RAJ_BOLD, 17), face(FONT_RAJ_MED, 14)
            region_w = 150

            strip = Image.new("RGB", (region_w, 24), NEON_PANEL)
            strip_pen = ImageDraw.Draw(strip)
            title_w = strip_pen.textlength(title, font=title_font)
            sep_w = 15 if artist else 0
            artist_w = strip_pen.textlength(artist, font=sub_font) if artist else 0

            offset = self.marquee_offset(title + artist, title_w + sep_w + artist_w - region_w)
            sx = -int(offset)
            ascent = title_font.getmetrics()[0]
            sub_ascent = sub_font.getmetrics()[0]
            strip_pen.text((sx, 0), title, font=title_font, fill=NEON_INK)
            if artist:
                dot_x = sx + int(title_w) + 6
                strip_pen.ellipse((dot_x, ascent - 5, dot_x + 3, ascent - 2), fill=NEON_MUTED)
                strip_pen.text((dot_x + 9, ascent - sub_ascent), artist, font=sub_font, fill=NEON_MUTED)
            image.paste(strip, (284, 262 - ascent))

            duration = track.get("duration") or 0
            if duration:
                elapsed = min(duration, (track.get("elapsed") or 0)
                              + max(0.0, time.time() - (track.get("anchor") or time.time())))
                clock = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}/{int(duration // 60)}:{int(duration % 60):02d}"
                small_font = face(FONT_RAJ_MED, 13)
                bar_end = int(446 - pen.textlength(clock, font=small_font) - 8)
                pen.rectangle((254, 278, bar_end, 286), outline=(20, 90, 105), width=1)
                pen.rectangle((256, 280, 256 + int((bar_end - 258) * elapsed / duration), 284), fill=NEON_CYAN)
                pen.text((446, 282), clock, font=small_font, fill=NEON_MUTED, anchor="rm")
        else:
            temp = f"{self.cpu_temp}°C" if self.cpu_temp is not None else "—"
            pen.text((254, 240), f"CPU {temp} ・ 稼働 {self.uptime}", font=face(FONT_JP, 16),
                     fill=NEON_INK)
            pen.text((254, 274), "音量", font=face(FONT_JP, 15), fill=NEON_MUTED, anchor="lm")
            pen.rectangle((292, 268, 446, 280), outline=(20, 90, 105), width=1)
            if self.volume is not None:
                pen.rectangle((294, 270, 294 + int(150 * self.volume / 100), 278), fill=NEON_CYAN)

        return image

    def tv_mascot_image(self):
        try:
            stamp = TV_MASCOT_FILE.stat().st_mtime
        except OSError:
            return None
        if self._tv_mascot and self._tv_mascot[0] == stamp:
            return self._tv_mascot[1]

        image = Image.open(TV_MASCOT_FILE).convert("RGBA")
        pixels = np.asarray(image, dtype=np.uint8).copy()
        if pixels[..., 3].min() >= 250:
            # opaque art on a white canvas: key the white out, soft-edged
            whiteness = pixels[..., :3].min(axis=2).astype(np.int16)
            pixels[..., 3] = np.clip((225 - whiteness) * 6, 0, 255).astype(np.uint8)
            image = Image.fromarray(pixels, "RGBA")

        image.thumbnail((122, 150))
        self._tv_mascot = (stamp, image)
        return image

    # ---------- retro tv ----------

    def draw_retrotv(self, now):
        image = Image.new("RGB", SIZE, TV_BEZEL)
        pen = ImageDraw.Draw(image)
        pen.rounded_rectangle((8, 8, 472, 312), radius=18, fill=TV_BG)

        track = read_nowplaying()
        ssid, signal, _, ip = self.status_lines()
        pen.text((26, 12), "AV-1", font=face(FONT_DOT, 18), fill=TV_GREEN)
        pen.text((84, 14), ip, font=face(FONT_DOT, 16), fill=TV_MUTED)

        moon = quiet_hours(now.hour)
        wifi_cx = (408 if moon else 430) if track else (430 if moon else 452)
        pen.text((wifi_cx - 18, 14), truncate(ssid.upper(), 12, dots="..."), font=face(FONT_DOT, 16),
                 fill=TV_MUTED, anchor="ra")
        draw_wifi_icon(pen, wifi_cx, 31, signal, TV_GREEN, TV_EDGE, strength_colors=False)
        if moon:
            draw_moon_icon(image, wifi_cx + 26, 26, TV_GREEN)

        if track:
            draw_source_badge(image, 448, 18, track.get("source"), TV_GREEN, TV_BG)

        mascot = self.tv_mascot_image()
        if mascot:
            image.paste(mascot, (28 + (122 - mascot.width) // 2,
                                 34 + (198 - mascot.height) // 2), mascot)

        clock_font = face(FONT_DOT, 96)
        show_colon = now.second % 2 == 0
        half_colon = pen.textlength(":", font=clock_font) / 2
        clock_cx = 448 - half_colon - pen.textlength(now.strftime("%M"), font=clock_font)
        draw_clock(pen, clock_cx - 3, 92, clock_font, now, (120, 40, 40), show_colon=show_colon, stroke=1)
        draw_clock(pen, clock_cx + 3, 92, clock_font, now, (40, 90, 110), show_colon=show_colon, stroke=1)
        draw_clock(pen, clock_cx, 92, clock_font, now, TV_INK, show_colon=show_colon, stroke=1)
        date_font = face(FONT_DOT, 20)
        segments = ((f"{now.month}月{now.day}日", TV_MUTED),
                    ("（", TV_MUTED),
                    (WEEKDAY_KANJI[now.weekday()], TV_GREEN),
                    ("）", TV_MUTED))
        seg_x = 448 - sum(pen.textlength(text, font=date_font) for text, _ in segments)
        for text, color in segments:
            pen.text((seg_x, 150), text, font=date_font, fill=color,
                     stroke_width=1, stroke_fill=color)
            seg_x += pen.textlength(text, font=date_font)

        self.draw_speech_ripple(pen, 264, 195, TV_GREEN)
        bar_width = 432 / len(TV_BARS)
        for i, color in enumerate(TV_BARS):
            pen.rectangle((24 + i * bar_width, 214, 24 + (i + 1) * bar_width, 222), fill=color)

        for box in ((24, 232, 226, 300), (238, 232, 456, 300)):
            pen.rounded_rectangle(box, radius=8, fill=TV_BOX, outline=TV_EDGE, width=1)

        if self.temperature is not None:
            _, city = self.weather_line()
            _, kind, _ = self.condition
            draw_weather_icon(pen, 52, 264, kind, TV_INK, is_night(now.hour),
                              moon_fill=TV_INK, moon_bg=TV_BOX, bolt_fill=TV_INK)
            pen.text((86, 246), f"{self.temperature}°C", font=face(FONT_DOT, 20), fill=TV_GREEN,
                     stroke_width=1, stroke_fill=TV_GREEN)
            city_jp = KATAKANA_CITIES.get(city or "", (city or "").upper())
            pen.text((88, 276), city_jp, font=face(FONT_DOT, 15), fill=TV_MUTED,
                     stroke_width=1, stroke_fill=TV_MUTED)

        if track:
            self.step_vu()
            for i, height in enumerate(self.vu):
                x = 250 + i * 8
                pen.rectangle((x, 262 - height, x + 5, 262), fill=TV_GREEN)

            artist = track.get("artist", "").upper()
            title = track["title"].upper()
            title_font, artist_font = face(FONT_DOT, 16), face(FONT_DOT, 15)
            region_w = 164

            strip = Image.new("RGB", (region_w, 24), TV_BOX)
            strip_pen = ImageDraw.Draw(strip)
            title_w = strip_pen.textlength(title, font=title_font)
            sep_w = 15 if artist else 0
            artist_w = strip_pen.textlength(artist, font=artist_font) if artist else 0

            offset = self.marquee_offset(title + artist, title_w + sep_w + artist_w - region_w)
            x = -int(offset)
            ascent = title_font.getmetrics()[0]
            sub_ascent = artist_font.getmetrics()[0]
            strip_pen.text((x, 0), title, font=title_font, fill=TV_INK)
            if artist:
                dot_x = x + int(title_w) + 6
                strip_pen.ellipse((dot_x, ascent - 5, dot_x + 3, ascent - 2), fill=TV_MUTED)
                strip_pen.text((dot_x + 9, ascent - sub_ascent), artist, font=artist_font, fill=TV_MUTED)
            image.paste(strip, (278, 262 - ascent))

            duration = track.get("duration") or 0
            if duration:
                elapsed = (track.get("elapsed") or 0) + max(0.0, time.time() - (track.get("anchor") or time.time()))
                elapsed = min(duration, elapsed)
                clock = f"{int(elapsed // 60)}:{int(elapsed % 60):02d}/{int(duration // 60)}:{int(duration % 60):02d}"
                small_font = face(FONT_DOT, 14)
                bar_end = int(448 - pen.textlength(clock, font=small_font) - 8)
                pen.rectangle((250, 276, bar_end, 284), outline=TV_EDGE, width=1)
                pen.rectangle((252, 278, 252 + int((bar_end - 254) * elapsed / duration), 282), fill=TV_GREEN)
                pen.text((448, 280), clock, font=small_font, fill=TV_MUTED, anchor="rm")
        else:
            temp = f"{self.cpu_temp}°C" if self.cpu_temp is not None else "—"
            pen.text((250, 240), f"CPU {temp} ・ 稼働 {self.uptime}", font=face(FONT_DOT, 16), fill=TV_INK)
            pen.text((250, 274), "音量", font=face(FONT_DOT, 14), fill=TV_MUTED, anchor="lm")
            pen.rectangle((290, 268, 448, 280), outline=TV_EDGE, width=1)
            if self.volume is not None:
                pen.rectangle((292, 270, 292 + int(154 * self.volume / 100), 278), fill=TV_GREEN)

        return image

    # ---------- pipeline ----------

    def draw(self):
        now = datetime.now()
        if self.skin == "terminal":
            return self.draw_terminal(now)
        if self.skin == "neon":
            return self.draw_neon(now)
        if self.skin == "retrotv":
            image = self.draw_retrotv(now)
            if time.time() < self.tv_intro_until:
                progress = 1 - (self.tv_intro_until - time.time()) / TV_INTRO_SECONDS
                mix = 0.0 if progress < 0.55 else (progress - 0.55) / 0.45
                arr = np.asarray(image.convert("RGB"), dtype=np.float32)
                noise = np.random.randint(0, 256, (304, 464, 1), dtype=np.uint8).astype(np.float32)
                arr[8:312, 8:472] = noise * (1 - mix) + arr[8:312, 8:472] * mix
                image = Image.fromarray(arr.astype(np.uint8))
            return image
        return self.draw_classic(now)

    def apply_effects(self, arr):
        t = time.time()

        if self.skin == "terminal":
            arr[..., 0] *= 0.8
            arr[..., 2] *= 0.75
            scanlines(arr, t, dark=0.72, speed=14)
            light_band(arr, (t * 120) % 400 - 40, 18, 26)
            glitch(arr, t)
        elif self.skin == "retrotv":
            scanlines(arr, t, y0=8, y1=312, dark=0.78, speed=10)
            light_band(arr, (t * 95) % 420 - 50, 46, 22, y0=8, y1=312)
            light_band(arr, ((t * 95) + 210) % 420 - 50, 30, 12, y0=8, y1=312)
        elif self.skin == "neon":
            if t < self.neon_intro_until:
                p = 1 - (self.neon_intro_until - t) / NEON_INTRO_SECONDS
                intensity = (1 - p) ** 1.4
                shift = max(2, int(16 * intensity))
                arr[..., 0] = np.roll(arr[..., 0], -random.randint(1, shift), axis=1)
                arr[..., 2] = np.roll(arr[..., 2], random.randint(1, shift), axis=1)
                for _ in range(2 + int(9 * intensity)):
                    y = random.randint(0, 300)
                    h = random.randint(4, 18)
                    reach = int(6 + 40 * intensity)
                    arr[y:y + h] = np.roll(arr[y:y + h], random.randint(-reach, reach), axis=1)
                if random.random() < 0.45 * intensity:
                    jump = int(8 + 30 * intensity)
                    arr[:] = np.roll(arr, random.randint(-jump, jump), axis=0)
                arr *= 1 - 0.30 * intensity * random.random()
                return

            if self.buzz_rect:
                phase = t % 6.5
                if 4.95 <= phase <= 5.08 or 5.22 <= phase <= 5.36:
                    x1, y1, x2, y2 = self.buzz_rect
                    arr[y1:y2, x1:x2] *= 0.66

            if self.neon_mascot_rect and t % 4.5 < 0.42:
                x1, y1, x2, y2 = self.neon_mascot_rect
                region = arr[y1:y2, x1:x2]
                region[..., 0] = np.roll(region[..., 0], -random.randint(2, 7), axis=1)
                region[..., 2] = np.roll(region[..., 2], random.randint(2, 7), axis=1)
                for _ in range(3):
                    y = random.randint(0, max(1, (y2 - y1) - 14))
                    h = random.randint(4, 12)
                    region[y:y + h] = np.roll(region[y:y + h], random.randint(-16, 16), axis=1)

    def on_tap(self, x, y):
        for name, (x1, y1, x2, y2) in self.buttons.items():
            if x1 <= x <= x2 and y1 <= y <= y2:
                if name == "playpause":
                    now = read_nowplaying() or {}
                    send_remote("Pause" if now.get("playing") else "Play")
                else:
                    send_remote(name.capitalize())
                self.dirty.set()
                return

    def draw_farewell(self, kind):
        title, sub = FAREWELL[kind][self.skin]
        now = datetime.now()

        if self.skin == "terminal":
            image = Image.new("RGB", SIZE, TERM_BG)
            pen = ImageDraw.Draw(image)
            pen.text((240, 142), title, font=face(FONT_MONOFONTO, 30), fill=TERM_FG, anchor="mm")
            pen.text((240, 184), sub, font=face(FONT_MONOFONTO, 17), fill=TERM_DIM, anchor="mm")
        elif self.skin == "neon":
            image = Image.new("RGB", SIZE, (10, 3, 22))
            pen = ImageDraw.Draw(image)
            pen.text((240, 140), title, font=face(FONT_RAJ_BOLD, 44), fill=NEON_CYAN, anchor="mm")
            pen.text((240, 190), sub, font=face(FONT_JP, 20), fill=NEON_MAGENTA, anchor="mm")
        elif self.skin == "retrotv":
            image = Image.new("RGB", SIZE, TV_BEZEL)
            pen = ImageDraw.Draw(image)
            pen.rounded_rectangle((8, 8, 472, 312), radius=18, fill=TV_BG)
            title_font = face(FONT_DOT, 30)
            for dx, color in ((-3, (120, 40, 40)), (3, (40, 90, 110)), (0, TV_INK)):
                pen.text((240 + dx, 136), title, font=title_font, fill=color, anchor="mm",
                         stroke_width=1, stroke_fill=color)
            pen.text((240, 180), sub, font=face(FONT_DOT, 18), fill=TV_MUTED, anchor="mm")
            bar_width = 432 / len(TV_BARS)
            for i, color in enumerate(TV_BARS):
                pen.rectangle((24 + i * bar_width, 236, 24 + (i + 1) * bar_width, 262), fill=color)
        else:
            night = theme_mode() == "dark" or (theme_mode() == "auto" and is_night(now.hour))
            theme = NIGHT if night else DAY
            image = Image.new("RGB", SIZE, theme["bg"])
            pen = ImageDraw.Draw(image)
            pen.text((240, 145), title, font=font(30, bold=True), fill=theme["ink"], anchor="mm")
            pen.text((240, 185), sub, font=font(16), fill=theme["muted"], anchor="mm")

        return image

    def show(self):
        self.blit(self.draw())

    def draw_speech_ripple(self, pen, x0, cy, color):
        if time.time() >= self.announcing_until:
            return

        for i in range(24):
            x = x0 + i * 7.5
            rise = 2 + 4 * abs(np.sin(time.time() * 7 + i * 0.9))
            pen.line((x, cy - rise, x, cy + rise), fill=color, width=2)

    def absolute_to_design(self, device, raw_x, raw_y):
        import evdev

        info_x = device.absinfo(evdev.ecodes.ABS_X)
        info_y = device.absinfo(evdev.ecodes.ABS_Y)
        x = (raw_x - info_x.min) / max(1, info_x.max - info_x.min) * SIZE[0]
        y = (raw_y - info_y.min) / max(1, info_y.max - info_y.min) * SIZE[1]

        return min(max(x, 0), SIZE[0]), min(max(y, 0), SIZE[1])

    def blit(self, image):
        arr = np.asarray(image.convert("RGB"), dtype=np.float32)
        self.apply_effects(arr)
        arr = np.clip(arr, 0, 255).astype(np.uint8)

        if self.spi_panel:
            arr = arr[::-1, ::-1]  # panel is mounted upside-down in the 3B case

        if (self.fb_w, self.fb_h) != SIZE:
            arr = np.asarray(Image.fromarray(arr).resize((self.fb_w, self.fb_h), Image.BILINEAR))

        if self.fb_bpp == 32:
            frame = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
            frame[..., 0], frame[..., 1], frame[..., 2] = arr[..., 2], arr[..., 1], arr[..., 0]
            frame = frame.tobytes()
        else:
            wide = arr.astype(np.uint16)
            r, g, b = wide[..., 0], wide[..., 1], wide[..., 2]
            frame = (((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).astype("<u2").tobytes()

        try:
            self.fb.write_bytes(frame)
        except OSError:
            self.fb, self.spi_panel = find_display_fb()
            self.fb.write_bytes(frame)


CADENCE = {"terminal": 0.14, "retrotv": 0.14, "neon": 0.18}


def main():
    panel = Panel()
    write_chime_wav()
    install_farewell(panel)
    threading.Thread(target=touch_loop, args=(panel,), daemon=True).start()

    while True:
        panel.tick()
        panel.show()
        panel.dirty.wait(timeout=CADENCE.get(panel.skin, 1))
        panel.dirty.clear()


if __name__ == "__main__":
    main()
