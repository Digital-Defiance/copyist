"""Check a sung recording against the score, note by note (SPEC.md section 6).

Uses pYIN pitch tracking (librosa). Each note is judged on the middle of its
length, so scoops into a note and slides out of it don't count against it:
real singing bends around the written pitch, and that's allowed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from music21 import pitch as m21pitch

from .sing import REST, SungNote

TOLERANCE_CENTS = 50   # within a quarter tone either way counts as the right note


@dataclass
class NoteCheck:
    note: SungNote
    sung_hz: float | None
    cents: float | None    # sung minus written; None if no pitch was found

    @property
    def ok(self) -> bool:
        return self.cents is not None and abs(self.cents) <= TOLERANCE_CENTS

    @property
    def target(self) -> str:
        return m21pitch.Pitch(midi=self.note.midi).nameWithOctave

    def describe(self) -> str:
        where = f"bar {self.note.bar}" if self.note.bar is not None else ""
        if self.cents is None:
            return f"{where} “{self.note.word}”: no clear pitch (written {self.target})"
        sung = m21pitch.Pitch()
        sung.frequency = self.sung_hz
        direction = "sharp" if self.cents > 0 else "flat"
        return (f"{where} “{self.note.word}”: sang {sung.nameWithOctave} ({abs(self.cents):.0f} cents {direction}),"
                f" written {self.target}")


def load_mono(path: Path):
    import librosa
    y, sr = librosa.load(str(path), sr=None, mono=True)
    return y, sr


def check(wav: Path, notes: list[SungNote], offset: float = 0.0, min_length: float = 0.12) -> list[NoteCheck]:
    """Compare each sung note's pitch with the written pitch.

    `offset` is where the excerpt's time zero falls in the recording, in seconds.
    """
    import librosa
    import numpy as np
    y, sr = load_mono(wav)
    hop = 256
    f0, voiced, _ = librosa.pyin(y, fmin=65.0, fmax=1100.0, sr=sr, frame_length=2048, hop_length=hop)
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop)
    results = []
    for n in notes:
        if n.kind == REST or n.dur < min_length:
            continue
        a = offset + n.start + min(0.25 * n.dur, 0.15)
        b = offset + n.start + n.dur - min(0.15 * n.dur, 0.1)
        sel = (times >= a) & (times <= b) & voiced & ~np.isnan(f0)
        if sel.sum() < 3:
            results.append(NoteCheck(n, None, None))
            continue
        hz = float(np.median(f0[sel]))
        target_hz = 440.0 * 2 ** ((n.midi - 69) / 12)
        results.append(NoteCheck(n, hz, 1200 * math.log2(hz / target_hz)))
    return results


def summary(results: list[NoteCheck]) -> str:
    if not results:
        return "No sung notes to check."
    good = sum(r.ok for r in results)
    return f"{good} of {len(results)} sung notes within ±{TOLERANCE_CENTS} cents of the written pitch."


def report_lines(results: list[NoteCheck]) -> list[str]:
    lines = ["## Sung pitch check", "", summary(results)]
    bad = [r for r in results if not r.ok]
    if bad:
        lines += ["", "| Where | What happened |", "|---|---|"]
        lines += [f"| bar {r.note.bar} | {r.describe().split(': ', 1)[1]} |" for r in bad]
    return lines
