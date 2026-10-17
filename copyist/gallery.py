"""The style gallery: one song played in every style that fits its meter (docs/styles.md).

Choosing a style should take listening, not reading. `copyist gallery SONG`
arranges the song in each style, performs it, and plays it on the band, at a
tempo inside the style's usual range (a pop take of a hymn at hymn tempo would
be misleading). `copyist gallery SONG --takes` makes a finished YuE2 take in
each style instead: the singer and the whole band, the style's own instruments
included. Everything lands in out/<song>/gallery/: one WAV per style, the takes
in takes/<style>/, and gallery.json, which the page reads.
"""
from __future__ import annotations

import dataclasses
import json
import tempfile
from pathlib import Path
from typing import Callable

import mido
from music21 import meter as m21meter

from . import arrange, engrave, perform, render, styles
from .song import Song

INDEX = "gallery.json"


def beat_bpm(song: Song) -> float:
    """The song's tempo in its own beats (dotted quarters in 6/8)."""
    mm = song.melody.recurse().getElementsByClass("MetronomeMark").first()
    beat = float(m21meter.TimeSignature(song.meter).beatDuration.quarterLength)
    return float(mm.getQuarterBPM()) / beat


def tempo_for(song: Song, style: styles.Style) -> float:
    low, high = style.tempo
    return min(max(beat_bpm(song), low), high)


def retempo(midi: Path, factor: float) -> None:
    """Play a MIDI file `factor` times as fast (every tempo event scaled)."""
    if abs(factor - 1) < 1e-6:
        return
    mid = mido.MidiFile(str(midi))
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                msg.tempo = max(1, round(msg.tempo / factor))
    mid.save(str(midi))


def build(song: Song, out_root: Path, cache: Path = Path(".cache"), seed: int = 1, only: list[str] | None = None,
          progress: Callable[[int, int, str], None] | None = None) -> list[dict]:
    """Play `song` in every style for its meter (or just `only`); returns the gallery's entries."""
    folder = out_root / song.slug / "gallery"
    folder.mkdir(parents=True, exist_ok=True)
    chosen = [s for s in styles.for_meter(song.meter) if not only or s.id in only]
    pickup = float(perform.pickup_of(song))
    entries = []
    for k, style in enumerate(chosen):
        if progress:
            progress(k, len(chosen), style.name)
        band = arrange.arrange_band(dataclasses.replace(song, style=style.id))
        bpm = tempo_for(song, style)
        with tempfile.TemporaryDirectory(prefix="copyist-gallery-") as tmp:
            midi = engrave.write_midi(band.performance(), Path(tmp) / f"{style.id}.mid")
            retempo(midi, bpm / beat_bpm(song))
            perform.perform(midi, midi, song.meter, pickup, seed=seed, swing=style.swing)
            audio = render.render_band(midi, folder / f"{style.id}.wav", style.id, cache)
        entries.append({"style": style.id, "name": style.name, "family": style.family, "about": style.about,
                        "feel": style.feel, "tempo": round(bpm), "file": f"{style.id}.wav",
                        "engine": audio.engine, "parts": sorted(band.parts), "notes": band.notes})
    if progress:
        progress(len(chosen), len(chosen), "")
    index = {e["style"]: e for e in read(folder)}
    for e in entries:
        index.setdefault(e["style"], {}).update(e)
    write(folder, song, list(index.values()))
    return entries


def build_takes(song_path: Path, out_root: Path, seed: int = 831001, verses: int = 1, only: list[str] | None = None,
                lora: list[str] | None = None, prefix: str = "", device: str | None = None,
                progress: Callable[[int, int, str], None] | None = None) -> list[dict]:
    """A finished YuE2 take of the song in every style for its meter (or just `only`): the singer
    and the band together, each style at a tempo inside its range, with the style's own words.

    Each take lands in out/<song>/gallery/takes/<style>/; gallery.json gets its path.
    """
    import shutil
    from . import yue
    from .song import load_song, set_style
    song = load_song(song_path)
    folder = out_root / song.slug / "gallery"
    chosen = [s for s in styles.for_meter(song.meter) if not only or s.id in only]
    made = []
    for k, style in enumerate(chosen):
        if progress:
            progress(k, len(chosen), style.name)
        with tempfile.TemporaryDirectory(prefix="copyist-take-") as tmp:
            copy = Path(tmp) / song_path.name                   # same name, so the same song
            shutil.copy(song_path, copy)
            set_style(copy, style.id, tempo_for(song, style))
            styled = load_song(copy)
        req = yue.request(styled, verses=verses, seed=seed)
        if prefix:
            req["style"] = f"{prefix.strip().rstrip(',.')}. {req['style']}"
        req["output_format"] = "wav16"
        extra = []
        if lora:
            req["adapters"], adapters = yue.lora_adapters(lora)
            extra = ["--adapters", adapters]
        audio = yue.run_yue2cpp(req, folder / "takes" / style.id, device=device, extra=extra)
        entry = {"style": style.id, "take": audio.relative_to(folder).as_posix(), "take_style": req["style"],
                 "take_seed": seed}
        made.append(entry)
        index = {e["style"]: e for e in read(folder)}         # written after every take, so a stop keeps them
        index.setdefault(style.id, {"style": style.id, "name": style.name, "family": style.family,
                                    "about": style.about, "feel": style.feel,
                                    "tempo": round(tempo_for(song, style))}).update(entry)
        write(folder, song, list(index.values()))
    if progress:
        progress(len(chosen), len(chosen), "")
    return made


def write(folder: Path, song: Song, entries: list[dict]) -> None:
    order = {s.id: i for i, s in enumerate(styles.for_meter(song.meter))}
    keep = [e for e in entries if (folder / e.get("file", "-")).is_file() or (folder / e.get("take", "-")).is_file()]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / INDEX).write_text(json.dumps({"song": song.slug, "meter": song.meter,
                                            "styles": sorted(keep, key=lambda e: order.get(e["style"], 999))},
                                           indent=1) + "\n", encoding="utf-8")


def read(folder: Path) -> list[dict]:
    try:
        return json.loads((folder / INDEX).read_text(encoding="utf-8"))["styles"]
    except (OSError, ValueError, KeyError):
        return []
