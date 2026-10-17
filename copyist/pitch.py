"""Check a sung recording against the score, note by note (SPEC.md section 6).

Uses pYIN pitch tracking (librosa). Each note is judged on the middle of its
length, so scoops into a note and slides out of it don't count against it:
real singing bends around the written pitch, and that's allowed.

Two allowances exist for performances Copyist didn't time itself (a YuE2
production, a recording):

- `search`: the recording may sit up to this many seconds early or late. The
  check first finds the shift that fits the whole excerpt best, then lets each
  phrase (`phrase_bars` bars) drift up to LOCAL_SEARCH seconds from it, and
  reports each phrase's shift.
- `any_octave`: a note sung in another octave still counts; the report says
  which octave. YuE2 picks the singer's octave itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from music21 import pitch as m21pitch

from .sing import REST, SungNote

TOLERANCE_CENTS = 50   # within a quarter tone either way counts as the right note
SEARCH_STEP = 0.05     # seconds between the timing shifts tried
LOCAL_SEARCH = 0.6     # seconds each phrase may drift from the recording's overall timing


@dataclass
class NoteCheck:
    note: SungNote
    sung_hz: float | None
    cents: float | None    # sung minus written (after any octave allowance); None if no pitch was found
    octave: int = 0        # octaves between the sung and written note, when any octave is allowed
    shift: float = 0.0     # seconds the note's phrase sat late (+) or early (-)

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


def track(wav: Path):
    """pYIN pitch track: (f0 in Hz with NaN where unvoiced, frame times)."""
    import librosa
    import numpy as np
    y, sr = load_mono(wav)
    hop = 256
    f0, voiced, _ = librosa.pyin(y, fmin=65.0, fmax=1100.0, sr=sr, frame_length=2048, hop_length=hop)
    f0 = np.where(voiced, f0, np.nan)
    return f0, librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop)


def _judge(n: SungNote, f0, times, at: float, any_octave: bool, shift: float) -> NoteCheck:
    import numpy as np
    a = at + n.start + min(0.25 * n.dur, 0.15)
    b = at + n.start + n.dur - min(0.15 * n.dur, 0.1)
    sel = (times >= a) & (times <= b) & ~np.isnan(f0)
    if sel.sum() < 3:
        return NoteCheck(n, None, None, 0, shift)
    hz = float(np.median(f0[sel]))
    cents = 1200 * math.log2(hz / (440.0 * 2 ** ((n.midi - 69) / 12)))
    octave = round(cents / 1200) if any_octave else 0
    return NoteCheck(n, hz, cents - 1200 * octave, octave, shift)


def check(wav: Path, notes: list[SungNote], offset: float = 0.0, min_length: float = 0.12,
          search: float = 0.0, any_octave: bool = False, phrase_bars: int = 4, tracked=None) -> list[NoteCheck]:
    """Compare each sung note's pitch with the written pitch.

    `offset` is where the excerpt's time zero falls in the recording, in seconds.
    `search` and `any_octave` are the allowances described at the top of this module.
    `tracked` is a result of `track(wav)`, to check several verses without tracking twice.
    """
    import numpy as np
    f0, times = tracked if tracked is not None else track(wav)
    notes = [n for n in notes if n.kind != REST and n.dur >= min_length]
    if search <= 0:
        return [_judge(n, f0, times, offset, any_octave, 0.0) for n in notes]
    phrases: dict[int, list[SungNote]] = {}
    for n in notes:
        phrases.setdefault((n.bar or 0) // phrase_bars, []).append(n)
    def middle_fit(group, shifts):
        counts = [sum(_judge(n, f0, times, offset + s, any_octave, 0.0).ok for n in group) for s in shifts]
        top = max(counts)
        return [float(s) for s, c in zip(shifts, counts) if c == top]

    overall = middle_fit(notes, np.arange(-search, search + 1e-9, SEARCH_STEP))
    base = overall[len(overall) // 2]
    shifts = np.arange(base - LOCAL_SEARCH, base + LOCAL_SEARCH + 1e-9, SEARCH_STEP)
    results = []
    for _, group in sorted(phrases.items()):
        # Every shift that keeps a note's middle inside the note fits equally
        # well. Timing drifts smoothly, so take the fit nearest the previous
        # phrase's shift (for the first phrase, nearest the overall shift).
        fits = middle_fit(group, shifts)
        s = min(fits, key=lambda f: abs(f - (results[-1].shift if results else base)))
        results += [_judge(n, f0, times, offset + s, any_octave, s) for n in group]
    return results


def octave_words(octave: int) -> str:
    if octave == 0:
        return "in the written octave"
    n = abs(octave)
    return f"{'an' if n == 1 else n} octave{'s' if n > 1 else ''} {'below' if octave < 0 else 'above'} the written pitch"


def summary(results: list[NoteCheck]) -> str:
    if not results:
        return "No sung notes to check."
    good = [r for r in results if r.ok]
    text = f"{len(good)} of {len(results)} sung notes within ±{TOLERANCE_CENTS} cents of the written pitch"
    octaves = {r.octave for r in good}
    if octaves and octaves != {0}:
        text += ", " + (octave_words(octaves.pop()) if len(octaves) == 1 else "in more than one octave")
    return text + "."


def timing_lines(results: list[NoteCheck], phrase_bars: int = 4) -> list[str]:
    """One line per phrase: how early or late it sat."""
    seen: dict[int, float] = {}
    for r in results:
        seen.setdefault((r.note.bar or 0) // phrase_bars, r.shift)
    lines = []
    for k, s in sorted(seen.items()):
        a, b = k * phrase_bars, k * phrase_bars + phrase_bars - 1
        when = "on time" if abs(s) < SEARCH_STEP / 2 else f"{abs(s):.2f} s {'late' if s > 0 else 'early'}"
        lines.append(f"- Bars {a}–{b}: {when}")
    return lines


def report_lines(results: list[NoteCheck]) -> list[str]:
    lines = ["## Sung pitch check", "", summary(results)]
    if any(r.shift for r in results):
        lines += ["", "Timing, per phrase:", ""] + timing_lines(results)
    bad = [r for r in results if not r.ok]
    if bad:
        lines += ["", "| Where | What happened |", "|---|---|"]
        lines += [f"| bar {r.note.bar} | {r.describe().split(': ', 1)[1]} |" for r in bad]
    return lines
