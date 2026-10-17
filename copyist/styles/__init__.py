"""Styles as data (SPEC section 8.2, docs/styles.md).

Each style is one YAML file in this folder (format `copyist-style/0`): its
name and family, its feel (straight, swing or shuffle), which instrument plays
each part, the words YuE2 gets for a finished take, and, for every meter it
supports, what each part plays in one bar. Adding a style means writing a file;
the arranger (arrange.py, drums.py) reads these patterns, and the tests check
every file.

A pattern is a list of [start, length, what] within one full bar, in quarter
notes. What a part can play:

- piano right hand (`rh`): `chord` (a close voicing that moves as little as
  possible), `shell` (the 3rd and 7th, or 6th: jazz comping), `arp1`…`arp4`
  (one note of the voicing, lowest first: broken chords and arpeggios);
- piano left hand (`lh`) and bass (`bass`): `root`, `third`, `fifth`, `sixth`,
  `seventh` (the chord's 7th, or the minor 7th), `octave` (the root an octave
  up), `approach` (a half step into the next chord's root);
- the bass can instead be `walk` (a walking line, a note a beat), a `line`
  (chord tones climbing from the root, e.g. `{line: [root, third, fifth,
  sixth, seventh, sixth, fifth, third], every: 0.5}` for a boogie), or `none`;
- drums: `hands`, `feet` and `fill`, each a list of [start, length, [pieces]],
  with pieces from drums.KIT; or `none` for a style without drums.

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
LINE_TONES = {"root", "third", "fifth", "sixth", "seventh", "octave"}
PARTS = ("melody", "piano", "bass", "drums")
DEFAULT_FOR_METER = {"3/4": "waltz", "4/4": "ballad", "6/8": "lullaby", "12/8": "gospel"}
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
    meters: dict[str, dict] = field(repr=False)

    def pattern(self, meter: str) -> dict | None:
        return self.meters.get(meter)

    def has_drums(self, meter: str) -> bool:
        p = self.meters.get(meter)
        return bool(p) and p.get("drums") != "none"


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
    meters = {}
    for meter, parts in data["meters"].items():
        where = f"{style_id} {meter}"
        try:
            full = bar_quarters(str(meter))
        except ValueError:
            raise StyleError(f"{where}: {meter!r} isn't a meter like 4/4") from None
        p: dict = {"rh": _tones(parts.get("rh"), RH_TONES, f"{where} rh", full),
                   "lh": _tones(parts.get("lh"), BASS_TONES, f"{where} lh", full)}
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
            p["bass"] = _tones(bass, BASS_TONES, f"{where} bass", full)
        kit = parts.get("drums")
        if kit == "none":
            p["drums"] = "none"
        elif kit is None:
            p["drums"] = None              # a plain beat-by-beat groove
        else:
            p["drums"] = {k: _hits(kit.get(k), f"{where} drums {k}", full, drums.KIT)
                          for k in ("hands", "feet", "fill")}
            if not p["drums"]["fill"]:
                raise StyleError(f"{where}: drums need a fill (or `drums: none`)")
        meters[str(meter)] = p
    return Style(style_id, str(data["name"]), str(data["family"]), str(data["about"]).strip(), feel, swing,
                 (tempo[0], tempo[-1]), chosen, " ".join(str(data["production"]).split()), meters)


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
