"""Compare a transcription (ABC, in the yue-plan / SheetSage dialect or Copyist's) with the true score.

Usage: python scripts/transcribe/evaluate.py SONG.yaml TRANSCRIPTION.abc [--octave-free]

Truth: the song's melody and chords in seconds (its tempo). Transcription: the ABC's Vocal voice
(or Ins, when SheetSage put an instrumental lead there) in seconds (its Q:). The best global time
shift and tempo ratio are found first (the transcriber may start the clock elsewhere), then notes
are matched one to one: onset within a quarter beat, pitch equal (or equal mod 12 with
--octave-free, for a take sung in another octave). Chords: root and major/minor, compared every
0.1 s. docs/transcribing.md has the numbers measured so far.
"""
from __future__ import annotations

import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from music21 import harmony, note  # noqa: E402

from copyist import abcplan  # noqa: E402
from copyist.song import load_song  # noqa: E402


def truth(song_path):
    song = load_song(song_path)
    mm = song.melody.recurse().getElementsByClass("MetronomeMark").first()
    spq = 60.0 / mm.getQuarterBPM()
    notes, chords = [], []
    for el in song.melody.recurse().notesAndRests:
        off = float(el.getOffsetInHierarchy(song.melody))
        if isinstance(el, harmony.ChordSymbol):
            chords.append((off * spq, el.root().pitchClass, "m" if "minor" in el.chordKind else ""))
            continue
        if isinstance(el, note.Note):
            if el.tie is not None and el.tie.type in ("stop", "continue"):
                notes[-1][1] += el.quarterLength * spq
                continue
            notes.append([off * spq, el.quarterLength * spq, el.pitch.midi])
    return notes, chords, spq


def transcribed(abc_text):
    """Notes from the Vocal voice, or from Ins when Vocal has none (SheetSage on an instrumental lead);
    chords from the Vocal voice."""
    try:
        plan = abcplan.parse(abc_text)
    except abcplan.PlanError:
        swapped = abc_text.replace("V: Vocal", "V: Tmp").replace("V: Ins", "V: Vocal").replace("V: Tmp", "V: Ins")
        plan = abcplan.parse(swapped)
    chord_bars = parse_any(abc_text).vocal
    tf = abcplan.tempo_field(plan.tempo)
    if isinstance(tf, int):
        q = 60.0 / tf
    else:
        unit_txt, bpm = tf.split("=")
        q = 60.0 / (float(bpm) * float(Fraction(unit_txt)) * 4)
    unit_q = float(plan.unit * 4)
    notes, chords, tied = [], [], False
    t = 0.0
    for bar, row in zip(plan.vocal, abcplan._note_midis(plan.vocal, plan.key)):
        for tok, m in zip(bar.toks, row):
            if tok.kind == "chord":
                continue
            length = float(tok.length) * unit_q
            if tok.kind == "note":
                if tied and notes:
                    notes[-1][1] += length * q
                else:
                    notes.append([t * q, length * q, m])
                tied = tok.tie
            else:
                tied = False
            t += length
    t = 0.0
    for bar in chord_bars:
        for tok in bar.toks:
            if tok.kind == "chord":
                try:
                    cs = harmony.ChordSymbol(re.sub(r"^([A-G])b", r"\1-", tok.text))
                    chords.append((t * q, cs.root().pitchClass, "m" if "minor" in cs.chordKind else ""))
                except Exception:
                    pass
            else:
                t += float(tok.length) * unit_q
    return notes, chords, plan


def parse_any(abc_text):
    """The Vocal voice even with no notes in it (its chords)."""
    import re
    header, voice, plan = {}, None, None
    for raw in abc_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%"):
            continue
        m = re.match(r"^([A-Za-z]):\s*(.*)$", line)
        if m and not line.startswith("V:"):
            header[m.group(1)] = m.group(2).strip()
            if m.group(1) == "K":
                plan = abcplan.Plan(header.get("M"), Fraction(header.get("L")), header.get("Q", ""), m.group(2).strip())
            continue
        if line.startswith("V:"):
            voice = line[2:].split()[0]
            continue
        if voice == "Vocal":
            for chunk in line.split("|"):
                if chunk.strip():
                    toks, z = abcplan.tokenize_bar(chunk)
                    plan.vocal.append(abcplan.Bar(toks or [abcplan.Tok("rest", length=plan.bar_units)], "x"))
    return plan


def match(truth_notes, notes, spq, octave_free, shift, ratio=1.0, tol_beats=0.25):
    tol = tol_beats * spq
    used = set()
    hits = 0
    pitch_off = []
    for ts, td, tm in truth_notes:
        best = None
        for k, (s, d, m) in enumerate(notes):
            if k in used:
                continue
            st = s * ratio + shift
            if abs(st - ts) <= tol:
                ok = (m % 12 == tm % 12) if octave_free else (m == tm)
                if ok and (best is None or abs(st - ts) < best[0]):
                    best = (abs(st - ts), k, m - tm)
        if best:
            used.add(best[1])
            hits += 1
            pitch_off.append(best[2])
    p = hits / max(1, len(notes))
    r = hits / max(1, len(truth_notes))
    f = 2 * p * r / max(1e-9, p + r)
    return f, p, r, hits, pitch_off


def best_alignment(truth_notes, notes, spq, octave_free, search=14.0):
    best = (-1, 0, 1.0)
    for ratio in [x / 1000 for x in range(900, 1101, 5)] + [0.5, 2.0, 2 / 3, 1.5]:
        for step in range(int(-search * 20), int(search * 20) + 1):
            shift = step / 20
            f = match(truth_notes, notes, spq, octave_free, shift, ratio)[0]
            if f > best[0]:
                best = (f, shift, ratio)
    # refine
    f0, s0, r0 = best
    for dr in [x / 2000 for x in range(-10, 11)]:
        for ds in [x / 100 for x in range(-10, 11)]:
            f = match(truth_notes, notes, spq, octave_free, s0 + ds, r0 + dr)[0]
            if f > best[0]:
                best = (f, s0 + ds, r0 + dr)
    return best


def chord_accuracy(truth_chords, chords, shift, ratio, end):
    if not chords or not truth_chords:
        return 0.0

    def at(seq, t):
        cur = None
        for s, root, q in seq:
            if s <= t:
                cur = (root, q)
        return cur
    step, ok, n = 0.1, 0, 0
    t = truth_chords[0][0]
    shifted = [(s * ratio + shift, r, q) for s, r, q in chords]
    while t < end:
        a, b = at(truth_chords, t), at(shifted, t)
        if a is not None:
            n += 1
            ok += a == b
        t += step
    return ok / max(1, n)


def main():
    song_path, abc_path = sys.argv[1], sys.argv[2]
    octave_free = "--octave-free" in sys.argv
    tn, tc, spq = truth(song_path)
    notes, chords, plan = transcribed(Path(abc_path).read_text())
    f, shift, ratio = best_alignment(tn, notes, spq, octave_free)
    f, p, r, hits, offs = match(tn, notes, spq, octave_free, shift, ratio)
    from collections import Counter
    end = tn[-1][0] + tn[-1][1]
    print(f"{Path(abc_path).name}: {plan.meter} {plan.key} Q:{plan.tempo}; {len(notes)} notes vs {len(tn)} true")
    print(f"  alignment: shift {shift:+.2f} s, time ratio {ratio:.3f}")
    print(f"  notes F1 {f:.2f} (precision {p:.2f}, recall {r:.2f}); octave of matches: {dict(Counter(o // 12 for o in offs))}")
    print(f"  chords (root and maj/min, by time): {chord_accuracy(tc, chords, shift, ratio, end):.2f}")


if __name__ == "__main__":
    main()
