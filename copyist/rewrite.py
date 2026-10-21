"""Section rewriting (`copyist rewrite`, docs/melody-writing.md): try a section again, higher, or simpler.

YuE2's planner writes whole songs, so "again" and "simpler" plan more candidates (or reuse the write
folder) and swap in a section that matches the base song's meter, mode and section length, moved into
the base song's key. "Higher" raises the notes of one section without calling the planner.
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

import yaml
from music21 import pitch as m21pitch

from . import abcplan, write
from .song import SongError
from .write import DEFAULT_VOICE, VOICES, Candidate, WriteError

HOW = ("again", "higher", "simpler")
SIMPLER_WORDS = "simple stepwise melody, mostly neighbouring notes, few leaps"
HIGHER_SHIFTS = (2, 3, 4, 5)          # semitones to try for "higher"


def bars_from_melody(melody: str, sections: list[dict] | None = None) -> list[abcplan.Bar]:
    """A song-file melody block as bars, tagged with section names from `sections`."""
    bars: list[abcplan.Bar] = []
    for line in str(melody).strip().splitlines():
        for chunk in line.split("|"):
            text = chunk.strip().rstrip("]")
            if not text:
                continue
            toks, z_bars = abcplan.tokenize_bar(text)
            if z_bars:
                raise WriteError("This song's melody still has whole-bar Z rests; rewrite needs written bars.")
            bars.append(abcplan.Bar(toks, section=""))
    if not bars:
        raise WriteError("The melody has no bars to rewrite.")
    named = list(sections or [{"name": "verse", "bar": 1}])
    for i, bar in enumerate(bars, start=1):
        name = named[0]["name"]
        for s in named:
            if s["bar"] <= i:
                name = s["name"]
        bar.section = name
    return bars


def section_bounds(sections: list[dict], name: str, n_bars: int) -> tuple[int, int]:
    """0-based [start, end) for the first section called `name`."""
    named = sections or [{"name": "verse", "bar": 1}]
    start = next((s["bar"] for s in named if s["name"] == name), None)
    if start is None:
        have = ", ".join(s["name"] for s in named) or "none"
        raise WriteError(f"There's no {name!r} section (have: {have}).")
    later = sorted(s["bar"] for s in named if s["bar"] > start)
    end = later[0] if later else n_bars + 1
    return start - 1, end - 1


def leap_score(bars: list[abcplan.Bar], key: str) -> tuple[int, int]:
    """(largest leap in semitones, sum of leaps) over note onsets."""
    ms = abcplan.pitches(bars, key)
    leaps = [abs(b - a) for a, b in zip(ms, ms[1:])]
    return (max(leaps, default=0), sum(leaps))


def mean_pitch(bars: list[abcplan.Bar], key: str) -> float:
    ms = abcplan.pitches(bars, key)
    return sum(ms) / len(ms) if ms else 0.0


def splice(base: list[abcplan.Bar], start: int, end: int, donor: list[abcplan.Bar]) -> list[abcplan.Bar]:
    """Replace base[start:end] with a deep copy of `donor` (same length)."""
    if len(donor) != end - start:
        raise WriteError(f"Section lengths don't match ({len(donor)} bars vs {end - start}).")
    out = copy.deepcopy(base)
    piece = copy.deepcopy(donor)
    for bar in piece:
        bar.section = out[start].section if start < len(out) else bar.section
    out[start:end] = piece
    return out


def voice_of(data: dict) -> str:
    """The voice preset that matches the song's written range, or alto."""
    rng = (data.get("voice") or {}).get("range")
    if rng:
        for name, (low, high, *_rest) in VOICES.items():
            if [str(low), str(high)] == [str(rng[0]), str(rng[1])]:
                return name
    return DEFAULT_VOICE


def lyrics_text(song_path: Path, out_root: Path, lyrics: Path | None, title: str) -> str:
    if lyrics is not None:
        return lyrics.read_text(encoding="utf-8")
    for path in (out_root / write.slug(title) / "write" / "lyrics.txt",
                 song_path.with_suffix(".txt")):
        if path.is_file():
            return path.read_text(encoding="utf-8")
    data = yaml.safe_load(song_path.read_text(encoding="utf-8"))
    verses = data.get("lyrics") or []
    if isinstance(verses, str):
        verses = [verses]
    if not verses:
        raise WriteError(f"No lyrics for {title}; pass --lyrics or keep out/<slug>/write/lyrics.txt.")
    return "\n\n".join(str(v).strip() for v in verses)


def candidate_from_bars(bars: list[abcplan.Bar], *, unit: Fraction, meter: str, key: str, tempo,
                        lyrics: str, title: str, voice: str, style: str | None,
                        written_with: dict, credits: dict | None = None,
                        notes: list[str] | None = None) -> Candidate:
    """Bars + lyrics → a song-file Candidate (re-fits the words)."""
    return write.song_from_bars(bars, unit=unit, meter=meter, key=key, tempo=tempo, lyrics=lyrics,
                                title=title, voice=voice, style=style, written_with=written_with,
                                credits=credits, notes=notes)


def load_data(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("melody"):
        raise WriteError(f"{path.name} isn't a Copyist song file.")
    return data


def raise_section(data: dict, section: str, semitones: int) -> tuple[list[abcplan.Bar], str]:
    """Bars of `data` with one section moved up by `semitones` (notes and chords together).

    Returns (bars, key). When the raise covers the whole song, the key moves with it so the
    file stays tidy; a partial section keeps the song key and reads as a short modulation.
    """
    bars = bars_from_melody(data["melody"], data.get("sections"))
    lo, hi = section_bounds(data.get("sections") or [{"name": "verse", "bar": 1}], section, len(bars))
    piece = copy.deepcopy(bars[lo:hi])
    old_key = str(data["key"])
    whole = lo == 0 and hi == len(bars)
    if whole:
        new_key = abcplan.respell(piece, old_key, semitones)
    else:
        abcplan.transpose_notes(piece, old_key, semitones)
        for bar in piece:
            for t in bar.toks:
                if t.kind == "chord":
                    t.text = abcplan.transpose_chord(t.text, semitones, old_key)
        new_key = old_key
    voice = data.get("voice") or {}
    if voice.get("range"):
        low, high = (m21pitch.Pitch(str(p)).midi for p in voice["range"])
        abcplan.clamp_notes(piece, new_key if whole else old_key, low, high)
    return splice(bars, lo, hi, piece), new_key


def section_slice(data: dict, section: str) -> list[abcplan.Bar]:
    bars = bars_from_melody(data["melody"], data.get("sections"))
    lo, hi = section_bounds(data.get("sections") or [{"name": "verse", "bar": 1}], section, len(bars))
    return bars[lo:hi]


def same_mode(a: str, b: str) -> bool:
    """Both major, both minor, ...: a donor in another key can be moved into the base key."""
    ma, mb = abcplan.key_mode(a), abcplan.key_mode(b)
    if ma is None or mb is None or abcplan.key_tonic(a) is None or abcplan.key_tonic(b) is None:
        return a == b
    return ma == mb


def donor_section(donor: dict, section: str, key: str, near: list[int],
                  voice_range: tuple[int, int] | None) -> tuple[list[abcplan.Bar], int]:
    """The donor's `section` moved into `key`, in the octave nearest the pitches `near`, kept inside
    the voice's range. Returns (bars, semitones moved)."""
    piece = copy.deepcopy(section_slice(donor, section))
    donor_key = str(donor["key"])
    up = (abcplan.key_tonic(key) - abcplan.key_tonic(donor_key)) % 12 if donor_key != key else 0
    if up:
        own = abcplan.pitches(piece, donor_key)
        mid = sorted(own)[len(own) // 2] if own else 60
        target = sorted(near)[len(near) // 2] if near else mid
        up = min((up, up - 12), key=lambda s: abs(mid + s - target))
        abcplan.move_to_key(piece, donor_key, key, up)
        if voice_range:
            abcplan.clamp_notes(piece, key, *voice_range)
    return piece, up


def donor_songs(write_folder: Path, base: dict, section: str, lo: int, hi: int,
                base_path: Path) -> list[tuple[int, Path, dict]]:
    """Usable write candidates with the same meter, mode and section length as the base (any key)."""
    index = write.read_index(write_folder)
    out: list[tuple[int, Path, dict]] = []
    base_melody = base_path.resolve()
    for e in index.get("candidates", []):
        if not e.get("ok"):
            continue
        path = write_folder / e["song"]
        if path.resolve() == base_melody:
            continue
        if e.get("meter") != base["meter"] or not same_mode(str(e.get("key")), str(base["key"])):
            continue
        try:
            data = load_data(path)
            bars = bars_from_melody(data["melody"], data.get("sections"))
            dlo, dhi = section_bounds(data.get("sections") or [{"name": "verse", "bar": 1}],
                                      section, len(bars))
        except (WriteError, OSError, TypeError):
            continue
        if dhi - dlo != hi - lo:
            continue
        out.append((e["seed"], path, data))
    return out


def rewrite_section(song_path: Path, section: str, how: str, out_root: Path = Path("out"),
                    lyrics: Path | None = None, candidates: int = 4, seed: int = 1,
                    device: str | None = None, cache: Path = Path(".cache"),
                    previews: bool = True, plan_more: bool = True,
                    progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Rewrite one section of a song. Candidates land in out/<slug>/rewrite/<how>/."""
    from . import validate
    from .song import load_song

    if how not in HOW:
        raise WriteError(f"Unknown how {how!r}: choose {', '.join(HOW)}.")
    song_path = Path(song_path)
    data = load_data(song_path)
    title = str(data["title"])
    name = write.slug(title)
    voice = voice_of(data)
    unit = Fraction(str(data.get("unit", "1/4")))
    meter, key, tempo = str(data["meter"]), str(data["key"]), data.get("tempo", 90)
    style = data.get("style")
    credits = data.get("credits")
    base_bars = bars_from_melody(data["melody"], data.get("sections"))
    lo, hi = section_bounds(data.get("sections") or [{"name": "verse", "bar": 1}], section, len(base_bars))
    folder = out_root / name / "rewrite" / how
    folder.mkdir(parents=True, exist_ok=True)
    words = lyrics_text(song_path, out_root, lyrics, title)
    (folder / "lyrics.txt").write_text(words, encoding="utf-8")
    (folder / "base.yaml").write_text(song_path.read_text(encoding="utf-8"), encoding="utf-8")

    index: dict = {"title": title, "slug": name, "section": section, "how": how,
                   "base": str(song_path), "candidates": []}
    entries: list[dict] = []

    if how == "higher":
        base_mean = mean_pitch(base_bars[lo:hi], key)
        for k, shift in enumerate(HIGHER_SHIFTS[:candidates]):
            s = seed + k
            if progress:
                progress(k, min(candidates, len(HIGHER_SHIFTS)), f"+{shift}")
            cdir = folder / f"candidate-{s}"
            cdir.mkdir(parents=True, exist_ok=True)
            entry: dict = {"seed": s, "folder": cdir.name, "ok": False, "how": how, "semitones": shift}
            try:
                raised, raised_key = raise_section(data, section, shift)
                if mean_pitch(raised[lo:hi], raised_key) <= base_mean:
                    raise WriteError(f"+{shift} didn't raise the section (range clamp undid it).")
                ww = dict(data.get("written_with") or {})
                ww.update({"rewrite": how, "section": section, "semitones": shift, "from": ww.get("seed")})
                note = f"Raised the {section} by {shift} semitones (melody and chords together)."
                if raised_key != key:
                    note = f"Raised the {section} by {shift} semitones to {raised_key}."
                cand = candidate_from_bars(
                    raised, unit=unit, meter=meter, key=raised_key, tempo=tempo, lyrics=words,
                    title=title, voice=voice, style=style, written_with=ww, credits=credits,
                    notes=[note])
                song_file = cdir / f"{name}.yaml"
                song_file.write_text(write.song_yaml(cand.data), encoding="utf-8")
                song = load_song(song_file)
                findings = validate.validate(song)
                entry.update({"ok": True, "song": f"{cdir.name}/{song_file.name}", "key": song.key,
                              "meter": song.meter, "tempo": song.tempo, "style": song.style,
                              "sections": song.sections, "scores": write.scores(song, findings, cand, style),
                              "notes": cand.notes})
                (cdir / write.REPORT_FILE).write_text(
                    "\n".join([f"# {title}: {how} {section} (+{shift})", ""] +
                              [f"- {n}" for n in cand.notes] +
                              ["", validate.report_markdown(song, findings)]), encoding="utf-8")
                if previews:
                    try:
                        entry["engine"] = write.band_preview(song, cdir / write.PREVIEW_FILE, cache, seed=s)
                        entry["preview"] = f"{cdir.name}/{write.PREVIEW_FILE}"
                    except Exception as e:
                        entry["preview_error"] = str(e)
            except (WriteError, abcplan.PlanError, SongError) as e:
                entry["reason"] = str(e)
                (cdir / write.REPORT_FILE).write_text(
                    f"# {title}: {how} {section}\n\nNot usable: {e}\n", encoding="utf-8")
            entries.append(entry)
            index["candidates"] = write.ranked(entries)
            write.write_index(folder, index)
        if progress:
            progress(len(entries), len(entries), "")
        return index

    write_folder = out_root / name / "write"
    plan_words = SIMPLER_WORDS if how == "simpler" else None
    donors = donor_songs(write_folder, data, section, lo, hi, song_path) if write_folder.is_dir() else []
    if plan_more and len(donors) < candidates:
        need = candidates - len(donors)
        plan_seed = seed
        if write_folder.is_dir():
            used = {e["seed"] for e in write.read_index(write_folder).get("candidates", [])}
            plan_seed = max(used, default=0) + 1
        if progress:
            progress(0, candidates, f"planning {need} more")
        write.write_songs(words, title, out_root, style, plan_words, voice, need, plan_seed, False,
                          device, cache, previews=previews, progress=progress)
        donors = donor_songs(write_folder, data, section, lo, hi, song_path)

    base_pitches = abcplan.pitches(base_bars[lo:hi], key)
    rng = (data.get("voice") or {}).get("range")
    voice_range = tuple(m21pitch.Pitch(str(p)).midi for p in rng) if rng else None
    moved = {d[1]: donor_section(d[2], section, key, base_pitches, voice_range) for d in donors}
    if how == "simpler":
        donors = sorted(donors, key=lambda d: leap_score(moved[d[1]][0], key))
    else:
        def different(d: tuple) -> bool:
            return abcplan.pitches(moved[d[1]][0], key) != base_pitches

        donors = sorted(donors, key=lambda d: (0 if different(d) else 1, d[0]))

    if not donors:
        raise WriteError(
            f"No donor {section} in {meter}, in a key of the same mode as {key}, {hi - lo} bars long. "
            "Run `copyist write` for these lyrics first, or pass more --candidates.")

    for k, (donor_seed, donor_path, donor_data) in enumerate(donors[:candidates]):
        s = seed + k
        if progress:
            progress(k, min(candidates, len(donors)), f"from candidate {donor_seed}")
        cdir = folder / f"candidate-{s}"
        cdir.mkdir(parents=True, exist_ok=True)
        entry = {"seed": s, "folder": cdir.name, "ok": False, "how": how, "donor": donor_seed}
        try:
            piece, moved_by = moved[donor_path]
            merged = splice(base_bars, lo, hi, piece)
            ww = dict(data.get("written_with") or {})
            ww.update({"rewrite": how, "section": section, "donor_seed": donor_seed,
                       "donor": str(donor_path)})
            notes = [f"Swapped the {section} from write candidate {donor_seed} ({how})."]
            if moved_by:
                notes.append(f"Moved it from {donor_data['key']} to {key} ({moved_by:+d} semitones).")
                ww["donor_key"] = str(donor_data["key"])
            if how == "simpler":
                notes.append(f"Donor section leaps: {leap_score(piece, key)}.")
            cand = candidate_from_bars(
                merged, unit=unit, meter=meter, key=key, tempo=tempo, lyrics=words,
                title=title, voice=voice, style=style, written_with=ww, credits=credits, notes=notes)
            song_file = cdir / f"{name}.yaml"
            song_file.write_text(write.song_yaml(cand.data), encoding="utf-8")
            song = load_song(song_file)
            findings = validate.validate(song)
            entry.update({"ok": True, "song": f"{cdir.name}/{song_file.name}", "key": song.key,
                          "meter": song.meter, "tempo": song.tempo, "style": song.style,
                          "sections": song.sections, "scores": write.scores(song, findings, cand, style),
                          "notes": cand.notes})
            (cdir / write.REPORT_FILE).write_text(
                "\n".join([f"# {title}: {how} {section} (from candidate {donor_seed})", ""] +
                          [f"- {n}" for n in cand.notes] +
                          ["", validate.report_markdown(song, findings)]), encoding="utf-8")
            if previews:
                try:
                    entry["engine"] = write.band_preview(song, cdir / write.PREVIEW_FILE, cache, seed=s)
                    entry["preview"] = f"{cdir.name}/{write.PREVIEW_FILE}"
                except Exception as e:
                    entry["preview_error"] = str(e)
        except (WriteError, abcplan.PlanError, SongError) as e:
            entry["reason"] = str(e)
            (cdir / write.REPORT_FILE).write_text(
                f"# {title}: {how} {section}\n\nNot usable: {e}\n", encoding="utf-8")
        entries.append(entry)
        index["candidates"] = write.ranked(entries)
        write.write_index(folder, index)
    if progress:
        progress(len(entries), len(entries), "")
    return index


def keep(out_root: Path, title_or_slug: str, how: str, seed: int, songs_dir: Path = Path("songs"),
         replace: bool = False) -> Path:
    """Copy a rewrite candidate into songs/."""
    name = write.slug(title_or_slug)
    folder = out_root / name / "rewrite" / how
    entry = next((e for e in write.read_index(folder).get("candidates", []) if e["seed"] == seed), None)
    if entry is None:
        raise WriteError(f"There's no {how} candidate {seed} for {name} in {folder}.")
    if not entry.get("ok"):
        raise WriteError(f"Candidate {seed} didn't make a song: {entry.get('reason', 'see its report')}.")
    source = folder / entry["song"]
    target = songs_dir / f"{name}.yaml"
    text = source.read_text(encoding="utf-8")
    if target.exists() and target.read_text(encoding="utf-8") != text and not replace:
        raise WriteError(f"{target} already exists; pass --replace to overwrite.")
    songs_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    index = write.read_index(folder)
    index["kept"] = seed
    write.write_index(folder, index)
    return target
