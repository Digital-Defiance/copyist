"""Arrangement templates (SPEC.md section 7).

M1 ships one template, `band`: voice, piano (grand staff) and bass guitar,
following a style pattern. Patterns are data: per role, a list of
(start, length) in quarter notes within a full bar, plus which chord tone to
play. Chord changes inside a pattern note split it, so the accompaniment
always matches the chord symbols.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from music21 import (chord, clef, harmony, instrument, interval, key, layout, meter, note,
                     pitch, stream, tempo)

from . import drums
from .song import INSTRUMENTS, Song

# Each pattern: role -> list of (start, length, tone). Starts and lengths are
# in quarter notes from the start of a full bar. Tones: "chord", "root", "fifth".
STYLES: dict[str, dict] = {
    "waltz": {
        "meter": "3/4",
        "rh": [(1, 1, "chord"), (2, 1, "chord")],
        "lh": [(0, 1, "root")],
        "bass": [(0, 2, "root"), (2, 1, "fifth")],
    },
    "ballad": {
        "meter": "4/4",
        "rh": [(0, 4, "chord")],
        "lh": [(0, 4, "root")],
        "bass": [(0, 2, "root"), (2, 2, "fifth")],
    },
    "straight": {
        "meter": "4/4",
        "rh": [(0, 1, "chord"), (1, 1, "chord"), (2, 1, "chord"), (3, 1, "chord")],
        "lh": [(0, 2, "root"), (2, 2, "root")],
        "bass": [(0, 1, "root"), (1, 1, "fifth"), (2, 1, "root"), (3, 1, "fifth")],
    },
}
DEFAULT_STYLE_FOR_METER = {"3/4": "waltz", "4/4": "ballad"}

# Ranges as MIDI numbers.
RH_LOW, RH_TOP_MAX = pitch.Pitch("G3").midi, pitch.Pitch("D5").midi
LH_LOW, LH_HIGH = pitch.Pitch("E2").midi, pitch.Pitch("D#3").midi
BASS_WRITTEN_LOW, BASS_WRITTEN_HIGH = pitch.Pitch("E2").midi, pitch.Pitch("D3").midi  # sounds an octave lower

VELOCITY = {"voice": 100, "rh": 58, "lh": 64, "bass": 80}
PROGRAM = {"voice": 53, "piano": 0, "bass": 33}  # GM: Voice Oohs, Acoustic Grand, Fingered Bass


@dataclass
class Arrangement:
    style: str
    score: stream.Score             # full score, written pitch
    parts: dict[str, stream.Score]  # one score per player, for part PDFs
    notes: list[str]                # anything the arranger had to decide or skip
    included: list[str]
    excluded: list[str]
    perf_extra: list[stream.Part]   # performance-only parts (the drum kit at GM drum notes)

    def performance(self) -> stream.Score:
        """The arrangement as it should sound: for MIDI and audio."""
        perf = performance(self.score)
        for part in list(perf.parts):
            if part.partName == "Drums":
                perf.remove(part)
        for part in self.perf_extra:
            perf.insert(0, copy.deepcopy(part))
        return perf


def pattern_for(song: Song) -> tuple[str, dict, list[str]]:
    notes = []
    style = song.style or DEFAULT_STYLE_FOR_METER.get(song.meter)
    if style in STYLES and STYLES[style]["meter"] == song.meter:
        return style, STYLES[style], notes
    full = meter.TimeSignature(song.meter).barDuration.quarterLength
    if style:
        notes.append(f"Style {style!r} has no pattern for {song.meter}; used whole-bar chords instead.")
    generic = {"meter": song.meter, "rh": [(0, full, "chord")], "lh": [(0, full, "root")],
               "bass": [(0, full, "root")]}
    return "generic", generic, notes


def chord_timeline(part: stream.Part) -> list[tuple[float, harmony.ChordSymbol]]:
    syms = [(float(cs.getOffsetInHierarchy(part)), cs)
            for cs in part.recurse().getElementsByClass(harmony.ChordSymbol)]
    return sorted(syms, key=lambda x: x[0])


def chord_at(timeline, t: float):
    current = None
    for off, cs in timeline:
        if off <= t + 1e-9:
            current = cs
        else:
            break
    return current


def change_points(timeline, start: float, end: float) -> list[float]:
    return [off for off, _ in timeline if start + 1e-9 < off < end - 1e-9]


# ---------------------------------------------------------------- voicing

def place(p: pitch.Pitch, low: int, high: int) -> pitch.Pitch:
    """The pitch with p's spelling in the lowest octave that fits [low, high]."""
    q = copy.deepcopy(p)
    q.octave = 0
    while q.midi < low:
        q.octave += 1
    return q if q.midi <= high else place_down(q, high)


def place_down(q: pitch.Pitch, high: int) -> pitch.Pitch:
    while q.midi > high:
        q.octave -= 1
    return q


def voicing_tones(cs: harmony.ChordSymbol) -> list[pitch.Pitch]:
    """The chord tones the right hand plays: a triad, or root, 3rd and 7th for
    bigger chords (the 5th is the first note a pianist drops)."""
    pcs = []
    for p in cs.pitches:
        if p.name not in [q.name for q in pcs]:
            pcs.append(p)
    if len(pcs) > 3:
        fifth = cs.getChordStep(5)
        if fifth is not None:
            pcs = [p for p in pcs if p.name != fifth.name]
    return pcs[:4]


def close_voicings(cs: harmony.ChordSymbol) -> list[list[pitch.Pitch]]:
    """Close-position voicings of the chord within the right-hand range."""
    pcs = voicing_tones(cs)
    out = []
    for rot in range(len(pcs)):
        order = pcs[rot:] + pcs[:rot]
        for start_octave in (3, 4):
            voicing, prev = [], None
            for p in order:
                q = copy.deepcopy(p)
                q.octave = start_octave
                while prev is not None and q.midi <= prev.midi:
                    q.octave += 1
                voicing.append(q)
                prev = q
            if voicing[0].midi >= RH_LOW and voicing[-1].midi <= RH_TOP_MAX:
                out.append(voicing)
    return out


def choose_voicing(cs: harmony.ChordSymbol, previous: list[pitch.Pitch] | None) -> list[pitch.Pitch]:
    options = close_voicings(cs)
    if not options:
        return [place(p, RH_LOW, RH_TOP_MAX) for p in cs.pitches]
    if previous is None:
        target = pitch.Pitch("B4").midi
        return min(options, key=lambda v: abs(v[-1].midi - target))
    def movement(v):
        a, b = sorted(p.midi for p in v), sorted(p.midi for p in previous)
        if len(a) == len(b):
            return sum(abs(x - y) for x, y in zip(a, b))
        return abs(sum(a) / len(a) - sum(b) / len(b)) * 3
    return min(options, key=movement)


def tone(cs: harmony.ChordSymbol, which: str, low: int, high: int) -> pitch.Pitch:
    root = cs.bass() if which == "root" else cs.root()  # slash chords: the bass note
    if which == "fifth":
        fifth = cs.getChordStep(5) or root.transpose("P5")
        return place(fifth, low, high)
    return place(root, low, high)


# ---------------------------------------------------------------- building parts

ABBREVIATIONS = {"Voice": "Vo.", "Piano": "Pno.", "Bass": "Bass"}


def new_part(cls, name: str, inst: instrument.Instrument, program: int) -> stream.Part:
    part = cls()
    part.partName = name
    part.partAbbreviation = ABBREVIATIONS.get(name)
    inst.midiProgram = program
    inst.partName = name
    inst.partAbbreviation = ABBREVIATIONS.get(name)
    part.insert(0, inst)
    return part


def bar_window(m: stream.Measure, full: float, first: bool) -> tuple[float, float, float]:
    """(lo, hi, length): which slice of a full bar this measure covers."""
    length = sum(e.quarterLength for e in m.notesAndRests if not isinstance(e, harmony.ChordSymbol))
    if first and length < full:
        return full - length, full, length
    return 0.0, length, length


def build_role(song: Song, role: str, pattern: list, timeline, velocity: int) -> list[stream.Measure]:
    """One list of measures for a role ("rh", "lh" or "bass")."""
    melody_bars = list(song.melody.getElementsByClass(stream.Measure))
    full = melody_bars[0].barDuration.quarterLength
    previous_voicing = None
    bars = []
    for i, mb in enumerate(melody_bars):
        lo, hi, length = bar_window(mb, full, first=i == 0)
        start_abs = float(mb.getOffsetInHierarchy(song.melody))
        events = []
        for s, d, which in pattern:
            s0, e0 = max(s, lo), min(s + d, hi)
            if e0 <= s0:
                continue
            a, b = start_abs + s0 - lo, start_abs + e0 - lo
            cuts = [a] + change_points(timeline, a, b) + [b]
            for x, y in zip(cuts, cuts[1:]):
                events.append((x - start_abs, y - x, which))
        m = stream.Measure(number=mb.number)
        m.paddingLeft = mb.paddingLeft
        t = 0.0
        for off, dur, which in sorted(events):
            if off > t + 1e-9:
                m.insert(t, note.Rest(quarterLength=off - t))
            cs = chord_at(timeline, start_abs + off)
            if cs is None:
                el = note.Rest(quarterLength=dur)
            elif role == "rh":
                previous_voicing = choose_voicing(cs, previous_voicing)
                el = chord.Chord(previous_voicing, quarterLength=dur)
            elif role == "lh":
                el = note.Note(tone(cs, which, LH_LOW, LH_HIGH), quarterLength=dur)
            else:
                el = note.Note(tone(cs, which, BASS_WRITTEN_LOW, BASS_WRITTEN_HIGH), quarterLength=dur)
            if not isinstance(el, note.Rest):
                el.volume.velocity = velocity
            m.insert(off, el)
            t = off + dur
        if t < length - 1e-9:
            m.insert(t, note.Rest(quarterLength=length - t))
        if mb.rightBarline is not None:
            m.rightBarline = copy.deepcopy(mb.rightBarline)
        bars.append(m)
    return bars


def start_bar(m: stream.Measure, song: Song, the_clef) -> None:
    m.insert(0, the_clef)
    m.insert(0, key.KeySignature(song.key_object().sharps))
    m.insert(0, meter.TimeSignature(song.meter))


def bar_length(m: stream.Measure) -> float:
    """How much time a bar actually holds (a pickup holds less than a full bar)."""
    return sum(e.quarterLength for e in m.notesAndRests if not isinstance(e, harmony.ChordSymbol))


def add_chord_symbols(part: stream.Part, timeline) -> None:
    """Copy chord symbols into a part at the same musical positions."""
    bars = list(part.getElementsByClass(stream.Measure))
    for off, cs in timeline:
        for m in bars:
            m_off = float(m.getOffsetInHierarchy(part))
            if m_off - 1e-9 <= off < m_off + bar_length(m) - 1e-9:
                m.insert(off - m_off, copy.deepcopy(cs))
                break


def arrange_band(song: Song) -> Arrangement:
    """Arrange the song for the instruments the song file asks for (default: all of them)."""
    style, pat, notes = pattern_for(song)
    timeline = chord_timeline(song.melody)
    if not timeline:
        notes.append("No chord symbols, so piano and bass have nothing to play.")
    wanted = song.instruments

    def single(*parts, group=False, chords=False):
        s = stream.Score()
        s.metadata = copy.deepcopy(song.score.metadata)
        for p in parts:
            p = copy.deepcopy(p)
            if chords:
                add_chord_symbols(p, timeline)
            # A part's name is in its page header; no staff labels needed.
            p.partName = p.partAbbreviation = None
            for inst in p.getElementsByClass(instrument.Instrument):
                inst.partName = inst.partAbbreviation = inst.instrumentName = inst.instrumentAbbreviation = None
            s.insert(0, p)
        if group:
            s.insert(0, layout.StaffGroup(list(s.parts), symbol="brace", barTogether=True))
        add_tempo(s, song)
        return s

    full = stream.Score()
    full.metadata = copy.deepcopy(song.score.metadata)
    perf_extra: list[stream.Part] = []
    parts: dict[str, stream.Score] = {}
    order: list[stream.Part] = []

    if "voice" in wanted:
        voice = copy.deepcopy(song.melody)
        voice.partName = "Voice"
        voice.partAbbreviation = ABBREVIATIONS["Voice"]
        v_inst = instrument.Vocalist()
        v_inst.midiProgram = PROGRAM["voice"]
        v_inst.partName, v_inst.partAbbreviation = "Voice", ABBREVIATIONS["Voice"]
        voice.insert(0, v_inst)
        for n in voice.recurse().notes:
            n.volume.velocity = VELOCITY["voice"]
        order.append(voice)
        parts["voice"] = single(voice)

    if "piano" in wanted:
        rh = new_part(stream.PartStaff, "Piano", instrument.Piano(), PROGRAM["piano"])
        lh = new_part(stream.PartStaff, "Piano", instrument.Piano(), PROGRAM["piano"])
        for part, role, the_clef in ((rh, "rh", clef.TrebleClef()), (lh, "lh", clef.BassClef())):
            bars = build_role(song, role, pat[role], timeline, VELOCITY[role])
            start_bar(bars[0], song, the_clef)
            for m in bars:
                part.append(m)
        order += [rh, lh]
        full.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace",
                                         barTogether=True))
        parts["piano"] = single(rh, lh, group=True)
        add_chord_symbols(parts["piano"].parts[0], timeline)  # chords above the right hand

    if "bass" in wanted:
        bass = new_part(stream.Part, "Bass", instrument.ElectricBass(), PROGRAM["bass"])
        bass.getElementsByClass(instrument.Instrument).first().transposition = interval.Interval("-P8")
        bass.atSoundingPitch = False
        bars = build_role(song, "bass", pat["bass"], timeline, VELOCITY["bass"])
        start_bar(bars[0], song, clef.BassClef())
        for m in bars:
            bass.append(m)
        order.append(bass)
        parts["bass"] = single(bass, chords=True)

    if "drums" in wanted:
        kit, kit_perf = drums.build(song, style, bar_window)
        order.append(kit)
        perf_extra.append(kit_perf)
        parts["drums"] = single(kit)

    for part in order:
        full.insert(0, part)
    if order:
        add_tempo(full, song)
    excluded = [i for i in INSTRUMENTS if i not in wanted]
    return Arrangement(style, full, parts, notes, list(wanted), excluded, perf_extra)


def add_tempo(s: stream.Score, song: Song) -> None:
    top = s.parts[0]
    if top.recurse().getElementsByClass(tempo.MetronomeMark):
        return
    mm = song.melody.recurse().getElementsByClass(tempo.MetronomeMark).first()
    first = top.getElementsByClass(stream.Measure).first()
    if mm is not None and first is not None:
        first.insert(0, copy.deepcopy(mm))


def performance(score: stream.Score) -> stream.Score:
    """A copy for MIDI: sounding pitch, no chord symbols (they'd play as chords)."""
    perf = copy.deepcopy(score)
    for cs in list(perf.recurse().getElementsByClass(harmony.ChordSymbol)):
        cs.activeSite.remove(cs)
    return perf.toSoundingPitch()
