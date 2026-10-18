"""Drum kit parts (SPEC.md section 7): a groove per style, fills and crashes.

The same list of hits builds two things: the drum part as notation (a
percussion staff with hands stems up and feet stems down) and a performance
part for MIDI on the General MIDI drum channel. Building both from one list
keeps what's written and what's heard identical.
"""
from __future__ import annotations

from dataclasses import dataclass

from music21 import clef, instrument, meter, note, percussion, stream

# piece: (display step, display octave, notehead or None, GM drum note, velocity)
KIT = {
    "kick": ("F", 4, None, 36, 96),
    "snare": ("C", 5, None, 38, 88),
    "sidestick": ("C", 5, "x", 37, 70),
    "hihat": ("G", 5, "x", 42, 62),
    "crash": ("A", 5, "x", 49, 100),
    "hihat-open": ("G", 5, "circle-x", 46, 70),
    "hihat-pedal": ("D", 4, "x", 44, 60),
    "ride": ("F", 5, "x", 51, 66),
    "tom": ("E", 5, None, 45, 84),
    "floor-tom": ("A", 4, None, 41, 86),
    "tambourine": ("B", 5, "x", 54, 60),
    "clap": ("D", 5, "x", 39, 80),
}

# Grooves come from the style (copyist/styles/): hands and feet as (start,
# length, pieces) within a full bar, in quarter notes, plus a fill that
# replaces the end of the bar.
FILL_EVERY = 8  # bars


def groove_for(spec: dict | list | None, ts: meter.TimeSignature) -> dict | list:
    """The style's groove (one bar, or a cycling phrase of bars), or a plain beat-by-beat groove."""
    if isinstance(spec, list):
        return [groove_for(g, ts) for g in spec]
    if spec:
        return {k: [(s, d, list(pieces)) for s, d, pieces in spec[k]] for k in ("hands", "feet", "fill")}
    beats = ts.beatCount
    beat = ts.beatDuration.quarterLength
    return {
        "hands": [(i * beat, beat, ["hihat"]) for i in range(beats)],
        "feet": [(0, beat, ["kick"])],
        "fill": [((beats - 1) * beat, beat / 2, ["snare"]), ((beats - 0.5) * beat, beat / 2, ["snare"])],
    }


def groove_bar(groove: dict | list, n_in_song: int) -> dict:
    """The groove for full-bar number `n_in_song` (1 = first full bar)."""
    if isinstance(groove, list):
        return groove[(max(n_in_song, 1) - 1) % len(groove)]
    return groove


@dataclass
class Hit:
    start: float   # quarter notes from the start of the bar, as written
    length: float
    pieces: list[str]


def bar_hits(groove: dict, n_in_song: int, is_last: bool, after_fill: bool, length: float,
             lo: float, hi: float) -> tuple[list[Hit], list[Hit]]:
    """Hands and feet hits for one bar, clipped to the part of the bar that exists."""
    if is_last:
        return [Hit(0, length, ["crash"])], [Hit(0, length, ["kick"])]
    hands = [list(e) for e in groove["hands"]]
    feet = [list(e) for e in groove["feet"]]
    if n_in_song % FILL_EVERY == 0:
        fill_start = min(s for s, _, _ in groove["fill"])
        hands = [e for e in hands if e[0] < fill_start] + [list(e) for e in groove["fill"]]
        feet = [e for e in feet if e[0] < fill_start]
    if after_fill or n_in_song == 1:
        for e in hands:
            if e[0] == 0:
                e[2] = ["crash" if p == "hihat" else p for p in e[2]]
    def clip(events):
        out = []
        for s, d, pieces in events:
            a, b = max(s, lo), min(s + d, hi)
            if b > a:
                out.append(Hit(a - lo, b - a, list(pieces)))
        return out
    return clip(hands), clip(feet)


def unpitched(piece: str, length: float, stem: str):
    step, octave, head, _, _ = KIT[piece]
    u = note.Unpitched(displayName=f"{step}{octave}", quarterLength=length)
    if head:
        u.notehead = head
    u.stemDirection = stem
    return u


def voice_from(hits: list[Hit], length: float, stem: str, voice_id: str) -> stream.Voice:
    v = stream.Voice(id=voice_id)
    t = 0.0
    for h in sorted(hits, key=lambda h: h.start):
        if h.start > t + 1e-9:
            v.insert(t, note.Rest(quarterLength=h.start - t))
        if len(h.pieces) == 1:
            el = unpitched(h.pieces[0], h.length, stem)
        else:
            el = percussion.PercussionChord([unpitched(p, h.length, stem) for p in h.pieces])
            el.quarterLength = h.length
            el.stemDirection = stem
        v.insert(h.start, el)
        t = h.start + h.length
    if t < length - 1e-9:
        v.insert(t, note.Rest(quarterLength=length - t))
    return v


def build(song, spec: dict | list | None, bar_window) -> tuple[stream.Part, stream.Part]:
    """(notation part, performance part) for the drum kit, playing the style's groove (`spec`)."""
    melody_bars = list(song.melody.getElementsByClass(stream.Measure))
    ts = meter.TimeSignature(song.meter)
    full = ts.barDuration.quarterLength
    groove = groove_for(spec, ts)

    notation = stream.Part()
    notation.partName, notation.partAbbreviation = "Drums", "Dr."
    kit = instrument.Percussion()
    kit.partName, kit.partAbbreviation = "Drums", "Dr."
    notation.insert(0, kit)

    perf = stream.Part()
    perf.partName = "Drums"
    perf_kit = instrument.UnpitchedPercussion()
    perf_kit.midiChannel = 9
    perf.insert(0, perf_kit)

    first_full = 0 if bar_window(melody_bars[0], full, True)[2] < full else 1
    after_fill = False
    for i, mb in enumerate(melody_bars):
        lo, hi, length = bar_window(mb, full, first=i == 0)
        m = stream.Measure(number=mb.number)
        m.paddingLeft = mb.paddingLeft
        if i == 0:
            m.insert(0, clef.PercussionClef())
            m.insert(0, meter.TimeSignature(song.meter))
        n_in_song = i + first_full if first_full == 1 else i  # 1 = first full bar
        is_pickup = i == 0 and length < full
        if is_pickup:
            m.insert(0, note.Rest(quarterLength=length))
            hands, feet = [], []
        else:
            hands, feet = bar_hits(groove_bar(groove, n_in_song), n_in_song,
                                   i == len(melody_bars) - 1, after_fill, length, lo, hi)
            m.insert(0, voice_from(hands, length, "up", "1"))
            m.insert(0, voice_from(feet, length, "down", "2"))
        after_fill = (not is_pickup) and n_in_song % FILL_EVERY == 0
        if mb.rightBarline is not None:
            m.rightBarline = mb.rightBarline
        notation.append(m)

        # Performance bar: the same hits as GM drum notes (MIDI wants measures
        # in every part when the others have them).
        pm = stream.Measure(number=mb.number)
        pm.paddingLeft = mb.paddingLeft
        if i == 0:
            pm.insert(0, meter.TimeSignature(song.meter))
        for h in hands + feet:
            for piece in h.pieces:
                _, _, _, gm, velocity = KIT[piece]
                n = note.Note(quarterLength=min(h.length, 0.5))
                n.pitch.midi = gm
                n.volume.velocity = velocity
                pm.insert(h.start, n)
        if not hands and not feet:
            pm.insert(0, note.Rest(quarterLength=length))
        perf.append(pm)
    return notation, perf
