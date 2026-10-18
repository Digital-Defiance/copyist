"""Write copyist/sound/flute.sfz: the VSCO 2 CE flute (sustained vibrato) as a melody voice.

VSCO ships the flute as WAV files only. This measures each one and writes an
SFZ for it:

- VSCO names its octaves one lower than MIDI's usual C4 = 60 (same as the
  clarinet), so the key is (octave + 2) * 12 + pitch class.
- Only the first take of each note is used (no round-robin), so previews stay
  deterministic.
- Some recordings start with silence; `offset` skips it.
- Held notes loop inside the steady part of the tone.
- Loudness is evened across the range.

Usage: python scripts/instruments/flute.py /path/to/VSCO-2-CE > copyist/sound/flute.sfz
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from librosa.util.exceptions import ParameterError

FOLDER = "Woodwinds/Flute/susvib"
# Prefer take 1 only (…_v1_1.wav); skip _2 round-robins for deterministic previews.
NAME = re.compile(r"LDFlute_susvib_([A-G])(#?)(\d)_v(\d)_1\.wav$")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
EVEN = 0.6


def key_of(m) -> int:
    return (int(m.group(3)) + 2) * 12 + PC[m.group(1)] + (1 if m.group(2) else 0)


def measure(path: Path, key: int) -> dict | None:
    x, sr = sf.read(str(path), always_2d=True)
    mono = x.mean(axis=1)
    ten = int(0.01 * sr)
    fine = 20 * np.log10(np.array(
        [np.sqrt(np.mean(mono[i:i + ten] ** 2)) for i in range(0, max(1, len(mono) - ten), ten)]) + 1e-9)
    steady_db = float(np.median(fine[min(40, len(fine) // 2): min(180, len(fine))]))
    onset = int(np.argmax(fine >= steady_db - 20)) * ten
    offset = max(0, onset - int(0.012 * sr))
    hop = int(0.05 * sr)
    frames = np.array([np.sqrt(np.mean(mono[i:i + hop] ** 2)) for i in range(0, max(1, len(mono) - hop), hop)])
    db = 20 * np.log10(frames + 1e-9)
    start_f = onset // hop
    body = db[start_f + 4:]
    loop = None
    if len(body) > 20:
        steady = np.median(body[: max(10, len(body) // 2)])
        inside = np.where(np.abs(body - steady) < 3.0)[0]
        if len(inside):
            first = start_f + 4 + int(inside[0]) + 2
            last = start_f + 4 + int(inside[-1]) - 2
            if (last - first) * hop > 0.8 * sr:
                loop = (first * hop, last * hop)
    a, b = onset + int(0.25 * sr), min(len(mono), onset + int(1.2 * sr))
    try:
        f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                     fmin=max(80.0, librosa.midi_to_hz(key - 6)),
                                     fmax=min(sr / 2 - 1, librosa.midi_to_hz(key + 6)),
                                     frame_length=4096)
    except (ValueError, ParameterError) as e:
        print(f"skip {path.name}: {e}", file=sys.stderr)
        return None
    if not np.any(voiced):
        print(f"skip {path.name}: no pitch", file=sys.stderr)
        return None
    heard = float(librosa.hz_to_midi(np.nanmedian(f0[voiced])))
    if abs(heard - key) > 2.5:
        print(f"skip {path.name}: sounds as MIDI {heard:.1f}, expected {key}", file=sys.stderr)
        return None
    key = round(heard)
    rms = 20 * np.log10(np.sqrt(np.mean(mono[onset:onset + sr] ** 2)) + 1e-9)
    return {"key": key, "offset": offset, "loop": loop, "tune": round(100 * (key - heard)), "rms": rms}


def main(root: Path) -> None:
    samples = []
    for p in sorted((root / FOLDER).glob("*.wav")):
        m = NAME.search(p.name)
        if not m:
            continue
        s = measure(p, key_of(m))
        if s:
            samples.append((s["key"], p, s))
    if not samples:
        raise SystemExit(f"No flute samples under {root / FOLDER}")
    # One sample per key (take 1 only).
    by_key = {}
    for key, p, s in samples:
        by_key.setdefault(key, (p, s))
    keys = sorted(by_key)
    loud = {k: by_key[k][1]["rms"] for k in keys}
    median = float(np.median(list(loud.values())))
    out = [
        "// Copyist flute: VSCO 2 Community Edition flute, susvib (CC0, Versilian Studios).",
        "// Written by scripts/instruments/flute.py; see that file for how each number was measured.",
        "<control>",
        f"default_path={FOLDER}/",
        "",
        "<global>",
        "ampeg_attack=0.015",
        "ampeg_release=0.2",
        "amp_veltrack=40",
        "loop_crossfade=0.1",
        "",
    ]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        p, s = by_key[key]
        gain = round(-(loud[key] - median) * EVEN, 1)
        out.append(f"<group> lokey={lo} hikey={hi} pitch_keycenter={key} volume={gain}")
        line = f"<region> lovel=1 hivel=127 offset={s['offset']} tune={s['tune']}"
        if s["loop"]:
            line += f" loop_mode=loop_sustain loop_start={s['loop'][0]} loop_end={s['loop'][1]}"
        out.append(line + f" sample={p.name}")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
