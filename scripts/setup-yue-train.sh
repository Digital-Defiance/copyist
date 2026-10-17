#!/usr/bin/env bash
# Set up YuE2 LoRA training (docs/voice-lora.md), once. Downloads about 8.5 GB into .cache/:
# the YuE2-3B weights and Python package, the realaudio tokenizer and MERT (for yue-tokenize),
# the regularizer pack, and the realaudio decoder adapter. Needs uv, and scripts/setup-yue.sh run first.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
train="$root/.cache/yue-train"
venv="$train/.venv"
mkdir -p "$train" "$root/.cache/yue/adapters"

if [ ! -x "$venv/bin/python" ]; then
  uv venv -p 3.12 "$venv"
fi
py="$venv/bin/python"
uv pip install --python "$py" "torch==2.10.0" "transformers==4.57.6" "huggingface-hub==0.36.2" \
  "safetensors==0.7.0" "tiktoken==0.12.0" "numpy==2.2.6" "soundfile==0.13.1" "accelerate==1.13.0"

"$py" - "$root" <<'PY'
import sys
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download
root = Path(sys.argv[1])
snapshot_download("m-a-p/YuE2-3B", local_dir=root / ".cache/yue-train/YuE2-3B",
                  allow_patterns=["model.safetensors", "*.json", "qwen.tiktoken", "yue2_infer-0.1.5-py3-none-any.whl"])
for name in ("yue2-mothersuperior-realaudio-tokenizer-v4-Q8_0.gguf", "MERT-v2-FullSong-Q8_0.gguf"):
    hf_hub_download("Serveurperso/YuE2-GGUF", name, local_dir=root / ".cache/yue")
hf_hub_download("Mothersuperior/yue2-minted-corpus", "regularizer/minted_regularizer_pack.pt",
                repo_type="dataset", local_dir=root / ".cache/yue-train")
hf_hub_download("Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4", "nar_lora_joint_v9.bf16.safetensors",
                local_dir=root / ".cache/yue/adapters")
PY
uv pip install --python "$py" --no-deps "$train/YuE2-3B/yue2_infer-0.1.5-py3-none-any.whl"
"$py" -c "import torch; print('PyTorch', torch.__version__, '- Mac GPU (mps):', torch.backends.mps.is_available())"
echo "Ready. Train with: scripts/yue-lora/run.sh SONGS.jsonl AUDIO_DIR NAME"
