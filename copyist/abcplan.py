"""Reading the score YuE2's planner writes (`yue-plan`), and the small ABC model used to rework it.

The planner's dialect (docs/melody-writing.md): a header (M, L, Q, K), then
`% section` comments and alternating `V: Vocal` / `V: Ins` blocks; lengths are
integers in units of L (1/32); chords are quoted; `Z` / `Zn` are whole-bar
rests; `-` ties. YuE2 sings an octave below what it writes.

Copyist keeps the vocal line and its chords, trims it to the bars that are
sung, puts it in the singer's octave, and writes it back as ABC a person can
read. Anything outside the dialect (tuplets, broken rhythms) is refused, never
guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction


class PlanError(ValueError):
    """A plan Copyist can't read faithfully."""


@dataclass
class Tok:
    kind: str                     # "chord", "note", "rest"
    text: str = ""                # chord: the symbol
    acc: str = ""                 # note: accidentals as written (^, _, =)
    step: str = ""                # note: letter, upper case
    octave: int = 4               # note: 4 = C4..B4 (ABC "C".."B")
    length: Fraction = Fraction(0)    # in units of L
    tie: bool = False             # note: tied to the next note


@dataclass
class Bar:
    toks: list[Tok]
    section: str
    units: Fraction | None = None        # how long the bar should be, if the score changed meter for it

    @property
    def length(self) -> Fraction:
        return sum((t.length for t in self.toks if t.kind != "chord"), Fraction(0))

    @property
    def sung(self) -> bool:
        return any(t.kind == "note" for t in self.toks)


@dataclass
class Plan:
    meter: str
    unit: Fraction                # L, as a fraction of a whole note
    tempo: str                    # the Q field, e.g. "1/4=86"
    key: str
    vocal: list[Bar] = field(default_factory=list)

    @property
    def bar_units(self) -> Fraction:
        num, den = (int(x) for x in self.meter.split("/"))
        return Fraction(num, den) / self.unit


NOTE = re.compile(r"""("[^"]*")|([_^=]*)([A-Ga-g])([,']*)(\d*)(/(\d*))?(-?)|([zx])(\d*)(/(\d*))?|(Z)(\d*)|(\S)""")


def _length(num: str, slash: str | None, den: str | None) -> Fraction:
    n = Fraction(int(num)) if num else Fraction(1)
    if slash:
        n /= int(den) if den else 2
    return n


def tokenize_bar(text: str) -> tuple[list[Tok], int]:
    """Tokens of one bar's text; returns (tokens, number of whole-bar rests if the bar is `Zn`)."""
    toks, z_bars = [], 0
    for m in NOTE.finditer(text):
        chord, acc, letter, marks, num, slash, den, tie, rest, rnum, rslash, rden, big_z, z_count, other = m.groups()
        if chord:
            toks.append(Tok("chord", chord[1:-1]))
        elif letter:
            octave = 4 if letter.isupper() else 5
            octave += marks.count("'") - marks.count(",")
            toks.append(Tok("note", acc=acc, step=letter.upper(), octave=octave,
                            length=_length(num, slash, den), tie=bool(tie)))
        elif rest:
            toks.append(Tok("rest", length=_length(rnum, rslash, rden)))
        elif big_z:
            z_bars = int(z_count) if z_count else 1
        elif other and other not in "[]":
            raise PlanError(f"The plan uses {other!r}, which Copyist doesn't read yet (in {text.strip()!r}).")
    return toks, z_bars


def parse(text: str) -> Plan:
    """The vocal line of a yue-plan score, bar by bar, each bar tagged with its section."""
    header: dict[str, str] = {}
    section, voice = "intro", None
    plan: Plan | None = None
    inline_units: Fraction | None = None     # a meter changed inside the music (a pickup bar, say)
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%"):
            section = line[1:].strip().lower() or section
            continue
        m = re.match(r"^([A-Za-z]):\s*(.*)$", line)
        if m and plan is not None and m.group(1) == "M":
            inline = Fraction(*(int(x) for x in m.group(2).strip().split("/"))) / plan.unit
            inline_units = None if inline == plan.bar_units else inline
            continue
        if m and not line.startswith("V:"):
            header[m.group(1)] = m.group(2).strip()
            if m.group(1) == "K":
                plan = Plan(header.get("M", "4/4"), Fraction(header.get("L", "1/8")), header.get("Q", ""), m.group(2).strip())
            continue
        if line.startswith("V:"):
            voice = line[2:].split()[0].strip()
            continue
        if plan is None:
            raise PlanError("The plan has no K: line before its music.")
        if voice != "Vocal":
            continue
        for chunk in line.split("|"):
            if not chunk.strip():
                continue
            toks, z_bars = tokenize_bar(chunk)
            if z_bars:
                for _ in range(z_bars):
                    plan.vocal.append(Bar([Tok("rest", length=inline_units or plan.bar_units)], section,
                                          inline_units))
                continue
            plan.vocal.append(Bar(toks, section, inline_units))
    if plan is None:
        raise PlanError("That isn't a plan: there's no K: line.")
    if not any(b.sung for b in plan.vocal):
        raise PlanError("The plan has no sung notes.")
    first_sung = next(k for k, b in enumerate(plan.vocal) if b.sung)
    for k, bar in enumerate(plan.vocal):
        expected = bar.units or plan.bar_units
        if bar.length != expected:
            raise PlanError(f"Bar {k + 1} of the plan's vocal line holds {bar.length} units, not {expected}.")
        if bar.units and bar.sung and not (k == first_sung and bar.units < plan.bar_units):
            raise PlanError(f"The plan changes meter at bar {k + 1}; Copyist songs keep one meter "
                            "(a short first bar, a pickup, is fine).")
    return plan


def trim(plan: Plan) -> list[Bar]:
    """The bars from the first sung one to the last."""
    sung = [k for k, b in enumerate(plan.vocal) if b.sung]
    return plan.vocal[sung[0]:sung[-1] + 1]


def written_meter(meter: str) -> str:
    """The meter a plan is written in for Copyist: 2/4 becomes 4/4 (`pair_bars`)."""
    return "4/4" if meter == "2/4" else meter


def pair_bars(bars: list[Bar], meter: str) -> tuple[list[Bar], str]:
    """A 2/4 plan as 4/4: two bars become one. No style plays 2/4, and a 2/4 lead sheet is twice as
    many bars to read. The pairing puts chord changes and section starts on the new downbeats."""
    if meter != "2/4":
        return bars, meter
    pickup = []
    if bars and bars[0].units:                        # a pickup stays a pickup
        pickup, bars = bars[:1], bars[1:]
    if not bars:
        return pickup, "4/4"
    full = sum((t.length for t in bars[0].toks if t.kind != "chord"), Fraction(0))

    def starts(offset: int) -> int:
        score = 0
        for k, bar in enumerate(bars):
            first = next((t for t in bar.toks), None)
            on_downbeat = (k + offset) % 2 == 0
            if on_downbeat and first is not None and first.kind == "chord":
                score += 1
            if on_downbeat and (k == 0 or bars[k - 1].section != bar.section):
                score += 2
        return score

    work = list(bars)
    if starts(1) > starts(0):
        work.insert(0, Bar([Tok("rest", length=full)], bars[0].section))
    if len(work) % 2:
        work.append(Bar([Tok("rest", length=full)], work[-1].section))
    paired = [Bar(a.toks + b.toks, a.section) for a, b in zip(work[::2], work[1::2])]
    return pickup + paired, "4/4"


KEY_SHARPS = ["F", "C", "G", "D", "A", "E", "B"]
NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTER_FIFTHS = {"F": -1, "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5}
MODE_SHIFT = {"": 0, "maj": 0, "major": 0, "ion": 0, "m": -3, "min": -3, "minor": -3, "aeo": -3, "dor": -2,
              "phr": -4, "lyd": 1, "mix": -1, "loc": -5}
ACC_TEXT = {2: "^^", 1: "^", 0: "=", -1: "_", -2: "__"}
KEY = re.compile(r"^([A-G])([#b]?)\s*([A-Za-z]*)$")


def _key_parts(key: str) -> tuple[str, str, str] | None:
    m = KEY.match(key.strip())
    return (m.group(1), m.group(2), m.group(3)) if m else None


def key_fifths(key: str) -> int:
    """Sharps (positive) or flats (negative) in a key signature: "Bm" 2, "Bb" -2, "Dmix" 1."""
    parts = _key_parts(key)
    if not parts:
        return 0
    letter, acc, mode = parts
    mode = mode.lower()
    shift = MODE_SHIFT.get(mode, MODE_SHIFT.get(mode[:3], 0))
    return LETTER_FIFTHS[letter] + {"#": 7, "b": -7, "": 0}[acc] + shift


def key_accidentals(key: str) -> dict[str, int]:
    """The sharps (+1) or flats (-1) a key signature applies, by letter ("Bm" -> F and C sharp)."""
    fifths = key_fifths(key)
    if fifths >= 0:
        return {s: 1 for s in KEY_SHARPS[:min(fifths, 7)]}
    return {s: -1 for s in list(reversed(KEY_SHARPS))[:min(-fifths, 7)]}


def transpose_key(key: str, semitones: int) -> str:
    """The key `semitones` higher, spelled with the fewest sharps or flats ("D" +1 -> "Eb")."""
    parts = _key_parts(key)
    if not parts or semitones % 12 == 0:
        return key
    letter, acc, mode = parts
    pc = (NATURAL[letter] + {"#": 1, "b": -1, "": 0}[acc] + semitones) % 12
    options = []
    for name, nat in NATURAL.items():
        for a, text in ((0, ""), (1, "#"), (-1, "b")):
            if (nat + a) % 12 == pc:
                options.append(f"{name}{text}{mode}")
    return min(options, key=lambda k: (abs(key_fifths(k)), "#" in k))


def _spell(midi: int, key: str) -> tuple[str, int, int]:
    """(letter, alteration, octave) for a MIDI pitch in `key`: the key's own note if there is one,
    else a natural, else a sharp in sharp keys and a flat in flat keys."""
    ka = key_accidentals(key)
    sharp_side = key_fifths(key) >= 0
    pc = midi % 12
    best = None
    for letter, nat in NATURAL.items():
        for alter in (-1, 0, 1):
            if (nat + alter) % 12 != pc:
                continue
            rank = 0 if alter == ka.get(letter, 0) else 1 if alter == 0 else 2 if (alter > 0) == sharp_side else 3
            if best is None or rank < best[0]:
                best = (rank, letter, alter)
    _, letter, alter = best
    return letter, alter, (midi - NATURAL[letter] - alter) // 12 - 1


def _note_midis(bars: list[Bar], key: str) -> list[list[int | None]]:
    """MIDI pitch of every note token, bar by bar (None for chords and rests), reading accidentals
    as YuE2 writes them: an accidental holds for the rest of the bar, for that letter in every
    octave (see yue.py)."""
    ka = key_accidentals(key)
    out = []
    for bar in bars:
        state: dict[str, int] = {}
        row: list[int | None] = []
        for t in bar.toks:
            if t.kind != "note":
                row.append(None)
                continue
            if t.acc:
                state[t.step] = t.acc.count("^") - t.acc.count("_")
            alter = state.get(t.step, ka.get(t.step, 0))
            row.append(12 * (t.octave + 1) + NATURAL[t.step] + alter)
        out.append(row)
    return out


def pitches(bars: list[Bar], key: str) -> list[int]:
    """MIDI pitch of every note onset (tie continuations are left out)."""
    out, tied = [], False
    for bar, row in zip(bars, _note_midis(bars, key)):
        for t, m in zip(bar.toks, row):
            if t.kind != "note":
                continue
            if not tied:
                out.append(m)
            tied = t.tie
    return out


def transpose_chord(symbol: str, semitones: int, key: str) -> str:
    """A chord symbol moved by `semitones`, the root and any slash bass respelled for `key`."""
    if semitones % 12 == 0:
        return symbol
    sharp_side = key_fifths(key) >= 0

    def move(letter: str, acc: str) -> str:
        pc = (NATURAL[letter] + {"#": 1, "b": -1, "": 0}[acc] + semitones) % 12
        ka = key_accidentals(key)
        choices = []
        for name, nat in NATURAL.items():
            for a, text in ((0, ""), (1, "#"), (-1, "b")):
                if (nat + a) % 12 == pc:
                    rank = 0 if a == ka.get(name, 0) else 1 if a == 0 else 2 if (a > 0) == sharp_side else 3
                    choices.append((rank, name + text))
        return min(choices)[1]

    m = re.match(r"^([A-G])([#b]?)(.*?)(?:/([A-G])([#b]?))?$", symbol)
    if not m:
        return symbol
    root = move(m.group(1), m.group(2))
    bass = f"/{move(m.group(4), m.group(5))}" if m.group(4) else ""
    return root + m.group(3) + bass


def respell(bars: list[Bar], key: str, semitones: int = 0) -> str:
    """Move the bars by `semitones` (0 just respells) and write every accidental explicitly.

    Plans carry an accidental through the bar; music21, which reads Copyist's song files, carries
    none. So every note whose alteration differs from the key signature gets its accidental, and so
    does a note after another accidental on the same letter in that bar. The file then reads the
    same under either rule. Returns the key the bars are now in.
    """
    new_key = transpose_key(key, semitones)
    ka = key_accidentals(new_key)
    midis = _note_midis(bars, key)
    for bar, row in zip(bars, midis):
        changed: set[str] = set()
        for t, m in zip(bar.toks, row):
            if t.kind == "chord":
                t.text = transpose_chord(t.text, semitones, new_key)
                continue
            if t.kind != "note":
                continue
            if semitones % 12 == 0:
                letter = t.step
                alter = m - 12 * (t.octave + 1) - NATURAL[t.step]
                octave = t.octave + semitones // 12
            else:
                letter, alter, octave = _spell(m + semitones, new_key)
            explicit = alter != ka.get(letter, 0) or letter in changed
            t.step, t.octave = letter, octave
            t.acc = ACC_TEXT[alter] if explicit else ""
            if explicit:
                changed.add(letter)
    return new_key


def best_octave(midis: list[int], low: int, high: int) -> int:
    """How many octaves to move a line so most of it fits [low, high], nearest the middle on a tie."""
    middle = (low + high) / 2
    median = sorted(midis)[len(midis) // 2]

    def cost(k):
        moved = [m + 12 * k for m in midis]
        return (sum(not low <= m <= high for m in moved), abs(median + 12 * k - middle))
    return min(range(-3, 4), key=cost)


SUNG_OCTAVE_BELOW = 1          # YuE2 sings an octave below what it writes (yue.SUNG_OCTAVE_BELOW)
OUTSIDE_LIMIT = 0.10


@dataclass
class Placement:
    key: str
    semitones: int                # how far the written plan moved, octaves included
    transposed: int               # the part of that that isn't whole octaves (0 if none)
    outside: int                  # notes still outside the range
    notes: int


def place_in_range(bars: list[Bar], key: str, low: int, high: int) -> Placement:
    """Put a plan's vocal line where the singer sings it, then where the voice fits.

    First down YuE2's octave, then by whole octaves to fit [low, high] best. If more than 10% of the
    notes are still outside, transpose by the fewest semitones that fits (the key changes to match).
    Respells the bars in place.
    """
    midis = [m - 12 * SUNG_OCTAVE_BELOW for m in pitches(bars, key)]
    octaves = best_octave(midis, low, high)

    def outside(shift: int) -> int:
        return sum(not low <= m + shift <= high for m in midis)

    shift = 12 * octaves
    transposed = 0
    if outside(shift) > OUTSIDE_LIMIT * len(midis):
        options = []
        for s in range(-6, 7):
            if s == 0:
                continue
            k = best_octave([m + s for m in midis], low, high)
            options.append((outside(s + 12 * k), abs(s), s, k))
        best = min(options)
        if best[0] < outside(shift):
            transposed = best[2]
            shift = best[2] + 12 * best[3]
    total = shift - 12 * SUNG_OCTAVE_BELOW
    new_key = respell(bars, key, total)
    return Placement(new_key, total, transposed, outside(shift), len(midis))


def place_as_sung(bars: list[Bar], key: str, octave_above: int = 0) -> Placement:
    """A transcription keeps the octave it was sung in (moved down `octave_above` octaves for an engine
    that writes YuE2's way); only the spelling changes. Respells the bars in place."""
    midis = [m - 12 * octave_above for m in pitches(bars, key)]
    new_key = respell(bars, key, -12 * octave_above)
    return Placement(new_key, -12 * octave_above, 0, 0, len(midis))


def best_unit(bars: list[Bar], unit: Fraction) -> Fraction:
    """The longest unit (1/4, 1/8, 1/16, ...) that keeps every length a whole number."""
    lengths = [t.length * unit for b in bars for t in b.toks if t.kind != "chord"]
    for candidate in (Fraction(1, 4), Fraction(1, 8), Fraction(1, 16), Fraction(1, 32), Fraction(1, 64)):
        if all((x / candidate).denominator == 1 for x in lengths):
            return candidate
    return unit


def _length_text(n: Fraction) -> str:
    if n == 1:
        return ""
    if n.denominator == 1:
        return str(n.numerator)
    return f"{n.numerator}/{n.denominator}" if n.numerator != 1 else f"/{n.denominator}"


def note_text(t: Tok) -> str:
    letter = t.step if t.octave <= 4 else t.step.lower()
    marks = "," * (4 - t.octave) if t.octave < 4 else "'" * (t.octave - 5) if t.octave > 5 else ""
    return f"{t.acc}{letter}{marks}"


def write(bars: list[Bar], unit_from: Fraction, unit_to: Fraction, per_line: int = 4) -> str:
    """The bars as Copyist melody ABC in units of `unit_to`."""
    scale = unit_from / unit_to
    lines, current = [], []
    chord = None                         # a chord lasts until the next one, so a repeat says nothing
    for k, bar in enumerate(bars):
        out = []
        for t in bar.toks:
            if t.kind == "chord":
                if t.text != chord:
                    out.append(f'"{t.text}"')
                chord = t.text
            elif t.kind == "rest":
                out.append("z" + _length_text(t.length * scale))
            else:
                out.append(note_text(t) + _length_text(t.length * scale) + ("-" if t.tie else ""))
        current.append(" ".join(_merge_chords(out)))
        if len(current) == per_line or k == len(bars) - 1:
            lines.append(" | ".join(current) + (" |]" if k == len(bars) - 1 else " |"))
            current = []
    return "\n".join(lines)


def _merge_chords(parts: list[str]) -> list[str]:
    """Glue each chord symbol to the note or rest after it ("G"B2), as ABC writes them."""
    out, pending = [], ""
    for p in parts:
        if p.startswith('"'):
            pending += p
        else:
            out.append(pending + p)
            pending = ""
    if pending:
        out.append(pending)
    return out


def sections_of(bars: list[Bar]) -> list[dict]:
    """[{name, bar}] where each section starts, numbering bars from 1. A one-bar section followed by
    another is the next section's pickup (the planner often leaves it in the intro), so it joins it."""
    out: list[dict] = []
    for k, bar in enumerate(bars, start=1):
        if not out or out[-1]["name"] != bar.section:
            out.append({"name": bar.section, "bar": k})
    merged: list[dict] = []
    for k, sec in enumerate(out):
        nxt = out[k + 1] if k + 1 < len(out) else None
        if nxt and nxt["bar"] - sec["bar"] == 1:
            nxt["bar"] = sec["bar"]
            continue
        if merged and merged[-1]["name"] == sec["name"]:
            continue
        merged.append(sec)
    return merged


def tempo_field(q: str):
    """`Q:1/4=86` -> 86; anything else stays an ABC tempo string."""
    m = re.fullmatch(r"1/4=(\d+)", q.replace(" ", ""))
    if m:
        return int(m.group(1))
    return q.replace(" ", "") or 90
