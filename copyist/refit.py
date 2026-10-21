"""Refit lyrics under an existing melody (`copyist refit`, docs/melody-writing.md).

The notes and chords stay; the words are placed again with the same fitter `copyist write`
uses. Note splits are allowed when there are more syllables than notes, so the melody may
gain a repeated pitch. The song file is rewritten in place.

Several verses (blocks of lines separated by a blank line, as the page shows them) are each
fitted to the melody on their own, as a hymn's verses are, when the words are too many for one
pass through it.
"""
from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

import yaml

from . import fit as fitting, rewrite, syllables, write
from .song import FORMAT
from .write import WriteError

MIN_VERSE_SHARE = 0.7    # a verse sung to the whole melody has at least this many syllables a note


def verse_blocks(lyrics: str) -> list[str]:
    """The lyrics' blocks of lines, split at blank lines."""
    return [b.strip() for b in re.split(r"\n\s*\n", lyrics) if b.strip()]


def syllable_count(text: str) -> int:
    return len(syllables.all_syllables(syllables.parse_lyrics(text)))


def verses_for(lyrics: str, n_notes: int) -> list[str]:
    """One pass through the melody when the words fit it; otherwise each block is a verse."""
    blocks = verse_blocks(lyrics)
    if len(blocks) < 2 or syllable_count(lyrics) <= n_notes * (1 + fitting.SPLIT_LIMIT):
        return [lyrics]
    for i, block in enumerate(blocks, start=1):
        n = syllable_count(block)
        if n < MIN_VERSE_SHARE * n_notes:
            raise WriteError(
                f"The melody has {n_notes} notes. The words have {syllable_count(lyrics)} syllables, too many "
                f"to sing once through it, and block {i} has only {n}, too few to be a verse of its own. "
                "Separate verses with a blank line, and keep each verse's lines together.")
    return blocks


def refit(path: Path, lyrics: str) -> Path:
    """Replace the lyrics on `path`'s melody, re-fit, and write the song file back."""
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise WriteError(f"Couldn't read {path.name}: {e}") from e
    if not isinstance(data, dict) or data.get("format", FORMAT) != FORMAT:
        raise WriteError(f"{path.name} isn't a Copyist song file.")
    if not data.get("melody"):
        raise WriteError(f"{path.name} has no melody to fit lyrics to.")
    lyrics = lyrics.strip()
    if not lyrics:
        raise WriteError("Paste the new lyrics.")
    if len(lyrics) > 20000:
        raise WriteError("The lyrics are too long (up to 20,000 characters).")

    bars = rewrite.bars_from_melody(data["melody"], data.get("sections"))
    unit = Fraction(str(data.get("unit", "1/4")))
    meter, key = str(data["meter"]), str(data["key"])
    tempo = data.get("tempo", 90)
    style = data.get("style")
    credits = data.get("credits")
    voice = rewrite.voice_of(data)
    ww = dict(data.get("written_with") or {})
    ww["refit"] = True
    verses = verses_for(lyrics, len(fitting.slots(bars, unit, meter)))
    notes = ["Lyrics refitted to the existing melody."
             + (f" {len(verses)} verses, each sung to the whole melody." if len(verses) > 1 else "")]

    def which(i: int) -> str:
        return f"Verse {i + 1}: " if len(verses) > 1 else ""

    # The longest verse goes first: it may split a long note in two for an extra syllable, and the
    # others are then fitted to that same melody, holding notes where they have fewer syllables.
    order = sorted(range(len(verses)), key=lambda i: -syllable_count(verses[i]))
    try:
        cand = write.song_from_bars(
            bars, unit=unit, meter=meter, key=key, tempo=tempo, lyrics=verses[order[0]],
            title=str(data["title"]), voice=voice, style=style, written_with=ww,
            credits=credits, notes=notes)
    except (WriteError, ValueError) as e:
        raise WriteError(which(order[0]) + str(e)) from e
    if len(verses) > 1:
        fitted = {order[0]: cand.data["lyrics"][0]}
        sung = rewrite.bars_from_melody(cand.data["melody"], cand.data.get("sections"))
        for i in order[1:]:
            sylls = syllables.all_syllables(syllables.parse_lyrics(verses[i]))
            if not sylls:
                raise WriteError(which(i) + "no words to sing.")
            try:
                fitted[i] = fitting.fit(sung, unit, meter, sylls).lyrics
            except ValueError as e:
                raise WriteError(which(i) + str(e)) from e
        cand.data["lyrics"] = [fitted[i] for i in range(len(verses))]

    # Keep fields write doesn't know about.
    out = cand.data
    if data.get("instruments") is not None:
        out["instruments"] = data["instruments"]
    if data.get("pronunciations"):
        out["pronunciations"] = data["pronunciations"]
    if data.get("production"):
        out["production"] = data["production"]
    # Prefer the song's written voice name/clef/range when present.
    if isinstance(data.get("voice"), dict):
        out["voice"] = {**out.get("voice", {}), **{k: v for k, v in data["voice"].items()
                                                    if k in ("name", "clef", "range") and v}}
    path.write_text(write.song_yaml(out), encoding="utf-8")
    return path


def plain_for_edit(verses: list[str]) -> str:
    """Hyphenated song verses → plain lines for a textarea (verses separated by a blank line).

    A word keeps its hyphens when Copyist would count its syllables differently by itself
    ("the-o-rem", which the dictionary sings as two) or doesn't know it ("Ma-jor-Ge-ne-ral"), so
    syllables someone typed survive the next edit. Where only the printed split differs
    ("moth-er" for "mo-ther"), the plain word is shown."""
    def word(token: str) -> str:
        joined = token.replace("-", "")
        if "-" not in token or not re.search(r"[A-Za-z]", joined):
            return joined
        typed = len(syllables.TYPED_HYPHEN.split(token))
        own = len(syllables.syllabify_word(joined))
        known = syllables.dictionary_stresses(joined) is not None
        return joined if known and typed == own else token

    def plain(t: str) -> list[str]:
        out = []
        for line in str(t).strip().split("\n"):
            s = line.replace("*", "").replace("_", "")
            s = re.sub(r"-\s+", "-", s)          # "al-_ read-y" -> "al-read-y"
            s = " ".join(word(w) for w in s.split())
            if s:
                out.append(s)
        return out

    blocks = ["\n".join(plain(v)) for v in verses if str(v).strip()]
    return "\n\n".join(blocks)
