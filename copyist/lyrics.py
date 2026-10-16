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

from music21 import note, stream

SYL, HOLD, SKIP = "syl", "hold", "skip"


@dataclass
class Token:
    kind: str                 # SYL, HOLD or SKIP
    text: str = ""
    syllabic: str = "single"  # single, begin, middle or end (MusicXML terms)
    word: int = -1            # index of the word this syllable belongs to


@dataclass
class Placed:
    """One syllable placed on one note."""
    text: str
    syllabic: str
    word: int
    note: note.Note


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
        for token, n in zip(tokens, slots):
            if token.kind != SYL:
                continue
            lyric = note.Lyric(text=token.text, number=number, syllabic=token.syllabic)
            n.lyrics.append(lyric)
            fit.placed.append(Placed(token.text, token.syllabic, token.word, n))
        fits.append(fit)
    return fits
