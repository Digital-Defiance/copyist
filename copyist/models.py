"""The models Copyist downloads, and the downloader (docs/desktop-app.md).

Every file is pinned to a repository revision, with its size and SHA-256, so a
download is the exact file listed here or it's thrown away. Downloads resume:
an interrupted one picks up from its .part file.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.request import Request, urlopen

from . import paths

LICENCE = ("YuE2's weights are licensed CC BY-NC 4.0 (non-commercial), with an added permission dated "
           "16 September 2026: an individual creator may sell the songs they make with them. A company "
           "needs a separate licence from the YuE team before using them commercially. The realaudio "
           "tokenizer and decoder adapter are CC BY-NC 4.0 too.")
LICENCE_URL = "https://huggingface.co/m-a-p/YuE2-3B"


@dataclass(frozen=True)
class Model:
    id: str
    file: str
    repo: str
    revision: str
    size: int
    sha256: str
    label: str


GGUF = ("Serveurperso/YuE2-GGUF", "e630f2b8f6aedf8254c3186438633c1b5eeaf80a")
REALAUDIO = ("Mothersuperior/yue2-mothersuperior-realaudio-tokenizer-v4", "e2e63d859f3af879baf1b4d4e9f22d1eeda6fde5")

CATALOG = {m.id: m for m in (
    Model("yue2", "YuE2-3B-Q6_K.gguf", *GGUF, 2943331072,
          "42068d5e57713df11b9f6a5a3751072d9bbefe231d1d088f9c100e026ffa4ef9", "YuE2, the singer and band"),
    Model("yue2-vae", "YuE2-Vae-F32.gguf", *GGUF, 530497344,
          "93e49dfb1970e89ad64cacb17cf13b5d05f6bb30ef7ed3adae3050bcb728638a", "YuE2's audio decoder"),
    Model("tokenizer", "yue2-mothersuperior-realaudio-tokenizer-v4-Q8_0.gguf", *GGUF, 46527328,
          "ab860529c61bcef0350d5e43d4291835b380e76246c48be4f26fa8839fe31ce5", "the audio tokenizer"),
    Model("mert", "MERT-v2-FullSong-Q8_0.gguf", *GGUF, 902283712,
          "35a6032ec7e8123c02becdefc7bfe10a3adb33faa8a1951dc0af864b4494b8ef", "MERT, which the tokenizer listens with"),
    Model("realaudio", "nar_lora_joint_v9.bf16.safetensors", *REALAUDIO, 70301896,
          "ce57f98e9e0e65c724c2a00aa23dea2568952590504a428c588d82f00bc61c55", "the realaudio decoder adapter"),
)}

# What a person installs, in their words
GROUPS = {
    "singer": {"label": "The singer", "why": "needed for every take", "models": ["yue2", "yue2-vae"]},
    "voices": {"label": "Voice tools", "why": "for training voices and opening a take with a recording",
               "models": ["tokenizer", "mert", "realaudio"]},
}

ENV = {"yue2": "COPYIST_YUE_MODEL", "yue2-vae": "COPYIST_YUE_VAE"}


def url(m: Model) -> str:
    return f"https://huggingface.co/{m.repo}/resolve/{m.revision}/{m.file}"


def path_of(model_id: str) -> Path | None:
    m = CATALOG[model_id]
    return paths.find_model(m.file, ENV.get(model_id))


def status(model_id: str) -> dict:
    m = CATALOG[model_id]
    p = path_of(model_id)
    part = paths.models_dir() / (m.file + ".part")
    if p and p.is_file() and p.stat().st_size == m.size:
        state, have = "ready", m.size
    elif part.is_file():
        state, have = "partial", part.stat().st_size
    else:
        state, have = "missing", 0
    return {**asdict(m), "state": state, "have": have, "path": str(p) if state == "ready" else None}


def group_status(group: str) -> dict:
    g = GROUPS[group]
    items = [status(i) for i in g["models"]]
    total = sum(i["size"] for i in items)
    return {"id": group, "label": g["label"], "why": g["why"], "size": total,
            "have": sum(i["have"] for i in items), "ready": all(i["state"] == "ready" for i in items), "models": items}


def sha256_of(path: Path, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


Progress = Callable[[int, int], None]


def download(model_id: str, progress: Progress | None = None, opener=urlopen, chunk: int = 1 << 20) -> Path:
    """Download one model into the data folder, resuming a .part file, and verify it."""
    m = CATALOG[model_id]
    dest = paths.models_dir()
    dest.mkdir(parents=True, exist_ok=True)
    final, part = dest / m.file, dest / (m.file + ".part")
    if final.is_file() and final.stat().st_size == m.size:
        return final
    start = part.stat().st_size if part.is_file() else 0
    if start > m.size:
        part.unlink()
        start = 0
    if start < m.size:
        req = Request(url(m), headers={"User-Agent": "copyist", **({"Range": f"bytes={start}-"} if start else {})})
        with opener(req, timeout=60) as r:
            if start and getattr(r, "status", 200) != 206:   # the server ignored the range: start over
                start = 0
            with open(part, "ab" if start else "wb") as f:
                done = start
                while block := r.read(chunk):
                    f.write(block)
                    done += len(block)
                    if progress:
                        progress(done, m.size)
    if part.stat().st_size != m.size or sha256_of(part) != m.sha256:
        part.unlink()
        raise ValueError(f"{m.file} didn't match its checksum; it was removed. Try the download again.")
    os.replace(part, final)
    return final


def download_group(group: str, progress: Progress | None = None, opener=urlopen) -> list[Path]:
    """Download every model in a group, reporting progress across the whole group."""
    ids = GROUPS[group]["models"]
    total = sum(CATALOG[i].size for i in ids)
    before = 0
    out = []
    for i in ids:
        if status(i)["state"] == "ready":
            before += CATALOG[i].size
            if progress:
                progress(before, total)
            out.append(path_of(i))
            continue
        base = before
        out.append(download(i, (lambda d, _t, base=base: progress(base + d, total)) if progress else None, opener))
        before += CATALOG[i].size
    return out
