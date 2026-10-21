"""Where Copyist's work runs: how many CPU jobs at once, and which device a model uses (docs/hardware.md).

Copyist runs on a Mac first (Apple silicon: CPU, Metal GPU, Neural Engine) and stays usable on
Linux and Windows with an NVIDIA GPU (CUDA), another GPU (Vulkan, through ggml), or the CPU alone.
Every choice here can be overridden with an environment variable, and every accelerated path has a
CPU fallback.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def performance_cores() -> int:
    """Cores for heavy work: the performance cores on Apple silicon (the efficiency cores are left
    for the rest of the machine), else every core."""
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True,
                               text=True, timeout=5)
            n = int(r.stdout.strip())
            if n > 0:
                return n
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return os.cpu_count() or 1


def cpu_workers(tasks: int | None = None) -> int:
    """How many CPU jobs to run at once: COPYIST_JOBS if set, else the performance cores, never more
    than there are tasks."""
    env = os.environ.get("COPYIST_JOBS", "").strip()
    n = int(env) if env.isdigit() and int(env) > 0 else performance_cores()
    return max(1, min(n, tasks)) if tasks else max(1, n)


@lru_cache(maxsize=None)
def torch_device(python: str | None = None) -> str:
    """The PyTorch device a tool's own Python environment can use: "mps" on Apple silicon, "cuda"
    where its PyTorch sees an NVIDIA GPU, else "cpu". On Linux and Windows this asks that environment
    (a PyTorch installed without CUDA can't use the GPU even when one is there)."""
    if sys.platform == "darwin":
        return "mps"
    if not shutil.which("nvidia-smi"):
        return "cpu"
    if not python or not Path(python).is_file():
        return "cpu"
    try:
        r = subprocess.run([python, "-c", "import torch; print('cuda' if torch.cuda.is_available() else 'cpu')"],
                           capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return "cpu"
    return "cuda" if r.stdout.strip() == "cuda" else "cpu"


def python_beside(program: str | None) -> str | None:
    """The Python interpreter in the same environment as a console script (a venv's bin/ or Scripts/)."""
    if not program:
        return None
    folder = Path(program).parent
    for name in ("python", "python3", "python.exe"):
        if (folder / name).is_file():
            return str(folder / name)
    return None
