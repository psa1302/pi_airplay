#!/usr/bin/env python3
"""Builds n4.json: the Shin Kanzen Master N4 word list merged with the authored examples.

    build.py            parse the list, merge examples/part-*.json, lint, write n4.json
    build.py --lint     lint the example parts only (used by the authoring loop)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCE = HERE / "shinkanzen-vocab-n4.md"        # snapshot of the study list; ids are row positions
EXAMPLES = HERE / "examples"
OUTPUT = HERE / "n4.json"

PAGE = re.compile(r"^## .*p\.(\d+)")
ROW = re.compile(r"^\| (?!漢字)(.+?) \| (.+?) \| (.+?) \| (.+?) \|$")
OPTIONAL = re.compile(r"[（(][^）)]*[）)]")
KANA_ONLY = re.compile(r"^[ぁ-ゖァ-ヺー、。！？]+$")
POLITE_END = re.compile(r"(?:です|ます|ません|でした|ました|ましょう|ください|ませんでした)(?:か|ね|よ)?。$")
BEYOND_N4 = {
    "passive/causative": r"(?:[かがさたなばまらわ](?:れ|せ)|られ|させ)(?:ます|ました|ません|て|た)",
    "ば conditional": r"[えけげせてねべめれ]ば|ければ",
    "ても": r"ても|[んい]でも",
    "のに": r"のに",
    "そうだ": r"(?<![、 ])そうです",
    "ようになる": r"ようにな",
    "すぎる": r"すぎ(?:ます|ました|て)",
    "やすい/にくい": r"[いりきしちみびにぎ](?:やすい|にくい)",
    "keigo": r"いらっしゃ|ございます|おっしゃ|いたします|申し|ご覧|いただき|伺い|なさい",
    "ておく/てしまう/てある": r"[てで](?:おき|しま(?:い|っ)|あり)",
    "んです": r"んです|のです",
    "でしょう/かもしれない/はず": r"でしょう|かもしれ|はずです",
}


def parse_words(text):
    words, page = [], None

    for line in text.splitlines():
        heading = PAGE.match(line)
        if heading:
            page = int(heading.group(1))
            continue

        row = ROW.match(line)
        if row:
            words.append(make_word(len(words) + 1, page, *row.groups()))

    return words


def make_word(number, page, word, kana, romaji, english):
    return {"id": f"{number:04d}", "page": page, "word": dedupe_variants(word),
            "kana": kana, "romaji": romaji, "english": clean_english(english),
            "speech": speech_form(kana)}


def dedupe_variants(word):
    return "、".join(dict.fromkeys(word.split("、")))


def speech_form(kana):
    return OPTIONAL.sub("", kana).replace("～", "")


def clean_english(english):
    english = english.replace("<br>", "; ")
    english = re.sub(r"\S*?\[(\S+?)\](\S*?)：", r"\1\2: ", english)
    return re.sub(r"^する：(.+)$", r"\1 (する)", english)


def conjugable(base):
    return len(base) >= 2 and re.match(r"[ぁ-ゖ]", base[-1]) is not None


def headword_needles(word):
    base = OPTIONAL.sub("", word).replace("～", "").split("、")[0]
    return {base, base[:-1]} if conjugable(base) else {base}


def without_headword(example, needles):
    for needle in sorted(needles, key=len, reverse=True):
        example = example.replace(needle, "◇")
    return example


def sentence_length(example):
    return len(re.sub(r"[。、！？!?\s]", "", example))


def lint_example(word, entry):
    example = entry.get("example", "")
    problems = []

    if not example.endswith("。") or example.count("。") != 1:
        problems.append("must be exactly one sentence ending in 。")
    if not 6 <= sentence_length(example) <= 14:
        problems.append(f"length {sentence_length(example)} outside 6-14")
    if not POLITE_END.search(example):
        problems.append("must end in polite form (です/ます family)")
    if not KANA_ONLY.match(entry.get("example_kana", "")):
        problems.append("example_kana must be kana and punctuation only (no kanji/digits/spaces)")
    if not entry.get("example_english", "").strip():
        problems.append("example_english missing")
    needles = headword_needles(word["word"])
    if not any(needle in example for needle in needles):
        problems.append(f"headword {word['word']} not found in the example")
    for name, pattern in BEYOND_N4.items():
        if re.search(pattern, without_headword(example, needles)):
            problems.append(f"grammar beyond initial N4: {name} (check, may be a false positive)")

    return problems


def load_examples(parts=None):
    examples = {}
    for part in sorted(EXAMPLES.glob("part-*.json")):
        if parts and part.stem.split("-")[1] not in parts:
            continue
        examples.update(json.loads(part.read_text()))
    return examples


def lint(words, examples):
    findings = []
    by_id = {word["id"]: word for word in words}

    for word_id, entry in examples.items():
        word = by_id.get(word_id, {"word": "?"})
        problems = lint_example(word, entry) if word_id in by_id else ["unknown word id"]
        findings.extend(f"{word_id} {word['word']}: {problem}" for problem in problems)

    return findings


def report(findings):
    print("\n".join(findings + [f"{len(findings)} finding(s)"]))


def build(words, examples):
    missing = [word["id"] for word in words if word["id"] not in examples]
    if missing:
        sys.exit(f"{len(missing)} words have no example, first: {missing[:8]}")

    merged = [{**word, **examples[word["id"]]} for word in words]
    OUTPUT.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(merged)} words written to {OUTPUT}")


def main(argv):
    words = parse_words(SOURCE.read_text())

    if argv[:1] == ["--lint"]:
        findings = lint(words, load_examples(argv[1:] or None))
        report(findings)
        sys.exit(1 if findings else 0)

    examples = load_examples()
    findings = lint(words, examples)
    if findings:
        report(findings)
        sys.exit("fix the findings above before building")
    build(words, examples)


if __name__ == "__main__":
    main(sys.argv[1:])
