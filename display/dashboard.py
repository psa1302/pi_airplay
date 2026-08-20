#!/usr/bin/env python3
"""Glanceable panel for the Waveshare 3.5" LCD: clock, weather, WiFi, EQ, themes."""
import json
import random
import re
import subprocess
import threading
import time
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
                return Path("/dev") / node.name
        except OSError:
            continue
    return Path("/dev/fb0")


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
NEON_YELLOW = (240, 225, 74)
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
MASCOT_FILE = Path("/opt/pi-speakers/mascot.png")

BOOT_LINES = ["PI-OS(R) V3.0 - PERSONAL AUDIO TERMINAL",
              "COPYRIGHT 2286 PI-TUNE INDUSTRIES",
              "LOADER V1.1",
              "EXEC AUDIO SUBSYSTEM ............ OK",
              "EXEC EQUALIZER [31Hz-16kHz] ..... OK",
              "EXEC AIRPLAY / SPOTIFY / BT ..... OK",
              "",
              "> WELCOME, OVERSEER"]
BOOT_SECONDS = 4.2

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
        return data if data.get("playing") and data.get("title") else None
    except Exception:
        return None


def send_remote(method):
    subprocess.run(["dbus-send", "--system", "--type=method_call",
                    "--dest=org.gnome.ShairportSync", "/org/gnome/ShairportSync",
                    f"org.gnome.ShairportSync.RemoteControl.{method}"],
                   capture_output=True, timeout=5)


# Measured on this panel via corner taps: raw Y runs right-to-left across the
# screen, raw X runs top-to-bottom. NOTE: display renders rotated 180 degrees,
# so if touch is re-enabled both axes must be mirrored.
RAW_Y_TO_COL = (470, 3700)
RAW_X_TO_ROW = (575, 3610)


def touch_to_screen(raw_x, raw_y):
    lo, hi = RAW_Y_TO_COL
    x = (hi - raw_y) / (hi - lo) * SIZE[0]

    lo, hi = RAW_X_TO_ROW
    y = (raw_x - lo) / (hi - lo) * SIZE[1]

    return min(max(x, 0), SIZE[0]), min(max(y, 0), SIZE[1])


def touch_loop(panel):
    import evdev

    device = None
    raw_x = raw_y = None
    touching = False
    last_tap = 0.0

    while True:
        try:
            if device is None:
                path = next((p for p in evdev.list_devices()
                             if "ADS7846" in evdev.InputDevice(p).name), None)
                if not path:
                    time.sleep(5)
                    continue
                device = evdev.InputDevice(path)

            for event in device.read_loop():
                if event.type == evdev.ecodes.EV_ABS:
                    if event.code == evdev.ecodes.ABS_X:
                        raw_x = event.value
                    elif event.code == evdev.ecodes.ABS_Y:
                        raw_y = event.value
                elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                    touching = event.value == 1
                elif (event.type == evdev.ecodes.EV_SYN and touching
                      and raw_x is not None and raw_y is not None
                      and time.time() - last_tap > 0.4):
                    last_tap = time.time()
                    x, y = touch_to_screen(raw_x, raw_y)
                    panel.on_tap(x, y)
        except Exception:
            device = None
            time.sleep(3)


def truncate(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


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


def draw_wifi_icon(pen, cx, cy, signal, ink, muted, strength_colors=True):
    bars = 3 if signal >= 70 else 2 if signal >= 45 else 1 if signal >= 20 else 0
    active = (signal_color(signal) or muted) if strength_colors else (ink if bars else muted)

    for i, radius in enumerate((5, 9, 13)):
        color = active if i < bars else muted
        pen.arc((cx - radius, cy - radius, cx + radius, cy + radius), 225, 315, fill=color, width=2)
    pen.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=active)


def draw_airplay_icon(pen, cx, cy, ink, bg):
    pen.rounded_rectangle((cx - 12, cy - 11, cx + 12, cy + 4), radius=4, outline=ink, width=2)
    pen.polygon(((cx, cy - 4), (cx + 10, cy + 12), (cx - 10, cy + 12)), fill=bg)
    pen.polygon(((cx, cy - 2), (cx + 8, cy + 11), (cx - 8, cy + 11)), fill=ink)


def draw_spotify_icon(pen, cx, cy, bg):
    pen.ellipse((cx - 12, cy - 12, cx + 12, cy + 12), fill=(30, 185, 84))
    center_y = cy + 13
    for radius in (18, 13, 8):
        pen.arc((cx - radius, center_y - radius, cx + radius, center_y + radius),
                245, 295, fill=bg, width=2)


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


def draw_clock(pen, cx, cy, clock_font, now, ink, colon_ink=None, show_colon=None):
    if show_colon is None:
        show_colon = now.second % 2 == 0
    half = pen.textlength(":", font=clock_font) / 2

    pen.text((cx - half, cy), now.strftime("%H"), font=clock_font, fill=ink, anchor="rm")
    pen.text((cx + half, cy), now.strftime("%M"), font=clock_font, fill=ink, anchor="lm")
    if show_colon:
        pen.text((cx, cy), ":", font=clock_font, fill=colon_ink or ink, anchor="mm")


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
        self.fb = find_display_fb()
        self.skin = "classic"
        self.skin_prev = None
        self.boot_until = 0
        self.cpu_temp = None
        self.uptime = "—"
        self.volume = None
        self.buzz_rect = None
        self._neon_bg = None
        self._mascot = None

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

        self.skin = read_skin()
        if self.skin == "terminal" and self.skin_prev != "terminal":
            self.boot_until = time.time() + BOOT_SECONDS
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

        draw_clock(pen, 240, 118, font(96, bold=True), now, theme["ink"])
        track = read_nowplaying()
        if track:
            airplay = track.get("source") != "spotify"
            title = truncate(track["title"], 30)
            byline = truncate(track.get("artist", ""), 38)
            title_font, byline_font = font(16, bold=True), font(13)

            text_w = max(pen.textlength(title, font=title_font),
                         pen.textlength(byline, font=byline_font) if byline else 0)
            start = max(14, 240 - (38 + text_w) / 2)

            if airplay:
                draw_airplay_icon(pen, start + 14, 192, theme["ink"], theme["bg"])
            else:
                draw_spotify_icon(pen, start + 14, 192, theme["bg"])
            pen.text((start + 38, 174), title, font=title_font, fill=theme["ink"])
            pen.text((start + 38, 197), byline, font=byline_font, fill=theme["muted"])
        else:
            pen.text((240, 182), now.strftime("%A, %-d %B"), font=font(17), fill=theme["muted"], anchor="ma")

        pen.rounded_rectangle((20, 220, 235, 300), radius=16, fill=theme["card"])
        if self.temperature is not None:
            text, kind, color = self.condition
            draw_weather_icon(pen, 52, 258, kind, color, night)
            pen.text((84, 240), f"{self.temperature}°C", font=font(32, bold=True), fill=theme["ink"])
            pen.text((148, 240), text, font=font(13), fill=color)
            pen.text((148, 260), self.city or "", font=font(13), fill=theme["muted"])
        else:
            pen.text((40, 250), "Weather unavailable", font=font(14), fill=theme["muted"])

        pen.rounded_rectangle((245, 220, 460, 300), radius=16, fill=theme["card"])
        ssid, signal, eq_line, ip = self.status_lines()
        pen.text((265, 232), ssid, font=font(14), fill=theme["ink"])
        draw_wifi_icon(pen, 436, 244, signal, theme["ink"], theme["muted"])
        pen.text((265, 254), eq_line, font=font(14), fill=theme["muted"])
        pen.text((265, 276), ip, font=font(13), fill=theme["muted"])

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
        wifi_cx = 422 if track else 444
        pen.text((20, 6), ip, font=face(FONT_MONOFONTO, 17), fill=TERM_DIM)
        pen.text((wifi_cx - 18, 6), truncate(ssid.upper(), 16), font=face(FONT_MONOFONTO, 17),
                 fill=TERM_DIM, anchor="ra")
        draw_wifi_icon(pen, wifi_cx, 19, signal, TERM_FG, TERM_DIM, strength_colors=False)

        if track:
            if track.get("source") == "spotify":
                pen.ellipse((442, 6, 458, 22), fill=(30, 185, 84))
                for radius in (11, 7):
                    pen.arc((450 - radius, 23 - 2 * radius, 450 + radius, 23),
                            245, 295, fill=TERM_BG, width=2)
            else:
                pen.rounded_rectangle((442, 6, 458, 17), radius=3, outline=TERM_FG, width=1)
                pen.polygon(((450, 11), (457, 23), (443, 23)), fill=TERM_BG)
                pen.polygon(((450, 13), (455, 22), (445, 22)), fill=TERM_FG)

        clock_font = face(FONT_MONOFONTO, 118)
        half = pen.textlength(":", font=clock_font) / 2
        clock_cx = 452 - half - pen.textlength(now.strftime("%M"), font=clock_font)
        draw_clock(pen, clock_cx, 92, clock_font, now, TERM_FG)
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

            def draw_line(x):
                strip_pen.text((x, 1), title, font=title_font, fill=TERM_FG)
                if artist:
                    dot_x = x + int(title_w) + 7
                    strip_pen.ellipse((dot_x, 11, dot_x + 3, 14), fill=TERM_DIM)
                    strip_pen.text((dot_x + 10, 4), artist, font=artist_font, fill=TERM_DIM)

            draw_line(-int(offset))
            image.paste(strip, (282, 236))

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

        glow = 0.82 + 0.18 * (np.sin(time.time() * 1.8) * 0.5 + 0.5)
        cyan = tuple(int(c * glow) for c in NEON_CYAN)
        draw_clock(pen, 240, 96, font(86, bold=True), now, cyan, colon_ink=NEON_MAGENTA)
        pen.text((240, 156), now.strftime("%A, %-d %B"), font=font(16), fill=NEON_MUTED, anchor="ma")

        track = read_nowplaying()
        if track:
            pen.text((240, 184), truncate(track["title"], 30), font=font(16, bold=True),
                     fill=NEON_INK, anchor="ma")
            pen.text((240, 205), truncate(track.get("artist", ""), 34), font=font(13),
                     fill=NEON_MUTED, anchor="ma")

        self.neon_panel(pen, (20, 230, 225, 302), NEON_MAGENTA, (120, 25, 60))
        self.buzz_rect = (20, 230, 225, 302)
        if self.temperature is not None:
            condition, city = self.weather_line()
            pen.text((38, 242), f"{self.temperature}°C", font=font(30, bold=True), fill=NEON_YELLOW)
            pen.text((104, 246), condition, font=font(13), fill=NEON_MUTED)
            pen.text((104, 266), city, font=font(13), fill=NEON_MUTED)

        self.neon_panel(pen, (237, 230, 460, 302), NEON_CYAN, (20, 90, 105))
        ssid, signal, eq_line, ip = self.status_lines()
        pen.text((254, 240), ssid, font=font(13, bold=True), fill=NEON_INK)
        draw_wifi_icon(pen, 438, 250, signal, NEON_CYAN, NEON_MUTED, strength_colors=False)
        pen.text((254, 260), eq_line, font=font(12), fill=NEON_MUTED)
        pen.text((254, 280), ip, font=font(12), fill=NEON_MUTED)

        return image

    # ---------- retro tv ----------

    def draw_retrotv(self, now):
        image = Image.new("RGB", SIZE, TV_BEZEL)
        pen = ImageDraw.Draw(image)
        pen.rounded_rectangle((8, 8, 472, 312), radius=18, fill=TV_BG)

        osd_font = face(FONT_VT323, 24)
        pen.text((26, 14), "AV-1", font=osd_font, fill=TV_GREEN)
        pen.polygon(((414, 20), (414, 34), (426, 27)), fill=TV_INK)
        pen.text((432, 14), "PLAY", font=osd_font, fill=TV_INK)

        clock_font = face(FONT_VT323, 118)
        show_colon = now.second % 2 == 0
        draw_clock(pen, 237, 92, clock_font, now, (120, 40, 40), show_colon=show_colon)
        draw_clock(pen, 243, 92, clock_font, now, (40, 90, 110), show_colon=show_colon)
        draw_clock(pen, 240, 92, clock_font, now, TV_INK, show_colon=show_colon)
        pen.text((240, 152), now.strftime("%A, %-d %B").upper(), font=face(FONT_VT323, 22),
                 fill=TV_MUTED, anchor="ma")

        track = read_nowplaying()
        if track:
            byline = truncate(track.get("artist", ""), 24)
            text = truncate(track["title"], 28) + (f" - {byline}" if byline else "")
            pen.text((240, 182), text, font=face(FONT_VT323, 22), fill=TV_INK, anchor="ma")

        bar_width = 432 / len(TV_BARS)
        for i, color in enumerate(TV_BARS):
            pen.rectangle((24 + i * bar_width, 214, 24 + (i + 1) * bar_width, 222), fill=color)

        for box in ((24, 232, 226, 300), (238, 232, 456, 300)):
            pen.rounded_rectangle(box, radius=8, fill=TV_BOX, outline=TV_EDGE, width=1)

        if self.temperature is not None:
            condition, city = self.weather_line()
            pen.text((40, 238), f"{self.temperature}°C", font=face(FONT_VT323, 44), fill=TV_INK)
            pen.text((106, 242), condition.upper(), font=face(FONT_VT323, 20), fill=TV_MUTED)
            pen.text((106, 266), city.upper(), font=face(FONT_VT323, 20), fill=TV_MUTED)

        ssid, signal, eq_line, ip = self.status_lines()
        pen.text((252, 236), truncate(ssid.upper(), 17), font=face(FONT_VT323, 20), fill=TV_INK)
        draw_wifi_icon(pen, 436, 248, signal, TV_GREEN, TV_EDGE, strength_colors=False)
        pen.text((252, 258), eq_line.upper(), font=face(FONT_VT323, 18), fill=TV_MUTED)
        pen.text((252, 278), ip, font=face(FONT_VT323, 18), fill=TV_MUTED)

        return image

    # ---------- pipeline ----------

    def draw(self):
        now = datetime.now()
        if self.skin == "terminal":
            return self.draw_terminal(now)
        if self.skin == "neon":
            return self.draw_neon(now)
        if self.skin == "retrotv":
            return self.draw_retrotv(now)
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
        elif self.skin == "neon" and self.buzz_rect:
            phase = t % 6.5
            if 4.95 <= phase <= 5.08 or 5.22 <= phase <= 5.36:
                x1, y1, x2, y2 = self.buzz_rect
                arr[y1:y2, x1:x2] *= 0.66

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

    def show(self):
        arr = np.asarray(self.draw().convert("RGB"), dtype=np.float32)
        self.apply_effects(arr)
        arr = np.clip(arr, 0, 255).astype(np.uint16)[::-1, ::-1]

        r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
        frame = (((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).astype("<u2").tobytes()
        try:
            self.fb.write_bytes(frame)
        except OSError:
            self.fb = find_display_fb()
            self.fb.write_bytes(frame)


CADENCE = {"terminal": 0.14, "retrotv": 0.14, "neon": 0.4}


def main():
    panel = Panel()
    threading.Thread(target=touch_loop, args=(panel,), daemon=True).start()

    while True:
        panel.tick()
        panel.show()
        panel.dirty.wait(timeout=CADENCE.get(panel.skin, 1))
        panel.dirty.clear()


if __name__ == "__main__":
    main()
