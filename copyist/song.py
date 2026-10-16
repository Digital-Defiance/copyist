"""Load a song file (SPEC.md section 4) into a music21 score."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import yaml
from music21 import converter, key as m21key, metadata, pitch, stream

from . import lyrics as lyr

FORMAT = "copyist-song/0"
REQUIRED = ("title", "key", "meter", "melody")


class SongError(ValueError):
    """A song file that can't be loaded, with a message a person can act on."""


@dataclass
class Song:
    path: Path
    title: str
    credits: dict
    key: str
    meter: str
    unit: str
    tempo: str
    voice_name: str
    voice_range: tuple[pitch.Pitch, pitch.Pitch] | None
    style: str | None
    melody_abc: str
    verses: list[str]
    score: stream.Score = field(repr=False)
    lyric_fits: list[lyr.VerseFit] = field(default_factory=list, repr=False)

    @property
    def slug(self) -> str:
        return self.path.stem

    @property
    def melody(self) -> stream.Part:
        return self.score.parts[0]

    def key_object(self) -> m21key.Key:
        return parse_key(self.key)

    def written_bars(self) -> list[Fraction]:
        """Each bar's length in quarter notes, exactly as written between bar lines.

        music21 re-bars an overfull bar by the meter, which would hide where the
        mistake is; validators use this instead.
        """
        return abc_bar_lengths(self.melody_abc, self.unit)


def parse_key(text: str) -> m21key.Key:
    """Turn an ABC-style key ("G", "Em", "Bb", "F#m", "D dorian") into a music21 Key."""
    m = re.fullmatch(r"\s*([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major|ionian|dorian|phrygian|lydian|"
                     r"mixolydian|aeolian|locrian)?\s*", text, re.I)
    if not m:
        raise SongError(f"Can't read the key {text!r}. Use something like G, Em, Bb, F#m or D dorian.")
    tonic = m.group(1).upper() + {"#": "#", "b": "-", "": ""}[m.group(2)]
    mode = (m.group(3) or "major").lower()
    mode = {"m": "minor", "min": "minor", "maj": "major", "ionian": "major", "aeolian": "minor"}.get(mode, mode)
    return m21key.Key(tonic.lower() if mode == "minor" else tonic, mode)


ABC_NOTE = re.compile(r"(?:\^{1,2}|_{1,2}|=)?([A-Ga-gzZx])[,']*(\d*)(/*)(\d*)")
ABC_IGNORE = re.compile(r'"[^"]*"|![^!]*!|\[[A-Za-z]:[^\]]*\]')
ABC_BARLINE = re.compile(r"\|\]|\|\||:\||\|:|\[\||\|")


def abc_bar_lengths(melody: str, unit: str = "1/4") -> list[Fraction]:
    """Bar lengths (in quarter notes) of an ABC melody in Copyist's subset (SPEC section 4)."""
    unit_ql = Fraction(unit) * 4
    text = ABC_IGNORE.sub(" ", melody)
    bars = []
    for chunk in ABC_BARLINE.split(text):
        if not chunk.strip():
            continue
        total = Fraction(0)
        for m in ABC_NOTE.finditer(chunk):
            num = int(m.group(2)) if m.group(2) else 1
            slashes, den = m.group(3), m.group(4)
            denom = int(den) if den else (2 ** len(slashes) if slashes else 1)
            total += Fraction(num, denom) * unit_ql
        bars.append(total)
    return bars


def number_bars(part: stream.Part) -> None:
    """Number bars the way players expect: a pickup is bar 0, the first full bar is bar 1."""
    bars = list(part.getElementsByClass(stream.Measure))
    if not bars:
        return
    full = bars[0].barDuration.quarterLength
    first = sum(e.quarterLength for e in bars[0].notesAndRests if "ChordSymbol" not in e.classes)
    start = 0 if first < full else 1
    for i, m in enumerate(bars):
        m.number = start + i


def build_abc(data: dict) -> str:
    tempo = data.get("tempo", 90)
    tempo = f"1/4={tempo}" if isinstance(tempo, (int, float)) else str(tempo)
    header = [
        "X:1",
        f"T:{data['title']}",
        f"M:{data['meter']}",
        f"L:{data.get('unit', '1/4')}",
        f"Q:{tempo}",
        f"K:{data['key']}",
    ]
    return "\n".join(header) + "\n" + data["melody"].strip() + "\n"


def load_song(path: str | Path) -> Song:
    """Read a song file, parse its melody and attach chord symbols and lyrics."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SongError(f"{path.name} isn't valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise SongError(f"{path.name} should be a YAML mapping (title:, key:, melody: ...).")
    fmt = data.get("format", FORMAT)
    if fmt != FORMAT:
        raise SongError(f"{path.name} is format {fmt!r}; this version of Copyist reads {FORMAT!r}.")
    missing = [k for k in REQUIRED if not data.get(k)]
    if missing:
        raise SongError(f"{path.name} is missing: {', '.join(missing)}.")

    parse_key(str(data["key"]))  # fail early with a readable message
    abc = build_abc(data)
    try:
        score = converter.parse(abc, format="abc")
    except Exception as e:  # music21 raises a variety of errors for bad ABC
        raise SongError(f"Couldn't read the melody in {path.name}: {e}") from e
    if not isinstance(score, stream.Score):
        wrapped = stream.Score()
        wrapped.insert(0, score)
        score = wrapped

    credits = data.get("credits") or {}
    voice = data.get("voice") or {}
    voice_name = voice.get("name", "Melody")
    voice_range = None
    if voice.get("range"):
        low, high = voice["range"]
        voice_range = (pitch.Pitch(str(low)), pitch.Pitch(str(high)))

    md = score.metadata or metadata.Metadata()
    md.title = data["title"]
    if credits.get("music"):
        md.composer = credits["music"]
    if credits.get("words"):
        md.lyricist = credits["words"]
    score.metadata = md

    part = score.parts[0]
    # No instrument name on a lead sheet; arrangements name their parts.
    part.partName = None
    number_bars(part)

    verses = data.get("lyrics") or []
    if isinstance(verses, str):
        verses = [verses]
    fits = lyr.align(part, [str(v) for v in verses])

    return Song(
        path=path,
        title=data["title"],
        credits=credits,
        key=str(data["key"]),
        meter=str(data["meter"]),
        unit=str(data.get("unit", "1/4")),
        tempo=str(data.get("tempo", 90)),
        voice_name=voice_name,
        voice_range=voice_range,
        style=data.get("style"),
        melody_abc=data["melody"],
        verses=verses,
        score=score,
        lyric_fits=fits,
    )
