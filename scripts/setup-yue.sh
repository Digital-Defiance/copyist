#!/usr/bin/env bash
# Build yue2.cpp (Metal on macOS) and download the YuE2 weights into .cache/.
# Usage: scripts/setup-yue.sh
# The weights are CC BY-NC 4.0. Read docs/production.md before using them.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/.cache/yue2.cpp"
models="$root/.cache/yue"
mkdir -p "$models"

if [ ! -d "$dest/.git" ]; then
  git clone --recurse-submodules --depth 1 https://github.com/ServeurpersoCom/yue2.cpp.git "$dest"
fi

if [ ! -x "$dest/build/yue-synth" ]; then
  ( cd "$dest" && ./buildcpu.sh )
fi

py="${PYTHON:-python3}"
if [ -x "$root/.venv/bin/python" ]; then
  py="$root/.venv/bin/python"
fi
"$py" - "$models" <<'PY'
import sys
from pathlib import Path
dest = Path(sys.argv[1])
needed = [n for n in ("YuE2-3B-Q6_K.gguf", "YuE2-Vae-F32.gguf") if not (dest / n).is_file()]
if not needed:
    raise SystemExit(0)
from huggingface_hub import hf_hub_download
for name in needed:
    hf_hub_download("Serveurperso/YuE2-GGUF", name, local_dir=dest)
PY

synth="$dest/build/yue-synth"
test -x "$synth"

echo
echo "Add these to your shell profile (e.g. ~/.zshrc):"
echo "  export COPYIST_YUE_SYNTH=\"$synth\""
echo "  export COPYIST_YUE_MODEL=\"$models/YuE2-3B-Q6_K.gguf\""
echo "  export COPYIST_YUE_VAE=\"$models/YuE2-Vae-F32.gguf\""
echo "  export COPYIST_YUE_DEVICE=MTL0"
