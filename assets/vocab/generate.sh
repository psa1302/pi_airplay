#!/usr/bin/env bash
# Renders the vocabulary audio (Mac only: `say` with the Kyoko voice + ffmpeg).
# One clip per word: the word, three seconds of silence, then its example
# sentence - loudness-matched exactly like the hourly announcements (gain by
# measurement to a hot mean level, tanh soft-clip, lift to -1.5 dBFS) so both
# sit at the same volume behind the announcement slider.
#
# Output: audio/NNNN.wav at 22.05 kHz mono (~180 MB, gitignored, resumable -
# existing clips are skipped). Then sync to the speaker:
#   rsync -a audio/ pi@airplay-pi.local:/tmp/vocab-audio/
#   ssh pi@airplay-pi.local 'sudo rsync -a /tmp/vocab-audio/ /opt/pi-speakers/vocab/audio/ && rm -r /tmp/vocab-audio'
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/audio"
TARGET_MEAN_DB=-12        # volumedetect mean_volume before clipping, same as assets/voice
JOBS=${JOBS:-6}

python3 "$HERE/build.py"
mkdir -p "$OUT"

mean_db() {
  ffmpeg -i "$1" -af volumedetect -f null - 2>&1 | sed -n 's/.*mean_volume: \(-*[0-9.]*\) dB/\1/p'
}

peak_db() {
  ffmpeg -i "$1" -af volumedetect -f null - 2>&1 | sed -n 's/.*max_volume: \(-*[0-9.]*\) dB/\1/p'
}

render_speech() {   # text out.wav
  local work; work="$(mktemp -d)"
  say -v Kyoko -o "$work/say.wav" --data-format=LEI16@22050 "$1"

  local gain; gain=$(echo "$TARGET_MEAN_DB - $(mean_db "$work/say.wav")" | bc)
  ffmpeg -y -loglevel error -i "$work/say.wav" \
    -af "volume=${gain}dB,asoftclip=type=tanh:threshold=0.45:output=1" \
    -ac 1 -sample_fmt s16 "$work/clipped.wav"

  local lift; lift=$(echo "-1.5 - $(peak_db "$work/clipped.wav")" | bc)
  ffmpeg -y -loglevel error -i "$work/clipped.wav" -af "volume=${lift}dB" -ac 1 -sample_fmt s16 "$2"
  rm -rf "$work"
}

render_word() {     # id word-reading example-sentence
  local out="$OUT/$1.wav"
  [ -s "$out" ] && return 0

  local work; work="$(mktemp -d)"
  render_speech "$2" "$work/word.wav"
  render_speech "$3" "$work/sentence.wav"
  ffmpeg -y -loglevel error -i "$work/word.wav" -i "$work/sentence.wav" \
    -filter_complex "[0]apad=pad_dur=3[word];[word][1]concat=n=2:v=0:a=1" \
    -ar 22050 -ac 1 -sample_fmt s16 "$work/clip.wav"
  mv "$work/clip.wav" "$out"            # only complete clips count as done on a rerun
  rm -rf "$work"
}

export -f render_word render_speech mean_db peak_db
export OUT TARGET_MEAN_DB

python3 -c '
import json, sys
for word in json.load(open(sys.argv[1])):
    print(word["id"], word["speech"], word["example"], sep="\0", end="\0")
' "$HERE/n4.json" | xargs -0 -P "$JOBS" -n 3 bash -c 'set -euo pipefail; render_word "$@"' _

echo "$(ls "$OUT"/*.wav | wc -l | tr -d ' ') clips in $OUT"
ffmpeg -i "$OUT/0001.wav" -af "ebur128=peak=true" -f null - 2>&1 | grep -E "I:|Peak:" | tail -2
