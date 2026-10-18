"""Validators (SPEC.md section 5).

Every check returns Findings with a severity of "pass", "warn" or "fail" and,
for anything musical, the bar and beat. A song is finished only when no check
fails.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

import pronouncing
from music21 import harmony, meter, note, stream

from .lyrics import lyric_slots
from .song import Song

PASS, WARN, FAIL = "pass", "warn", "fail"


@dataclass
class Finding:
    check: str
    severity: str
    message: str
    bar: int | None = None
    beat: float | None = None

    @property
    def where(self) -> str:
        if self.bar is None:
            return ""
        if self.beat is None:
            return f"bar {self.bar}"
        return f"bar {self.bar}, beat {fmt_beat(self.beat)}"


def fmt_beat(beat: float) -> str:
    f = Fraction(beat).limit_denominator(16)
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(f.numerator, f.denominator)
    return f"{whole} {rem}/{f.denominator}" if whole else f"{rem}/{f.denominator}"


def onset_strength(n: note.GeneralNote, meter: str) -> float:
    """Metric weight of a note's onset in its bar (dotted-quarter beats in 6/8 and 12/8)."""
    from .fit import beat_strength
    m = n.getContextByClass(stream.Measure)
    pos = Fraction(str(n.getOffsetInHierarchy(m) if m is not None else n.offset)).limit_denominator(64)
    return beat_strength(pos, meter)


def is_strong(n: note.GeneralNote, meter: str) -> bool:
    """Downbeats and the other main beats of the bar (e.g. beat 2 in 6/8, beats 2–4 in 4/4)."""
    return onset_strength(n, meter) >= 0.5


# ---------------------------------------------------------------- bars

def check_bars(song: Song) -> list[Finding]:
    """Bars as written in the song file add up to the meter."""
    out = []
    totals = song.written_bars()
    if not totals:
        return [Finding("bars", FAIL, "The melody has no bars.")]
    ts = meter.TimeSignature(song.meter)
    full = Fraction(ts.barDuration.quarterLength).limit_denominator(64)
    beat = Fraction(ts.beatDuration.quarterLength).limit_denominator(64)
    first_number = 0 if totals[0] < full else 1
    for i, total in enumerate(totals):
        if total == full:
            continue
        first, last = i == 0, i == len(totals) - 1
        if total < full and (first or last):
            continue
        what = "too long" if total > full else "too short"
        out.append(Finding("bars", FAIL, f"{what}: {fmt_beat(total / beat)} beats in a bar of "
                           f"{fmt_beat(full / beat)}.", bar=first_number + i))
    pickup, final = totals[0], totals[-1]
    if len(totals) > 1 and pickup < full and final < full and pickup + final != full:
        out.append(Finding("bars", WARN,
                           f"The pickup ({fmt_beat(pickup / beat)} beats) and the last bar "
                           f"({fmt_beat(final / beat)} beats) should add up to one full bar.",
                           bar=first_number + len(totals) - 1))
    if not out:
        out.append(Finding("bars", PASS, f"All {len(totals)} bars add up."))
    return out


# ---------------------------------------------------------------- lyrics

def check_lyrics_fit(song: Song) -> list[Finding]:
    out = []
    if not song.verses:
        return [Finding("lyrics-fit", WARN, "The song has no lyrics.")]
    for fit in song.lyric_fits:
        if fit.fits:
            out.append(Finding("lyrics-fit", PASS, f"Verse {fit.number} fits ({fit.syllables} syllables)."))
            continue
        diff = fit.slots_used - fit.slots_available
        if diff > 0:
            out.append(Finding("lyrics-fit", FAIL,
                               f"Verse {fit.number} has {diff} more syllable{'s' if diff != 1 else ''} "
                               f"(counting _ and *) than the melody has notes."))
        else:
            first_empty = lyric_slots(song.melody)[fit.slots_used]
            out.append(Finding("lyrics-fit", FAIL,
                               f"Verse {fit.number} runs out of syllables {-diff} note{'s' if diff != -1 else ''} early.",
                               bar=first_empty.measureNumber, beat=float(first_empty.beat)))
    return out


# ---------------------------------------------------------------- range

def check_range(song: Song) -> list[Finding]:
    notes = [n for n in song.melody.recurse().notes if isinstance(n, note.Note)]
    if not notes:
        return [Finding("range", FAIL, "The melody has no notes.")]
    low = min(notes, key=lambda n: n.pitch.ps)
    high = max(notes, key=lambda n: n.pitch.ps)
    summary = f"Melody spans {low.nameWithOctave} to {high.nameWithOctave}."
    if not song.voice_range:
        return [Finding("range", PASS, summary + " (No voice range given to check against.)")]
    lo, hi = song.voice_range
    out = []
    for n in notes:
        if n.tie is not None and n.tie.type in ("stop", "continue"):
            continue
        under, over = lo.ps - n.pitch.ps, n.pitch.ps - hi.ps
        by = max(under, over)
        if by > 0:
            sev = FAIL if by > 2 else WARN
            side = "below" if under > 0 else "above"
            out.append(Finding("range", sev,
                               f"{n.nameWithOctave} is {int(by)} semitone{'s' if by != 1 else ''} {side} "
                               f"the voice's range ({lo.nameWithOctave}–{hi.nameWithOctave}).",
                               bar=n.measureNumber, beat=float(n.beat)))
    if not out:
        out.append(Finding("range", PASS, summary + f" Within {lo.nameWithOctave}–{hi.nameWithOctave}."))
    return out


# ---------------------------------------------------------------- chords

def chord_timeline(part: stream.Part) -> list[tuple[float, harmony.ChordSymbol]]:
    syms = [(float(cs.getOffsetInHierarchy(part)), cs)
            for cs in part.recurse().getElementsByClass(harmony.ChordSymbol)]
    return sorted(syms, key=lambda x: x[0])


def check_chord_tones(song: Song) -> list[Finding]:
    part = song.melody
    timeline = chord_timeline(part)
    if not timeline:
        return [Finding("chord-tones", WARN, "The song has no chord symbols.")]
    out = []
    checked = 0
    for n in part.recurse().notes:
        if not isinstance(n, note.Note) or (n.tie is not None and n.tie.type in ("stop", "continue")):
            continue
        if not is_strong(n, song.meter):
            continue
        at = float(n.getOffsetInHierarchy(part))
        current = [cs for off, cs in timeline if off <= at + 1e-9]
        if not current:
            continue
        cs = current[-1]
        checked += 1
        if n.pitch.pitchClass not in {p.pitchClass for p in cs.pitches}:
            out.append(Finding("chord-tones", WARN,
                               f"{n.name} over {cs.figure} isn't a chord tone on a strong beat "
                               f"(fine if it's a suspension or appoggiatura that resolves).",
                               bar=n.measureNumber, beat=float(n.beat)))
    if not out:
        out.append(Finding("chord-tones", PASS, f"All {checked} strong-beat melody notes are chord tones."))
    return out


# ---------------------------------------------------------------- prosody

def word_stresses(word: str) -> list[str] | None:
    """CMU dictionary stress digits for each syllable of a word, or None if unknown."""
    clean = re.sub(r"[^a-z']", "", word.lower()).strip("'")
    phones = pronouncing.phones_for_word(clean)
    if not phones:
        return None
    return list(pronouncing.stresses(phones[0]))


def check_prosody(song: Song) -> list[Finding]:
    """Stressed syllables shouldn't sit weaker than an unstressed syllable of the same word.

    Strength uses Copyist's beat grid (fit.beat_strength): a dotted quarter is the beat in
    6/8 and 12/8, not a quarter note — music21's beatStrength alone used to misread that.
    """
    out = []
    checked = 0
    for fit in song.lyric_fits:
        words: dict[int, list] = {}
        for p in fit.placed:
            words.setdefault(p.word, []).append(p)
        for sylls in words.values():
            if len(sylls) < 2:
                continue
            text = "".join(s.text for s in sylls)
            stresses = word_stresses(text)
            if not stresses or len(stresses) != len(sylls):
                continue
            checked += 1
            primary = [s for s, d in zip(sylls, stresses) if d == "1"]
            unstressed = [s for s, d in zip(sylls, stresses) if d == "0"]
            for st in primary:
                st_w = onset_strength(st.note, song.meter)
                for un in unstressed:
                    if onset_strength(un.note, song.meter) > st_w:
                        out.append(Finding("prosody", WARN,
                                           f"Verse {fit.number}: in “{display_word(sylls)}” the stressed syllable "
                                           f"“{st.text}” falls on a weaker beat than “{un.text}”.",
                                           bar=st.note.measureNumber, beat=float(st.note.beat)))
                        break
    if not out:
        out.append(Finding("prosody", PASS, f"Stress fits the beat in all {checked} multi-syllable words checked."))
    return out


def display_word(sylls) -> str:
    return "-".join(s.text.strip(".,;:!?\"“”") for s in sylls)


# ---------------------------------------------------------------- key

def check_key(song: Song) -> list[Finding]:
    out = []
    k = song.key_object()
    for cs in song.melody.recurse().getElementsByClass(harmony.ChordSymbol):
        if not cs.pitches:
            out.append(Finding("key", WARN, f"Couldn't read the chord symbol {cs.figure!r}.",
                               bar=cs.measureNumber))
    diatonic = {p.pitchClass for p in k.pitches}
    outside = [n for n in song.melody.recurse().notes
               if isinstance(n, note.Note) and n.pitch.pitchClass not in diatonic]
    for n in outside:
        out.append(Finding("key", WARN, f"{n.name} is outside {k.tonic.name} {k.mode}.",
                           bar=n.measureNumber, beat=float(n.beat)))
    if not out:
        out.append(Finding("key", PASS, f"Melody and chords read cleanly in {k.tonic.name} {k.mode}."))
    return out


CHECKS = [check_bars, check_lyrics_fit, check_range, check_chord_tones, check_prosody, check_key]


def validate(song: Song) -> list[Finding]:
    findings = []
    for check in CHECKS:
        findings.extend(check(song))
    return findings


def is_finished(findings: list[Finding]) -> bool:
    return not any(f.severity == FAIL for f in findings)


def report_markdown(song: Song, findings: list[Finding]) -> str:
    fails = sum(f.severity == FAIL for f in findings)
    warns = sum(f.severity == WARN for f in findings)
    status = "Finished" if fails == 0 else "Not finished"
    lines = [f"# {song.title}: validation report", "",
             f"**{status}:** {fails} failing, {warns} warning{'s' if warns != 1 else ''}.", "",
             "| Check | Result | Where | Details |", "|---|---|---|---|"]
    order = {FAIL: 0, WARN: 1, PASS: 2}
    for f in sorted(findings, key=lambda f: (order[f.severity], CHECK_ORDER.get(f.check, 99))):
        lines.append(f"| {f.check} | {f.severity} | {f.where} | {f.message.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


CHECK_ORDER = {name: i for i, name in enumerate(["bars", "lyrics-fit", "range", "chord-tones", "prosody", "key"])}
