"""Full productions with YuE2: Copyist writes the score, YuE2 performs it
(SPEC.md section 6).

YuE2 plans every song as an ABC score before it makes any sound, and it
accepts a finished score instead. This module writes a Copyist song in
YuE2's own ABC dialect (see the mlx-Yue "abc-editing" reference):

- header X/T/M/L/Q, two voices `Vocal` and `Ins`, then K;
- blocks of up to four bars, `V: Vocal` then `V: Ins`, under `% section` comments;
- chord symbols in the Vocal voice at the onset where they change;
- every bar complete (a pickup is padded with a rest), no repeats, no tuplets;
- durations from {1,2,3,4,6,8,12,16,24,32,48} units, anything else tied;
- accidentals relative to the key, carried by letter across octaves within a bar.

The lyrics go separately, in [Section] blocks, one line per phrase.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from music21 import harmony, note, pitch as m21pitch, stream

from .song import Song, SongError

ALLOWED = (48, 32, 24, 16, 12, 8, 6, 4, 3, 2, 1)

# YuE2 sings one octave below the ABC it is given. Measured on Amazing Grace,
# seed 831001: written D4-D5, it sang D3-D4 (32 of 32 notes, an octave low);
# written an octave up, it sang D4-D5 (30 of 32, in the octave we wanted).
# So the vocal is written this many octaves above where it should sound.
SUNG_OCTAVE_BELOW = 1
STEPS = "CDEFGAB"


@dataclass
class Event:
    start: Fraction          # in quarter notes from the start of the score
    dur: Fraction
    pitch: m21pitch.Pitch | None   # None for a rest


def tune_events(song: Song) -> tuple[list[Event], list[tuple[Fraction, str]], Fraction, Fraction, Fraction]:
    """The melody once through: events, chords, length, pickup length, full-bar length."""
    part = song.melody
    events, chords = [], []
    for el in part.recurse().notesAndRests:
        off = Fraction(el.getOffsetInHierarchy(part)).limit_denominator(96)
        if isinstance(el, harmony.ChordSymbol):
            chords.append((off, el.figure))
            continue
        dur = Fraction(el.quarterLength).limit_denominator(96)
        if isinstance(el, note.Note):
            if el.tie is not None and el.tie.type in ("stop", "continue") and events and events[-1].pitch is not None:
                events[-1].dur += dur
                continue
            events.append(Event(off, dur, el.pitch))
        else:
            events.append(Event(off, dur, None))
    bars = list(part.getElementsByClass(stream.Measure))
    full = Fraction(bars[0].barDuration.quarterLength).limit_denominator(96)
    first = sum((e.dur for e in events if e.start < Fraction(bars[1].getOffsetInHierarchy(part)).limit_denominator(96)),
                Fraction(0)) if len(bars) > 1 else full
    pickup = first if first < full else Fraction(0)
    length = max(e.start + e.dur for e in events)
    return events, chords, length, pickup, full


def unit_for(events: list[Event]) -> int:
    """The ABC unit denominator (16 means L:1/16) that makes every length a whole number."""
    for den in (16, 32, 64):
        q = Fraction(4, den)   # one unit in quarter notes
        if all((e.dur / q).denominator == 1 and (e.start / q).denominator == 1 for e in events):
            return den
    raise SongError("This melody has rhythms (tuplets?) YuE2's score format can't write yet.")


def split_lengths(units: int) -> list[int]:
    out = []
    while units > 0:
        piece = next(a for a in ALLOWED if a <= units)
        out.append(piece)
        units -= piece
    return out


def key_alters(song: Song) -> dict[str, int]:
    ks = song.key_object()
    alters = {s: 0 for s in STEPS}
    for p in ks.alteredPitches:
        alters[p.step] = int(p.alter)
    return alters


def abc_pitch(p: m21pitch.Pitch, state: dict[str, int]) -> str:
    alter = int(p.alter) if p.accidental is not None else 0
    acc = ""
    if state.get(p.step) != alter:
        acc = {-2: "__", -1: "_", 0: "=", 1: "^", 2: "^^"}[alter]
        state[p.step] = alter
    octave = p.octave if p.octave is not None else 4
    letter = p.step if octave <= 4 else p.step.lower()
    if octave >= 6:
        letter += "'" * (octave - 5)
    elif octave <= 3:
        letter += "," * (4 - octave)
    return acc + letter


def bar_text(events: list[Event], chords: list[tuple[Fraction, str]], bar_start: Fraction, full: Fraction,
             q: Fraction, base_alters: dict[str, int], with_chords: bool) -> str:
    """One bar of one voice in YuE2's ABC."""
    bar_end = bar_start + full
    cuts = {bar_start, bar_end}
    if with_chords:
        cuts |= {t for t, _ in chords if bar_start <= t < bar_end}
    for e in events:
        for t in (e.start, e.start + e.dur):
            if bar_start < t < bar_end:
                cuts.add(t)
    cuts = sorted(cuts)
    chord_at = {t: name for t, name in chords} if with_chords else {}
    state = dict(base_alters)
    out = []
    for a, b in zip(cuts, cuts[1:]):
        ev = next((e for e in events if e.start <= a < e.start + e.dur), None)
        units = int((b - a) / q)
        prefix = f'"{chord_at[a]}"' if a in chord_at else ""
        if ev is None or ev.pitch is None:
            out.append(prefix + "".join(f"z{n if n > 1 else ''}" for n in split_lengths(units)))
        else:
            name = abc_pitch(ev.pitch, state)
            bare = name.lstrip("^_=")
            pieces = split_lengths(units)
            notes = [(name if i == 0 else bare) + (str(n) if n > 1 else "") for i, n in enumerate(pieces)]
            tied_on = b < ev.start + ev.dur
            out.append(prefix + "-".join(notes) + ("-" if tied_on else ""))
    return "".join(out)


def score_abc(song: Song, verses: int, intro_bars: int = 4,
              octave: int = SUNG_OCTAVE_BELOW) -> tuple[str, list[str]]:
    """YuE2 ABC for the song sung `verses` times, after an instrumental intro.

    Bar lines fall on whole bars: a pickup is padded with a rest before the
    first verse, each later verse's pickup shares a bar with the previous
    verse's last bar, and the final bar is padded at the end. The intro has the
    chords of the tune's first full bars and no melody, so YuE2 plays an
    introduction over them. The melody is written `octave` octaves above
    where it should sound (see SUNG_OCTAVE_BELOW). Returns the ABC and each block's section label.
    """
    events, chords, _, pickup, full = tune_events(song)
    q = Fraction(4, unit_for(events))
    lead, period, full = _placed(song, intro_bars)
    all_events: list[Event] = []
    all_chords: list[tuple[Fraction, str]] = []
    for k in range(verses):
        base = lead + k * period
        all_events += [Event(base + e.start, e.dur, e.pitch.transpose(12 * octave) if e.pitch is not None else None)
                       for e in events]
        all_chords += [(base + t, name) for t, name in chords]

    def chord_in_effect(t: Fraction) -> str | None:
        current = None
        for off, name in chords:
            if off <= t:
                current = name
        return current

    intro_chords = []
    for b in range(intro_bars):
        tune_t = pickup + b * full            # the tune's full bar b+1
        changes = [(t - tune_t, n) for t, n in chords if tune_t <= t < tune_t + full]
        if not any(dt == 0 for dt, _ in changes):
            name = chord_in_effect(tune_t)
            if name:
                changes.insert(0, (Fraction(0), name))
        intro_chords += [(b * full + dt, n) for dt, n in changes]
    all_chords = intro_chords + all_chords

    end = max(e.start + e.dur for e in all_events)
    n_bars = int(-(-end // full))
    bars_per_verse = int(period // full)

    def section_of(bar: int) -> tuple[str, int | None]:
        if bar < intro_bars:
            return ("intro", None)
        return ("verse", min((bar - intro_bars) // bars_per_verse, verses - 1))

    alters = key_alters(song)
    blocks, labels = [], []
    bar = 0
    previous = None
    while bar < n_bars:
        sec = section_of(bar)
        group = []
        while bar < n_bars and len(group) < 4 and section_of(bar) == sec:
            group.append(bar)
            bar += 1
        if sec != previous:
            blocks.append(f"% {sec[0]}")
            previous = sec
        labels.append(sec[0])
        voc = "|".join(bar_text(all_events, all_chords, b * full, full, q, alters, True) for b in group) + "|"
        blocks += ["V: Vocal", voc, "V: Ins", f"Z{len(group) if len(group) > 1 else ''}|"]
    mm = song.melody.recurse().getElementsByClass("MetronomeMark").first()
    bpm = round(mm.getQuarterBPM()) if mm is not None else 90
    header = ["X:1", "T:", f"M:{song.meter}", f"L:1/{int(Fraction(4) / q)}", f"Q:1/4={bpm}",
              'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
              'V: Ins clef=treble name="Ins Melody" snm="Inst."',
              f"K:{song.key}"]
    return "\n".join(header + blocks) + "\n", labels


def lyrics_text(song: Song, verses: int, intro: bool = True) -> str:
    """YuE2 lyrics: [Intro] then one [Verse] per verse, one line per phrase."""
    from .sing import ONSET, soulx_segments, sung_notes
    parts = ["[Intro]", ""] if intro else []
    for v in range(1, verses + 1):
        notes = sung_notes(song, v)
        lines = []
        for seg in soulx_segments(notes):
            texts, types = seg["text"].split(), seg["note_type"].split()
            words = [t for t, ty in zip(texts, types) if int(ty) == ONSET]
            lines.append(" ".join(words))
        parts += ["[Verse]"] + lines + [""]
    return "\n".join(parts).strip() + "\n"


def default_style(song: Song) -> str:
    bpm = round(song.melody.recurse().getElementsByClass("MetronomeMark").first().getQuarterBPM())
    feel = {"waltz": "gentle 3/4 waltz", "ballad": "slow ballad", "straight": "steady groove"}.get(song.style or "", "")
    return f"English, {feel + ', ' if feel else ''}warm expressive female vocal, acoustic piano, soft strings, " \
           f"warm bass, light brushed drums, intimate and heartfelt, {bpm} BPM"


def _placed(song: Song, intro_bars: int) -> tuple[Fraction, Fraction, Fraction]:
    """Where verse 1 starts, how long one verse is, and one bar, in quarter notes.

    Same placement as `score_abc`: the intro, then a rest that fills the pickup
    out to a bar, then the tune.
    """
    _, _, length, pickup, full = tune_events(song)
    if pickup and (length % full) != 0:
        raise SongError("The pickup and the last bar should add up to one full bar, so that verses can "
                        "follow each other; fix the melody first.")
    period = length if pickup else (-(-length // full)) * full
    pad = (full - pickup) if pickup else Fraction(0)
    lead = intro_bars * full + pad
    return lead, period, full


def vocal_offset(song: Song, intro_bars: int = 4) -> float:
    """Seconds from the start of a render to verse 1's first note."""
    from .sing import seconds_per_quarter
    lead, _, _ = _placed(song, intro_bars)
    return float(lead) * seconds_per_quarter(song)


def verse_offset(song: Song, verse: int = 1, intro_bars: int = 4) -> float:
    """Seconds from the start of a render to the first note of `verse` (1-based)."""
    from .sing import seconds_per_quarter
    lead, period, _ = _placed(song, intro_bars)
    return float(lead + (verse - 1) * period) * seconds_per_quarter(song)


def score_seconds(song: Song, verses: int, intro_bars: int = 4) -> float:
    """Length of the written score, in seconds, including the padded final bar."""
    from .sing import seconds_per_quarter
    lead, period, full = _placed(song, intro_bars)
    end = lead + verses * period
    n_bars = int(-(-end // full))
    return float(n_bars * full) * seconds_per_quarter(song)


def request(song: Song, verses: int | None = None, style: str | None = None, seed: int = 831001,
            intro_bars: int = 4, octave: int = SUNG_OCTAVE_BELOW) -> dict:
    verses = verses or len(song.verses)
    abc, _ = score_abc(song, verses, intro_bars, octave)
    # yue2.cpp draws the score's performance from `lm_seed` and the noise from
    # `seed`. One seed drives both, so the same request renders the same song.
    # `duration` is the score's length; the default (360 s) would ask for a
    # song much longer than the one we wrote.
    return {"style": style or song_production_style(song) or default_style(song),
            "lyrics": lyrics_text(song, verses, intro=intro_bars > 0),
            "cot": "full", "abc": abc,
            "lm_seed": seed, "seed": seed,
            "duration": score_seconds(song, verses, intro_bars)}


def lora_adapters(specs: list[str]) -> tuple[list[dict], str]:
    """`path/to/name.safetensors[:scale]` for each LoRA -> (request adapters, the folder for --adapters).

    yue-synth reads adapters from one folder, so every LoRA given must sit in the same one.
    """
    adapters, folders = [], set()
    for spec in specs:
        path, _, scale = spec.rpartition(":") if ":" in spec and spec.rsplit(":", 1)[1].replace(".", "", 1).isdigit() \
            else (spec, "", "")
        p = Path(path)
        if not p.is_file():
            raise SongError(f"No LoRA at {p}.")
        adapters.append({"name": p.name, "scale": float(scale) if scale else 1.0})
        folders.add(str(p.resolve().parent))
    if len(folders) > 1:
        raise SongError("Put every LoRA for one render in the same folder (yue-synth reads one adapters folder).")
    return adapters, folders.pop()


def song_production_style(song: Song) -> str | None:
    return getattr(song, "production", None)


# ---------------------------------------------------------------- running YuE2

def run_yue2cpp(req: dict, out_dir: Path, binary: str | None = None, model: str | None = None,
                vae: str | None = None, device: str | None = None, extra: list[str] | None = None) -> Path:
    """Render a request with yue2.cpp (`yue-synth`).

    Paths come from the arguments, then the COPYIST_YUE_* variables, then the
    desktop app's programs and downloaded models, then the developer copies in
    .cache/ (copyist/paths.py).
    """
    from . import models, paths
    binary = binary or (str(p) if (p := paths.find_program("yue-synth", "COPYIST_YUE_SYNTH")) else None)
    model = model or (str(p) if (p := models.path_of("yue2")) else None)
    vae = vae or (str(p) if (p := models.path_of("yue2-vae")) else None)
    device = device or os.environ.get("COPYIST_YUE_DEVICE")
    if not binary:
        raise SongError("YuE2's renderer (yue-synth) isn't installed here: run scripts/setup-yue.sh, or set "
                        "COPYIST_YUE_SYNTH (see docs/production.md).")
    if not (model and vae):
        raise SongError("The singer isn't downloaded yet: run `copyist models download singer` (or use the page), "
                        "or set COPYIST_YUE_MODEL and COPYIST_YUE_VAE (see docs/production.md).")
    out_dir.mkdir(parents=True, exist_ok=True)
    req_path = out_dir / "yue-request.json"
    req_path.write_text(json.dumps(req, ensure_ascii=False, indent=1), encoding="utf-8")
    ext = ".wav" if str(req.get("output_format", "")).startswith("wav") else ".mp3"
    audio = out_dir / f"production{ext}"
    cmd = [binary, "--model", model, "--vae", vae, "--request", str(req_path), "--out", str(audio)]
    if device:
        cmd += ["--device", device]
    cmd += extra or []
    where = f" on {device}" if device else ""
    print(f"Rendering with YuE2 (yue2.cpp){where}...", file=sys.stderr)
    try:
        r = subprocess.run(cmd)
    except FileNotFoundError:
        raise SongError(f"Can't run {binary}. See docs/production.md.") from None
    if r.returncode != 0:
        raise RuntimeError(f"yue-synth failed (exit {r.returncode}).")
    if not audio.is_file():
        raise RuntimeError(f"yue-synth finished without writing {audio.name}.")
    return audio
