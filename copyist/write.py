"""Melody writing (`copyist write`, docs/melody-writing.md): lyrics and a style in, several finished
songs out, to choose between by ear.

YuE2's planner (`yue-plan`) writes each candidate as an ABC score. This module turns a score into a
Copyist song file: the vocal line in the singer's range, the lyrics fitted under the notes
(copyist/fit.py), sections and provenance recorded. Then it checks, ranks and previews them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

import yaml
from music21 import pitch as m21pitch

from . import abcplan, fit as fitting, syllables
from .song import FORMAT

# name: (low, high, clef, words for the planner's style line)
VOICES = {
    "soprano": ("C4", "A5", "treble", "warm female soprano vocal"),
    "alto": ("G3", "E5", "treble", "warm female alto vocal"),
    "tenor": ("C3", "A4", "treble-8vb", "warm male tenor vocal"),
    "baritone": ("A2", "F4", "bass", "warm male baritone vocal"),
}
DEFAULT_VOICE = "alto"


class WriteError(ValueError):
    """A candidate Copyist can't turn into a song file, with the reason for the report."""


@dataclass
class Candidate:
    data: dict                         # the song file, as YAML data
    placement: abcplan.Placement
    fit: fitting.Fit
    syllables: int
    notes: list[str] = field(default_factory=list)    # lines for the report

    @property
    def cost_per_syllable(self) -> float:
        return self.fit.cost / max(1, self.syllables)


def song_from_plan(plan_text: str, lyrics: str, title: str, voice: str = DEFAULT_VOICE,
                   style: str | None = None, written_with: dict | None = None,
                   credits: dict | None = None) -> Candidate:
    """One planner score and the lyrics it was written for -> a Copyist song file (as data)."""
    if voice not in VOICES:
        raise WriteError(f"Unknown voice {voice!r}: choose {', '.join(VOICES)}.")
    low, high, clef, _ = VOICES[voice]
    try:
        plan = abcplan.parse(plan_text)
    except abcplan.PlanError as e:
        raise WriteError(str(e)) from e
    bars = abcplan.trim(plan)
    placement = abcplan.place_in_range(bars, plan.key, m21pitch.Pitch(low).midi, m21pitch.Pitch(high).midi)
    sections = syllables.parse_lyrics(lyrics)
    sylls = syllables.all_syllables(sections)
    if not sylls:
        raise WriteError("The lyrics have no words to sing.")
    try:
        fitted = fitting.fit(bars, plan.unit, plan.meter, sylls)
    except ValueError as e:
        raise WriteError(str(e)) from e
    unit = abcplan.best_unit(bars, plan.unit)
    melody = abcplan.write(bars, plan.unit, unit)

    notes = [f"{placement.key}, {plan.meter}, {abcplan.tempo_field(plan.tempo)} to the quarter note; "
             f"{len(bars)} bars, {placement.notes} sung notes."]
    octaves = (placement.semitones - placement.transposed) // 12
    if placement.transposed:
        notes.append(f"Transposed {placement.transposed:+d} semitones (to {placement.key}) to fit the {voice} range.")
    notes.append(f"Moved {abs(octaves)} octave{'s' if abs(octaves) != 1 else ''} "
                 f"{'down' if octaves < 0 else 'up'} from the plan" if octaves else "Kept the plan's octave.")
    if placement.outside:
        notes.append(f"{placement.outside} note(s) still outside the {voice} range ({low}–{high}).")
    holds = sum(b - a for a, b in fitted.spans)
    notes.append(f"Lyrics: {len(sylls)} syllables on {len(fitted.spans) + holds} notes; {holds} held, "
                 f"{fitted.splits} note(s) split; fit cost {fitted.cost / len(sylls):.2f} a syllable.")

    data = {"format": FORMAT, "title": title}
    if credits:
        data["credits"] = credits
    data.update({
        "key": placement.key,
        "meter": plan.meter,
        "unit": f"{unit.numerator}/{unit.denominator}",
        "tempo": abcplan.tempo_field(plan.tempo),
        "voice": {"name": "Voice", "range": [low, high], "clef": clef},
    })
    if style:
        data["style"] = style
    data["sections"] = abcplan.sections_of(bars)
    if written_with:
        data["written_with"] = written_with
    data["melody"] = melody
    data["lyrics"] = [fitted.lyrics]
    return Candidate(data, placement, fitted, len(sylls), notes)


def song_yaml(data: dict) -> str:
    """The song file as people expect to read it: melody and lyrics as blocks, in the usual order."""
    def scalar(v) -> str:
        return yaml.safe_dump(v, default_flow_style=True, allow_unicode=True, width=10_000).strip().removesuffix("...").strip()

    out = []
    for k, v in data.items():
        if k == "melody":
            out.append("melody: |")
            out += ["  " + line for line in str(v).strip().splitlines()]
        elif k == "lyrics":
            out.append("lyrics:")
            for verse in v:
                out.append("  - |")
                out += ["    " + line for line in str(verse).strip().splitlines()]
        elif k == "sections":
            out.append("sections:")
            out += [f"  - {{name: {scalar(s['name'])}, bar: {s['bar']}}}" for s in v]
        elif isinstance(v, dict):
            out.append(f"{k}:")
            out += [f"  {kk}: {scalar(vv)}" for kk, vv in v.items()]
        else:
            out.append(f"{k}: {scalar(v)}")
    return "\n".join(out) + "\n"


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "song"


def to_quarters(unit: str) -> Fraction:
    return Fraction(unit) * 4
