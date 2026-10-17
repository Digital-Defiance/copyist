#!/usr/bin/env bash
# Install Demucs into .cache/demucs for vocal separation. See docs/production.md.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
uv venv -p 3.12 "$root/.cache/demucs/.venv"
uv pip install --python "$root/.cache/demucs/.venv/bin/python" demucs numpy soundfile
echo "Demucs is ready:"
echo "  $root/.cache/demucs/.venv/bin/demucs -d mps --two-stems vocals --other-method none -o OUT MIX.wav"
