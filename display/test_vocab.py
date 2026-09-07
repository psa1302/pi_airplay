import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import vocab

WORDS = [{"id": f"{n:04d}", "word": f"w{n}", "kana": f"k{n}", "english": f"e{n}",
          "example": "x。", "example_kana": "x。", "example_english": "x"} for n in range(1, 6)]
T0 = datetime(2026, 9, 7, 10, 15)


def at(hours=0, minutes=0):
    return datetime.fromtimestamp(T0.timestamp() + hours * 3600 + minutes * 60)


def shown(state, word_id, when, is_new=False):
    vocab.record_showing(state, word_id, when, is_new)


class Slots(unittest.TestCase):
    def test_quarter_hours_fire_but_not_the_top_of_the_hour(self):
        self.assertEqual(vocab.slot_key(T0, 15), "2026-09-07 10:15")
        self.assertEqual(vocab.slot_key(at(minutes=15), 15), "2026-09-07 10:30")
        self.assertEqual(vocab.slot_key(at(minutes=30), 15), "2026-09-07 10:45")
        self.assertIsNone(vocab.slot_key(at(minutes=45), 15))

    def test_longer_intervals_avoid_the_top_of_the_hour(self):
        self.assertEqual(vocab.slot_key(T0, 30), "2026-09-07 10:15")
        self.assertIsNone(vocab.slot_key(at(minutes=15), 30))
        self.assertEqual(vocab.slot_key(at(minutes=30), 30), "2026-09-07 10:45")
        self.assertIsNone(vocab.slot_key(T0, 60))
        self.assertEqual(vocab.slot_key(at(minutes=15), 60), "2026-09-07 10:30")

    def test_next_slot(self):
        self.assertEqual(vocab.next_slot(datetime(2026, 9, 7, 10, 3), 15), datetime(2026, 9, 7, 10, 15))
        self.assertEqual(vocab.next_slot(datetime(2026, 9, 7, 10, 50), 15), datetime(2026, 9, 7, 11, 15))
        self.assertEqual(vocab.next_slot(datetime(2026, 9, 7, 23, 46), 30), datetime(2026, 9, 8, 0, 15))

    def test_card_slot_marks_the_slot_a_loaded_card_came_from(self):
        card = vocab.stamp({"id": "0001"}, T0.timestamp())
        self.assertEqual(vocab.card_slot(card, 15), "2026-09-07 10:15")
        self.assertIsNone(vocab.card_slot(vocab.stamp({"id": "0001"}, at(minutes=3).timestamp()), 15))
        self.assertIsNone(vocab.card_slot(None, 15))


class Picking(unittest.TestCase):
    def test_fresh_state_starts_with_the_first_word(self):
        word, is_new = vocab.pick(WORDS, vocab.empty_state(), T0, quota=10)
        self.assertEqual((word["id"], is_new), ("0001", True))

    def test_new_words_follow_list_order_and_respect_the_quota(self):
        state = vocab.empty_state()
        picked = []
        for slot in range(4):
            word, is_new = vocab.pick(WORDS, state, at(minutes=15 * slot), quota=2)
            if word:
                shown(state, word["id"], at(minutes=15 * slot), is_new)
            picked.append(word and word["id"])
        self.assertEqual(picked, ["0001", "0002", None, None])

    def test_a_shown_word_comes_back_after_an_hour_as_a_review(self):
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        self.assertEqual(vocab.pick(WORDS, state, at(minutes=45), quota=0), (None, False))
        word, is_new = vocab.pick(WORDS, state, at(hours=1), quota=0)
        self.assertEqual((word["id"], is_new), ("0001", False))

    def test_reviews_and_new_words_interleave(self):
        state = vocab.empty_state()
        for n in (1, 2, 3):
            shown(state, f"{n:04d}", at(hours=-24))
        kinds = []
        for slot in range(5):
            word, is_new = vocab.pick(WORDS, state, at(minutes=15 * slot), quota=10)
            shown(state, word["id"], at(minutes=15 * slot), is_new)
            kinds.append("new" if is_new else word["id"])
        self.assertEqual(kinds, ["new", "0001", "new", "0002", "0003"])

    def test_earliest_due_review_first(self):
        state = vocab.empty_state()
        shown(state, "0003", at(hours=-3))
        shown(state, "0002", at(hours=-5))
        word, _ = vocab.pick(WORDS, state, T0, quota=0)
        self.assertEqual(word["id"], "0002")

    def test_new_words_wait_while_the_review_backlog_is_large(self):
        words = [{"id": f"{n:04d}"} for n in range(1, 30)]
        state = vocab.empty_state()
        for n in range(1, vocab.REVIEW_BACKLOG_LIMIT + 2):
            shown(state, f"{n:04d}", at(hours=-24))
        word, is_new = vocab.pick(words, state, T0, quota=10)
        self.assertFalse(is_new)
        shown(state, word["id"], T0)
        word, is_new = vocab.pick(words, state, at(minutes=15), quota=10)
        self.assertTrue(is_new)

    def test_state_for_words_missing_from_the_list_is_ignored(self):
        state = vocab.empty_state()
        shown(state, "9999", at(hours=-24))
        self.assertEqual(vocab.pick([], state, T0, quota=10), (None, False))
        word, is_new = vocab.pick(WORDS, state, T0, quota=10)
        self.assertEqual((word["id"], is_new), ("0001", True))


class Spacing(unittest.TestCase):
    def test_intervals_expand_and_cap(self):
        state = vocab.empty_state()
        waits = []
        for step in range(9):
            shown(state, "0001", T0)
            waits.append(state["cards"]["0001"]["due"] - T0.timestamp())
        self.assertEqual(waits[:7], list(vocab.STEPS))
        self.assertEqual(waits[7:], [vocab.STEPS[-1]] * 2)
        self.assertEqual(state["cards"]["0001"]["seen"], 9)

    def test_new_quota_resets_each_day(self):
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        vocab.roll_day(state, T0)
        self.assertEqual(state["new_today"], 1)
        vocab.roll_day(state, at(hours=24))
        self.assertEqual(state["new_today"], 0)

    def test_stats_are_a_pure_read(self):
        state = vocab.empty_state()
        shown(state, "0001", at(hours=-2), is_new=True)
        shown(state, "0002", T0, is_new=True)
        before = dict(state)
        self.assertEqual(vocab.stats(WORDS, state, T0), {"new_today": 2, "due": 1, "seen": 2, "total": 5})
        self.assertEqual(vocab.stats(WORDS, state, at(hours=24))["new_today"], 0)
        self.assertEqual(state, before)

    def test_review_counter_starts_at_one_and_caps(self):
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        self.assertEqual(vocab.card_for(WORDS[0], True, state)["step"], 0)
        shown(state, "0001", at(hours=1))
        self.assertEqual(vocab.card_for(WORDS[0], False, state)["step"], 1)
        for _ in range(10):
            shown(state, "0001", at(hours=1))
        self.assertEqual(vocab.card_for(WORDS[0], False, state)["step"], len(vocab.STEPS))


class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        self.saved = (vocab.STATE_FILE, vocab.CARD_FILE, vocab.COMMAND_FILE)
        vocab.STATE_FILE, vocab.CARD_FILE, vocab.COMMAND_FILE = (base / "srs.json", base / "card.json", base / "cmd")

    def tearDown(self):
        vocab.STATE_FILE, vocab.CARD_FILE, vocab.COMMAND_FILE = self.saved
        self.dir.cleanup()

    def test_state_round_trip_and_missing_file(self):
        self.assertEqual(vocab.load_state(), vocab.empty_state())
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        vocab.save_state(state)
        self.assertEqual(vocab.load_state(), state)

    def test_card_round_trip(self):
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        card = vocab.stamp(vocab.card_for(WORDS[0], True, state), T0.timestamp())
        vocab.publish_card(card)
        self.assertEqual(vocab.load_card(), card)
        self.assertEqual(card["until"] - card["shown_at"], vocab.CARD_SECONDS)
        self.assertEqual((card["step"], card["steps"], card["new"], card["kana"]), (0, 7, True, "k1"))

    def test_kana_is_blank_when_it_repeats_the_word(self):
        state = vocab.empty_state()
        shown(state, "0001", T0, is_new=True)
        card = vocab.card_for({**WORDS[0], "kana": "w1"}, True, state)
        self.assertEqual(card["kana"], "")

    def test_malformed_card_files_are_ignored(self):
        for text in ("", "[1, 2]", '{"word": "x"}', "{bad json"):
            vocab.CARD_FILE.write_text(text)
            self.assertIsNone(vocab.load_card())

    def test_commands_are_consumed_once_and_validated(self):
        self.assertIsNone(vocab.take_command())
        vocab.send_command("again")
        self.assertEqual(vocab.take_command(), "again")
        self.assertIsNone(vocab.take_command())
        with self.assertRaises(ValueError):
            vocab.send_command("grade")
        vocab.COMMAND_FILE.write_text("rm -rf")
        self.assertIsNone(vocab.take_command())


if __name__ == "__main__":
    unittest.main()
