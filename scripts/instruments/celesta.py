"""Build the compact celesta sample set for Copyist from Neil Bickford's SF2.

Source: https://gitlab.com/Nbickford/a-sampled-celesta (CC0) — Tuned Denoised Mix.
We redistribute a mono whole-tone subset in Digital-Defiance/copyist-celesta.

Usage (developer machine, once):

    # Download the SF2 from GitLab (about 66 MB), then:
    python scripts/instruments/celesta.py /path/to/Celesta\\ Tuned\\ Denoised\\ Mix.sf2 \\
        /path/to/copyist-celesta

Writes samples/*.wav into that folder. Then commit and refresh the manifest:

    python scripts/instruments/manifest.py /path/to/clones
"""
from __future__ import annotations

import sys
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np
from sf2utils.sf2parse import Sf2File

KEEP_PC = {0, 2, 4, 6, 8, 10}  # whole-tone grid from C
SECONDS = 2.2


def midi_of(name: str) -> int:
    note = name.split()[0]
    pc = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
          "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}[note[:-1]]
    return pc + (int(note[-1]) + 1) * 12


def extract(sf2_path: Path, dest: Path) -> None:
    samples_dir = dest / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    for old in samples_dir.glob("*.wav"):
        old.unlink()
    with sf2_path.open("rb") as f:
        sf2 = Sf2File(f)
        groups: dict[str, dict[str, object]] = defaultdict(dict)
        for s in sf2.samples:
            n = (s.name or "").strip()
            if not n or "rr1" not in n or any(x in n for x in ("creak", "keyRelease", "pedal")):
                continue
            side = "L" if n.endswith("L") else "R" if n.endswith("R") else "?"
            groups[n[:-1].strip()][side] = s
        for key, sides in sorted(groups.items(), key=lambda kv: midi_of(kv[0])):
            mid = midi_of(key)
            if mid % 12 not in KEEP_PC:
                continue
            left_s, right_s = sides.get("L"), sides.get("R")
            if not left_s or not right_s:
                continue
            left = np.frombuffer(left_s.raw_sample_data, dtype="<i2").astype(np.float32)
            right = np.frombuffer(right_s.raw_sample_data, dtype="<i2").astype(np.float32)
            n = min(len(left), len(right), int(SECONDS * left_s.sample_rate))
            mono = (left[:n] + right[:n]) * 0.5
            fade = int(0.15 * left_s.sample_rate)
            if fade > 0 and n > fade:
                mono[-fade:] *= np.linspace(1, 0, fade)
            mono = np.clip(mono, -32767, 32767).astype(np.int16)
            name = f"{mid:03d}_{key.split()[0].replace('#', 's')}.wav"
            with wave.open(str(samples_dir / name), "w") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(left_s.sample_rate)
                w.writeframes(mono.tobytes())
            print(name, file=sys.stderr)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    extract(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
