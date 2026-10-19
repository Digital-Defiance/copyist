"""MusicXML → Copyist song file (lead sheet: melody, chords, lyrics).

This is the first slice of MusicXML import: a lead sheet (or the vocal line of a
piano-vocal score) becomes a song YAML. Full-score edit round-trip (keeping every
Copyist field) is still ahead.
"""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

from music21 import chord as m21chord, converter, harmony, key as m21key, meter, note, stream, tempo

from . import abcplan
from .song import FORMAT, SongError
from .write import song_yaml

# Prefer a part that looks like the sung line when a piano-vocal file has several.
_VOCAL_NAME = re.compile(r"(voice|vocal|melody|solo|singer|major.?general)", re.IGNORECASE)


class MusicxmlImportError(SongError):
    """MusicXML Copyist can't turn into a song file."""


def load_score(path: str | Path) -> stream.Score:
    path = Path(path)
    if not path.is_file():
        raise MusicxmlImportError(f"No file at {path}.")
    try:
        score = converter.parse(str(path))
    except Exception as e:  # music21 raises many types for bad XML
        raise MusicxmlImportError(f"Couldn't read {path.name} as MusicXML: {e}") from e
    if isinstance(score, stream.Part):
        wrapped = stream.Score()
        wrapped.insert(0, score)
        score = wrapped
    if not isinstance(score, stream.Score):
        raise MusicxmlImportError(f"{path.name} isn't a score or part Copyist can read.")
    return score


def pick_melody_part(score: stream.Score) -> stream.Part:
    """The sung line: a part named like a voice, else the first part with pitched notes."""
    parts = list(score.parts)
    if not parts:
        raise MusicxmlImportError("That MusicXML has no parts.")
    def _label(p: stream.Part) -> str:
        return str(p.partName or p.id or "")

    named = [p for p in parts if _VOCAL_NAME.search(_label(p))]
    candidates = named or parts
    for part in candidates:
        if any(isinstance(n, note.Note) for n in part.recurse().notes):
            return part
    raise MusicxmlImportError("No pitched melody notes found in that MusicXML.")


def _key_name(score: stream.Score, part: stream.Part) -> str:
    for src in (part, score):
        k = src.recurse().getElementsByClass(m21key.Key).first()
        if k is not None:
            return _key_to_abc(k)
        ks = src.recurse().getElementsByClass(m21key.KeySignature).first()
        if ks is not None:
            return _key_to_abc(ks.asKey())
    analyzed = score.analyze("key")
    return _key_to_abc(analyzed)


def _key_to_abc(k: m21key.Key) -> str:
    tonic = k.tonic.name.replace("-", "b")
    if k.mode == "minor":
        return f"{tonic}m" if not tonic.endswith("m") else tonic
    return tonic


def _meter_text(score: stream.Score, part: stream.Part) -> str:
    for src in (part, score):
        ts = src.recurse().getElementsByClass(meter.TimeSignature).first()
        if ts is not None:
            return f"{ts.numerator}/{ts.denominator}"
    return "4/4"


def _tempo_value(score: stream.Score) -> int:
    mark = score.recurse().getElementsByClass(tempo.MetronomeMark).first()
    if mark is not None and mark.number:
        return round(mark.number)
    return 120


def _abc_pitch(p) -> tuple[str, str, str, int]:
    """Accidentals, step, octave marks, and octave number for abcplan.Tok."""
    step = p.step.upper()
    octave = p.octave if p.octave is not None else 4
    acc = ""
    if p.accidental is not None:
        acc = {"sharp": "^", "flat": "_", "natural": "=", "double-sharp": "^^",
               "double-flat": "__"}.get(p.accidental.name, "")
    return acc, step, "", octave


def _ql_to_units(ql: float | Fraction, unit: Fraction) -> Fraction:
    unit_ql = unit * 4
    return Fraction(ql).limit_denominator(64) / unit_ql


def part_to_bars(part: stream.Part, unit: Fraction, key: str | None = None) -> list[abcplan.Bar]:
    """One abcplan.Bar per measure, with chord symbols glued to the next note/rest.

    `key` is the song's key: a natural on a letter it alters is written `=`, so the score's own key
    changes keep their pitches under the song's one key signature (SPEC section 4)."""
    key_alters = abcplan.key_accidentals(key) if key else {}
    measures = list(part.getElementsByClass(stream.Measure))
    if not measures:
        # Flat part: one synthetic bar stream
        return [_elements_to_bar(list(part.flatten().notesAndRests) +
                                 list(part.flatten().getElementsByClass(harmony.ChordSymbol)), unit, key_alters)]

    bars: list[abcplan.Bar] = []
    for meas in measures:
        els = []
        for el in meas.recurse():
            if isinstance(el, (note.Note, note.Rest, harmony.ChordSymbol)):
                els.append(el)
            elif isinstance(el, m21chord.Chord) and not isinstance(el, harmony.ChordSymbol):
                # Melody should be single notes; take the top pitch if a chord slipped in.
                top = max(el.pitches, key=lambda p: p.ps)
                n = note.Note(top)
                n.duration = el.duration
                n.tie = el.tie
                n.lyrics = el.lyrics
                n.offset = el.offset
                els.append(n)
        # Sort by offset so chord symbols precede notes at the same beat.
        els.sort(key=lambda e: (e.offset, 0 if isinstance(e, harmony.ChordSymbol) else 1))
        bars.append(_elements_to_bar(els, unit, key_alters))
    # Drop trailing empty bars
    while bars and not bars[-1].sung and bars[-1].length == 0:
        bars.pop()
    return bars


def _elements_to_bar(els: list, unit: Fraction, key_alters: dict[str, int] | None = None) -> abcplan.Bar:
    toks: list[abcplan.Tok] = []
    for el in els:
        if isinstance(el, harmony.ChordSymbol):
            figure = (el.figure or "").replace("-", "b").strip()
            if not figure and el.root() is not None:
                figure = el.root().name.replace("-", "b")
                if getattr(el, "quality", None) == "minor":
                    figure += "m"
            if figure:
                toks.append(abcplan.Tok("chord", figure))
            continue
        length = _ql_to_units(el.quarterLength, unit)
        if length <= 0:
            continue
        if isinstance(el, note.Rest):
            toks.append(abcplan.Tok("rest", length=length))
            continue
        acc, step, _, octave = _abc_pitch(el.pitch)
        if not acc and el.pitch.alter == 0 and (key_alters or {}).get(step):
            acc = "="                    # natural here (a key change in the score), altered in the song's key
        tie = bool(el.tie and el.tie.type in ("start", "continue"))
        toks.append(abcplan.Tok("note", acc=acc, step=step, octave=octave, length=length, tie=tie))
    return abcplan.Bar(toks, section="verse")


def _lyrics_by_verse(part: stream.Part) -> list[str]:
    """One lyric string per verse number, syllables joined for Copyist's lyric fit."""
    verses: dict[int, list[str]] = {}
    for n in part.recurse().notes:
        if not isinstance(n, note.Note):
            continue
        if n.tie and n.tie.type in ("stop", "continue"):
            # Tied continuation: melisma already marked on the start in export; skip empties.
            pass
        for ly in n.lyrics:
            if not ly or not ly.text or ly.text == "_":
                continue
            num = int(ly.number) if ly.number else 1
            text = str(ly.text).strip()
            if ly.syllabic in ("begin", "middle"):
                text = text + "-"
            verses.setdefault(num, []).append(text)
    if not verses:
        return []
    out = []
    for num in sorted(verses):
        # Hyphen already on begin/middle; join with spaces between words.
        parts = verses[num]
        line = []
        buf = ""
        for p in parts:
            if p.endswith("-"):
                buf += p
            else:
                line.append(buf + p)
                buf = ""
        if buf:
            line.append(buf.rstrip("-"))
        out.append(" ".join(line))
    return out


def _title_credits(score: stream.Score, path: Path, title: str | None,
                   credits: dict | None) -> tuple[str, dict]:
    md = score.metadata
    t = title
    if not t and md:
        t = md.bestTitle or md.movementName or md.title or None
    if not t:
        t = path.stem.replace("-", " ").replace("_", " ").title()
    cred = dict(credits or {})
    if md:
        if md.composer and "music" not in cred:
            cred["music"] = md.composer
        if md.lyricist and "words" not in cred:
            cred["words"] = md.lyricist
    return str(t), cred


def song_data_from_musicxml(path: str | Path, *, title: str | None = None,
                            credits: dict | None = None, style: str | None = None,
                            tempo: int | None = None) -> dict:
    """Read MusicXML and return a song-file mapping (format copyist-song/0)."""
    path = Path(path)
    score = load_score(path)
    part = pick_melody_part(score)
    key_name = _key_name(score, part)
    meter_text = _meter_text(score, part)
    unit = Fraction(1, 8)  # patter and most lead sheets; write() will coarsen when possible
    bars = part_to_bars(part, unit, key_name)
    if not any(b.sung for b in bars):
        raise MusicxmlImportError(f"{path.name}: the melody part has no notes.")
    unit = abcplan.best_unit(bars, unit)
    melody = abcplan.write(bars, unit, unit)
    verses = _lyrics_by_verse(part)
    t, cred = _title_credits(score, path, title, credits)
    data: dict = {
        "format": FORMAT,
        "title": t,
    }
    if cred:
        data["credits"] = cred
    data.update({
        "key": key_name,
        "meter": meter_text,
        "unit": f"{unit.numerator}/{unit.denominator}",
        "tempo": tempo if tempo is not None else _tempo_value(score),
        "voice": {"name": "Melody", "clef": "treble"},
    })
    if style:
        data["style"] = style
    data["melody"] = melody
    if verses:
        data["lyrics"] = verses
    return data


def import_musicxml(path: str | Path, out: str | Path, **kwargs) -> Path:
    """Write a song YAML from MusicXML; return the path written."""
    data = song_data_from_musicxml(path, **kwargs)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(song_yaml(data), encoding="utf-8")
    return out
