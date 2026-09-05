#!/usr/bin/env bash
# Regenerates the hourly announcements (Mac only: needs `say` with the Kyoko
# voice and ffmpeg). Output: assets/voice/hour-NN.wav, 24 files.
#
# What the ear hears is average level, not peak. Speech is spiky: normalized
# by peak it sounds quiet next to a pure-tone chirp. So the voice is gained by
# measurement to a target MEAN level, the peaks that poke over are soft-
# clipped (tanh - no hard clipping), and the chirp is set by amplitude.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

VOICE_CHAIN="chorus=0.6:0.9:50|63:0.35|0.3:0.25|0.4:2.1|2.6,highpass=f=160,aecho=0.8:0.55:26:0.18"
TARGET_MEAN_DB=-12        # volumedetect mean_volume before clipping - hot on purpose
CHIRP_AMPLITUDE=0.45

hour_text() {
  local h=$1
  if [ "$h" -eq 0 ]; then echo "時刻、午前0時"
  elif [ "$h" -lt 12 ]; then echo "時刻、午前${h}時"
  elif [ "$h" -eq 12 ]; then echo "時刻、正午"
  else echo "時刻、午後$((h - 12))時"
  fi
}

mean_db() {
  ffmpeg -i "$1" -af volumedetect -f null - 2>&1 | sed -n 's/.*mean_volume: \(-*[0-9.]*\) dB/\1/p'
}

peak_db() {
  ffmpeg -i "$1" -af volumedetect -f null - 2>&1 | sed -n 's/.*max_volume: \(-*[0-9.]*\) dB/\1/p'
}

ffmpeg -y -loglevel error -f lavfi \
  -i "aevalsrc=${CHIRP_AMPLITUDE}*sin(2*PI*1250*t)*lt(t\,0.045)+${CHIRP_AMPLITUDE}*sin(2*PI*1870*t)*between(t\,0.07\,0.115):s=44100:d=0.25" \
  -ar 44100 -ac 1 -sample_fmt s16 "$WORK/chirp.wav"

for h in $(seq 0 23); do
  say -v Kyoko -o "$WORK/say.wav" --data-format=LEI16@44100 "$(hour_text "$h")"
  ffmpeg -y -loglevel error -i "$WORK/say.wav" -af "$VOICE_CHAIN" -ar 44100 -ac 1 -sample_fmt s16 "$WORK/styled.wav"

  gain=$(echo "$TARGET_MEAN_DB - $(mean_db "$WORK/styled.wav")" | bc)
  ffmpeg -y -loglevel error -i "$WORK/styled.wav" \
    -af "volume=${gain}dB,asoftclip=type=tanh:threshold=0.45:output=1" \
    -ar 44100 -ac 1 -sample_fmt s16 "$WORK/clipped.wav"

  # the clipper's threshold is also its ceiling - lift the result to full scale
  lift=$(echo "-1.5 - $(peak_db "$WORK/clipped.wav")" | bc)
  ffmpeg -y -loglevel error -i "$WORK/clipped.wav" -af "volume=${lift}dB" \
    -ar 44100 -ac 1 -sample_fmt s16 "$WORK/voice.wav"

  ffmpeg -y -loglevel error -i "$WORK/chirp.wav" -i "$WORK/voice.wav" \
    -filter_complex "[0][1]concat=n=2:v=0:a=1" -ar 44100 -ac 1 -sample_fmt s16 \
    "$(printf '%s/hour-%02d.wav' "$HERE" "$h")"
done

echo "24 announcements written to $HERE"
echo "hour-16 gain applied: ${gain} dB"
ffmpeg -i "$HERE/hour-16.wav" -af "ebur128=peak=true" -f null - 2>&1 | grep -E "I:|Peak:" | tail -2
