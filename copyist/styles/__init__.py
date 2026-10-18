"""Styles as data (SPEC section 8.2, docs/styles.md).

Each style is one YAML file in this folder (format `copyist-style/0`): its
name and family, its feel (straight, swing or shuffle), which instrument plays
each part, the words YuE2 gets for a finished take, and, for every meter it
supports, what each part plays in one bar. Adding a style means writing a file;
the arranger (arrange.py, drums.py) reads these patterns, and the tests check
every file.

A pattern is a list of [start, length, what] within one full bar, in quarter
notes. A part can also list several bars; those cycle as a phrase (bar 1 of
the song plays the first, bar 2 the second, then it repeats). What a part can
play:

- piano right hand (`rh`): `chord` (a close voicing that moves as little as
  possible), `shell` (the 3rd and 7th, or 6th: jazz comping), `arp1`…`arp4`
  (one note of the voicing, lowest first: broken chords and arpeggios);
- guitar (`guitar`): one treble staff of shapes and picks — `chord` / `strum`
  (a guitar-range shape), `arp1`…`arp4`, plus the bass tones (`root`, `fifth`,
  …) for thumb notes in a fingerpicking pattern;
- piano left hand (`lh`) and bass (`bass`): `root`, `third`, `fifth`, `sixth`,
  `seventh` (the chord's 7th, or the minor 7th), `octave` (the root an octave
  up), `approach` (a half step into the next chord's root);
- the bass can instead be `walk` (a walking line, a note a beat), a `line`
  (chord tones climbing from the root, e.g. `{line: [root, third, fifth,
  sixth, seventh, sixth, fifth, third], every: 0.5}` for a boogie), or `none`;
- drums: `hands`, `feet` and `fill`, each a list of [start, length, [pieces]],
  with pieces from drums.KIT; or `none` for a style without drums. Drums can
  also cycle a list of those groove maps.

Starts and lengths can be fractions written as strings ("1/3") for triplets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import yaml

FOLDER = Path(__file__).parent
FORMAT = "copyist-style/0"
FEELS = {"straight": 0.5, "swing": 2 / 3, "shuffle": 2 / 3}
RH_TONES = {"chord", "shell", "arp1", "arp2", "arp3", "arp4"}
BASS_TONES = {"root", "third", "fifth", "sixth", "seventh", "octave", "approach"}
GUITAR_TONES = RH_TONES | BASS_TONES | {"strum"} - {"shell"}  # shapes and picks, not jazz shells
LINE_TONES = {"root", "third", "fifth", "sixth", "seventh", "octave"}
PARTS = ("melody", "piano", "guitar", "bass", "drums")
DEFAULT_FOR_METER = {"3/4": "waltz", "4/4": "ballad", "6/8": "lullaby"}
FAMILIES = ["Pop and rock", "Country and folk", "Musical theatre", "Jazz and blues", "Soul and gospel",
            "Latin and Caribbean", "Hymns and classical", "Children's", "Electronic"]


class StyleError(ValueError):
    """A style file that doesn't follow copyist-style/0."""


@dataclass(frozen=True)
class Style:
    id: str
    name: str
    family: str
    about: str
    feel: str
    swing: float                       # where an off-beat eighth falls, as a share of the beat (0.5 = straight)
    tempo: tuple[int, int]
    instruments: dict[str, str]        # part -> instrument id (copyist/instruments.py)
    production: str                    # words for YuE2's style line
    keep_rh: bool = False              # piano-vocal: keep the right-hand figure (open melody pitches)
    meters: dict[str, dict] = field(default_factory=dict, repr=False)

    def pattern(self, meter: str) -> dict | None:
        return self.meters.get(meter)

    def has_drums(self, meter: str) -> bool:
        p = self.meters.get(meter)
        return bool(p) and p.get("drums") != "none"


def is_cycle(pattern) -> bool:
    """True when a part lists several bars that cycle as a phrase."""
    return bool(pattern) and isinstance(pattern[0], list)


def bar_of(pattern, n_in_song: int):
    """The one-bar pattern for full-bar number `n_in_song` (1 = first full bar)."""
    if not pattern:
        return []
    if is_cycle(pattern):
        return pattern[(max(n_in_song, 1) - 1) % len(pattern)]
    return pattern


def bar_quarters(meter: str) -> Fraction:
    num, den = (int(x) for x in meter.split("/"))
    return Fraction(4 * num, den)


def _span(entry, where: str, full: Fraction) -> tuple[float, float]:
    if not (isinstance(entry, list) and len(entry) == 3):
        raise StyleError(f"{where}: each entry is [start, length, what], got {entry!r}")
    start, length = Fraction(str(entry[0])), Fraction(str(entry[1]))
    if start < 0 or length <= 0 or start + length > full:
        raise StyleError(f"{where}: [{entry[0]}, {entry[1]}] doesn't fit in a bar of {float(full)} quarters")
    return float(start), float(length)


def _tones(entries, allowed: set[str], where: str, full: Fraction) -> list[tuple[float, float, str]]:
    out = []
    for e in entries or []:
        s, d = _span(e, where, full)
        if e[2] not in allowed:
            raise StyleError(f"{where}: {e[2]!r} isn't something this part can play ({', '.join(sorted(allowed))})")
        out.append((s, d, str(e[2])))
    return out


def _is_phrase_cycle(entries) -> bool:
    """A list of bars (each a list of [start, length, what]), not one bar's entries."""
    if not entries or not isinstance(entries[0], list):
        return False
    if not entries[0]:
        return len(entries) > 1
    return isinstance(entries[0][0], list)


def _tones_field(entries, allowed: set[str], where: str, full: Fraction):
    """One bar's tones, or a list of bars that cycle."""
    if _is_phrase_cycle(entries):
        return [_tones(bar, allowed, f"{where}[{i}]", full) for i, bar in enumerate(entries)]
    return _tones(entries, allowed, where, full)


def _hits(entries, where: str, full: Fraction, kit) -> list[tuple[float, float, list[str]]]:
    out = []
    for e in entries or []:
        s, d = _span(e, where, full)
        pieces = e[2] if isinstance(e[2], list) else [e[2]]
        unknown = [p for p in pieces if p not in kit]
        if unknown:
            raise StyleError(f"{where}: no drum called {', '.join(unknown)} (the kit has {', '.join(kit)})")
        out.append((s, d, [str(p) for p in pieces]))
    return out


def _drums_groove(kit: dict, where: str, full: Fraction, drum_kit) -> dict:
    groove = {k: _hits(kit.get(k), f"{where} drums {k}", full, drum_kit)
              for k in ("hands", "feet", "fill")}
    if not groove["fill"]:
        raise StyleError(f"{where}: drums need a fill (or `drums: none`)")
    return groove


def parse(data: dict, style_id: str) -> Style:
    from .. import drums, instruments
    if data.get("format") != FORMAT:
        raise StyleError(f"{style_id}: format should be {FORMAT}")
    for key in ("name", "family", "about", "production", "meters"):
        if not data.get(key):
            raise StyleError(f"{style_id}: {key} is missing")
    if data["family"] not in FAMILIES:
        raise StyleError(f"{style_id}: family {data['family']!r} isn't one of {', '.join(FAMILIES)}")
    feel = data.get("feel", "straight")
    if feel not in FEELS:
        raise StyleError(f"{style_id}: feel should be one of {', '.join(FEELS)}")
    swing = float(data.get("swing", FEELS[feel]))
    if not 0.5 <= swing < 0.8:
        raise StyleError(f"{style_id}: swing should be from 0.5 (straight) to under 0.8")
    tempo = tuple(int(x) for x in data.get("tempo", [60, 160]))
    chosen = {str(k): str(v) for k, v in (data.get("instruments") or {}).items()}
    for part, inst in chosen.items():
        if part not in PARTS or inst not in instruments.CATALOG:
            raise StyleError(f"{style_id}: instruments: {part}: {inst} isn't a known part and instrument")
    keep_rh = bool(data.get("keep_rh", False))
    if keep_rh and chosen.get("melody") != "piano":
        raise StyleError(f"{style_id}: keep_rh only makes sense when instruments.melody is piano")
    meters = {}
    for meter, parts in data["meters"].items():
        where = f"{style_id} {meter}"
        try:
            full = bar_quarters(str(meter))
        except ValueError:
            raise StyleError(f"{where}: {meter!r} isn't a meter like 4/4") from None
        p: dict = {"rh": _tones_field(parts.get("rh"), RH_TONES, f"{where} rh", full),
                   "lh": _tones_field(parts.get("lh"), BASS_TONES, f"{where} lh", full),
                   "guitar": _tones_field(parts.get("guitar"), GUITAR_TONES, f"{where} guitar", full)}
        bass = parts.get("bass")
        if bass in ("walk", "none"):
            p["bass"] = bass
        elif isinstance(bass, dict):
            line, every = bass.get("line") or [], Fraction(str(bass.get("every", "1/2")))
            if not line or any(x not in LINE_TONES for x in line) or every <= 0 or full % every:
                raise StyleError(f"{where} bass: a line is chord tones ({', '.join(sorted(LINE_TONES))}) "
                                 f"and `every`, a step that divides the bar")
            p["bass"] = {"line": [str(x) for x in line], "every": float(every)}
        else:
            p["bass"] = _tones_field(bass, BASS_TONES, f"{where} bass", full)
        kit = parts.get("drums")
        if kit == "none":
            p["drums"] = "none"
        elif kit is None:
            p["drums"] = None              # a plain beat-by-beat groove
        elif isinstance(kit, list):
            if not kit:
                raise StyleError(f"{where}: drums phrase is empty")
            p["drums"] = [_drums_groove(g, f"{where}[{i}]", full, drums.KIT) for i, g in enumerate(kit)]
        else:
            p["drums"] = _drums_groove(kit, where, full, drums.KIT)
        meters[str(meter)] = p
    return Style(style_id, str(data["name"]), str(data["family"]), str(data["about"]).strip(), feel, swing,
                 (tempo[0], tempo[-1]), chosen, " ".join(str(data["production"]).split()), keep_rh, meters)


@lru_cache(maxsize=None)
def catalog() -> dict[str, Style]:
    """Every style in this folder, by id (the file name)."""
    out = {}
    for path in sorted(FOLDER.glob("*.yaml")):
        out[path.stem] = parse(yaml.safe_load(path.read_text(encoding="utf-8")), path.stem)
    return out


def get(style_id: str | None) -> Style | None:
    return catalog().get(style_id) if style_id else None


def for_meter(meter: str) -> list[Style]:
    """The styles that have patterns for this meter, by family then name."""
    order = {f: i for i, f in enumerate(FAMILIES)}
    return sorted((s for s in catalog().values() if meter in s.meters),
                  key=lambda s: (order[s.family], s.name))


def default_for(meter: str) -> str | None:
    return DEFAULT_FOR_METER.get(meter)
