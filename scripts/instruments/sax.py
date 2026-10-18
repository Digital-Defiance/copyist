"""Write copyist/sound/sax.sfz: Karoryfer Weresax alto (dynamic mic, rr1 only).

Weresax ships a complex SFZ with humanize LFOs and round-robins. Copyist needs
deterministic previews, so this keeps only the first take of each note on the
dynamic mic, with p/f velocity layers, measured loops, and no random LFOs.

Usage: python scripts/instruments/sax.py /path/to/karoryfer.weresax > copyist/sound/sax.sfz
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from librosa.util.exceptions import ParameterError

FOLDER = "Samples/alto"
NAME = re.compile(r"^([a-g])([bs]?)(\d)_([pf])_rr1_dnm\.wav$")
PC = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
VEL = {"p": (1, 79), "f": (80, 127)}
EVEN = 0.5


def key_of(m) -> int:
    n = PC[m.group(1)]
    if m.group(2) == "s":
        n += 1
    elif m.group(2) == "b":
        n -= 1
    return (int(m.group(3)) + 1) * 12 + n


def measure(path: Path, key: int) -> dict | None:
    x, sr = sf.read(str(path), always_2d=True)
    mono = x.mean(axis=1)
    ten = int(0.01 * sr)
    fine = 20 * np.log10(np.array(
        [np.sqrt(np.mean(mono[i:i + ten] ** 2)) for i in range(0, max(1, len(mono) - ten), ten)]) + 1e-9)
    steady_db = float(np.median(fine[min(30, len(fine) // 2): min(160, len(fine))]))
    onset = int(np.argmax(fine >= steady_db - 18)) * ten
    offset = max(0, onset - int(0.008 * sr))
    hop = int(0.05 * sr)
    frames = np.array([np.sqrt(np.mean(mono[i:i + hop] ** 2)) for i in range(0, max(1, len(mono) - hop), hop)])
    db = 20 * np.log10(frames + 1e-9)
    start_f = onset // hop
    body = db[start_f + 3:]
    loop = None
    if len(body) > 16:
        steady = np.median(body[: max(8, len(body) // 2)])
        inside = np.where(np.abs(body - steady) < 3.5)[0]
        if len(inside):
            first = start_f + 3 + int(inside[0]) + 2
            last = start_f + 3 + int(inside[-1]) - 2
            if (last - first) * hop > 0.6 * sr:
                loop = (first * hop, last * hop)
    a, b = onset + int(0.1 * sr), min(len(mono), onset + int(0.9 * sr))
    heard = float(key)
    tune = 0
    fl = min(2048, max(512, (b - a) // 4))
    try:
        f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                     fmin=max(40.0, librosa.midi_to_hz(key - 5)),
                                     fmax=min(sr / 2 - 1, librosa.midi_to_hz(key + 5)),
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
    for p in sorted((root / FOLDER).glob("*_rr1_dnm.wav")):
        m = NAME.match(p.name)
        if not m:
            continue
        s = measure(p, key_of(m))
        if s:
            samples.append((s["key"], m.group(4), p, s))
    if not samples:
        raise SystemExit(f"No sax samples under {root / FOLDER}")
    keys = sorted({k for k, *_ in samples})
    loud = {k: s["rms"] for k, v, _, s in samples if v == "f"}
    median = float(np.median(list(loud.values())))
    out = [
        "// Copyist alto sax: Karoryfer Weresax (CC0), dynamic mic, rr1 only.",
        "// Written by scripts/instruments/sax.py; no humanize LFOs (deterministic).",
        "<control>",
        f"default_path={FOLDER}/",
        "",
        "<global>",
        "ampeg_attack=0.02",
        "ampeg_release=0.25",
        "amp_veltrack=55",
        "loop_crossfade=0.08",
        "",
    ]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        gain = round(-(loud.get(key, median) - median) * EVEN, 1)
        out.append(f"<group> lokey={lo} hikey={hi} pitch_keycenter={key} volume={gain}")
        for k, vel, p, s in sorted(samples, key=lambda t: (0 if t[1] == "p" else 1)):
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
