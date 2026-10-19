"""Lyric syllables and their alignment to melody notes.

The syntax follows ABC `w:` lines (see SPEC.md section 4):

- spaces separate syllables; a hyphen splits a word into syllables
  ("A-maz-ing"), and a word continues across a hyphen at the end of a chunk
  ("al-_ read-y");
- "_" holds the previous syllable over the next note (melisma);
- "*" skips a note;
- tied continuation notes and rests never take a syllable.

Copyist aligns lyrics itself rather than relying on music21's ABC lyric
handling, so the rules are explicit and testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from music21 import note, spanner, stream

SYL, HOLD, SKIP = "syl", "hold", "skip"

# Marks a lyric whose word ends on a held syllable, so the engraver draws an
# extender line under the held notes (MusicXML <extend>; see engrave.py).
EXTEND_MARK = "copyist-extend"


@dataclass
class Token:
    kind: str                 # SYL, HOLD or SKIP
    text: str = ""
    syllabic: str = "single"  # single, begin, middle or end (MusicXML terms)
    word: int = -1            # index of the word this syllable belongs to


@dataclass
class Placed:
    """One syllable placed on one note, plus the notes it's held over (a melisma)."""
    text: str
    syllabic: str
    word: int
    note: note.Note
    held: list[note.Note] = field(default_factory=list)
    slot: int = -1


@dataclass
class VerseFit:
    """How one verse's syllables fit the melody."""
    number: int
    syllables: int            # syllables in the verse (excluding _ and *)
    slots_used: int           # notes consumed (syllables, holds and skips)
    slots_available: int      # notes that can take a syllable
    placed: list[Placed] = field(default_factory=list)

    @property
    def fits(self) -> bool:
        return self.slots_used == self.slots_available


def note_target(text: str) -> int:
    """How many melody notes the lyric line expects: syllables plus `_` holds and `*` skips.

    The open engine's tidy/split target must count holds — Silent Night has 41 syllables
    but 46 sung notes because of `night_`, `peace_`, etc.
    """
    return sum(1 for t in tokenize(text) if t.kind in (SYL, HOLD, SKIP))


def tokenize(text: str) -> list[Token]:
    """Split a verse into syllable, hold and skip tokens."""
    tokens: list[Token] = []
    word = -1
    continuing = False        # previous chunk ended with a hyphen
    for chunk in text.split():
        # Separate the hold/skip markers glued to a chunk, e.g. "ing_" or "_".
        parts = re.findall(r"[^_*]+|_|\*", chunk)
        for part in parts:
            if part == "_":
                tokens.append(Token(HOLD))
                continue
            if part == "*":
                tokens.append(Token(SKIP))
                continue
            pieces = part.split("-")
            ends_with_hyphen = part.endswith("-")
            if ends_with_hyphen:
                pieces = pieces[:-1]
            pieces = [p for p in pieces if p]
            if not pieces:
                continuing = continuing or ends_with_hyphen
                continue
            for i, piece in enumerate(pieces):
                first_of_word = i == 0 and not continuing
                if first_of_word:
                    word += 1
                more_follow = i < len(pieces) - 1 or ends_with_hyphen
                if first_of_word and not more_follow:
                    syllabic = "single"
                elif first_of_word:
                    syllabic = "begin"
                elif more_follow:
                    syllabic = "middle"
                else:
                    syllabic = "end"
                tokens.append(Token(SYL, piece, syllabic, word))
            continuing = ends_with_hyphen
    return tokens


def lyric_slots(part: stream.Stream) -> list[note.Note]:
    """Notes that can take a syllable: note onsets, not tie continuations or rests."""
    slots = []
    for n in part.recurse().notes:
        if not isinstance(n, note.Note) or n.duration.isGrace:
            continue
        if n.tie is not None and n.tie.type in ("stop", "continue"):
            continue
        slots.append(n)
    return slots


def align(part: stream.Stream, verses: list[str]) -> list[VerseFit]:
    """Attach each verse's syllables to the melody as music21 lyrics.

    Returns one VerseFit per verse, whether or not it fits, so validators can
    report exactly where a verse runs short or long.
    """
    slots = lyric_slots(part)
    fits = []
    for number, text in enumerate(verses, start=1):
        tokens = tokenize(text)
        fit = VerseFit(number, sum(t.kind == SYL for t in tokens), len(tokens), len(slots))
        last: Placed | None = None
        for i, (token, n) in enumerate(zip(tokens, slots)):
            if token.kind == SYL:
                lyric = note.Lyric(text=token.text, number=number, syllabic=token.syllabic)
                n.lyrics.append(lyric)
                last = Placed(token.text, token.syllabic, token.word, n, slot=i)
                fit.placed.append(last)
            elif token.kind == HOLD and last is not None:
                last.held.append(n)
            else:
                last = None
        for placed in fit.placed:
            if placed.held and placed.syllabic in ("single", "end"):
                placed.note.lyrics[-1].identifier = EXTEND_MARK
        fits.append(fit)
    return fits


def melisma_slurs(part: stream.Part, fits: list[VerseFit]) -> list[spanner.Slur]:
    """Slur the notes of each held syllable, where every verse holds there.

    Singers read a slur as "one syllable across these notes". If verses
    disagree (one holds, another sings a new syllable), no slur is drawn.
    """
    if not fits:
        return []
    def groups(fit: VerseFit) -> dict[int, tuple]:
        return {p.slot: tuple(id(n) for n in p.held) for p in fit.placed if p.held}
    first, rest = groups(fits[0]), [groups(f) for f in fits[1:]]
    slurs = []
    for placed in fits[0].placed:
        if not placed.held:
            continue
        if all(g.get(placed.slot) == first[placed.slot] for g in rest):
            slur = spanner.Slur([placed.note] + placed.held)
            part.insert(0, slur)
            slurs.append(slur)
    return slurs
