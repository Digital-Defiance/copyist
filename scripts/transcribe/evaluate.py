"""Compare a transcription with the true score, or with what was sung in a recording.

Usage:
  python scripts/transcribe/evaluate.py SONG.yaml TRANSCRIPTION.abc [--octave-free]
  python scripts/transcribe/evaluate.py --sung VOCAL.wav SONG.yaml [--octave-free]
  python scripts/transcribe/evaluate.py --sung VOCAL.wav DRAFT.abc [--tempo 106] [--octave-free]

Truth (score mode): the song's melody and chords in seconds (its tempo).
Truth (--sung): notes heard on the vocal stem (pYIN + the same tidy rules as the open engine,
without a lyric count), for songs that only exist as a recording (e.g. the owner's musical).

Hypothesis: the ABC's Vocal voice (or Ins, when SheetSage put the lead there), or a song file.
The best global time shift and tempo ratio are found first (`best_alignment`: a draft that already
matches every note stays put, and past ±14 s the shifts where same-pitch onsets line up are tried,
so a long intro still aligns), then notes are matched one to one: onset within a quarter beat, pitch
equal (or equal mod 12 with --octave-free). Chords (score mode only): root and major/minor, every
0.1 s. docs/transcribing.md has the numbers measured so far.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
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


def sung_truth(vocals: Path, target: int | None = None):
    """Notes heard on a vocal stem: truth when there is no written score to compare against."""
    import librosa
    from copyist import transcribe as tr
    y, _ = librosa.load(str(vocals), sr=tr.SR, mono=True)
    times, midi, rms = tr.vocal_track(y)
    onsets = librosa.onset.onset_detect(y=y, sr=tr.SR, hop_length=tr.PITCH_HOP, units="time",
                                        backtrack=True)
    heard = tr.clean_notes(tr.vocal_notes(times, midi, rms, onsets), times, midi, rms, target=target)
    notes = [[n.start, max(0.05, n.end - n.start), int(round(n.midi))] for n in heard]
    if len(notes) >= 2:
        iois = sorted(notes[i + 1][0] - notes[i][0] for i in range(len(notes) - 1))
        spq = float(iois[len(iois) // 2])          # median onset gap ≈ a beat for matching tolerance
    else:
        spq = 0.5
    return notes, [], spq


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


def hypothesis(path: Path):
    """Notes (and chords, seconds-per-quarter) from a song file or a draft ABC."""
    if path.suffix.lower() in (".yaml", ".yml"):
        notes, chords, spq = truth(path)
        song = load_song(path)
        return notes, chords, spq, f"{song.meter} {song.key} Q:{song.tempo}"
    notes, chords, plan = transcribed(path.read_text())
    label = f"{plan.meter} {plan.key} Q:{plan.tempo}"
    tf = abcplan.tempo_field(plan.tempo)
    if isinstance(tf, int):
        spq = 60.0 / tf
    else:
        unit_txt, bpm = tf.split("=")
        spq = 60.0 / (float(bpm) * float(Fraction(unit_txt)) * 4)
    return notes, chords, spq, label


def parse_any(abc_text):
    """The Vocal voice's bars, chords included, even with no notes in it: Copyist's own reader
    (`abcplan.read_vocal`), so every bar is kept across key changes and `Zn` is n bars."""
    return abcplan.read_vocal(abc_text)


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


# Tempo ratios tried when lining a draft up with the truth: near 1, then half, double and the 3:2 pair.
RATIOS = [x / 1000 for x in range(900, 1101, 5)] + [0.5, 2.0, 2 / 3, 1.5]


def best_alignment(truth_notes, notes, spq, octave_free, search=14.0):
    """The time shift (seconds) and tempo ratio that match the most notes: returns (F1, shift, ratio).

    1. A draft that already matches every true note where it stands stays there (0 s, ratio 1).
    2. Every ratio in RATIOS with every shift within ±`search` s, in 0.05 s steps; the first best wins.
    3. Past ±`search` s, the places where same-pitch onsets would line up (`_voted_steps`) are tried
       too, and win only by matching more notes. So a draft that keeps a long intro (SheetSage2
       does) still aligns, and a stray intro note can't mislead it the way the first note would.
    4. A finer search around the best.
    """
    if match(truth_notes, notes, spq, octave_free, 0.0, 1.0)[0] == 1.0:
        return (1.0, 0.0, 1.0)
    best = (-1, 0, 1.0)
    limit = int(search * 20)
    for ratio in RATIOS:
        for step in range(-limit, limit + 1):
            shift = step / 20
            f = match(truth_notes, notes, spq, octave_free, shift, ratio)[0]
            if f > best[0]:
                best = (f, shift, ratio)
    width = max(1, int(0.25 * spq * 20))          # match's onset tolerance, in steps
    for ratio in RATIOS:
        for step in _voted_steps(truth_notes, notes, octave_free, ratio, limit, width):
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


def _voted_steps(truth_notes, notes, octave_free, ratio, limit, width):
    """Shifts past ±`limit` steps (0.05 s each) worth trying at this tempo ratio, in order.

    Every true note and draft note on the same pitch (pitch class with `octave_free`) votes for the
    shift that would line them up. The three places outside the window with the most votes within
    `width` steps (match's onset tolerance) are kept, ties going to the lower shift, and every step
    within `width` of them that lies outside the window is returned."""
    def key(m):
        return m % 12 if octave_free else m

    onsets: dict[int, list[float]] = {}
    for s, _, m in notes:
        onsets.setdefault(key(m), []).append(s * ratio)
    votes = Counter()
    for ts, _, tm in truth_notes:
        for st in onsets.get(key(tm), ()):
            votes[round((ts - st) * 20)] += 1

    def support(b):
        return sum(votes.get(b + d, 0) for d in range(-width, width + 1))

    places = sorted((b for b in votes if abs(b) > limit), key=lambda b: (-support(b), b))[:3]
    steps: list[int] = []
    for b in places:
        steps += [s for s in range(b - width, b + width + 1) if abs(s) > limit and s not in steps]
    return steps


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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    octave_free = "--octave-free" in argv
    argv = [a for a in argv if a != "--octave-free"]
    tempo = None
    if "--tempo" in argv:
        i = argv.index("--tempo")
        tempo = float(argv[i + 1])
        del argv[i:i + 2]
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    if argv[0] == "--sung":
        if len(argv) < 3:
            print("Usage: evaluate.py --sung VOCAL.wav SONG.yaml|DRAFT.abc [--octave-free]", file=sys.stderr)
            return 2
        vocals, hyp_path = Path(argv[1]), Path(argv[2])
        tn, tc, sung_spq = sung_truth(vocals)
        notes, chords, hyp_spq, label = hypothesis(hyp_path)
        # Matching window from the transcription's tempo when we have one; else sung IOI.
        if hyp_path.suffix.lower() in (".yaml", ".yml"):
            spq = hyp_spq
        elif tempo is not None:
            spq = 60.0 / tempo
        else:
            spq = sung_spq
        source = f"sung({vocals.name}, {len(tn)} notes)"
        shown = hyp_path.name
    else:
        if len(argv) < 2:
            print("Usage: evaluate.py SONG.yaml TRANSCRIPTION.abc [--octave-free]", file=sys.stderr)
            return 2
        tn, tc, spq = truth(argv[0])
        notes, chords, _, label = hypothesis(Path(argv[1]))
        source = f"{Path(argv[0]).name} ({len(tn)} true)"
        shown = Path(argv[1]).name
    f, shift, ratio = best_alignment(tn, notes, spq, octave_free)
    f, p, r, hits, offs = match(tn, notes, spq, octave_free, shift, ratio)
    from collections import Counter
    end = tn[-1][0] + tn[-1][1] if tn else 0.0
    print(f"{shown}: {label}; {len(notes)} notes vs {source}")
    print(f"  alignment: shift {shift:+.2f} s, time ratio {ratio:.3f}")
    print(f"  notes F1 {f:.2f} (precision {p:.2f}, recall {r:.2f}); octave of matches: {dict(Counter(o // 12 for o in offs))}")
    if tc and chords:
        print(f"  chords (root and maj/min, by time): {chord_accuracy(tc, chords, shift, ratio, end):.2f}")
    else:
        print("  chords: (no written chord truth in --sung mode)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
