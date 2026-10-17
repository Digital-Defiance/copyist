"""Write copyist/sound/clarinet.sfz: the VSCO 2 CE clarinet (sustained, three dynamics) as a melody voice.

VSCO ships the clarinet as WAV files only. This measures each one and writes an
SFZ for it:

- VSCO names its octaves one lower than MIDI's usual C4 = 60 (the file named
  D4 sounds D5, MIDI 74), so the key is (octave + 2) * 12 + pitch class.
- Some recordings start with up to 0.2 s of silence; `offset` skips it, so
  notes speak on the beat.
- Each sample's pitch is measured: `tune` corrects it to equal temperament,
  and the measured note wins over the file name (the files named F#5 are F).
- The loudness of the middle dynamic is evened out across the range (the low
  register is quieter, which a preview melody shouldn't be).
- Held notes loop inside the steady part of the tone, so a long phrase ending
  doesn't run out of sample.

Usage: python scripts/instruments/clarinet.py /path/to/VSCO-2-CE > copyist/sound/clarinet.sfz
"""
import re
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

FOLDER = "Woodwinds/Clarinet/susLong"
NAME = re.compile(r"DCClar_susLong_([A-G])(#?)(\d)_v(\d)_rr1_sum\.wav$")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
VEL = {1: (1, 63), 2: (64, 99), 3: (100, 127)}
EVEN = 0.7          # how much of each note's loudness difference from the median to take out


def key_of(m) -> int:
    return (int(m.group(3)) + 2) * 12 + PC[m.group(1)] + (1 if m.group(2) else 0)


def measure(path: Path, key: int) -> dict:
    x, sr = sf.read(str(path), always_2d=True)
    mono = x.mean(axis=1)
    # Onset: the first 10 ms that reaches 20 dB under the steady tone (before that is room noise
    # and breath); start 15 ms ahead of it so the attack is kept.
    ten = int(0.01 * sr)
    fine = 20 * np.log10(np.array([np.sqrt(np.mean(mono[i:i + ten] ** 2)) for i in range(0, len(mono) - ten, ten)]) + 1e-9)
    steady_db = float(np.median(fine[50:200]))
    onset = int(np.argmax(fine >= steady_db - 20)) * ten
    offset = max(0, onset - int(0.015 * sr))
    hop = int(0.05 * sr)
    frames = np.array([np.sqrt(np.mean(mono[i:i + hop] ** 2)) for i in range(0, len(mono) - hop, hop)])
    db = 20 * np.log10(frames + 1e-9)
    start_f = onset // hop
    body = db[start_f + 6:]                       # skip the attack (300 ms)
    loop = None
    if len(body) > 20:
        steady = np.median(body[: max(10, len(body) // 2)])
        inside = np.where(np.abs(body - steady) < 3.0)[0]
        if len(inside):
            first = start_f + 6 + int(inside[0]) + 4
            last = start_f + 6 + int(inside[-1]) - 4
            if (last - first) * hop > 1.0 * sr:
                loop = (first * hop, last * hop)
    a, b = onset + int(0.3 * sr), onset + int(1.3 * sr)
    f0, voiced, _ = librosa.pyin(mono[a:b].astype(np.float32), sr=sr,
                                 fmin=librosa.midi_to_hz(key - 8), fmax=librosa.midi_to_hz(key + 8))
    heard = float(librosa.hz_to_midi(np.nanmedian(f0[voiced])))
    if abs(heard - key) > 2:
        raise SystemExit(f"{path.name}: sounds as MIDI {heard:.1f}, named {key}; the octave rule is wrong for it")
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
        samples.append((s["key"], int(m.group(4)), p, s))
    keys = sorted({k for k, *_ in samples})
    mid = {k: s["rms"] for k, v, _, s in samples if v == 2}
    median = float(np.median(list(mid.values())))
    out = ["// Copyist melody voice: the VSCO 2 Community Edition clarinet (CC0, Versilian Studios).",
           "// Written by scripts/instruments/clarinet.py; see that file for how each number was measured.",
           "<control>", f"default_path={FOLDER}/", "",
           "<global>", "ampeg_attack=0.01", "ampeg_release=0.18", "amp_veltrack=45",
           "loop_crossfade=0.12", ""]
    for i, key in enumerate(keys):
        lo = 0 if i == 0 else (keys[i - 1] + key) // 2 + 1
        hi = 127 if i == len(keys) - 1 else (key + keys[i + 1]) // 2
        gain = round(-(mid[key] - median) * EVEN, 1)
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
