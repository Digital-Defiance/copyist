"""Write copyist/sound/organ.sfz: the VCSL pipe organ manuals (Quiet + Loud).

VCSL ships the organ as WAV files only. This measures each one and writes an
SFZ for it: Quiet is the soft dynamic, Loud the hard; samples are named by
note (C4 = MIDI 60). Held notes loop in the steady tone.

Usage: python scripts/instruments/organ.py /path/to/VCSL > copyist/sound/organ.sfz
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

QUIET = "Aerophones/Edge-blown Aerophones/Pipe Organ/Quiet"
LOUD = "Aerophones/Edge-blown Aerophones/Pipe Organ/Loud"
NAME = re.compile(r"(?:NT5_Man3Quiet|Rode_Man3Open)_([A-G])(#?)(\d)_rr1\.wav$")
# Loud files use Rode_Man3Open_C4.wav (no _rr1 in some? check)
NAME_LOUD = re.compile(r"Rode_Man3Open_([A-G])(#?)(\d)\.wav$")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VEL = {"quiet": (1, 84), "loud": (85, 127)}


def named_key(letter: str, sharp: str, octave: str) -> int:
    """MIDI from the file name (C4 = 60)."""
    return (int(octave) + 1) * 12 + PC[letter] + (1 if sharp else 0)


def measure(path: Path, key: int) -> dict | None:
    x, sr = sf.read(str(path), always_2d=True)
    mono = x.mean(axis=1)
    ten = int(0.01 * sr)
    fine = 20 * np.log10(np.array(
        [np.sqrt(np.mean(mono[i:i + ten] ** 2)) for i in range(0, len(mono) - ten, ten)]) + 1e-9)
    steady_db = float(np.median(fine[30:150]))
    onset = int(np.argmax(fine >= steady_db - 25)) * ten
    offset = max(0, onset - int(0.01 * sr))
    hop = int(0.05 * sr)
    frames = np.array([np.sqrt(np.mean(mono[i:i + hop] ** 2)) for i in range(0, len(mono) - hop, hop)])
    db = 20 * np.log10(frames + 1e-9)
    start_f = max(0, onset // hop)
    body = db[start_f + 4:]
    loop = None
    if len(body) > 16:
        steady = np.median(body[: max(8, len(body) // 2)])
        inside = np.where(np.abs(body - steady) < 4.0)[0]
        if len(inside):
            first = start_f + 4 + int(inside[0]) + 2
            last = start_f + 4 + int(inside[-1]) - 2
            if (last - first) * hop > 0.6 * sr:
                loop = (first * hop, last * hop)
    a, b = onset + int(0.2 * sr), min(len(mono), onset + int(1.0 * sr))
    fmin = max(27.5, librosa.midi_to_hz(max(24, key - 8)))
    fmax = min(sr / 2 - 1, librosa.midi_to_hz(min(108, key + 8)))
    try:
        f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                     fmin=fmin, fmax=fmax, frame_length=4096)
    except Exception as e:
        print(f"skip {path.name}: pitch failed ({e})", file=sys.stderr)
        return None
    if not np.any(voiced):
        print(f"skip {path.name}: no pitch", file=sys.stderr)
        return None
    heard = float(librosa.hz_to_midi(np.nanmedian(f0[voiced])))
    if abs(heard - key) > 3:
        print(f"skip {path.name}: sounds as MIDI {heard:.1f}, expected {key}", file=sys.stderr)
        return None
    key = round(heard)
    return {"key": key, "offset": offset, "loop": loop, "tune": round(100 * (key - heard))}


def collect(root: Path) -> list[tuple[int, str, Path, dict]]:
    # Quiet manuals are named an octave low (file C4 sounds C5); Loud matches MIDI.
    out = []
    for folder, dyn, pat, bump in (
        (QUIET, "quiet", NAME, 12),
        (LOUD, "loud", NAME_LOUD, 0),
    ):
        for p in sorted((root / folder).glob("*.wav")):
            m = pat.search(p.name)
            if not m:
                continue
            key = named_key(m.group(1), m.group(2), m.group(3)) + bump
            s = measure(p, key)
            if s:
                out.append((s["key"], dyn, p, s))
    return out


def main(root: Path) -> None:
    samples = collect(root)
    if not samples:
        raise SystemExit(f"No organ manuals found under {root}")
    keys = sorted({k for k, *_ in samples})
    out = [
        "// Copyist pipe organ: VCSL manuals, Quiet + Loud (CC0, Versilian Studios / Simon Dalzell).",
        "// Written by scripts/instruments/organ.py; see that file for how each number was measured.",
        "<control>",
        "",
        "<global>",
        "ampeg_attack=0.02",
        "ampeg_release=0.35",
        "amp_veltrack=55",
        "loop_crossfade=0.08",
        "",
    ]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        out.append(f"<group> lokey={lo} hikey={hi} pitch_keycenter={key}")
        for k, dyn, p, s in sorted(samples, key=lambda t: (t[0], t[1])):
            if k != key:
                continue
            lv, hv = VEL[dyn]
            # default_path differs for Quiet vs Loud — use absolute path from instrument root.
            rel = p.relative_to(root).as_posix()
            line = f"<region> lovel={lv} hivel={hv} offset={s['offset']} tune={s['tune']}"
            if s["loop"]:
                line += f" loop_mode=loop_sustain loop_start={s['loop'][0]} loop_end={s['loop'][1]}"
            out.append(line + f" sample={rel}")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
