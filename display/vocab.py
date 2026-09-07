#!/usr/bin/env python3
"""Passive N4 vocabulary drill: which card to show at which slot, and its spaced-repetition state."""
import json
from datetime import datetime, timedelta
from pathlib import Path

WORDS_FILE = Path("/opt/pi-speakers/vocab/n4.json")
AUDIO_DIR = Path("/opt/pi-speakers/vocab/audio")
STATE_FILE = Path("/var/lib/pi-speakers/vocab-srs.json")
ENABLED_FILE = Path("/var/lib/pi-speakers/vocab")
INTERVAL_FILE = Path("/var/lib/pi-speakers/vocab-interval")
NEW_PER_DAY_FILE = Path("/var/lib/pi-speakers/vocab-new-per-day")
CARD_FILE = Path("/run/pi-speakers/vocab.json")
COMMAND_FILE = Path("/run/pi-speakers/vocab-cmd")

HOUR, DAY = 3600, 86400
STEPS = (HOUR, 4 * HOUR, DAY, 3 * DAY, 7 * DAY, 14 * DAY, 30 * DAY)
SLOT_MINUTES = {15: (15, 30, 45), 30: (15, 45), 60: (30,)}      # :00 belongs to the time signal
MAX_NEW_PER_DAY = 30
REVIEW_BACKLOG_LIMIT = 8          # new words wait while more reviews than this are overdue
CARD_SECONDS = 45
COMMANDS = ("again", "next")
CARD_FIELDS = ("id", "word", "kana", "english", "example", "example_kana", "example_english")
CARD_KEYS = CARD_FIELDS + ("new", "step", "steps", "shown_at", "until")


# ---------- settings ----------

def enabled():
    try:
        return ENABLED_FILE.read_text().strip() != "off"
    except OSError:
        return True


def interval():
    try:
        minutes = int(INTERVAL_FILE.read_text().strip())
    except (OSError, ValueError):
        return 15
    return minutes if minutes in SLOT_MINUTES else 15


def new_per_day():
    try:
        return clamp_new_per_day(int(NEW_PER_DAY_FILE.read_text().strip()))
    except (OSError, ValueError):
        return 10


def clamp_new_per_day(count):
    return min(MAX_NEW_PER_DAY, max(0, count))


def set_enabled(on):
    ENABLED_FILE.write_text("on" if on else "off")


def set_interval(minutes):
    if minutes not in SLOT_MINUTES:
        raise ValueError("interval must be 15, 30 or 60 minutes")
    INTERVAL_FILE.write_text(str(minutes))


def set_new_per_day(count):
    NEW_PER_DAY_FILE.write_text(str(clamp_new_per_day(count)))


# ---------- words and state ----------

def load_words():
    try:
        return json.loads(WORDS_FILE.read_text())
    except (OSError, ValueError):
        return []


def audio_path(card):
    return AUDIO_DIR / f"{card['id']}.wav"


def empty_state():
    return {"cards": {}, "new_day": "", "new_today": 0, "last_kind": "review"}


def load_state():
    try:
        state = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return empty_state()
    return {**empty_state(), **state}


def write_atomic(path, text):
    temp = path.with_suffix(".tmp")
    temp.write_text(text)
    temp.replace(path)


def save_state(state):
    write_atomic(STATE_FILE, json.dumps(state))


# ---------- scheduling ----------

def slot_key(now, minutes):
    if now.minute not in SLOT_MINUTES[minutes]:
        return None
    return now.strftime("%Y-%m-%d %H:%M")


def day_of(now):
    return now.strftime("%Y-%m-%d")


def roll_day(state, now):
    if state["new_day"] != day_of(now):
        state["new_day"], state["new_today"] = day_of(now), 0


def due_ids(state, now_ts):
    cards = state["cards"]
    return sorted((card_id for card_id in cards if cards[card_id]["due"] <= now_ts),
                  key=lambda card_id: cards[card_id]["due"])


def next_new(words, state):
    return next((word for word in words if word["id"] not in state["cards"]), None)


def pick(words, state, now, quota):
    """The card for this slot: due reviews and new words interleaved, reviews otherwise."""
    roll_day(state, now)
    by_id = {word["id"]: word for word in words}
    due = [card_id for card_id in due_ids(state, now.timestamp()) if card_id in by_id]
    new_allowed = state["new_today"] < quota and len(due) <= REVIEW_BACKLOG_LIMIT
    fresh = next_new(words, state) if new_allowed else None

    if fresh and (not due or state["last_kind"] == "review"):
        return fresh, True
    if due:
        return by_id[due[0]], False

    return None, False


def record_showing(state, word_id, now, is_new):
    roll_day(state, now)
    card = state["cards"].get(word_id, {"step": 0, "seen": 0})
    wait = STEPS[min(card["step"], len(STEPS) - 1)]

    state["cards"][word_id] = {"step": card["step"] + 1, "seen": card["seen"] + 1,
                               "due": now.timestamp() + wait, "last": now.timestamp()}
    state["last_kind"] = "new" if is_new else "review"
    if is_new:
        state["new_today"] += 1


def next_slot(now, minutes):
    candidates = [now.replace(minute=m, second=0, microsecond=0) for m in SLOT_MINUTES[minutes]]
    later = [slot for slot in candidates if slot > now]
    return later[0] if later else candidates[0] + timedelta(hours=1)


def stats(words, state, now):
    new_today = state["new_today"] if state["new_day"] == day_of(now) else 0
    return {"new_today": new_today, "due": len(due_ids(state, now.timestamp())),
            "seen": len(state["cards"]), "total": len(words)}


# ---------- card and commands (dashboard <-> web UI) ----------

def card_for(word, is_new, state):
    card = {key: word[key] for key in CARD_FIELDS}
    if card["kana"] == card["word"]:
        card["kana"] = ""
    reviews = state["cards"][word["id"]]["step"] - 1
    return {**card, "new": is_new, "step": min(reviews, len(STEPS)), "steps": len(STEPS)}


def stamp(card, shown_at):
    return {**card, "shown_at": shown_at, "until": shown_at + CARD_SECONDS}


def card_slot(card, minutes):
    if not card:
        return None
    return slot_key(datetime.fromtimestamp(card["shown_at"]), minutes)


def publish_card(card):
    write_atomic(CARD_FILE, json.dumps(card, ensure_ascii=False))


def load_card():
    try:
        card = json.loads(CARD_FILE.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(card, dict) or any(key not in card for key in CARD_KEYS):
        return None
    return card


def take_command():
    try:
        command = COMMAND_FILE.read_text().strip()
        COMMAND_FILE.unlink()
    except OSError:
        return None
    return command if command in COMMANDS else None


def send_command(command):
    if command not in COMMANDS:
        raise ValueError("unknown vocab command")
    write_atomic(COMMAND_FILE, command)
