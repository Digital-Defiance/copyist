#!/usr/bin/env bash
# Install SoulX-Singer next to Copyist, in its own Python 3.10 environment.
# Usage: scripts/setup-soulx.sh [/path/to/install]   (default: ../SoulX-Singer)
# Needs: git, uv (https://docs.astral.sh/uv/), about 4 GB of disk.
set -euo pipefail

dest="${1:-$(cd "$(dirname "$0")/../.." && pwd)/SoulX-Singer}"
if [ ! -d "$dest/.git" ]; then
  git clone --depth 1 https://github.com/Soul-AILab/SoulX-Singer.git "$dest"
fi
cd "$dest"
uv venv -p 3.10 .venv
# Just what inference needs. The full requirements.txt also pulls in the
# preprocessing tools (and CUDA-only packages that won't install on a Mac).
# torch 2.8: 2.2's Apple GPU (mps) build crashes in SoulX's vocoder (a complex
# multiply assert), and 2.9+ moves torchaudio.load, which SoulX uses, to TorchCodec.
uv pip install --python .venv/bin/python \
  "torch==2.8.0" "torchaudio==2.8.0" "numpy<2" "transformers==4.41.2" \
  "librosa==0.11.0" "omegaconf==2.3.0" "accelerate==1.11.0" \
  soundfile scipy tqdm einops "huggingface_hub>=0.20"
.venv/bin/python - <<'PY'
from huggingface_hub import hf_hub_download, snapshot_download
for f in ("model.pt", "config.yaml"):
    hf_hub_download("Soul-AILab/SoulX-Singer", f, local_dir="pretrained_models/SoulX-Singer")
snapshot_download("openai/whisper-base", allow_patterns=["*.json", "*.safetensors", "*.txt"])
print("SoulX-Singer is ready.")
PY
echo
echo "Add these to your shell profile (e.g. ~/.zshrc):"
echo "  export COPYIST_SOULX_DIR=\"$dest\""
echo "  export COPYIST_SOULX_PYTHON=\"$dest/.venv/bin/python\""
