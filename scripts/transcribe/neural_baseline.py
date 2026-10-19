#!/usr/bin/env python3
"""Thin bridge: run open-transcriber T0 baselines from a Copyist checkout.

  python scripts/transcribe/neural_baseline.py
  python scripts/transcribe/neural_baseline.py --only silent-night
  python scripts/transcribe/neural_baseline.py --write out/t0-basic-pitch.md

Requires the submodule and its baseline extra:

  git submodule update --init open-transcriber
  pip install -e "./open-transcriber[baseline]"
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "open-transcriber" / "scripts" / "t0_baseline.py"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not SCRIPT.is_file():
        print(
            f"Missing {SCRIPT}. Init the submodule:\n"
            "  git submodule update --init open-transcriber",
            file=sys.stderr,
        )
        return 2
    if "--copyist-root" not in argv:
        argv = ["--copyist-root", str(ROOT), *argv]
    # Load the submodule script as a module so we get its main() return code.
    ns = runpy.run_path(str(SCRIPT), run_name="t0_baseline")
    return int(ns["main"](argv))


if __name__ == "__main__":
    raise SystemExit(main())
