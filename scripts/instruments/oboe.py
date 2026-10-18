"""Write copyist/sound/oboe.sfz: the VSCO 2 CE oboe (vibrato) as a melody voice.

VSCO ships the oboe as WAV files only. This measures each one and writes an
SFZ for it:

- VSCO names its octaves one lower than MIDI's usual C4 = 60 (same as the
  clarinet and flute).
- Dynamics are v1 (soft) and v3 (loud). Only those takes are used (no
  round-robin), so previews stay deterministic.
- Held notes loop inside the steady part of the tone.
- Loudness of the loud layer is evened across the range.

Usage: python scripts/instruments/oboe.py /path/to/VSCO-2-CE > copyist/sound/oboe.sfz
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from librosa.util.exceptions import ParameterError

FOLDER = "Woodwinds/Oboe/Vib"
NAME = re.compile(r"Oboe_Vib_([A-G])(#?)(\d)_v([13])_Main\.wav$")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VEL = {"1": (1, 79), "3": (80, 127)}
EVEN = 0.55


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
    heard = float(key)
    tune = 0
    fl = min(4096, max(512, (b - a) // 4))
    try:
        f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                     fmin=max(100.0, librosa.midi_to_hz(key - 6)),
                                     fmax=min(sr / 2 - 1, librosa.midi_to_hz(key + 6)),
                                     frame_length=fl)
        if np.any(voiced):
            heard = float(librosa.hz_to_midi(np.nanmedian(f0[voiced])))
            if abs(heard - key) <= 2.5:
                key = round(heard)
                tune = round(100 * (key - heard))
            else:
                print(f"keep name {path.name}: sounds as MIDI {heard:.1f}, using named {key}",
                      file=sys.stderr)
                heard = float(key)
    except (ValueError, ParameterError) as e:
        print(f"keep name {path.name}: {e}", file=sys.stderr)
    rms = 20 * np.log10(np.sqrt(np.mean(mono[onset:onset + min(sr, len(mono) - onset)] ** 2)) + 1e-9)
    return {"key": key, "offset": offset, "loop": loop, "tune": tune, "rms": rms}


def main(root: Path) -> None:
    samples = []
    for p in sorted((root / FOLDER).glob("*.wav")):
        m = NAME.search(p.name)
        if not m:
            continue
        s = measure(p, key_of(m))
        if s:
            samples.append((s["key"], m.group(4), p, s))
    if not samples:
        raise SystemExit(f"No oboe samples under {root / FOLDER}")
    keys = sorted({k for k, *_ in samples})
    loud = {k: s["rms"] for k, v, _, s in samples if v == "3"}
    median = float(np.median(list(loud.values()))) if loud else 0.0
    out = [
        "// Copyist oboe: VSCO 2 Community Edition oboe, vibrato (CC0, Versilian Studios).",
        "// Written by scripts/instruments/oboe.py; see that file for how each number was measured.",
        "<control>",
        f"default_path={FOLDER}/",
        "",
        "<global>",
        "ampeg_attack=0.02",
        "ampeg_release=0.22",
        "amp_veltrack=45",
        "loop_crossfade=0.1",
        "",
    ]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        gain = round(-(loud.get(key, median) - median) * EVEN, 1)
        out.append(f"<group> lokey={lo} hikey={hi} pitch_keycenter={key} volume={gain}")
        for k, vel, p, s in sorted(samples, key=lambda t: t[1]):
            if k != key:
                continue
            lv, hv = VEL[vel]
            line = f"<region> lovel={lv} hivel={hv} offset={s['offset']} tune={s['tune']}"
            if s["loop"]:
                line += f" loop_mode=loop_sustain loop_start={s['loop'][0]} loop_end={s['loop'][1]}"
            out.append(line + f" sample={p.name}")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
