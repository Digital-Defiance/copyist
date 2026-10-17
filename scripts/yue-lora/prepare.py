"""Build a YuE2 LoRA training set (docs/voice-lora.md).

Each song's audio becomes YuE2 semantic tokens (yue2.cpp's yue-tokenize, 25 per
second), and its style and lyrics become the prompt prefix YuE2 reads first.
A regularizer pack of YuE2's own songs is added, so a small artist set can't
wear away what the model already knows.

usage: prepare.py --songs songs.jsonl --audio AUDIO_DIR --out OUT_DIR \
                  --snapshot YUE2_3B_DIR --regularizer minted_regularizer_pack.pt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from yue2.protocol import SongRequest, token_prefixes
from yue2.tokenization_yue2 import YuE2TextTokenizer


def held_out(names: list[str], count: int) -> set[str]:
    """A stable choice of songs kept out of training to measure it."""
    return set(sorted(names, key=lambda n: hashlib.md5(n.encode()).hexdigest())[:count])


def tokenize(audio: Path, out_csv: Path, binary: str, model: str, device: str | None) -> np.ndarray:
    if not out_csv.is_file():
        cmd = [binary, "--model", model, "--audio", str(audio), "--out", str(out_csv)]
        if device:
            cmd += ["--device", device]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if r.returncode != 0 or not out_csv.is_file():
            sys.exit(f"yue-tokenize failed on {audio.name}:\n{r.stderr[-2000:]}")
    values = [int(v) for v in out_csv.read_text().replace("\n", ",").split(",") if v.strip()]
    return np.array(values, dtype=np.int32)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--songs", required=True, help="songs.jsonl from `copyist lora-songs`")
    ap.add_argument("--audio", required=True, help="folder holding the songs' audio")
    ap.add_argument("--out", required=True, help="output folder (tokens/ and dataset.pt)")
    ap.add_argument("--snapshot", required=True, help="folder with YuE2-3B's qwen.tiktoken")
    ap.add_argument("--regularizer", required=True, help="minted_regularizer_pack.pt")
    synth = os.environ.get("COPYIST_YUE_SYNTH", "")
    ap.add_argument("--yue-tokenize", default=str(Path(synth).with_name("yue-tokenize")) if synth else None)
    ap.add_argument("--tokenizer", default=os.environ.get("COPYIST_YUE_TOKENIZER"),
                    help="realaudio tokenizer GGUF, with MERT-v2-FullSong GGUF beside it")
    ap.add_argument("--device", default=os.environ.get("COPYIST_YUE_DEVICE"))
    ap.add_argument("--hold", type=int, default=2, help="songs kept out of training to measure it (default 2)")
    args = ap.parse_args(argv)
    if not (args.yue_tokenize and args.tokenizer):
        sys.exit("Need --yue-tokenize and --tokenizer (or COPYIST_YUE_SYNTH and COPYIST_YUE_TOKENIZER).")

    out = Path(args.out)
    (out / "tokens").mkdir(parents=True, exist_ok=True)
    tok = YuE2TextTokenizer(str(Path(args.snapshot) / "qwen.tiktoken"))
    songs = [json.loads(line) for line in Path(args.songs).read_text(encoding="utf-8").splitlines() if line.strip()]
    hold = held_out([s["name"] for s in songs], args.hold)
    data = []
    for i, s in enumerate(songs, 1):
        codec = tokenize(Path(args.audio) / s["audio"], out / "tokens" / f"{s['name']}.csv",
                         args.yue_tokenize, args.tokenizer, args.device)
        prefix = token_prefixes(SongRequest(style=s["style"], lyrics=s["lyrics"], cot="off", seed=1, id="artist"), tok)
        data.append(dict(name=s["name"], src="artist_val" if s["name"] in hold else "artist",
                         prefix=np.array(prefix, dtype=np.int64), codec=codec))
        print(f"[{i}/{len(songs)}] {s['name']}: {len(codec) / 25:.0f} s, prefix {len(prefix)} tokens"
              + (" (held out)" if s["name"] in hold else ""), flush=True)

    pack = torch.load(args.regularizer, weights_only=False)
    for r in pack:
        prefix = token_prefixes(SongRequest(style=r["style"], lyrics=r["lyrics"], cot="off", seed=1, id="minted"), tok)
        data.append(dict(name=r["name"], src=r["src"], prefix=np.array(prefix, dtype=np.int64),
                         codec=np.asarray(r["codec"], dtype=np.int32)))
    torch.save(data, out / "dataset.pt")
    counts = {k: sum(1 for d in data if d["src"] == k) for k in ("artist", "artist_val", "minted", "minted_val")}
    print(f"Wrote {out / 'dataset.pt'}: {counts}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
