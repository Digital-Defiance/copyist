#!/usr/bin/env bash
# Train a YuE2 LoRA from a song list, start to finish (docs/voice-lora.md).
# usage: scripts/yue-lora/run.sh SONGS.jsonl AUDIO_DIR NAME [train.py options, e.g. --steps 800 or --resume]
# Tokenizing is skipped for songs already done, and --resume continues an interrupted training run.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
songs="$1"; audio="$2"; name="$3"; shift 3
work="$root/.cache/lora/$name"
py="$root/.cache/yue-train/.venv/bin/python"
snap="$root/.cache/yue-train/YuE2-3B"
synth="${COPYIST_YUE_SYNTH:-$root/.cache/yue2.cpp/build/yue-synth}"
mkdir -p "$work"
"$py" "$root/scripts/yue-lora/prepare.py" --songs "$songs" --audio "$audio" --out "$work" --snapshot "$snap" \
  --regularizer "$root/.cache/yue-train/regularizer/minted_regularizer_pack.pt" \
  --yue-tokenize "$(dirname "$synth")/yue-tokenize" \
  --tokenizer "$root/.cache/yue/yue2-mothersuperior-realaudio-tokenizer-v4-Q8_0.gguf" \
  --device "${COPYIST_YUE_DEVICE:-MTL0}"
# caffeinate keeps the Mac awake until training ends
caffeinate -i "$py" "$root/scripts/yue-lora/train.py" --dataset "$work/dataset.pt" --snapshot "$snap" \
  --out "$work/lora" "$@" 2>&1 | tee -a "$work/train-output.txt"
