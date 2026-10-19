"""Where Copyist finds things outside a song library (docs/desktop-app.md).

- The library (`copyist serve --root`): songs/, out/, voices/, .cache/lora/,
  the person's own work.
- The data folder (COPYIST_HOME, else the platform's usual place): models/,
  downloaded once and shared by every library.
- Programs such as yue-synth and sfizz_render: COPYIST_BIN (the desktop app's
  bundled sidecars).

When those aren't set, the developer setup in the current folder's .cache/
(scripts/setup-yue.sh, setup-sfizz.sh and friends) is used, so a checkout keeps working.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP = "Copyist"


def desktop_app() -> bool:
    """True when the Tauri shell is running the engine (`COPYIST_DESKTOP=1`)."""
    return os.environ.get("COPYIST_DESKTOP", "").strip().lower() in ("1", "true", "yes")


def data_home() -> Path:
    env = os.environ.get("COPYIST_HOME")
    if env:
        return Path(env).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "copyist"


def models_dir() -> Path:
    return data_home() / "models"


def find_model(filename: str, env_var: str | None = None) -> Path | None:
    """A model file: the env var if given, then the data folder, then the developer copies in .cache/."""
    if env_var and os.environ.get(env_var):
        return Path(os.environ[env_var]).expanduser()
    for folder in (models_dir(), Path(".cache/yue"), Path(".cache/yue/adapters")):
        p = folder / filename
        if p.is_file():
            return p.resolve()
    return None


def find_program(name: str, env_var: str | None = None) -> Path | None:
    """A program: the env var, then COPYIST_BIN, then the developer build in .cache/, then PATH."""
    if env_var and os.environ.get(env_var):
        return Path(os.environ[env_var]).expanduser()
    exe = name + (".exe" if os.name == "nt" else "")
    candidates = []
    if os.environ.get("COPYIST_BIN"):
        candidates.append(Path(os.environ["COPYIST_BIN"]).expanduser() / exe)
    candidates += [Path(".cache/yue2.cpp/build") / exe, Path(".cache/sfizz") / exe]
    for p in candidates:
        if p.is_file():
            return p.resolve()
    found = shutil.which(exe)
    return Path(found) if found else None
