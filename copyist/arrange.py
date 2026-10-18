"""Arrangement templates (SPEC.md section 7).

M1 ships one template, `band`: voice, piano (grand staff), bass and drums,
following a style. Styles are data files (copyist/styles/, docs/styles.md):
per part, a list of (start, length, what to play) in quarter notes within a
full bar. Chord changes inside a pattern note split it, so the accompaniment
always matches the chord symbols.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from music21 import (chord, clef, expressions, harmony, instrument, interval, key, layout, meter, note,
                     pitch, stream, tempo)

from . import drums, styles
from .song import INSTRUMENTS, Song

# Ranges as MIDI numbers.
RH_LOW, RH_TOP_MAX = pitch.Pitch("G3").midi, pitch.Pitch("D5").midi
LH_LOW, LH_HIGH = pitch.Pitch("E2").midi, pitch.Pitch("D#3").midi
BASS_WRITTEN_LOW, BASS_WRITTEN_HIGH = pitch.Pitch("E2").midi, pitch.Pitch("D3").midi  # sounds an octave lower

SHELL_LOW = pitch.Pitch("E3").midi
WALK_LOW, WALK_HIGH = pitch.Pitch("E2").midi, pitch.Pitch("A3").midi  # written; sounds an octave lower

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
    """(style id, what each part plays in one bar, notes for the report)."""
    notes = []
    style_id = song.style or styles.default_for(song.meter)
    style = styles.get(style_id)
    if style and style.pattern(song.meter):
        return style_id, style.pattern(song.meter), notes
    full = float(meter.TimeSignature(song.meter).barDuration.quarterLength)
    if style_id and not style:
        notes.append(f"There's no style called {style_id!r}; used whole-bar chords instead.")
    elif style_id:
        notes.append(f"Style {style_id!r} has no pattern for {song.meter}; used whole-bar chords instead.")
    generic = {"rh": [(0, full, "chord")], "lh": [(0, full, "root")], "bass": [(0, full, "root")],
               "drums": None}
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


def chord_tone(cs: harmony.ChordSymbol, which: str) -> pitch.Pitch:
    """A chord tone by name; a 7th that isn't in the chord is the minor 7th (the blues 7th)."""
    root = cs.root()
    if which == "root":
        return cs.bass()                     # slash chords: the bass note
    if which == "third":
        return cs.getChordStep(3) or root.transpose("M3")
    if which == "fifth":
        return cs.getChordStep(5) or root.transpose("P5")
    if which == "sixth":
        return root.transpose("M6")
    if which == "seventh":
        return cs.getChordStep(7) or root.transpose("m7")
    return root


def tone(cs: harmony.ChordSymbol, which: str, low: int, high: int,
         next_cs: harmony.ChordSymbol | None = None) -> pitch.Pitch:
    if which == "octave":
        return place(cs.bass(), low, high).transpose(12)
    if which == "approach":
        target = place((next_cs or cs).bass(), low + 1, high + 1)
        return target.transpose(-1)          # a half step below the next chord's root
    return place(chord_tone(cs, which), low, high)


def shell(cs: harmony.ChordSymbol) -> list[pitch.Pitch]:
    """The 3rd and the 7th (the 6th on a plain major chord): the two notes that say what a chord is."""
    third = cs.getChordStep(3) or cs.root().transpose("M3")
    seventh = cs.getChordStep(7)
    if seventh is None:
        minor = third.midi % 12 == (cs.root().midi + 3) % 12
        seventh = cs.root().transpose("m7" if minor else "M6")
    low = place(third, SHELL_LOW, SHELL_LOW + 11)
    high = place(seventh, low.midi + 1, low.midi + 12)
    return [low, high]


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


def melody_names_at(song: Song, t: float) -> set[str]:
    """Pitch-class names of melody notes sounding at absolute quarter-note time `t`."""
    names = set()
    for n in song.melody.recurse().notes:
        if isinstance(n, harmony.ChordSymbol):
            continue
        start = float(n.getOffsetInHierarchy(song.melody))
        if start - 1e-9 <= t < start + float(n.quarterLength) - 1e-9:
            names.add(n.pitch.name)
    return names


def build_role(song: Song, role: str, pattern: list, timeline, velocity: int,
               open_for_melody: bool = False) -> list[stream.Measure]:
    """One list of measures for a role ("rh", "lh" or "bass").

    When `open_for_melody`, the right hand drops any pitch the melody is already
    singing (solo-piano textures that keep an accompaniment figure).
    """
    melody_bars = list(song.melody.getElementsByClass(stream.Measure))
    full = melody_bars[0].barDuration.quarterLength
    previous_voicing = None
    bars = []
    first_full = 0 if bar_window(melody_bars[0], full, True)[2] < full else 1
    for i, mb in enumerate(melody_bars):
        lo, hi, length = bar_window(mb, full, first=i == 0)
        start_abs = float(mb.getOffsetInHierarchy(song.melody))
        n_in_song = i + first_full if first_full == 1 else i   # 1 = first full bar (0 on a pickup)
        events = []
        for s, d, which in styles.bar_of(pattern, n_in_song):
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
            next_cs = chord_at(timeline, start_abs + off + dur)
            blocked = melody_names_at(song, start_abs + off) if open_for_melody and role == "rh" else set()
            if cs is None:
                el = note.Rest(quarterLength=dur)
            elif role == "rh" and which == "shell":
                kept = [p for p in shell(cs) if p.name not in blocked]
                el = chord.Chord(kept, quarterLength=dur) if kept else note.Rest(quarterLength=dur)
            elif role == "rh":
                previous_voicing = choose_voicing(cs, previous_voicing)
                if which.startswith("arp"):
                    ordered = [p for p in sorted(previous_voicing, key=lambda q: q.midi) if p.name not in blocked]
                    if not ordered:
                        el = note.Rest(quarterLength=dur)
                    else:
                        el = note.Note(ordered[(int(which[3:]) - 1) % len(ordered)], quarterLength=dur)
                else:
                    kept = [p for p in previous_voicing if p.name not in blocked]
                    el = chord.Chord(kept, quarterLength=dur) if kept else note.Rest(quarterLength=dur)
            elif role == "lh":
                el = note.Note(tone(cs, which, LH_LOW, LH_HIGH, next_cs), quarterLength=dur)
            else:
                el = note.Note(tone(cs, which, BASS_WRITTEN_LOW, BASS_WRITTEN_HIGH, next_cs), quarterLength=dur)
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


WALK_PLANS = {1: [["root"]], 2: [["root", "approach"]],
              3: [["root", "third", "approach"], ["root", "fifth", "approach"]],
              4: [["root", "third", "fifth", "approach"], ["root", "fifth", "sixth", "approach"]]}


def walk_bars(song: Song, timeline, velocity: int) -> list[stream.Measure]:
    """A walking bass, a note a beat. Each stretch of one chord starts on its root, climbs
    through chord tones (3rd and 5th, or 5th and 6th, alternating so it doesn't repeat itself),
    and ends a half step from the next root; every note sits in the octave nearest the last."""
    melody_bars = list(song.melody.getElementsByClass(stream.Measure))
    full = melody_bars[0].barDuration.quarterLength
    beat = float(meter.TimeSignature(song.meter).beatDuration.quarterLength)
    previous = None
    bars = []
    stretch = 0
    for i, mb in enumerate(melody_bars):
        lo, hi, length = bar_window(mb, full, first=i == 0)
        start_abs = float(mb.getOffsetInHierarchy(song.melody))
        m = stream.Measure(number=mb.number)
        m.paddingLeft = mb.paddingLeft
        if i == len(melody_bars) - 1:                       # the last bar: the root, held
            cs = chord_at(timeline, start_abs)
            if cs is None:
                m.insert(0, note.Rest(quarterLength=length))
            else:
                el = note.Note(near(chord_tone(cs, "root"), previous), quarterLength=length)
                el.volume.velocity = velocity
                m.insert(0, el)
            bars.append(m)
            continue
        beats = [k * beat for k in range(int(round(length / beat)))]
        groups: list[list[float]] = []
        for b in beats:
            if groups and same_chord(chord_at(timeline, start_abs + groups[-1][0]), chord_at(timeline, start_abs + b)):
                groups[-1].append(b)
            else:
                groups.append([b])
        for group in groups:
            cs = chord_at(timeline, start_abs + group[0])
            plans = WALK_PLANS[min(len(group), 4)]
            plan = plans[stretch % len(plans)] + ["fifth"] * (len(group) - 4)
            stretch += 1
            for b, which in zip(group, plan):
                if cs is None:
                    m.insert(b, note.Rest(quarterLength=beat))
                    continue
                if which == "approach":
                    after = chord_at(timeline, start_abs + b + beat) or cs
                    target = near(chord_tone(after, "root"), previous)
                    if same_chord(cs, after):
                        # Harmony isn't moving: stay inside the chord. A chromatic
                        # half-step into the same root sounds like a wrong note under
                        # a sung melody (Saints on C for bars at a time).
                        choices = [near(chord_tone(cs, w), previous)
                                   for w in ("third", "fifth", "sixth")]
                        p = min(choices, key=lambda q: (
                            previous is not None and q.midi == previous.midi,
                            abs(q.midi - target.midi),
                            abs(q.midi - previous.midi) if previous else 0,
                        ))
                    else:
                        below, above = target.transpose(-1), target.transpose(1)
                        p = min((below, above), key=lambda q: (
                            previous is not None and q.midi == previous.midi,
                            not WALK_LOW <= q.midi <= WALK_HIGH,
                            abs(q.midi - previous.midi) if previous else 0,
                        ))
                else:
                    p = near(chord_tone(cs, which), previous)
                el = note.Note(p, quarterLength=beat)
                el.volume.velocity = velocity
                m.insert(b, el)
                previous = p
        if mb.rightBarline is not None:
            m.rightBarline = copy.deepcopy(mb.rightBarline)
        bars.append(m)
    return bars


def line_bars(song: Song, timeline, velocity: int, line: list[str], every: float) -> list[stream.Measure]:
    """A bass line of chord tones climbing from the root, one every `every` quarters (a boogie,
    octaves): the root low in the bass's range, the other tones above it."""
    melody_bars = list(song.melody.getElementsByClass(stream.Measure))
    full = melody_bars[0].barDuration.quarterLength
    bars = []
    for i, mb in enumerate(melody_bars):
        lo, hi, length = bar_window(mb, full, first=i == 0)
        start_abs = float(mb.getOffsetInHierarchy(song.melody))
        m = stream.Measure(number=mb.number)
        m.paddingLeft = mb.paddingLeft
        t, k = 0.0, 0
        while k * every < hi - 1e-9:
            s = k * every
            if s >= lo - 1e-9:
                at = start_abs + s - lo
                cs = chord_at(timeline, at)
                dur = min(every, hi - s)
                if cs is None:
                    el = note.Rest(quarterLength=dur)
                else:
                    root = place(cs.bass(), BASS_WRITTEN_LOW, BASS_WRITTEN_LOW + 11)
                    which = line[k % len(line)]
                    if which == "octave":
                        p = root.transpose(12)
                    else:
                        p = place(chord_tone(cs, which), root.midi, root.midi + 11)
                    el = note.Note(p, quarterLength=dur)
                    el.volume.velocity = velocity
                m.insert(s - lo, el)
            k += 1
        if mb.rightBarline is not None:
            m.rightBarline = copy.deepcopy(mb.rightBarline)
        bars.append(m)
    return bars


def same_chord(a, b) -> bool:
    return a is not None and b is not None and a.figure == b.figure


def near(p: pitch.Pitch, previous: pitch.Pitch | None) -> pitch.Pitch:
    """p in the walking range, in the octave closest to the previous note."""
    if previous is None:
        return place(p, WALK_LOW, WALK_LOW + 11)
    options = []
    for octave in range(1, 5):
        q = copy.deepcopy(p)
        q.octave = octave
        if WALK_LOW <= q.midi <= WALK_HIGH:
            options.append(q)
    return min(options, key=lambda q: abs(q.midi - previous.midi)) if options else place(p, WALK_LOW, WALK_HIGH)


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
    # Piano-vocal: the melody is already on the piano. A band under it leaves the
    # right hand open unless the style asks to keep its figure (`keep_rh`); solo
    # piano and keep_rh drop only the pitches the melody is already singing.
    style_obj = styles.get(style)
    open_rh_for_melody = False
    if style_obj and style_obj.instruments.get("melody") == "piano":
        if pat.get("bass") != "none" and not style_obj.keep_rh:
            pat = {**pat, "rh": []}
            notes.append("Piano-vocal: the right hand rests so the melody isn't struck twice.")
        else:
            open_rh_for_melody = True
            notes.append("Piano-vocal: the right hand leaves the melody's pitches open.")
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
            bars = build_role(song, role, pat[role], timeline, VELOCITY[role],
                              open_for_melody=open_rh_for_melody and role == "rh")
            start_bar(bars[0], song, the_clef)
            for m in bars:
                part.append(m)
        order += [rh, lh]
        full.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace",
                                         barTogether=True))
        parts["piano"] = single(rh, lh, group=True)
        add_chord_symbols(parts["piano"].parts[0], timeline)  # chords above the right hand

    if "bass" in wanted and pat["bass"] == "none":
        notes.append(f"The {style} style has no bass, so there's no bass part.")
    elif "bass" in wanted:
        bass = new_part(stream.Part, "Bass", instrument.ElectricBass(), PROGRAM["bass"])
        bass.getElementsByClass(instrument.Instrument).first().transposition = interval.Interval("-P8")
        bass.atSoundingPitch = False
        if pat["bass"] == "walk":
            bars = walk_bars(song, timeline, VELOCITY["bass"])
        elif isinstance(pat["bass"], dict):
            bars = line_bars(song, timeline, VELOCITY["bass"], pat["bass"]["line"], pat["bass"]["every"])
        else:
            bars = build_role(song, "bass", pat["bass"], timeline, VELOCITY["bass"])
        start_bar(bars[0], song, clef.BassClef())
        for m in bars:
            bass.append(m)
        order.append(bass)
        parts["bass"] = single(bass, chords=True)

    if "drums" in wanted and pat.get("drums") == "none":
        notes.append(f"The {style} style has no drums, so there's no drum part.")
    elif "drums" in wanted:
        kit, kit_perf = drums.build(song, pat.get("drums"), bar_window)
        order.append(kit)
        perf_extra.append(kit_perf)
        parts["drums"] = single(kit)

    for part in order:
        full.insert(0, part)
    if order:
        add_tempo(full, song)
    feel = styles.get(style).feel if styles.get(style) else "straight"
    if feel != "straight":
        for s in [full, *parts.values()]:
            mark_feel(s, feel)
    excluded = [i for i in INSTRUMENTS if i not in parts]
    return Arrangement(style, full, parts, notes, [i for i in wanted if i in parts], excluded, perf_extra)


def mark_feel(s: stream.Score, feel: str) -> None:
    """"Swing" or "Shuffle" over the first bar of the top staff: play the eighths long-short."""
    if not s.parts:
        return
    first = s.parts[0].getElementsByClass(stream.Measure).first()
    if first is not None:
        text = expressions.TextExpression(feel.title())
        text.style.fontStyle = "bold"
        text.placement = "above"
        first.insert(0, text)


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
