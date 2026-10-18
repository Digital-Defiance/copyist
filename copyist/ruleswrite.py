"""A rule-based melody writer (MIT): lyrics and a style in, bars out, without YuE2.

Rhythm follows syllable stress; pitches follow the chords with a contour template;
motifs repeat and vary; line ends cadence. Used by `copyist write --engine rules`
and as the fallback when yue-plan isn't installed (`--engine auto`).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from fractions import Fraction

from music21 import pitch as m21pitch

from . import abcplan, syllables
from .abcplan import Bar, Tok
from .write import WriteError

# Major keys the writer picks among (seeded). Prefer sharp-side for folk/waltz feel.
KEYS = ("C", "G", "D", "F", "Bb", "A", "Eb")
# Scale degree progressions (1-based), looping.
PROGRESSIONS = (
    (1, 5, 6, 4),
    (1, 4, 5, 1),
    (1, 6, 4, 5),
    (1, 4, 1, 5),
    (1, 5, 1, 4),
)
# Contour as scale-degree offsets from the chord's root (in chord-tone / scale steps).
CONTOURS = (
    (0, 2, 4, 2, 0, -1, 0, 2),
    (0, 1, 2, 3, 2, 1, 0, -2),
    (2, 0, 2, 4, 3, 2, 0, 0),
    (0, 2, 1, 3, 4, 2, 0, -1),
)
# Rhythm cells in units of the song unit (1/8): each cell fills one bar when scaled.
# Chosen by meter; lengths sum to bar_units.
RHYTHMS_4_4 = (
    (2, 2, 2, 2),
    (2, 1, 1, 2, 2),
    (1, 1, 2, 2, 2),
    (2, 2, 1, 1, 2),
)
RHYTHMS_3_4 = (
    (2, 2, 2),
    (2, 1, 1, 2),
    (1, 1, 2, 2),
    (2, 2, 1, 1),
)
RHYTHMS_6_8 = (
    (3, 3),
    (2, 1, 3),
    (3, 2, 1),
    (1, 2, 3),
)

DEGREE_NAME = {1: "", 2: "m", 3: "m", 4: "", 5: "", 6: "m", 7: "dim"}
NATURAL = abcplan.NATURAL


@dataclass
class Draft:
    bars: list[Bar]
    key: str
    meter: str
    unit: Fraction
    tempo: int
    notes: list[str]


def _meter_of(style_id: str | None, rng: random.Random) -> str:
    from . import styles
    st = styles.get(style_id) if style_id else None
    if st and st.meters:
        meters = list(st.meters)
        # Prefer the style's "home" meter when it has only one; else seeded.
        return meters[0] if len(meters) == 1 else rng.choice(meters)
    return rng.choice(["4/4", "3/4", "6/8"])


def _tempo_of(style_id: str | None, rng: random.Random) -> int:
    from . import styles
    st = styles.get(style_id) if style_id else None
    if st:
        lo, hi = st.tempo
        mid = (lo + hi) // 2
        return int(rng.triangular(lo, min(hi, mid + 20), mid))
    return rng.choice([72, 84, 96, 108])


def _rhythms(meter: str) -> tuple[tuple[int, ...], ...]:
    if meter == "3/4":
        return RHYTHMS_3_4
    if meter.endswith("/8"):
        return RHYTHMS_6_8
    return RHYTHMS_4_4


def _bar_units(meter: str, unit: Fraction) -> Fraction:
    num, den = (int(x) for x in meter.split("/"))
    return Fraction(num, den) / unit


def _key_pc(key: str) -> int:
    parts = abcplan._key_parts(key)
    if not parts:
        return 0
    letter, acc, _mode = parts
    return (NATURAL[letter] + {"#": 1, "b": -1, "": 0}[acc]) % 12


def _scale_pcs(key: str) -> list[int]:
    """Pitch classes of the major scale on `key`."""
    root = _key_pc(key)
    return [(root + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)]


def _chord_symbol(key: str, degree: int) -> str:
    root_pc = _scale_pcs(key)[(degree - 1) % 7]
    # Spell the root for this key.
    sharp_side = abcplan.key_fifths(key) >= 0
    choices = []
    for name, nat in NATURAL.items():
        for a, text in ((0, ""), (1, "#"), (-1, "b")):
            if (nat + a) % 12 == root_pc:
                ka = abcplan.key_accidentals(key)
                rank = 0 if a == ka.get(name, 0) else 1 if a == 0 else 2 if (a > 0) == sharp_side else 3
                choices.append((rank, name + text))
    root = min(choices)[1]
    return root + DEGREE_NAME.get(((degree - 1) % 7) + 1, "")


def _chord_tones(key: str, degree: int) -> list[int]:
    """Pitch classes: root, third, fifth of the diatonic triad."""
    scale = _scale_pcs(key)
    i = (degree - 1) % 7
    return [scale[i], scale[(i + 2) % 7], scale[(i + 4) % 7]]


def _midi_near(pc: int, target: int) -> int:
    """MIDI note with pitch class `pc` nearest `target`."""
    base = target - (target % 12) + pc
    options = [base - 12, base, base + 12]
    return min(options, key=lambda m: abs(m - target))


def _spell_midi(midi: int, key: str) -> Tok:
    letter, alter, octave = abcplan._spell(midi, key)
    ka = abcplan.key_accidentals(key)
    acc = abcplan.ACC_TEXT.get(alter, "") if alter != ka.get(letter, 0) else ""
    return Tok("note", acc=acc, step=letter, octave=octave, length=Fraction(1))


def compose(lyrics: str, style_id: str | None, voice: str, seed: int) -> Draft:
    """Lyrics + style + voice + seed → bars in the singer's range."""
    from .write import VOICES
    if voice not in VOICES:
        raise WriteError(f"Unknown voice {voice!r}.")
    sections = syllables.parse_lyrics(lyrics)
    sylls = syllables.all_syllables(sections)
    if not sylls:
        raise WriteError("The lyrics have no words to sing.")
    rng = random.Random(seed)
    meter = _meter_of(style_id, rng)
    tempo = _tempo_of(style_id, rng)
    key = rng.choice(KEYS)
    unit = Fraction(1, 8)
    bar_len = _bar_units(meter, unit)
    progression = PROGRESSIONS[seed % len(PROGRESSIONS)]
    contour = CONTOURS[(seed // 3) % len(CONTOURS)]
    rhythm_pool = _rhythms(meter)
    low, high = (m21pitch.Pitch(p).midi for p in VOICES[voice][:2])
    middle = (low + high) // 2

    bars: list[Bar] = []
    # Motif: first line's interval sequence, reused with small changes.
    motif_intervals: list[int] | None = None
    chord_i = 0
    section_name = sections[0].name if sections else "verse"

    # Walk line by line so line ends land on cadences / rests.
    for sec in sections:
        section_name = sec.name
        for line in sec.lines:
            line_sylls = line.syllables
            if not line_sylls:
                continue
            # Pick a rhythm cell; repeat / trim to the syllable count.
            cell = list(rng.choice(rhythm_pool))
            while sum(cell) < bar_len and len(cell) < 12:
                cell.append(1)
            # Build note lengths for this line (one note per syllable).
            lengths: list[Fraction] = []
            for k, sy in enumerate(line_sylls):
                # Stressed syllables prefer longer slots.
                base = cell[k % len(cell)]
                if sy.weight >= 1.5 and base == 1 and k + 1 < len(line_sylls):
                    base = 2
                lengths.append(Fraction(base))
            # Pad or trim so bars fill cleanly: group into bars of bar_len.
            events: list[tuple[Fraction, syllables.Syllable | None]] = []  # (length, syll or rest)
            for length, sy in zip(lengths, line_sylls):
                events.append((length, sy))
            # Fill last bar with a rest if short; split overlong runs into bars.
            packed: list[list[tuple[Fraction, syllables.Syllable | None]]] = [[]]
            filled = Fraction(0)
            for length, sy in events:
                if filled + length > bar_len and packed[-1]:
                    # Rest out the bar, then start a new one.
                    gap = bar_len - filled
                    if gap > 0:
                        packed[-1].append((gap, None))
                    packed.append([])
                    filled = Fraction(0)
                length = min(length, bar_len)
                packed[-1].append((length, sy))
                filled += length
                if filled == bar_len:
                    packed.append([])
                    filled = Fraction(0)
            if packed[-1] and filled < bar_len:
                packed[-1].append((bar_len - filled, None))
            elif not packed[-1]:
                packed.pop()

            line_midis: list[int] = []
            for bar_events in packed:
                degree = progression[chord_i % len(progression)]
                chord_i += 1
                symbol = _chord_symbol(key, degree)
                tones = _chord_tones(key, degree)
                scale = _scale_pcs(key)
                toks: list[Tok] = [Tok("chord", symbol)]
                pos_in_bar = Fraction(0)
                for length, sy in bar_events:
                    if sy is None:
                        toks.append(Tok("rest", length=length))
                        pos_in_bar += length
                        continue
                    # Contour index + motif variation.
                    idx = len(line_midis)
                    if motif_intervals and idx < len(motif_intervals) and idx > 0:
                        step = motif_intervals[idx - 1] + rng.choice((-1, 0, 0, 1))
                        prev = line_midis[-1]
                        target = prev + step
                    else:
                        off = contour[idx % len(contour)]
                        # Strong beat → chord tone; weak → scale neighbour.
                        strong = pos_in_bar == 0 or (pos_in_bar / (bar_len / 2)).denominator == 1
                        if strong or sy.weight >= 1.5:
                            pc = tones[off % len(tones)]
                        else:
                            pc = scale[(scale.index(tones[0]) + off) % len(scale)]
                        target = _midi_near(pc, middle + (2 if sy.weight >= 1.5 else 0))
                    # Cadence: last syllable of the line toward tonic root/third.
                    if sy.line_end:
                        tonic = _chord_tones(key, 1)
                        target = _midi_near(tonic[0] if sy.weight >= 1 else tonic[1], target)
                    target = max(low, min(high, target))
                    if line_midis and abs(target - line_midis[-1]) > 7:
                        # Prefer a smaller leap into range.
                        step = 2 if target > line_midis[-1] else -2
                        target = max(low, min(high, line_midis[-1] + step))
                    note = _spell_midi(target, key)
                    note.length = length
                    toks.append(note)
                    line_midis.append(target)
                    pos_in_bar += length
                bars.append(Bar(toks, section=section_name))

            if motif_intervals is None and len(line_midis) >= 3:
                motif_intervals = [b - a for a, b in zip(line_midis, line_midis[1:])]

    if not bars:
        raise WriteError("Couldn't shape a melody from these lyrics.")
    # Tag bars with section names already set; ensure first bar of each section is marked.
    notes = [f"Rule-based melody in {key} {meter} at {tempo}; seed {seed}.",
             f"Progression {[ _chord_symbol(key, d) for d in progression ]}, contour varied by seed."]
    return Draft(bars, key, meter, unit, tempo, notes)


def plan_abc(draft: Draft) -> str:
    """Optional YuE2-shaped ABC for the report folder (not required to build the song)."""
    lines = [
        "X:1", "T:", f"M:{draft.meter}", f"L:{draft.unit.numerator}/{draft.unit.denominator}",
        f"Q:1/4={draft.tempo}", f"K:{draft.key}", "% verse", "V: Vocal",
    ]
    # Write without Ins voice; tests don't need a full dialect plan.
    body = abcplan.write(draft.bars, draft.unit, draft.unit)
    for line in body.splitlines():
        lines.append(line)
    return "\n".join(lines) + "\n"
