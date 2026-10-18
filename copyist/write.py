"""Melody writing (`copyist write`, docs/melody-writing.md): lyrics and a style in, several finished
songs out, to choose between by ear.

YuE2's planner (`yue-plan`) writes each candidate as an ABC score. This module turns a score into a
Copyist song file: the vocal line in the singer's range, the lyrics fitted under the notes
(copyist/fit.py), sections and provenance recorded. Then it checks, ranks and previews them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable

import yaml
from music21 import pitch as m21pitch

from . import abcplan, fit as fitting, syllables
from .song import FORMAT, SongError

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


def voice_for(midis: list[int]) -> str:
    """The voice preset whose range holds the most of these notes (the narrowest on a tie)."""
    def fit(name):
        low, high = (m21pitch.Pitch(p).midi for p in VOICES[name][:2])
        middle = (low + high) / 2
        median = sorted(midis)[len(midis) // 2] if midis else middle
        return (-sum(low <= m <= high for m in midis), abs(median - middle))
    return min(VOICES, key=fit)


def song_from_plan(plan_text: str, lyrics: str, title: str, voice: str | None = DEFAULT_VOICE,
                   style: str | None = None, written_with: dict | None = None,
                   credits: dict | None = None, as_sung: int | None = None,
                   hints: list[float] | None = None) -> Candidate:
    """One planner score and the lyrics it was written for -> a Copyist song file (as data).

    `as_sung` is for transcriptions: keep the octave the score says was sung (after moving it down
    that many octaves, for an engine that writes YuE2's way) instead of fitting a voice; `voice`
    None then picks the preset that fits."""
    try:
        plan = abcplan.parse(plan_text)
    except abcplan.PlanError as e:
        raise WriteError(str(e)) from e
    bars, meter = abcplan.pair_bars(abcplan.trim(plan), plan.meter)
    if as_sung is not None:
        placement = abcplan.place_as_sung(bars, plan.key, as_sung)
        voice = voice or voice_for(abcplan.pitches(bars, placement.key))
    if voice not in VOICES:
        raise WriteError(f"Unknown voice {voice!r}: choose {', '.join(VOICES)}.")
    low, high, clef, _ = VOICES[voice]
    if as_sung is None:
        placement = abcplan.place_in_range(bars, plan.key, m21pitch.Pitch(low).midi, m21pitch.Pitch(high).midi)
    sections = syllables.parse_lyrics(lyrics)
    sylls = syllables.all_syllables(sections)
    if not sylls:
        raise WriteError("The lyrics have no words to sing.")
    try:
        fitted = fitting.fit(bars, plan.unit, meter, sylls, hints)
    except ValueError as e:
        raise WriteError(str(e)) from e
    unit = abcplan.best_unit(bars, plan.unit)
    melody = abcplan.write(bars, plan.unit, unit)

    notes = [f"{placement.key}, {meter}, {abcplan.tempo_field(plan.tempo)} to the quarter note; "
             f"{len(bars)} bars, {placement.notes} sung notes."]
    if meter != plan.meter:
        notes.append(f"The planner wrote {plan.meter}; written as {meter}, two of its bars to one.")
    octaves = (placement.semitones - placement.transposed) // 12
    if placement.transposed:
        notes.append(f"Transposed {placement.transposed:+d} semitones (to {placement.key}) to fit the {voice} range.")
    if as_sung is not None:
        notes.append(f"Written in the octave it was sung, for {voice}.")
    else:
        notes.append(f"Moved {abs(octaves)} octave{'s' if abs(octaves) != 1 else ''} "
                     f"{'down' if octaves < 0 else 'up'} from the plan." if octaves else "Kept the plan's octave.")
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
        "meter": meter,
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


# ---------------------------------------------------------------- the planner

PLAN_FILE, REQUEST_FILE, REPORT_FILE, PREVIEW_FILE, INDEX = "plan.abc", "request.json", "report.md", "preview.wav", \
    "candidates.json"


def style_line(style_id: str | None, words: str | None, voice: str) -> str:
    """The planner's style line: the style's own words (or the person's), the voice, and the style's
    meter and tempo when it has only one, since they steer what the planner writes."""
    from . import styles
    style = styles.get(style_id)
    if style_id and not style:
        raise WriteError(f"There's no style called {style_id!r}; `copyist styles` lists them.")
    parts = ["English"]
    if style:
        parts.append(style.production)
    if words:
        parts.append(words.strip().rstrip(",."))
    if not style and not words:
        parts.append("gentle ballad, acoustic piano, soft strings, intimate and heartfelt")
    parts.append(VOICES[voice][3])
    if style and len(style.meters) == 1:
        meter = next(iter(style.meters))
        parts.append(meter)
        if not meter.endswith("/8"):
            parts.append(f"{round(sum(style.tempo) / 2)} BPM")
    phrases, seen = [], set()
    for phrase in ", ".join(parts).split(","):
        phrase = phrase.strip()
        if phrase and phrase.lower() not in seen and not any(phrase.lower() in p.lower().split() for p in phrases):
            seen.add(phrase.lower())
            phrases.append(phrase)
    return ", ".join(phrases)


def planner_request(lyrics: str, style: str, seed: int) -> dict:
    """What yue-plan reads: the same request yue-synth takes, asking for the score only."""
    from .lora import yue_lyrics
    return {"style": style, "lyrics": yue_lyrics(lyrics), "cot": "full", "abc": "", "lm_seed": seed, "seed": seed}


def run_planner(req: dict, folder: Path, binary: str | None = None, model: str | None = None,
                device: str | None = None) -> Path:
    """Ask YuE2's planner for a score. Reuses a plan already written for the same request."""
    from . import models, paths
    folder.mkdir(parents=True, exist_ok=True)
    req_path, plan_path = folder / REQUEST_FILE, folder / PLAN_FILE
    text = json.dumps(req, ensure_ascii=False, indent=1)
    if plan_path.is_file() and req_path.is_file() and req_path.read_text(encoding="utf-8") == text:
        return plan_path
    binary = binary or (str(p) if (p := paths.find_program("yue-plan", "COPYIST_YUE_PLAN")) else None)
    model = model or (str(p) if (p := models.path_of("yue2")) else None)
    device = device or os.environ.get("COPYIST_YUE_DEVICE")
    if not binary:
        raise WriteError("YuE2's planner (yue-plan) isn't installed here: run scripts/setup-yue.sh, "
                         "or set COPYIST_YUE_PLAN.")
    if not model:
        raise WriteError("YuE2 isn't downloaded yet: run `copyist models download singer` (or use the page).")
    req_path.write_text(text, encoding="utf-8")
    plan_path.unlink(missing_ok=True)
    cmd = [binary, "--model", model, "--request", str(req_path), "--out", str(plan_path),
           "--lm-seed", str(req["lm_seed"])]
    if device:
        cmd += ["--device", device]
    with open(folder / "planner.log", "w", encoding="utf-8") as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not plan_path.is_file():
        raise WriteError(f"yue-plan failed (exit {r.returncode}); see {folder / 'planner.log'}.")
    return plan_path


# ---------------------------------------------------------------- scoring

def melody_notes(song) -> list:
    from music21 import note
    return [n for n in song.melody.recurse().notes if isinstance(n, note.Note)
            and not (n.tie is not None and n.tie.type in ("stop", "continue"))]


def largest_leap(song) -> int:
    ms = [n.pitch.midi for n in melody_notes(song)]
    return max((abs(b - a) for a, b in zip(ms, ms[1:])), default=0)


def hook_count(song) -> int | None:
    """How often the chorus's first two bars come back (same rhythm and contour) elsewhere in the
    song; None when the song has no chorus."""
    from music21 import stream
    start = next((s["bar"] for s in song.sections if s["name"] == "chorus"), None)
    if start is None:
        return None
    measures = {m.number: m for m in song.melody.getElementsByClass(stream.Measure)}

    def shape(first: int):
        notes = []
        for k in (first, first + 1):
            m = measures.get(k)
            if m is None:
                return None
            notes += [(k - first, float(n.offset), float(n.quarterLength), n.pitch.midi)
                      for n in m.notes if hasattr(n, "pitch")]
        if len(notes) < 3:
            return None
        rhythm = tuple((b, round(o, 3), round(d, 3)) for b, o, d, _ in notes)
        contour = tuple((y > x) - (y < x) for (*_, x), (*_, y) in zip(notes, notes[1:]))
        return rhythm, contour

    hook = shape(start)
    if hook is None:
        return 0
    return sum(1 for k in measures if k != start and shape(k) == hook)


def scores(song, findings, cand: Candidate) -> dict:
    count = lambda check, sev: sum(f.check == check and f.severity == sev for f in findings)
    return {
        "fails": sum(f.severity == "fail" for f in findings),
        "warnings": sum(f.severity == "warn" for f in findings),
        "fit_cost": round(cand.cost_per_syllable, 3),
        "splits": cand.fit.splits,
        "prosody": count("prosody", "warn"),
        "range": count("range", "fail") + count("range", "warn"),
        "leap": largest_leap(song),
        "chord_tones": count("chord-tones", "warn"),
        "hook": hook_count(song),
    }


def rank_key(s: dict) -> tuple:
    """Spec order: no failing checks, the fit, prosody, range, then leaps over a 9th, chord tones, the hook."""
    return (s["fails"], s["fit_cost"], s["prosody"], s["range"], int(s["leap"] > 14), s["chord_tones"],
            -(s["hook"] or 0))


# ---------------------------------------------------------------- the command

def band_preview(song, wav: Path, cache: Path, seed: int = 1) -> str:
    """The candidate on the band, in its style, at its own tempo. Returns the engine used."""
    import tempfile
    from . import arrange, engrave, perform, render, styles
    style = styles.get(song.style)
    with tempfile.TemporaryDirectory(prefix="copyist-write-") as tmp:
        midi = engrave.write_midi(arrange.arrange_band(song).performance(), Path(tmp) / "preview.mid")
        perform.perform(midi, midi, song.meter, float(perform.pickup_of(song)), seed=seed,
                        swing=style.swing if style else 0.5)
        return render.render_band(midi, wav, song.style, cache).engine


def write_songs(lyrics: str, title: str, out_root: Path = Path("out"), style: str | None = None,
                words: str | None = None, voice: str = DEFAULT_VOICE, candidates: int = 4, seed: int = 1,
                takes: bool = False, device: str | None = None, cache: Path = Path(".cache"),
                credits: dict | None = None, previews: bool = True,
                progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Plan `candidates` songs for the lyrics (seeds seed, seed+1, ...), turn each into a song file,
    check, preview and rank them. Everything lands in out/<slug>/write/; returns the index."""
    from . import styles, validate
    from .song import load_song
    if voice not in VOICES:
        raise WriteError(f"Unknown voice {voice!r}: choose {', '.join(VOICES)}.")
    line = style_line(style, words, voice)
    name = slug(title)
    folder = out_root / name / "write"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lyrics.txt").write_text(lyrics, encoding="utf-8")
    index = read_index(folder)
    words_id = hashlib.sha256(lyrics.strip().encode("utf-8")).hexdigest()[:16]
    if index.get("lyrics_id") not in (None, words_id):
        index["candidates"] = []                      # new words: earlier melodies were written for others
        index.pop("kept", None)
    index.update({"title": title, "slug": name, "style": style, "words": words, "voice": voice,
                  "style_line": line, "lyrics_id": words_id})
    entries = {e["seed"]: e for e in index.get("candidates", [])}
    for k in range(candidates):
        s = seed + k
        if progress:
            progress(k, candidates, f"candidate {s}")
        cdir = folder / f"candidate-{s}"
        entry = {"seed": s, "folder": cdir.name, "ok": False}
        try:
            plan_path = run_planner(planner_request(lyrics, line, s), cdir, device=device)
            plan_text = plan_path.read_text(encoding="utf-8")
            meter = abcplan.written_meter(abcplan.parse(plan_text).meter)
            chosen = style if style and (st := styles.get(style)) and meter in st.meters else styles.default_for(meter)
            written_with = {"planner": "yue-plan", "model": "YuE2-3B", "seed": s, "style": line}
            cand = song_from_plan(plan_text, lyrics, title, voice, chosen, written_with, credits)
            if style and chosen != style:
                cand.notes.append(f"The planner wrote {meter}, which the {style} style doesn't play; "
                                  f"the preview uses {chosen or 'the default band'}.")
            song_path = cdir / f"{name}.yaml"
            song_path.write_text(song_yaml(cand.data), encoding="utf-8")
            song = load_song(song_path)
            findings = validate.validate(song)
            entry.update({"ok": True, "song": f"{cdir.name}/{song_path.name}", "key": song.key,
                          "meter": song.meter, "tempo": song.tempo, "style": song.style,
                          "sections": song.sections, "scores": scores(song, findings, cand), "notes": cand.notes})
            report = [f"# {title}: candidate {s}", "", f"Planner style: {line}", ""] + \
                [f"- {n}" for n in cand.notes] + ["", validate.report_markdown(song, findings)]
            (cdir / REPORT_FILE).write_text("\n".join(report), encoding="utf-8")
            if not previews and (cdir / PREVIEW_FILE).is_file():
                entry["preview"] = f"{cdir.name}/{PREVIEW_FILE}"     # from an earlier run of the same plan
            if previews:
                try:
                    entry["engine"] = band_preview(song, cdir / PREVIEW_FILE, cache, seed=s)
                    entry["preview"] = f"{cdir.name}/{PREVIEW_FILE}"
                except Exception as e:                  # a preview is a convenience; the song file stands
                    entry["preview_error"] = str(e)
            if takes:
                from . import yue
                req = yue.request(song, verses=1, seed=831000 + s)
                req["style"] = line
                req["output_format"] = "wav16"
                audio = yue.run_yue2cpp(req, cdir / "take", device=device)
                entry["take"] = audio.relative_to(folder).as_posix()
        except (WriteError, abcplan.PlanError, SongError) as e:
            entry["reason"] = str(e)
            cdir.mkdir(parents=True, exist_ok=True)
            (cdir / REPORT_FILE).write_text(f"# {title}: candidate {s}\n\nNot usable: {e}\n", encoding="utf-8")
        entries[s] = entry
        index["candidates"] = ranked(list(entries.values()))
        write_index(folder, index)                       # after every candidate, so the page shows it at once
    if progress:
        progress(candidates, candidates, "")
    return index


def ranked(entries: list[dict]) -> list[dict]:
    good = sorted((e for e in entries if e.get("ok")), key=lambda e: rank_key(e["scores"]))
    bad = sorted((e for e in entries if not e.get("ok")), key=lambda e: e["seed"])
    for r, e in enumerate(good, start=1):
        e["rank"] = r
    for e in bad:
        e.pop("rank", None)
    return good + bad


def read_index(folder: Path) -> dict:
    try:
        return json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_index(folder: Path, index: dict) -> None:
    tmp = folder / (INDEX + ".tmp")
    tmp.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(folder / INDEX)


def keep(out_root: Path, title_or_slug: str, seed: int, songs_dir: Path = Path("songs"), replace: bool = False) -> Path:
    """Copy candidate `seed`'s song file into songs/. Refuses to overwrite a different song unless asked."""
    name = slug(title_or_slug)
    folder = out_root / name / "write"
    entry = next((e for e in read_index(folder).get("candidates", []) if e["seed"] == seed), None)
    if entry is None:
        raise WriteError(f"There's no candidate {seed} for {name} in {folder}.")
    if not entry.get("ok"):
        raise WriteError(f"Candidate {seed} didn't make a song: {entry.get('reason', 'see its report')}.")
    source = folder / entry["song"]
    target = songs_dir / f"{name}.yaml"
    text = source.read_text(encoding="utf-8")
    if target.exists() and target.read_text(encoding="utf-8") != text and not replace:
        raise WriteError(f"{target} already exists; keep it under another title, or pass --replace.")
    songs_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    index = read_index(folder)
    index["kept"] = seed
    write_index(folder, index)
    return target
