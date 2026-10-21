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

# Among parts with words, or without lyrics to go by, prefer a part named like the sung line;
# in a choir score, the soprano.
_VOCAL_NAME = re.compile(r"(voice|vocal|melody|solo|singer|lead)", re.IGNORECASE)
_TOP_VOICE = re.compile(r"(soprano|treble|cantus)", re.IGNORECASE)
SHARE_OF_WORDS = 0.8          # parts with this share of the most sung words are all candidates
REFRAIN_RUN = 4               # a verse silent this many notes where another sings shares its words


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
    """The sung line. Parts with words come first (a vocal part is often named for its character,
    such as "Major-General"); among those with about as many words as the most, one named like a
    voice, else the highest soprano, else the highest part. Without words: a part named like a voice, else the
    first part with pitched notes."""
    parts = list(score.parts)
    if not parts:
        raise MusicxmlImportError("That MusicXML has no parts.")
    def _label(p: stream.Part) -> str:
        return str(p.partName or p.id or "")

    def _sung(p: stream.Part) -> int:
        return sum(1 for n in p.recurse().notes if isinstance(n, note.Note) and n.lyrics)

    def _height(p: stream.Part) -> float:
        ps = [n.pitch.ps for n in p.recurse().notes if isinstance(n, note.Note)]
        return sum(ps) / len(ps) if ps else 0.0

    words = {id(p): _sung(p) for p in parts}
    most = max(words.values())
    if most > 0:
        close = [p for p in parts if words[id(p)] >= SHARE_OF_WORDS * most]
        named = [p for p in close if _VOCAL_NAME.search(_label(p))]
        if named:
            return max(named, key=lambda p: words[id(p)])
        top = [p for p in close if _TOP_VOICE.search(_label(p))]
        return max(top or close, key=_height)    # Soprano I over Soprano II, a choir's top line
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


def _sung_slots(part: stream.Part) -> list[note.NotRest | None]:
    """The notes that can take a syllable, in order (tie continuations and grace notes left out),
    with None for each rest, which ends a held syllable."""
    out: list[note.NotRest | None] = []
    for el in part.recurse().notesAndRests:
        if isinstance(el, note.Rest):
            if out and out[-1] is not None:
                out.append(None)
            continue
        if not isinstance(el, note.NotRest) or el.duration.isGrace or el.quarterLength == 0:
            continue
        if el.tie is not None and el.tie.type in ("stop", "continue"):
            continue
        out.append(el)
    return out


def _syllable(n: note.NotRest, verse: int) -> tuple[str, str] | None:
    for ly in n.lyrics:
        if (int(ly.number) if ly.number else 1) == verse and ly.text and ly.text.strip() not in ("", "_"):
            return "".join(str(ly.text).split()), ly.syllabic or "single"
    return None


def _verse_tokens(slots: list, verse: int, verses: list[int]) -> list[tuple]:
    """One token per sung note for `verse`: ("syl", text, syllabic), ("hold",) or ("skip",).

    A note with no syllable for this verse holds the syllable before it, unless a rest came
    between (then it's skipped). Where this verse is silent for REFRAIN_RUN notes or more and
    another verse sings, the words are shared: a refrain printed once, under the first verse."""
    notes = [n for n in slots if n is not None]
    own = [_syllable(n, verse) for n in notes]
    donor_of = []
    for n in notes:
        donor = next((v for v in verses if v != verse and _syllable(n, v)), None)
        donor_of.append(donor)
    shared = [False] * len(notes)
    k = 0
    while k < len(notes):
        if own[k] is None:
            j = k
            while j < len(notes) and own[j] is None:
                j += 1
            donors = [d for d in donor_of[k:j] if d is not None]
            if j - k >= REFRAIN_RUN and len(donors) >= REFRAIN_RUN - 1:
                for i in range(k, j):
                    shared[i] = True
            k = j
        else:
            k += 1
    tokens: list[tuple] = []
    sung_since_rest = False
    i = 0
    for n in slots:
        if n is None:
            sung_since_rest = False
            continue
        syl = own[i]
        if syl is None and shared[i]:
            first = next(d for d in donor_of[i:] + donor_of[:i] if d is not None)
            syl = _syllable(n, donor_of[i] or first)
        if syl:
            tokens.append(("syl", *syl))
            sung_since_rest = True
        elif sung_since_rest:
            tokens.append(("hold",))
        else:
            tokens.append(("skip",))
        i += 1
    return tokens


def _render_verse(tokens: list[tuple]) -> str:
    """Tokens in Copyist's lyric syntax: "A-maz-ing_ grace", "al-_ read-y", "*" for a skip."""
    chunks: list[str] = []
    buf = ""
    for tok in tokens:
        if tok[0] == "syl":
            _, text, syllabic = tok
            text = text.replace("-", "").replace("_", "").replace("*", "")
            buf += text
            if syllabic in ("begin", "middle"):
                buf += "-"
            else:
                chunks.append(buf)
                buf = ""
        elif tok[0] == "hold":
            if buf:                      # inside a word: "al-_" and the word goes on in the next chunk
                chunks.append(buf + "_")
                buf = ""
            elif chunks:
                chunks[-1] += "_"
        else:
            if buf:
                chunks.append(buf.rstrip("-"))
                buf = ""
            chunks.append("*")
    if buf:
        chunks.append(buf.rstrip("-"))
    text = " ".join(chunks)
    return re.sub(r"^\d+\.\s*", "", text)      # a verse number printed before the first word


def _lyrics_by_verse(part: stream.Part) -> list[str]:
    """One lyric string per verse number, in Copyist's syntax, with holds and skips so every verse
    lines up with the melody's notes as the score placed it."""
    slots = _sung_slots(part)
    verses = sorted({int(ly.number) if ly.number else 1 for n in slots if n is not None
                     for ly in n.lyrics if ly.text and ly.text.strip()})
    return [_render_verse(_verse_tokens(slots, v, verses)) for v in verses]


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
