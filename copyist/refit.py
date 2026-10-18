"""Refit lyrics under an existing melody (`copyist refit`, docs/melody-writing.md).

The notes and chords stay; the words are placed again with the same fitter `copyist write`
uses. Note splits are allowed when there are more syllables than notes, so the melody may
gain a repeated pitch. The song file is rewritten in place.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import yaml

from . import abcplan, rewrite, write
from .song import FORMAT, SongError
from .write import WriteError


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
    notes = ["Lyrics refitted to the existing melody."]
    try:
        cand = write.song_from_bars(
            bars, unit=unit, meter=meter, key=key, tempo=tempo, lyrics=lyrics,
            title=str(data["title"]), voice=voice, style=style, written_with=ww,
            credits=credits, notes=notes)
    except WriteError:
        raise
    except ValueError as e:
        raise WriteError(str(e)) from e

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
    """Hyphenated song verses → plain lines for a textarea (verses separated by a blank line)."""
    import re

    def plain(t: str) -> list[str]:
        lines = str(t).strip().split("\n")
        out = []
        for line in lines:
            s = re.sub(r"\*", "", line)
            s = re.sub(r"_", "", s)
            s = re.sub(r"-\s*", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            if s:
                out.append(s)
        return out

    blocks = ["\n".join(plain(v)) for v in verses if str(v).strip()]
    return "\n\n".join(blocks)
