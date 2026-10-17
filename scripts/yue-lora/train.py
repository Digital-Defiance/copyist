"""Train a LoRA on YuE2's autoregressive half (docs/voice-lora.md).

The AR half writes a song's semantic tokens from its style and lyrics; a LoRA
on it learns how an artist sounds. Half the batches come from the artist and
half from YuE2's own songs, so the model keeps its grammar. Checkpoints are
saved in a form yue2.cpp loads with --adapters.

usage: train.py --dataset DIR/dataset.pt --snapshot YUE2_3B_DIR --out OUT_DIR [--steps 800]

Runs on Apple Silicon (mps), CUDA or CPU. On a Mac, run it under `caffeinate -i`
so the machine doesn't sleep; `--resume` picks up after an interruption.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint
from yue2.modeling_yue2 import YuE2Config, YuE2ForCausalLM
from yue2.nar import attention
from yue2.protocol import CODEC_OFFSET, MUSIC_END

SITES = (("self_attn", ("q_proj", "k_proj", "v_proj", "o_proj")), ("mlp", ("gate_proj", "up_proj", "down_proj")))
LOGIT_CHUNK = 1024


class LoRALinear(nn.Module):
    """base(x) + B(A(x)), with A and B in float32. Starts as the base layer (B = 0)."""

    def __init__(self, base: nn.Linear, rank: int):
        super().__init__()
        self.base = base
        dev = base.weight.device
        self.lora_A = nn.Parameter(torch.randn(rank, base.in_features, device=dev) / math.sqrt(base.in_features))
        self.lora_B = nn.Parameter(torch.zeros(base.out_features, rank, device=dev))

    def forward(self, x):
        return self.base(x) + ((x.float() @ self.lora_A.T) @ self.lora_B.T).to(x.dtype)


def add_lora(model, rank: int) -> dict[str, LoRALinear]:
    """LoRA on every AR projection (not the nar_ ones). Keys are yue2.cpp's adapter names."""
    sites = {}
    for i, layer in enumerate(model.model.layers):
        for block, names in SITES:
            mod = getattr(layer, block)
            for n in names:
                wrapped = LoRALinear(getattr(mod, n), rank)
                setattr(mod, n, wrapped)
                sites[f"layers.{i}.{block}.{n}"] = wrapped
    return sites


def pick_device(name: str) -> str:
    if name != "auto":
        return name
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_model(args, dev):
    if args.tiny:   # a small random YuE2 with the real vocabulary, for testing this script
        cfg = YuE2Config(hidden_size=64, num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
                         head_dim=16, intermediate_size=128, vocab_size=184704)
        torch.manual_seed(0)
        model = YuE2ForCausalLM(cfg).to(torch.bfloat16)
    else:
        model = YuE2ForCausalLM.from_pretrained(args.snapshot, torch_dtype=torch.bfloat16, low_cpu_mem_usage=True)
    model = model.to(dev).eval()
    model.requires_grad_(False)
    return model


def ar_layer(layer, x, cos, sin):
    """One layer of the AR path, with attention in query blocks (what YuE2 does on MPS and CPU)."""
    q, k, v = layer.self_attn.project_qkv(layer.input_layernorm(x), cos, sin)
    h = attention(q[0], k[0], v[0], causal=True)
    x = x + layer.self_attn.o_proj(h.flatten(1)[None])
    return x + layer.mlp(layer.post_attention_layernorm(x))


def chunk_loss(lm_head, h, target):
    return F.cross_entropy(lm_head(h).float(), target, reduction="sum")


def sequence(item, max_len: int, dev):
    prefix = [int(t) for t in item["prefix"]]
    room = max_len - len(prefix) - 1
    codes = [int(c) + CODEC_OFFSET for c in item["codec"]]
    body = codes[:room] + ([MUSIC_END] if len(codes) <= room else [])
    return torch.tensor([prefix + body], device=dev), len(prefix)


def lm_loss(model, ids, n_prefix, grad=True):
    """Mean cross entropy over the codec tokens only (the prompt is given, not learned)."""
    bb = model.model
    x = bb.embed_tokens(ids)
    cos, sin = bb.rotary_emb(torch.arange(ids.shape[1], device=ids.device)[None])
    for layer in bb.layers:
        x = checkpoint(ar_layer, layer, x, cos, sin, use_reentrant=False) if grad else ar_layer(layer, x, cos, sin)
    h = bb.norm(x[0])[n_prefix - 1:-1]
    target = ids[0, n_prefix:]
    total = 0.0
    for s in range(0, len(h), LOGIT_CHUNK):
        part = (model.lm_head, h[s:s + LOGIT_CHUNK], target[s:s + LOGIT_CHUNK])
        total = total + (checkpoint(chunk_loss, *part, use_reentrant=False) if grad else chunk_loss(*part))
    return total / len(h)


def save_adapter(sites, rank: int, path: Path, info: dict):
    from safetensors.torch import save_file
    tensors = {}
    for key, m in sites.items():
        tensors[f"{key}.lora_A"] = m.lora_A.detach().float().cpu().contiguous()
        tensors[f"{key}.lora_B"] = m.lora_B.detach().float().cpu().contiguous()
    meta = {"rank": str(rank), "half": "ar", "format": "copyist yue-lora 1", **{k: str(v) for k, v in info.items()}}
    tmp = path.with_suffix(".tmp")
    save_file(tensors, str(tmp), metadata=meta)
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--snapshot", help="YuE2-3B folder (model.safetensors, config.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=800, help="optimizer steps (default 800; past ~1500 it memorizes)")
    ap.add_argument("--rank", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--artist-share", type=float, default=0.5, help="share of songs drawn from the artist (default 0.5)")
    ap.add_argument("--accumulate", type=int, default=1, help="songs per optimizer step (default 1)")
    ap.add_argument("--max-len", type=int, default=8192, help="tokens per song, prompt included (25 per second)")
    ap.add_argument("--save-from", type=int, default=300)
    ap.add_argument("--save-every", type=int, default=100)
    ap.add_argument("--eval-every", type=int, default=100)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--resume", action="store_true", help="continue from OUT/resume.pt")
    ap.add_argument("--tiny", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if not args.tiny and not args.snapshot:
        sys.exit("--snapshot is required")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dev = pick_device(args.device)
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    data = torch.load(args.dataset, weights_only=False)
    artist = [d for d in data if d["src"] == "artist"]
    held = [d for d in data if d["src"] == "artist_val"]
    minted = [d for d in data if d["src"] == "minted"]
    minted_val = [d for d in data if d["src"] == "minted_val"][:6]
    if not artist or not minted:
        sys.exit("The dataset needs artist songs and minted songs (run prepare.py).")
    print(f"device {dev}; artist {len(artist)} (+{len(held)} held out), minted {len(minted)}", flush=True)

    model = load_model(args, dev)
    sites = add_lora(model, args.rank)
    params = [p for m in sites.values() for p in (m.lora_A, m.lora_B)]
    opt = torch.optim.AdamW(params, lr=args.lr, betas=(0.9, 0.95), weight_decay=0.0)
    print(f"LoRA rank {args.rank}: {sum(p.numel() for p in params) / 1e6:.1f}M parameters", flush=True)

    start = 1
    resume = out / "resume.pt"
    if args.resume and resume.is_file():
        state = torch.load(resume, map_location=dev, weights_only=False)
        with torch.no_grad():
            for key, m in sites.items():
                m.lora_A.copy_(state["lora"][f"{key}.lora_A"])
                m.lora_B.copy_(state["lora"][f"{key}.lora_B"])
        opt.load_state_dict(state["opt"])
        random.setstate(state["random"])
        start = state["step"] + 1
        print(f"resumed after step {state['step']}", flush=True)

    @torch.no_grad()
    def evaluate():
        result = {}
        for tag, items in (("artist_held_out", held), ("artist_trained", artist[:4]), ("minted_val", minted_val)):
            if items:
                result[tag] = round(sum(lm_loss(model, *sequence(it, args.max_len, dev), grad=False).item()
                                        for it in items) / len(items), 4)
        return result

    log = open(out / "train.log", "a")
    if start == 1:
        e = evaluate()
        print(f"EVAL step 0 {e}", flush=True)
        log.write(json.dumps({"step": 0, **e}) + "\n")
        log.flush()
    warm, t0 = 50, time.time()
    for step in range(start, args.steps + 1):
        for g in opt.param_groups:
            g["lr"] = args.lr * min(1.0, step / warm) * (0.2 + 0.8 * 0.5 * (1 + math.cos(math.pi * step / args.steps)))
        total = 0.0
        for _ in range(args.accumulate):
            item = random.choice(artist) if random.random() < args.artist_share else random.choice(minted)
            loss = lm_loss(model, *sequence(item, args.max_len, dev)) / args.accumulate
            loss.backward()
            total += loss.item()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        if step <= 3 or step % 10 == 0:
            per = (time.time() - t0) / (step - start + 1)
            eta = per * (args.steps - step) / 3600
            print(f"step {step}/{args.steps} loss {total:.3f} {per:.1f} s/step, about {eta:.1f} h to go", flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            e = evaluate()
            print(f"EVAL step {step} {e}", flush=True)
            log.write(json.dumps({"step": step, **e}) + "\n")
            log.flush()
        if step % args.save_every == 0 or step == args.steps:
            info = {"step": step, "steps": args.steps, "lr": args.lr}
            if step >= args.save_from or step == args.steps:
                save_adapter(sites, args.rank, out / f"step-{step}.safetensors", info)
            save_adapter(sites, args.rank, out / "last.safetensors", info)
            torch.save({"step": step, "opt": opt.state_dict(), "random": random.getstate(),
                        "lora": {f"{k}.lora_{w}": getattr(m, f"lora_{w}").detach() for k, m in sites.items() for w in "AB"}},
                       resume)
    print(f"Done. Adapters are in {out} (step-N.safetensors); load one with yue-synth --adapters {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
