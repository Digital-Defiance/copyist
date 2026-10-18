"""Write copyist/sound/harp.sfz: the VSCO 2 CE concert harp.

VSCO ships the harp as WAV files only. This measures each sample and writes an
SFZ: note names match MIDI (C4 = 60); dynamics are mp / mf / f from the file name.
Plucked notes decay naturally (no loop).

Usage: python scripts/instruments/harp.py /path/to/VSCO-2-CE > copyist/sound/harp.sfz
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from librosa.util.exceptions import ParameterError

FOLDER = "Strings/Harp"
NAME = re.compile(r"KSHarp_([A-G])(#?)(\d)_(mp|mf|f)\.wav$")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VEL = {"mp": (1, 54), "mf": (55, 99), "f": (100, 127)}


def key_of(m) -> int:
    return (int(m.group(3)) + 1) * 12 + PC[m.group(1)] + (1 if m.group(2) else 0)


def measure(path: Path, key: int) -> dict | None:
    x, sr = sf.read(str(path), always_2d=True)
    mono = x.mean(axis=1)
    ten = int(0.005 * sr)
    fine = 20 * np.log10(np.array(
        [np.sqrt(np.mean(mono[i:i + ten] ** 2)) for i in range(0, max(1, len(mono) - ten), ten)]) + 1e-9)
    peak = float(np.max(fine[: min(80, len(fine))]))
    onset = int(np.argmax(fine >= peak - 18)) * ten
    offset = max(0, onset - int(0.005 * sr))
    a, b = onset, min(len(mono), onset + int(0.5 * sr))
    try:
        f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                     fmin=max(27.5, librosa.midi_to_hz(key - 6)),
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
    return {"key": key, "offset": offset, "tune": round(100 * (key - heard))}


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
        raise SystemExit(f"No harp samples under {root / FOLDER}")
    keys = sorted({k for k, *_ in samples})
    out = [
        "// Copyist concert harp: VSCO 2 Community Edition (CC0, Versilian Studios).",
        "// Written by scripts/instruments/harp.py; see that file for how each number was measured.",
        "<control>",
        f"default_path={FOLDER}/",
        "",
        "<global>",
        "ampeg_attack=0.002",
        "ampeg_release=1.8",
        "amp_veltrack=70",
        "",
    ]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        out.append(f"<group> lokey={lo} hikey={hi} pitch_keycenter={key}")
        at_key = [(dyn, p, s) for k, dyn, p, s in samples if k == key]
        # One sample for this note: cover the whole velocity range.
        if len(at_key) == 1:
            dyn, p, s = at_key[0]
            out.append(f"<region> lovel=1 hivel=127 offset={s['offset']} tune={s['tune']} sample={p.name}")
        else:
            for dyn, p, s in sorted(at_key, key=lambda t: t[0]):
                lv, hv = VEL[dyn]
                out.append(f"<region> lovel={lv} hivel={hv} offset={s['offset']} tune={s['tune']} "
                           f"sample={p.name}")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
