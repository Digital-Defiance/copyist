"""Editing a song by ear (SPEC §14, docs/web.md): small changes to the notes, chords and lyric
placement, written back into the song file.

The song file stays the source of truth. An edit reads the melody into bars and notes (`abcplan`),
makes one change, and writes back only the bars it changed, as text in place, so the rest of the file
reads exactly as before: other bars, line breaks, other fields and comments. A split or a join also
changes the one line of each verse that moves a syllable, so every verse stays on its notes. Each
edit is checked (the song still loads, its bars add up and its verses fit, unless they didn't
before) and saves the file as it was first, so it can be undone.

Notes are addressed as "b{bar}.{n}": the bar as written from 1 (as `sections:` counts them), and the
note or rest's place in that bar from 0. The page shows bar numbers as the score does (a pickup is 0).
Pitches are read as Copyist's loader (music21) reads a song file, where an accidental belongs to its
own note only. A changed note is written so it reads the same under the ABC rule too (an accidental
lasts to the end of the bar), adding a natural to a later note where that rule would misread it.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import yaml

from . import abcplan, lyrics as lyr
from .rewrite import WriteError, bars_from_melody
from .song import SongError

PITCH_OPS = ("up", "down", "up-half", "down-half")
OPS = PITCH_OPS + ("longer", "shorter", "split", "join", "chord")
HISTORY_LIMIT = 200
PITCH_RANGE = (36, 96)                   # C2..C7: nudging stops at the edges
LETTERS = "CDEFGAB"
CHORD = re.compile(r"[A-G][#b]?[A-Za-z0-9#+()]*(/[A-G][#b]?)?")
_LOCK = threading.Lock()                 # one edit at a time, from any number of page requests


class EditError(SongError):
    """An edit that can't be made, said in plain words."""


@dataclass
class Event:
    id: str
    bar: int                             # index into bars
    tok: int                             # index into bars[bar].toks
    kind: str                            # "note" or "rest"
    start: Fraction                      # quarter notes from the start of the bar
    length: Fraction                     # quarter notes
    midi: int | None = None
    tie: bool = False                    # tied into the next note
    held_over: bool = False              # the continuation of a tie (takes no syllable)
    chord: str | None = None             # a chord symbol that starts here
    sounding: str | None = None          # the chord in force here
    slot: int | None = None              # its place among the notes that take a syllable


# ------------------------------------------------------------------ reading

def load(path: Path) -> tuple[str, dict]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise EditError(f"{path.name} isn't readable YAML: {e}") from e
    if not isinstance(data, dict) or not data.get("melody"):
        raise EditError(f"{path.name} has no melody to edit.")
    return text, data


def key_of(data: dict) -> str:
    return str(data.get("key", "C"))


def unit_of(data: dict) -> Fraction:
    return Fraction(str(data.get("unit", "1/4")))


def meter_of(data: dict) -> tuple[int, int]:
    num, den = (int(x) for x in str(data.get("meter", "4/4")).split("/"))
    return num, den


def verses_of(data: dict) -> list[str]:
    v = data.get("lyrics") or []
    return [str(x) for x in ([v] if isinstance(v, str) else v)]


def bars_of(data: dict) -> list[abcplan.Bar]:
    try:
        return bars_from_melody(data["melody"], data.get("sections"))
    except (WriteError, abcplan.PlanError) as e:
        raise EditError(f"This melody can't be edited here yet: {e}") from e


def midi_of(t: abcplan.Tok, key: str) -> int:
    """A note's pitch as music21 reads a song file: its own accidental, else the key signature's."""
    if t.acc:
        alter = t.acc.count("^") - t.acc.count("_")
    else:
        alter = abcplan.key_accidentals(key).get(t.step, 0)
    return 12 * (t.octave + 1) + abcplan.NATURAL[t.step] + alter


def events_of(bars: list[abcplan.Bar], unit: Fraction, key: str) -> list[list[Event]]:
    """Every note and rest, bar by bar, with its time, pitch, chord and lyric slot."""
    out, slot, tied, sounding = [], 0, False, None
    q = unit * 4
    for b, bar in enumerate(bars):
        row, pos, pending, n = [], Fraction(0), None, 0
        for k, t in enumerate(bar.toks):
            if t.kind == "chord":
                pending = t.text
                continue
            if t.kind not in ("note", "rest"):
                continue
            ev = Event(f"b{b + 1}.{n}", b, k, t.kind, pos * q, t.length * q)
            if pending is not None:
                ev.chord = sounding = pending
                pending = None
            ev.sounding = sounding
            if t.kind == "note":
                ev.midi = midi_of(t, key)
                ev.tie = t.tie
                ev.held_over = tied
                if not tied:
                    ev.slot = slot
                    slot += 1
                tied = t.tie
            else:
                tied = False
            row.append(ev)
            pos += t.length
            n += 1
        out.append(row)
    return out


def words_by_slot(verses: list[str], slots: int) -> list[list[str]]:
    """Per verse, what each syllable slot sings: the syllable (with a hyphen when its word goes on),
    "_" (the syllable before it, held), "*" (skipped) or "" (the verse has ended)."""
    out = []
    for v in verses:
        tokens = lyr.tokenize(v)
        row = []
        for i in range(slots):
            if i >= len(tokens):
                row.append("")
            elif tokens[i].kind == lyr.SYL:
                row.append(tokens[i].text + ("-" if tokens[i].syllabic in ("begin", "middle") else ""))
            else:
                row.append("_" if tokens[i].kind == lyr.HOLD else "*")
        out.append(row)
    return out


def tempo_qpm(data: dict) -> float:
    """Quarter notes a minute, from the song's tempo field (90, or "3/8=56")."""
    t = data.get("tempo", 90)
    if isinstance(t, (int, float)):
        return float(t)
    m = re.fullmatch(r"\s*(\d+)/(\d+)\s*=\s*(\d+(?:\.\d+)?)\s*", str(t))
    if m:
        return float(m.group(3)) * 4 * int(m.group(1)) / int(m.group(2))
    try:
        return float(str(t))
    except ValueError:
        return 90.0


def chord_figure(symbol: str) -> str:
    """A Copyist chord symbol as music21 reads one: flats as "-" ("Bb7/Ab" -> "B-7/A-")."""
    figure = re.sub(r"^([A-G])b", r"\1-", symbol.strip())
    return re.sub(r"/([A-G])b", r"/\1-", figure)


@lru_cache(maxsize=512)
def _chord_pitches(symbol: str) -> tuple[int, ...]:
    from music21 import harmony
    try:
        cs = harmony.ChordSymbol(chord_figure(symbol))
    except Exception:              # music21 raises several types for symbols it can't read
        return ()
    return tuple(p.midi for p in cs.pitches)


def chord_tones(symbol: str | None) -> list[int]:
    """The chord's notes from the octave below middle C, for playing it (empty if unreadable)."""
    pitches = list(_chord_pitches(symbol.strip())) if symbol else []
    if not pitches:
        return []
    shift = 12 * round((48 - min(pitches)) / 12)
    return [p + shift for p in pitches]


def name_of(midi: int, key: str) -> str:
    letter, alter, octave = abcplan._spell(midi, key)
    return letter + {1: "♯", -1: "♭", 2: "𝄪", -2: "𝄫"}.get(alter, "") + str(octave)


def view(path: Path, history: Path | None = None) -> dict:
    """What the page draws: bars of notes with their words and chords, and what's needed to play them."""
    _, data = load(path)
    key, unit = key_of(data), unit_of(data)
    bars = bars_of(data)
    rows = events_of(bars, unit, key)
    slots = sum(1 for row in rows for e in row if e.slot is not None)
    words = words_by_slot(verses_of(data), slots)
    num, den = meter_of(data)
    full = Fraction(num, den) * 4
    lengths = [sum((e.length for e in row), Fraction(0)) for row in rows]
    first_number = 0 if lengths and lengths[0] < full else 1     # a pickup is bar 0, as on the score
    out_bars = []
    for b, (bar, row) in enumerate(zip(bars, rows)):
        events = []
        for e in row:
            item = {"id": e.id, "kind": e.kind, "start": float(e.start), "length": float(e.length),
                    "chord": e.chord, "sounding": e.sounding, "chord_tones": chord_tones(e.sounding)}
            if e.kind == "note":
                item.update({"midi": e.midi, "name": name_of(e.midi, key), "tie": e.tie,
                             "held_over": e.held_over,
                             "words": [w[e.slot] for w in words] if e.slot is not None else []})
            events.append(item)
        out_bars.append({"number": first_number + b, "section": bar.section, "length": float(lengths[b]),
                         "events": events})
    midis = [e.midi for row in rows for e in row if e.midi is not None]
    hist = _history(history)
    return {"title": data.get("title"), "key": key, "meter": f"{num}/{den}",
            "bar_quarters": float(Fraction(num, den) * 4), "qpm": tempo_qpm(data), "verses": len(words),
            "low": min(midis) if midis else 60, "high": max(midis) if midis else 72, "bars": out_bars,
            "can_undo": bool(hist["undo"]), "can_redo": bool(hist["redo"])}


def chord_options(path: Path, at: str, limit: int = 8) -> list[dict]:
    """Chords to try at a note, best first (see `best_chords`)."""
    _, data = load(path)
    key = key_of(data)
    rows = events_of(bars_of(data), unit_of(data), key)
    return best_chords(rows, _find(rows, at), key, limit)


# ------------------------------------------------------------------ changing

def _find(rows: list[list[Event]], at: str) -> Event:
    for row in rows:
        for e in row:
            if e.id == at:
                return e
    raise EditError(f"There's no note {at} in this song.")


def scale_pcs(key: str) -> set[int]:
    acc = abcplan.key_accidentals(key)
    return {(abcplan.NATURAL[l] + acc.get(l, 0)) % 12 for l in LETTERS}


def moved(midi: int, how: str, key: str) -> int:
    """A pitch a scale step (in the key) or a half step higher or lower."""
    if how == "up-half":
        return midi + 1
    if how == "down-half":
        return midi - 1
    pcs = scale_pcs(key)
    step = 1 if how == "up" else -1
    m = midi + step
    while m % 12 not in pcs:
        m += step
    return m


def respell_bar(bar: abcplan.Bar, key: str, targets: dict[int, int]) -> None:
    """Give the notes at token indexes `targets` new pitches. Every other note keeps its spelling;
    a natural or accidental is added only where the ABC rule (an accidental lasts the bar) would
    otherwise read a note differently from music21 (it lasts one note)."""
    ka = abcplan.key_accidentals(key)
    carried: dict[str, int] = {}
    for k, t in enumerate(bar.toks):
        if t.kind != "note":
            continue
        if k in targets:
            letter, alter, octave = abcplan._spell(targets[k], key)
            t.step, t.octave = letter, octave
            plain = ka.get(letter, 0)
            t.acc = "" if alter == plain == carried.get(letter, plain) else abcplan.ACC_TEXT[alter]
        elif not t.acc:
            plain = ka.get(t.step, 0)
            if carried.get(t.step, plain) != plain:
                t.acc = abcplan.ACC_TEXT[plain]
        if t.acc:
            carried[t.step] = t.acc.count("^") - t.acc.count("_")


def tie_chain(rows: list[list[Event]], e: Event) -> list[Event]:
    """The note a tie starts on and every note tied on from it (just `e` when it isn't tied)."""
    flat = [x for row in rows for x in row if x.kind == "note"]
    i = next(i for i, x in enumerate(flat) if x.id == e.id)
    while flat[i].held_over and i > 0:
        i -= 1
    chain = [flat[i]]
    while flat[i].tie and i + 1 < len(flat):
        i += 1
        chain.append(flat[i])
    return chain


def _next_in_bar(rows, e: Event) -> Event | None:
    row = rows[e.bar]
    i = row.index(e)
    return row[i + 1] if i + 1 < len(row) else None


def _next_event(rows, e: Event) -> Event | None:
    """The note or rest after `e`, in its bar or at the start of the next bar with any."""
    nxt = _next_in_bar(rows, e)
    if nxt is not None:
        return nxt
    return next((row[0] for row in rows[e.bar + 1:] if row), None)


def _sixteenths(length: Fraction, unit: Fraction) -> Fraction:
    return length * unit * 16


def simple_length(length: Fraction, unit: Fraction) -> bool:
    """A length one note can show: a power of two sixteenths, or one dotted (3 x a power of two)."""
    n = _sixteenths(length, unit)
    if n.denominator != 1 or n <= 0:
        return False
    n = int(n)
    while n % 2 == 0:
        n //= 2
    return n in (1, 3)


def _change_amount(unit: Fraction, length: Fraction, rest: bool = False) -> Fraction | None:
    """How much "longer" or "shorter" moves: an eighth note, or a sixteenth when the note giving up
    the time would otherwise vanish (a rest may); None when even that's too much."""
    for whole in (Fraction(1, 8), Fraction(1, 16)):
        step = whole / unit
        if length > step or (rest and length == step):
            return step
    return None


def split_lengths(length: Fraction, unit: Fraction) -> tuple[Fraction, Fraction] | None:
    """Two lengths for a note split in two: a dotted note into its note and the dot (a dotted
    quarter into a quarter and an eighth), any other into the largest power of two that leaves
    something; None when it's shorter than an eighth."""
    n = _sixteenths(length, unit)
    if n.denominator != 1 or n < 2:
        return None
    n = int(n)
    first = 1
    while first * 2 < n:
        first *= 2
    sixteenth = Fraction(1, 16) / unit
    return first * sixteenth, (n - first) * sixteenth


def render_line(tokens: list[lyr.Token]) -> str:
    """One line of a verse in Copyist's lyric syntax. A word that goes on to the next line keeps
    its hyphen."""
    chunks, buf = [], ""
    for t in tokens:
        if t.kind == lyr.SYL:
            buf += t.text
            if t.syllabic in ("begin", "middle"):
                buf += "-"
            else:
                chunks.append(buf)
                buf = ""
        elif t.kind == lyr.HOLD:
            if buf:
                chunks.append(buf + "_")
                buf = ""
            elif chunks:
                chunks[-1] += "_"
            else:
                chunks.append("_")
        else:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.append("*")
    if buf:
        chunks.append(buf)
    return " ".join(chunks)


def change_slot(verse: str, slot: int, insert: str | None = None, remove: bool = False) -> str:
    """A verse with "_" or "*" inserted after its token at `slot`, or the token at `slot` removed.
    Only the line that holds that token is written again; the verse's other lines stay as they are."""
    lines = verse.split("\n")
    per_line = [lyr.tokenize(line) for line in lines]
    where = [(li, j) for li, toks in enumerate(per_line) for j in range(len(toks))]
    if slot >= len(where):
        return verse                                    # the verse has already ended: nothing moves
    li, j = where[slot]
    toks = per_line[li]
    if insert is not None:
        toks.insert(j + 1, lyr.Token(lyr.HOLD if insert == "_" else lyr.SKIP))
    if remove:
        del toks[j]
    indent = lines[li][:len(lines[li]) - len(lines[li].lstrip())]
    lines[li] = indent + render_line(toks)
    return "\n".join(lines)


DEGREE_LETTERS = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}


def degree_root(key: str, semitones: int) -> str:
    """The chord root `semitones` above the key's tonic, spelled from the scale's letters: in C, 10
    is Bb (the flat seventh), not A#."""
    parts = abcplan._key_parts(key)
    tonic_letter = parts[0] if parts else "C"
    tonic = abcplan.key_tonic(key) or 0
    letter = LETTERS[(LETTERS.index(tonic_letter) + DEGREE_LETTERS[semitones % 12]) % 7]
    alter = (tonic + semitones - abcplan.NATURAL[letter]) % 12
    alter = alter - 12 if alter > 6 else alter
    if abs(alter) > 1:                                  # a double sharp or flat: name it plainly
        letter, alter, _ = abcplan._spell(60 + (tonic + semitones) % 12, key)
    return letter + {1: "#", -1: "b"}.get(alter, "")


def best_chords(rows, e: Event, key: str, limit: int = 8) -> list[dict]:
    """Chords to try from this note to the next chord change, best first: the share of that
    stretch's melody (by length) that's in the chord, then the chords a song in this key leans on
    most. The chord there now is always included."""
    flat = [x for row in rows for x in row]
    i = next(i for i, x in enumerate(flat) if x.id == e.id)
    span = [flat[i]]
    for x in flat[i + 1:]:
        if x.chord is not None:
            break
        span.append(x)
    weights: dict[int, float] = {}
    for x in span:
        if x.midi is not None:
            weights[x.midi % 12] = weights.get(x.midi % 12, 0.0) + float(x.length)
    total = sum(weights.values()) or 1.0
    mode = abcplan.key_mode(key)
    tonic = abcplan.key_tonic(key) or 0
    if mode is not None and mode <= -2:                 # minor, dorian, phrygian, locrian
        degrees = [(0, "m"), (7, ""), (5, "m"), (8, ""), (3, ""), (10, ""), (7, "7"), (2, "dim"), (7, "m")]
    else:
        degrees = [(0, ""), (5, ""), (7, ""), (9, "m"), (2, "m"), (7, "7"), (4, "m"), (11, "dim"), (10, "")]
    names = []
    for deg, quality in degrees:
        names.append(degree_root(key, deg) + quality)
    current = e.sounding
    if current and current not in names:
        names.append(current)
    out = []
    for rank, name in enumerate(names):
        pcs = {p % 12 for p in _chord_pitches(name)}
        if not pcs:
            continue
        fit = sum(w for pc, w in weights.items() if pc in pcs) / total
        out.append({"symbol": name, "fit": round(fit, 2), "tones": chord_tones(name), "rank": rank,
                    "now": name == current})
    out.sort(key=lambda c: (-c["fit"], c["rank"]))
    top = out[:limit]
    if current and not any(c["now"] for c in top):
        top[-1:] = [c for c in out if c["now"]]
    return top


def apply(path: Path, op: str, at: str, value: str | None = None, history: Path | None = None) -> dict:
    """Make one edit to the song file at `path`. Returns what changed, in a few words, and the note
    to keep selected."""
    if op not in OPS:
        raise EditError(f"Unknown edit {op!r}.")
    with _LOCK:
        return _apply(Path(path), op, at, value, history)


def _apply(path: Path, op: str, at: str, value: str | None, history: Path | None) -> dict:
    text, data = load(path)
    key, unit = key_of(data), unit_of(data)
    bars = bars_of(data)
    sources = _sources(bars, data["melody"])
    rows = events_of(bars, unit, key)
    e = _find(rows, at)
    verses = verses_of(data)
    slots = sum(1 for row in rows for x in row if x.slot is not None)
    words = words_by_slot(verses, slots)
    new_verses = None
    touched = {e.bar}
    toks = bars[e.bar].toks

    if op in PITCH_OPS:
        if e.kind != "note":
            raise EditError("That's a rest; pick a note to move.")
        chain = tie_chain(rows, e)
        new = moved(chain[0].midi, op, key)
        if not PITCH_RANGE[0] <= new <= PITCH_RANGE[1]:
            raise EditError("That's as far as it goes.")
        for b in {x.bar for x in chain}:
            respell_bar(bars[b], key, {x.tok: new for x in chain if x.bar == b})
        touched = {x.bar for x in chain}
        what = f"{name_of(chain[0].midi, key)} → {name_of(new, key)}"

    elif op == "longer":
        # The sound ends later: its last note (after any tie) takes time from what follows, which
        # starts later. Over a bar line, the note is held into the next bar with a tie.
        last = tie_chain(rows, e)[-1] if e.kind == "note" else e
        nxt = _next_event(rows, last)
        if nxt is None:
            raise EditError("It's the last note of the song.")
        ntoks = bars[nxt.bar].toks
        step = _change_amount(unit, ntoks[nxt.tok].length, rest=nxt.kind == "rest")
        if step is None:
            raise EditError("The next note is already as short as it gets; join the two instead.")
        ntoks[nxt.tok].length -= step
        if ntoks[nxt.tok].length == 0:
            del ntoks[nxt.tok]
        ltok = bars[last.bar].toks[last.tok]
        if nxt.bar == last.bar:
            ltok.length += step
        elif last.kind == "rest":
            ntoks.insert(nxt.tok, abcplan.Tok("rest", length=step))
        else:
            ltok.tie = True
            ntoks.insert(nxt.tok, abcplan.Tok("note", step=ltok.step, octave=ltok.octave, length=step))
            respell_bar(bars[nxt.bar], key, {nxt.tok: last.midi})
        touched = {last.bar, nxt.bar}
        what = "longer"

    elif op == "shorter":
        # The sound ends sooner: what follows in the bar starts earlier (a rest if nothing does).
        chain = tie_chain(rows, e) if e.kind == "note" else [e]
        last = chain[-1]
        ltoks = bars[last.bar].toks
        step = _change_amount(unit, ltoks[last.tok].length)
        touched = {x.bar for x in chain}
        if step is None and len(chain) > 1:            # drop a short held-over end instead
            ltoks[last.tok] = abcplan.Tok("rest", length=ltoks[last.tok].length)
            bars[chain[-2].bar].toks[chain[-2].tok].tie = False
        elif step is None:
            raise EditError("It's already as short as it gets.")
        else:
            ltoks[last.tok].length -= step
            nxt = _next_in_bar(rows, last)
            if nxt is not None:
                ltoks[nxt.tok].length += step
            else:
                ltoks.insert(last.tok + 1, abcplan.Tok("rest", length=step))
        what = "shorter"

    elif op == "split":
        if e.kind != "note":
            raise EditError("That's a rest; pick a note to split.")
        tok = toks[e.tok]
        parts = split_lengths(tok.length, unit)
        if parts is None:
            raise EditError("It's too short to split.")
        first = abcplan.Tok("note", acc=tok.acc, step=tok.step, octave=tok.octave, length=parts[0])
        tok.length = parts[1]                       # the second half keeps the note's tie and spacing
        toks.insert(e.tok, first)
        owner = tie_chain(rows, e)[0].slot          # the syllable the second half goes on holding
        new_verses = [change_slot(v, owner, insert="*" if w[owner] == "*" else "_")
                      for v, w in zip(verses, words)]
        what = "split in two"

    elif op == "join":
        # This note and the next become one held sound, at this note's pitch.
        if e.kind != "note":
            raise EditError("That's a rest; pick the first of two notes to join.")
        last = tie_chain(rows, e)[-1]
        nxt = _next_event(rows, last)
        if nxt is None or nxt.kind != "note":
            raise EditError("There's no note right after it to join.")
        sung = [w[nxt.slot] for w in words if w[nxt.slot] not in ("_", "*", "")]
        if sung:
            raise EditError(f"The next note has its own syllable (“{sung[0].rstrip('-')}”). Join "
                            "notes that hold one syllable, or change the words first.")
        others = tie_chain(rows, nxt)                 # the next note and anything tied on from it
        for b in {x.bar for x in others}:
            respell_bar(bars[b], key, {x.tok: last.midi for x in others if x.bar == b})
        ltok, ntok = bars[last.bar].toks[last.tok], bars[nxt.bar].toks[nxt.tok]
        total = ltok.length + ntok.length
        if nxt.bar == last.bar and nxt.tok == last.tok + 1 and simple_length(total, unit):
            # One note: the second token takes the first's spelling, keeping its spacing to the next.
            ntok.acc, ntok.step, ntok.octave, ntok.length = ltok.acc, ltok.step, ltok.octave, total
            del bars[last.bar].toks[last.tok]
        else:                     # over a bar line, past a chord change, or no single note that long
            ltok.tie = True
        new_verses = [change_slot(v, nxt.slot, remove=True) for v in verses]
        touched = {last.bar} | {x.bar for x in others}
        what = "joined with the next note"

    else:
        symbol = (value or "").strip().strip('"')
        if symbol and not CHORD.fullmatch(symbol):
            raise EditError(f"“{symbol}” isn't a chord symbol Copyist reads.")
        if symbol and not _chord_pitches(symbol):
            raise EditError(f"Copyist can't play “{symbol}”.")
        k = e.tok
        if k > 0 and toks[k - 1].kind == "chord":
            if symbol:
                toks[k - 1].text = symbol
            else:
                del toks[k - 1]
        elif symbol:
            toks.insert(k, abcplan.Tok("chord", symbol))
        what = f"chord {symbol}" if symbol else "chord taken out"

    for b in touched:                                 # every note still reads the same under the ABC rule
        respell_bar(bars[b], key, {})
    new_text = write_back(text, data, bars, touched, new_verses, sources)
    check(text, new_text, path)
    _save_history(history, text)
    path.write_text(new_text, encoding="utf-8")
    return {"changed": what, "at": at}


# ------------------------------------------------------------------ writing back

def _length_text(n: Fraction) -> str:
    return "/" if n == Fraction(1, 2) else abcplan._length_text(n)


def _tok_text(t: abcplan.Tok) -> str:
    if t.kind == "chord":
        return f'"{t.text}"'
    if t.kind == "rest":
        return "z" + _length_text(t.length)
    return abcplan.note_text(t) + _length_text(t.length) + ("-" if t.tie else "")


def bar_text(bar: abcplan.Bar) -> str:
    """One bar as song-file ABC, every chord symbol as written (the form edits are compared in)."""
    return " ".join(abcplan._merge_chords([_tok_text(t) for t in bar.toks]))


def _state(t: abcplan.Tok) -> tuple:
    return (t.kind, t.text, t.acc, t.step, t.octave, t.length, t.tie)


def _sources(bars: list[abcplan.Bar], melody: str) -> dict[int, tuple[str, str | None, tuple]]:
    """For each token as read: its text in the song file, the space after it (None for a bar's last
    token) and what it was. Lets an edited bar keep the spacing it was written with, which in ABC
    also says which short notes are beamed together ("B/G/" against "B/ G/")."""
    chunks = [c.strip().rstrip("]") for line in str(melody).strip().splitlines() for c in line.split("|")]
    chunks = [c for c in chunks if c]
    out: dict[int, tuple[str, str | None, tuple]] = {}
    if len(chunks) != len(bars):
        return out
    for bar, text in zip(bars, chunks):
        spans = [m.span() for m in abcplan.NOTE.finditer(text) if m.group(4) or m.group(6) or m.group(12)]
        if len(spans) != len(bar.toks):
            continue
        for i, (t, (a, b)) in enumerate(zip(bar.toks, spans)):
            gap = text[b:spans[i + 1][0]] if i + 1 < len(spans) else None
            out[id(t)] = (text[a:b], gap, _state(t))
    return out


def bar_source(bar: abcplan.Bar, sources: dict | None = None) -> str:
    """One edited bar's text: every token the edit didn't touch as it was written, changed and new
    ones written out, with the original spacing wherever there was some."""
    out = ""
    for i, t in enumerate(bar.toks):
        known = (sources or {}).get(id(t))
        piece = known[0] if known and known[2] == _state(t) else _tok_text(t)
        gap = known[1] if known and known[1] is not None else ("" if t.kind == "chord" else " ")
        out += piece + (gap if i + 1 < len(bar.toks) else "")
    return out


def _block(lines: list[str], field: str) -> tuple[int, int] | None:
    """[start, end) of a top-level field: its own line and the indented lines under it."""
    start = next((i for i, l in enumerate(lines) if re.match(rf"{re.escape(field)}\s*:", l)), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
        end += 1
    while end > start + 1 and not lines[end - 1].strip():
        end -= 1
    return start, end


def _bar_places(lines: list[str], block: tuple[int, int]) -> list[tuple[int, int]] | None:
    """Where each bar's text is in a `melody: |` block, as (line, chunk between bar lines); None
    when the block isn't a plain literal block."""
    start, end = block
    if not re.fullmatch(r"melody\s*:\s*\|[-+]?\s*(#.*)?", lines[start].rstrip()):
        return None
    places = []
    for i in range(start + 1, end):
        for c, chunk in enumerate(lines[i].split("|")):
            if chunk.strip().rstrip("]"):
                places.append((i, c))
    return places


def _whole_melody(text: str, bars: list[abcplan.Bar], unit: Fraction) -> str:
    return _replace_block(text, "melody", ["melody: |"] + ["  " + line for line in
                                                          abcplan.write(bars, unit, unit).splitlines()])


def _write_melody(text: str, bars: list[abcplan.Bar], touched: set[int], unit: Fraction,
                  sources: dict | None = None) -> str:
    lines = text.split("\n")
    block = _block(lines, "melody")
    places = _bar_places(lines, block) if block else None
    if places is None or len(places) != len(bars):
        return _whole_melody(text, bars, unit)
    for b in sorted(touched):
        i, c = places[b]
        chunks = lines[i].split("|")
        old = chunks[c]
        lead, trail = old[:len(old) - len(old.lstrip())], old[len(old.rstrip()):]
        chunks[c] = lead + bar_source(bars[b], sources) + trail
        lines[i] = "|".join(chunks)
    return "\n".join(lines)


def _verse_line(line: str) -> tuple[str, str, str] | None:
    """(what comes before the words, the words, how they're written) for one line of a lyrics
    block: a list item ("- words", "- 'words'", '- "words"') or a line inside a `- |` block."""
    s = line.rstrip()
    m = re.match(r"(\s*-\s+)(\S.*)$", s)
    if not m:
        return s[:len(s) - len(s.lstrip())], s.strip(), "block"
    try:
        value = yaml.safe_load(m.group(2))
    except yaml.YAMLError:
        return None
    if not isinstance(value, str):
        return None
    style = m.group(2)[0] if m.group(2)[0] in "'\"" else "plain"
    return m.group(1), value.strip(), style


def _scalar(words: str, style: str) -> str:
    """Words written back the way the line had them, quoted when YAML would misread them plain."""
    if style == "block":
        return words
    if style == "'":
        return "'" + words.replace("'", "''") + "'"
    if style == "plain":
        try:
            if yaml.safe_load(words) == words:
                return words
        except yaml.YAMLError:
            pass
    return json.dumps(words, ensure_ascii=False)


def _write_lyrics_in_place(text: str, old: list[str], new: list[str]) -> str | None:
    """Change just the verse lines that changed, where each verse's lines can be found in order in
    the `lyrics:` block; None when they can't."""
    lines = text.split("\n")
    block = _block(lines, "lyrics")
    if not block:
        return None
    cursor = block[0] + 1
    for before, after in zip(old, new):
        for line_before, line_after in zip(before.split("\n"), after.split("\n")):
            want = line_before.strip()
            if not want:
                continue
            while cursor < block[1] and (_verse_line(lines[cursor]) or ("", "", ""))[1] != want:
                cursor += 1
            if cursor >= block[1]:
                return None
            if line_after.strip() != want:
                prefix, _, style = _verse_line(lines[cursor])
                lines[cursor] = prefix + _scalar(line_after.strip(), style)
            cursor += 1
    return "\n".join(lines)


def _whole_lyrics(text: str, verses: list[str]) -> str:
    block = ["lyrics:"]
    for v in verses:
        block.append("  - |")
        block += ["    " + line.strip() for line in v.strip().splitlines()]
    return _replace_block(text, "lyrics", block)


def write_back(text: str, data: dict, bars: list[abcplan.Bar], touched: set[int],
               verses: list[str] | None, sources: dict | None = None) -> str:
    """The song file's text with the changed bars (and verse lines) written in, everything else as
    it was. Falls back to writing the whole melody or lyrics block when the text written in place
    wouldn't read back as intended."""
    unit = unit_of(data)
    want_bars = [bar_text(b) for b in bars]
    old_verses = verses_of(data)
    want_verses = [v.strip() for v in (verses if verses is not None else old_verses)]
    others = {k: v for k, v in data.items() if k not in ("melody", "lyrics")}

    def melody_ok(candidate: str) -> bool:
        try:
            got = yaml.safe_load(candidate)
            return [bar_text(b) for b in bars_from_melody(got["melody"], got.get("sections"))] == want_bars
        except Exception:
            return False

    def reads_back(candidate: str) -> bool:
        if not melody_ok(candidate):
            return False
        got = yaml.safe_load(candidate)
        return ({k: v for k, v in got.items() if k not in ("melody", "lyrics")} == others
                and [v.strip() for v in verses_of(got)] == want_verses)

    out = _write_melody(text, bars, touched, unit, sources)
    if not melody_ok(out):
        out = _whole_melody(text, bars, unit)
    if verses is not None:
        in_place = _write_lyrics_in_place(out, old_verses, verses)
        out = in_place if in_place is not None and reads_back(in_place) else _whole_lyrics(out, verses)
    if not reads_back(out):
        raise EditError("Copyist couldn't write that edit back into the song file.")
    return out


def _replace_block(text: str, field: str, new_lines: list[str]) -> str:
    """Replace a top-level field (its line and the indented lines under it) with `new_lines`."""
    lines = text.split("\n")
    block = _block(lines, field)
    if block is None:
        at = len(lines) - (1 if lines and lines[-1] == "" else 0)
        return "\n".join(lines[:at] + new_lines + lines[at:])
    start, end = block
    return "\n".join(lines[:start] + new_lines + lines[end:])


def _problems(path: Path) -> set[tuple]:
    from .song import load_song
    from .validate import FAIL, check_bars, check_lyrics_fit
    song = load_song(path)
    return {(f.check, f.message, f.bar) for f in check_bars(song) + check_lyrics_fit(song)
            if f.severity == FAIL}


def check(old_text: str, new_text: str, path: Path) -> None:
    """The edited song must still load, add up bar by bar and fit its words, unless it already
    didn't before the edit (a song mid-revision can still be edited)."""
    probe = path.with_name(f".{path.stem}.edit-check{path.suffix}")
    try:
        probe.write_text(old_text, encoding="utf-8")
        try:
            before = _problems(probe)
        except SongError:
            before = set()                              # it didn't load before: only ask that it loads
        probe.write_text(new_text, encoding="utf-8")
        try:
            after = _problems(probe)
        except SongError as e:
            raise EditError(f"That edit would break the song: {e}") from e
    finally:
        probe.unlink(missing_ok=True)
    new = sorted(after - before, key=str)
    if new:
        raise EditError("That edit would break the song: " + "; ".join(m for _, m, _ in new[:2]))


# ------------------------------------------------------------------ undo

def _history(folder: Path | None) -> dict:
    if not folder:
        return {"undo": [], "redo": []}
    try:
        hist = json.loads((Path(folder) / "history.json").read_text(encoding="utf-8"))
        return {"undo": list(hist.get("undo", [])), "redo": list(hist.get("redo", []))}
    except (OSError, ValueError, AttributeError):
        return {"undo": [], "redo": []}


def _write_history(folder: Path, hist: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "history.json").write_text(json.dumps(hist), encoding="utf-8")


def _keep(folder: Path, hist: dict, text: str) -> str:
    """Save one version of the song file; returns its name."""
    taken = [int(Path(f).stem) for f in hist["undo"] + hist["redo"] if Path(f).stem.isdigit()]
    name = f"{max(taken + [0]) + 1:05d}.yaml"
    (folder / "versions").mkdir(parents=True, exist_ok=True)
    (folder / "versions" / name).write_text(text, encoding="utf-8")
    return name


def _save_history(folder: Path | None, text: str) -> None:
    if not folder:
        return
    folder = Path(folder)
    hist = _history(folder)
    hist["undo"].append(_keep(folder, hist, text))
    for name in hist["redo"]:
        (folder / "versions" / name).unlink(missing_ok=True)
    hist["redo"] = []
    for name in hist["undo"][:-HISTORY_LIMIT]:
        (folder / "versions" / name).unlink(missing_ok=True)
    hist["undo"] = hist["undo"][-HISTORY_LIMIT:]
    _write_history(folder, hist)


def step_back(path: Path, folder: Path, redo: bool = False) -> dict:
    """Undo the last edit (or redo the last one undone). The song as it is now is kept, so the step
    can be taken back the other way."""
    with _LOCK:
        path, folder = Path(path), Path(folder)
        hist = _history(folder)
        source, target = ("redo", "undo") if redo else ("undo", "redo")
        if not hist[source]:
            raise EditError("Nothing to redo." if redo else "Nothing to undo.")
        name = hist[source][-1]
        saved = folder / "versions" / name
        if not saved.is_file():
            raise EditError("That earlier version is missing from the edit history.")
        hist[target].append(_keep(folder, hist, path.read_text(encoding="utf-8")))
        hist[source].pop()
        shutil.copyfile(saved, path)
        saved.unlink(missing_ok=True)
        _write_history(folder, hist)
        return {"changed": "redone" if redo else "undone"}
