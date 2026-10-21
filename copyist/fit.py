"""Fitting lyrics to a melody that wasn't written for Copyist's syllables (docs/melody-writing.md).

Every note onset takes exactly one syllable or holds the one before (a
melisma), so the fit is a path through syllables and notes. Dynamic programming
finds the cheapest path, where cost is what a singer or songwriter would
object to: a stressed syllable on a weak beat, a line that ends mid-phrase, a
breath in the middle of a word, a held note across a rest. When there are more
syllables than notes, the longest notes are split in two first (a repeated
pitch, as singers do with an extra word).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from .abcplan import Bar, Tok
from .syllables import Section, Syllable

MAX_HOLD = 5                    # extra notes one syllable may hold
SPLIT_BEAT = 0.5                # a held note and the next syllable's first note share a beat
HINT_WEIGHT = 1.0               # what the recording says outweighs a weak beat
SPLIT_LIMIT = 0.10              # split at most this share of the notes


def syllables_for_transcription(sections: list[Section], n_notes: int) -> tuple[list[Syllable], list[str]]:
    """Syllables that can sit under a transcribed melody, plus notes for the report.

    A full libretto (repeats, spoken word) often has far more syllables than notes heard.
    For transcription the melody is the source of truth: drop spoken sections, then take
    whole lines from the start until the fit's split budget would be exceeded.
    """
    from .syllables import all_syllables
    max_sylls = n_notes + int(SPLIT_LIMIT * n_notes)
    notes: list[str] = []
    sung = [s for s in sections if s.name != "spoken"]
    if sum(1 for s in sections if s.name == "spoken"):
        notes.append("Left spoken words off the lead sheet (they're not sung under the melody).")
    total = len(all_syllables(sections))
    kept: list[Syllable] = []
    for sec in sung:
        for line in sec.lines:
            if len(kept) + len(line.syllables) > max_sylls:
                notes.append(f"The lyrics have {total} syllables and the melody has {n_notes} notes; "
                             f"fitted the opening {len(kept)} syllables and left the rest off. Check by ear.")
                return kept, notes
            kept.extend(line.syllables)
    if not kept and sections:
        # Only spoken (or empty) lyrics: fall back to everything, still capped.
        for sec in sections:
            for line in sec.lines:
                if len(kept) + len(line.syllables) > max_sylls:
                    break
                kept.extend(line.syllables)
    return kept, notes


@dataclass
class Slot:
    bar: int
    tok: int                    # index of the onset token in its bar
    start: Fraction             # in quarter notes from the start of the line
    length: Fraction            # in quarter notes, ties included
    strength: float             # metric weight of the onset
    rest_after: bool            # a rest follows before the next onset
    breath_before: bool         # a rest, or a note at least a beat long, comes before it
    syllable_hint: float | None = None   # from a recording: how surely a new syllable starts here (0..1)
    beat: tuple[int, int] = (0, 0)       # (bar, beat in the bar) the onset falls in


@dataclass
class Fit:
    spans: list[tuple[int, int]]        # per syllable: (first slot, last slot)
    cost: float
    splits: int
    lyrics: str                         # in Copyist's lyric syntax


def beat_length(meter: str) -> Fraction:
    """One beat in quarter notes: a dotted quarter in 6/8, 9/8 and 12/8."""
    num, den = (int(x) for x in meter.split("/"))
    return Fraction(12, den) if den == 8 and num % 3 == 0 and num > 3 else Fraction(4, den)


def beat_strength(pos_q: Fraction, meter: str) -> float:
    """Metric weight of a position in the bar (quarter notes from the bar line)."""
    num, den = (int(x) for x in meter.split("/"))
    compound = den == 8 and num % 3 == 0 and num > 3
    beat = beat_length(meter)
    if pos_q == 0:
        return 1.0
    beats = pos_q / beat
    n_beats = num // 3 if compound else num
    if beats.denominator == 1:
        middle = n_beats % 2 == 0 and beats == n_beats // 2
        return 0.5 if middle else 0.25
    if (pos_q / (beat / (3 if compound else 2))).denominator == 1:
        return 0.125
    return 0.0625


def slots(bars: list[Bar], unit: Fraction, meter: str) -> list[Slot]:
    """Note onsets with their length, metric strength and the rests around them."""
    q_per_unit = unit * 4
    beat = beat_length(meter)
    out: list[Slot] = []
    pos = Fraction(0)
    tied = False
    rest_pending = True
    num, den = (int(x) for x in meter.split("/"))
    full = Fraction(num, den) / unit
    for b, bar in enumerate(bars):
        # A short first bar is a pickup: its notes sit at the end of a bar.
        in_bar = (full - bar.length) * q_per_unit if b == 0 and bar.length < full else Fraction(0)
        for k, t in enumerate(bar.toks):
            if t.kind == "chord":
                continue
            length = t.length * q_per_unit
            if t.kind == "rest":
                if out and not tied:
                    out[-1].rest_after = True
                rest_pending = True
            elif tied and out:
                out[-1].length += length
            else:
                breath = rest_pending or (bool(out) and out[-1].length >= beat)
                out.append(Slot(b, k, pos, length, beat_strength(in_bar, meter), False, breath,
                                beat=(b, int(in_bar // beat))))
                rest_pending = False
            tied = t.kind == "note" and t.tie
            pos += length
            in_bar += length
    if out:
        out[-1].rest_after = True
    return out


def split_notes(bars: list[Bar], unit: Fraction, meter: str, needed: int) -> int:
    """Split the `needed` longest notes (a beat or longer, not tied, not before a rest, where a line
    would end) into two equal notes of the same pitch."""
    beat_units = beat_length(meter) / (unit * 4)
    done = 0
    for _ in range(needed):
        cands = []
        for s in slots(bars, unit, meter):
            t = bars[s.bar].toks[s.tok]
            if t.tie or s.rest_after or t.length < beat_units or t.length < 2:
                continue
            cands.append((t.length, -s.start, s))
        if not cands:
            break
        _, _, s = max(cands, key=lambda c: (c[0], c[1]))
        t = bars[s.bar].toks[s.tok]
        half = Fraction(int(t.length) // 2) if t.length.denominator == 1 else t.length / 2
        first = Tok("note", acc=t.acc, step=t.step, octave=t.octave, length=half)
        second = Tok("note", acc=t.acc, step=t.step, octave=t.octave, length=t.length - half)
        bars[s.bar].toks[s.tok:s.tok + 1] = [first, second]
        done += 1
    return done


def cost_of(syl: Syllable, span: list[Slot], beat_q: Fraction) -> float:
    first, last = span[0], span[-1]
    w = syl.weight
    c = w * (1 - first.strength) * 1.0 + (1 - w / 2) * first.strength * 0.3
    held = len(span) - 1
    if held:
        each = 0.15 if syl.line_end else (0.6 if syl.word_end else 0.4)
        c += held * each
        if any(s.rest_after for s in span[:-1]):
            c += 5.0
    if syl.line_end and not last.rest_after and last.length < beat_q:
        c += 1.5
    if not syl.line_end and last.rest_after:
        c += 2.0 if not syl.word_end else 0.8
    if syl.line_start and not first.breath_before:
        c += 0.5
    # A transcription knows where the singer started syllables (a consonant, a breath) and where the
    # voice only moved to another pitch (a melisma).
    if first.syllable_hint is not None:
        c += HINT_WEIGHT * (1 - first.syllable_hint)
    c += HINT_WEIGHT * sum(s.syllable_hint for s in span[1:] if s.syllable_hint is not None)
    return c


WORD_STRESS = 1.5               # a word's stressed syllable on a weaker beat than its neighbour


def pair_cost(prev: Syllable, prev_slot: Slot, syl: Syllable, slot: Slot) -> float:
    """Neighbouring syllables of one word: the stressed one shouldn't land on the weaker beat
    ("a-BASH" sung "A-bash"), the rule `copyist check` warns about."""
    if prev.word_end or prev.word != syl.word:
        return 0.0
    if prev.weight >= 2 and syl.weight == 0 and slot.strength > prev_slot.strength:
        return WORD_STRESS
    if syl.weight >= 2 and prev.weight == 0 and prev_slot.strength > slot.strength:
        return WORD_STRESS
    return 0.0


def align(sylls: list[Syllable], notes: list[Slot], meter: str) -> tuple[list[tuple[int, int]], float]:
    """Cheapest assignment of every note to a syllable, each syllable taking 1..MAX_HOLD+1 notes in order.

    The state is (syllables placed, notes used, notes the last syllable took), so the cost can
    compare a syllable with the one before it in the same word, and see a held note just before it.
    A syllable shouldn't start in the middle of a beat whose first note only held the one before:
    "A-maz-ing_ grace" sings "ing" on both eighths of beat 3, not "A-maz-_ ing" with "maz" carried
    onto the first eighth and "ing" squeezed onto the second.
    """
    beat_q = beat_length(meter)
    S, N = len(sylls), len(notes)
    T = MAX_HOLD + 1
    INF = float("inf")
    # best[i][j][t]: syllables 0..i-1 on notes 0..j-1, syllable i-1 on t notes (t = 0 before any)
    best = [[[INF] * (T + 1) for _ in range(N + 1)] for _ in range(S + 1)]
    back: dict[tuple[int, int, int], int] = {}
    best[0][0][0] = 0.0
    for i in range(S):
        syl = sylls[i]
        lo, hi = i, N - (S - i)                 # every syllable before and after needs a note
        for j in range(lo, hi + 1):
            for t in range(T + 1):
                here = best[i][j][t]
                if here == INF:
                    continue
                pair_prev = (sylls[i - 1], notes[j - t]) if i and t else None
                for take in range(1, T + 1):
                    if j + take > N - (S - i - 1):
                        break
                    c = here + cost_of(syl, notes[j:j + take], beat_q)
                    if t >= 2 and notes[j - 1].beat == notes[j].beat:
                        c += SPLIT_BEAT
                    if pair_prev:
                        c += pair_cost(pair_prev[0], pair_prev[1], syl, notes[j])
                    if c < best[i + 1][j + take][take]:
                        best[i + 1][j + take][take] = c
                        back[(i + 1, j + take, take)] = t
    end_t = min(range(T + 1), key=lambda t: best[S][N][t])
    if best[S][N][end_t] == INF:
        raise ValueError(f"{S} syllables can't fit {N} notes with at most {MAX_HOLD} held notes each.")
    total = best[S][N][end_t]
    spans, j, t = [], N, end_t
    for i in range(S, 0, -1):
        spans.append((j - t, j - 1))
        t, j = back[(i, j, t)], j - t
    return list(reversed(spans)), total


def lyric_text(sylls: list[Syllable], spans: list[tuple[int, int]]) -> str:
    """Copyist's lyric syntax: "fea-thers", a hold inside a word "al-_ read-y", at a word's end
    "soul_". One lyric line per line of text (the loader treats line breaks as spaces)."""
    lines: list[list[str]] = [[]]
    chunk = ""
    for syl, (a, b) in zip(sylls, spans):
        holds = b - a
        text = syl.text.replace("-", "").replace("_", "").replace("*", "")
        if syl.word_end:
            lines[-1].append(chunk + text + "_" * holds)
            chunk = ""
        elif holds:
            lines[-1].append(chunk + text + "-" + "_" * holds)
            chunk = ""
        else:
            chunk += text + "-"
        if syl.line_end and syl.word_end:
            lines.append([])
    if chunk:
        lines[-1].append(chunk.rstrip("-"))
    return "\n".join(" ".join(words) for words in lines if words)


def fit(bars: list[Bar], unit: Fraction, meter: str, sylls: list[Syllable],
        hints: list[float] | None = None) -> Fit:
    """Fit the syllables to the bars, splitting notes first if there are too few. Changes `bars` when it
    splits. `hints`, one per note from a transcription, say how surely a syllable starts on each."""
    notes = slots(bars, unit, meter)
    splits = 0
    if len(sylls) > len(notes):
        needed = len(sylls) - len(notes)
        if needed > SPLIT_LIMIT * len(notes):
            raise ValueError(f"The melody has {len(notes)} notes for {len(sylls)} syllables; "
                             "it was written for different words.")
        splits = split_notes(bars, unit, meter, needed)
        notes = slots(bars, unit, meter)
        if len(sylls) > len(notes):
            raise ValueError(f"Couldn't make room for {len(sylls)} syllables in {len(notes)} notes.")
    if hints and len(hints) == len(notes):
        for slot, h in zip(notes, hints):
            slot.syllable_hint = h
    spans, cost = align(sylls, notes, meter)
    return Fit(spans, cost + 2.0 * splits, splits, lyric_text(sylls, spans))
