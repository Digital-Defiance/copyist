"""Separate a recording's vocal, for checking it against the score (docs/production.md)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .song import SongError


def demucs_binary() -> str | None:
    """COPYIST_DEMUCS, else the copy scripts/setup-demucs.sh installs."""
    env = os.environ.get("COPYIST_DEMUCS")
    if env:
        return env
    local = Path(".cache/demucs/.venv/bin/demucs")
    return str(local) if local.is_file() else None


def demucs_device(binary: str | None) -> str:
    """COPYIST_DEMUCS_DEVICE, else the GPU Demucs's own PyTorch can use (Apple's on a Mac, an NVIDIA
    one with CUDA elsewhere), else the CPU."""
    from .compute import python_beside, torch_device
    return os.environ.get("COPYIST_DEMUCS_DEVICE") or torch_device(python_beside(binary))


def vocal_stem(recording: Path, binary: str | None = None, device: str | None = None) -> Path:
    """The vocal of `recording`, separated with Demucs into <folder>/htdemucs/<name>/vocals.wav (kept for reuse)."""
    recording = Path(recording)
    out = recording.parent / "htdemucs" / recording.stem / "vocals.wav"
    if out.is_file() and out.stat().st_mtime >= recording.stat().st_mtime:
        return out
    binary = binary or demucs_binary()
    if not binary:
        raise SongError("Separating the vocal needs Demucs: run scripts/setup-demucs.sh, or set COPYIST_DEMUCS.")
    device = device or demucs_device(binary)
    print(f"Separating the vocal with Demucs on {device}...", file=sys.stderr)
    r = subprocess.run([binary, "-d", device, "--two-stems", "vocals", "--other-method", "none",
                        "-o", str(recording.parent), str(recording)])
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"Demucs didn't separate {recording.name} (exit {r.returncode}).")
    return out


def split_vocals(recording: Path, out_dir: Path, binary: str | None = None, device: str | None = None) -> tuple[Path, Path]:
    """(vocal, everything else) of `recording`, separated with Demucs into <out_dir>/htdemucs/<name>/
    (kept for reuse)."""
    recording = Path(recording)
    folder = Path(out_dir) / "htdemucs" / recording.stem
    vocals, rest = folder / "vocals.wav", folder / "no_vocals.wav"
    if vocals.is_file() and rest.is_file() and vocals.stat().st_mtime >= recording.stat().st_mtime:
        return vocals, rest
    binary = binary or demucs_binary()
    if not binary:
        raise SongError("Separating the vocal needs Demucs: run scripts/setup-demucs.sh, or set COPYIST_DEMUCS.")
    device = device or demucs_device(binary)
    print(f"Separating the vocal from the band with Demucs on {device}...", file=sys.stderr, flush=True)
    r = subprocess.run([binary, "-d", device, "--two-stems", "vocals", "-o", str(out_dir), str(recording)])
    if r.returncode != 0 or not (vocals.is_file() and rest.is_file()):
        raise RuntimeError(f"Demucs didn't separate {recording.name} (exit {r.returncode}).")
    return vocals, rest
