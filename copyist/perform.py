"""Expressive performance (SPEC section 6, step 2).

Turns the plain arrangement MIDI, every note at one velocity and exactly on
the grid, into a performance, without changing a single note:

- dynamics: each phrase rises and settles, the band builds across the song
  (soft open → full middle → settle), strong beats lean, the melody sings
  over the band and swells with its contour, and no two notes are hit quite
  alike;
- timing: small human variation, the melody a hair ahead of the band, piano
  chords rolled upward by a few milliseconds, a breath at each phrase end, and
  a ritardando into the last chord, which then rings;
- touch: a legato melody, a tighter bass, and sustain pedal on the piano,
  changed with the harmony;
- feel: in a swing or shuffle style, off-beat eighths land late (at two
  thirds of the beat for a full swing), as they're played, not as written.

Everything comes from a seed, so the same song and seed give the same MIDI.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import mido

PHRASE_BARS = 4
SIGMA_MS = {"melody": 7.0, "piano_rh": 5.0, "piano_lh": 5.0, "bass": 5.0, "drums": 4.0, "other": 5.0}
MELODY_LEAD_MS = 8.0
ROLL_MS = 7.0          # per note of a piano chord, bottom up
METRIC = {"down": 1.08, "secondary": 1.03, "beat": 0.97, "off": 0.92}
RIT_TO = 0.80          # the final tempo, as a share of the written tempo
BREATH = 0.95          # tempo on the last beat of each phrase
BAND_ROLES = frozenset({"piano_rh", "piano_lh", "bass", "drums", "other"})


def form_build(bar: int, n_bars: int) -> float:
    """How loud the band sits in the song: soft open → full → settle at the end.

    The melody is left alone so the tune stays clear; accompaniment follows this.
    """
    if n_bars <= 4 or bar < 0:
        return 1.0
    x = bar / (n_bars - 1)
    if x < 0.35:
        return 0.70 + 0.30 * (x / 0.35)
    if x > 0.80:
        return 1.0 - 0.18 * ((x - 0.80) / 0.20)
    return 1.0


@dataclass
class Note:
    track: int
    channel: int
    pitch: int
    start: int
    end: int
    velocity: int
    off_velocity: int = 64


@dataclass
class Shape:
    """What the performer knows about the song's time."""
    beats: int                 # beats in a bar
    beat_q: float              # a beat, in quarter notes
    pickup_q: float            # the pickup, in quarter notes (0 if none)
    tpq: int                   # MIDI ticks per quarter note
    bar_q: float = field(init=False)

    def __post_init__(self):
        self.bar_q = self.beats * self.beat_q

    def where(self, tick: int) -> tuple[int, float]:
        """(full bar index, position in that bar in quarters); the pickup is bar -1."""
        q = tick / self.tpq
        if q < self.pickup_q - 1e-6:
            return -1, self.bar_q - self.pickup_q + q
        rel = q - self.pickup_q
        bar = int(rel // self.bar_q + 1e-9)
        return bar, rel - bar * self.bar_q

    def strength(self, tick: int) -> str:
        _, pos = self.where(tick)
        b = pos / self.beat_q
        if abs(b) < 0.02:
            return "down"
        if abs(b - round(b)) < 0.02:
            return "secondary" if self.beats == 4 and round(b) == 2 else "beat"
        return "off"


def shape_for(meter: str, pickup_q: float, tpq: int) -> Shape:
    num, den = (int(x) for x in meter.split("/"))
    if den == 8 and num % 3 == 0 and num > 3:           # compound: dotted-quarter beats
        return Shape(num // 3, 1.5, pickup_q, tpq)
    return Shape(num, 4 / den, pickup_q, tpq)


# ------------------------------------------------------------------ reading

def read(mid: mido.MidiFile) -> tuple[list[Note], list[list[tuple[int, mido.Message]]]]:
    """Notes, and every other event per track at its absolute tick."""
    notes, others = [], []
    for ti, track in enumerate(mid.tracks):
        t, open_, rest = 0, {}, []
        for msg in track:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                open_.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type in ("note_off", "note_on"):
                stack = open_.get((msg.channel, msg.note))
                if stack:
                    start, vel = stack.pop(0)
                    notes.append(Note(ti, msg.channel, msg.note, start, t, vel,
                                      msg.velocity if msg.type == "note_off" else 64))
            elif msg.type != "end_of_track":
                rest.append((t, msg))
        others.append(rest)
    return notes, others


def roles(mid: mido.MidiFile, notes: list[Note]) -> dict[int, str]:
    """Each track's job, from its name and channel."""
    names = {ti: next((m.name for m in tr if m.type == "track_name"), "") for ti, tr in enumerate(mid.tracks)}
    by_track: dict[int, list[Note]] = {}
    for n in notes:
        by_track.setdefault(n.track, []).append(n)
    out, pianos = {}, []
    for ti, ns in by_track.items():
        name = names[ti].lower()
        if any(n.channel == 9 for n in ns):
            out[ti] = "drums"
        elif "voice" in name or "vocal" in name or "melody" in name:
            out[ti] = "melody"
        elif "bass" in name:
            out[ti] = "bass"
        elif "piano" in name:
            pianos.append(ti)
        else:
            out[ti] = "other"
    if pianos:
        mean = {ti: sum(n.pitch for n in by_track[ti]) / len(by_track[ti]) for ti in pianos}
        top = max(pianos, key=mean.get)
        for ti in pianos:
            out[ti] = "piano_rh" if ti == top else "piano_lh"
    return out


# ------------------------------------------------------------------ shaping

def phrase_arc(x: float) -> float:
    """Loudness across a phrase (x from 0 to 1): rises to a peak at 60%, settles at the end."""
    if x < 0.6:
        return 0.92 + 0.16 * x / 0.6
    return 1.08 - 0.18 * (x - 0.6) / 0.4


def swing_notes(notes: list[Note], shape: Shape, ratio: float) -> int:
    """Move off-beat eighths (starts and ends) to `ratio` of the beat; returns how many notes moved."""
    if ratio <= 0.5 + 1e-6 or shape.beat_q != 1.0:
        return 0
    delay = round((ratio - 0.5) * shape.tpq)

    def swung(tick: int) -> int:
        _, pos = shape.where(tick)
        return tick + delay if abs(pos % 1.0 - 0.5) < 0.01 else tick
    moved = 0
    for n in notes:
        start, end = swung(n.start), swung(n.end)
        moved += start != n.start
        n.start, n.end = start, max(start + 1, end)
    return moved


def write(mid: mido.MidiFile, notes: list[Note], others, midi_out: Path, extra=None) -> None:
    """Write notes and every other event back out, track by track; `extra` adds events per track."""
    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    for ti in range(len(mid.tracks)):
        events: list[tuple[int, int, mido.Message]] = [(t, 0, msg) for t, msg in others[ti]]
        if extra:
            events = extra(ti, events)
        for n in notes:
            if n.track == ti:
                events.append((n.start, 2, mido.Message("note_on", channel=n.channel, note=n.pitch, velocity=n.velocity)))
                events.append((n.end, 0, mido.Message("note_off", channel=n.channel, note=n.pitch, velocity=n.off_velocity)))
        events.sort(key=lambda e: (e[0], e[1]))
        track, now = mido.MidiTrack(), 0
        for t, _, msg in events:
            track.append(msg.copy(time=t - now))
            now = t
        track.append(mido.MetaMessage("end_of_track", time=0))
        out.tracks.append(track)
    out.save(str(midi_out))


def swing_only(midi_in: Path, midi_out: Path, meter: str, pickup_q: float, ratio: float) -> int:
    """Just the feel, for `--plain`: swung eighths, nothing else changed."""
    mid = mido.MidiFile(str(midi_in))
    notes, others = read(mid)
    moved = swing_notes(notes, shape_for(meter, float(pickup_q), mid.ticks_per_beat), ratio)
    write(mid, notes, others, midi_out)
    return moved


def perform(midi_in: Path, midi_out: Path, meter: str, pickup_q: float = 0.0, seed: int = 1,
            phrase_bars: int = PHRASE_BARS, swing: float = 0.5, melody_legato: bool = True) -> dict:
    """Write an expressive performance of `midi_in` to `midi_out`; returns what was done, for the report.

    `melody_legato` overlaps successive melody notes (good for a wind sample). Turn it off when the
    melody is on the piano: overlapping hammers click.
    """
    mid = mido.MidiFile(str(midi_in))
    tpq = mid.ticks_per_beat
    notes, others = read(mid)
    if not notes:
        mid.save(str(midi_out))
        return {"notes": 0}
    rng = random.Random(seed)
    shape = shape_for(meter, float(pickup_q), tpq)
    swung = swing_notes(notes, shape, swing)
    role = roles(mid, notes)
    tempos = [(t, m.tempo) for tr in others for t, m in tr if m.type == "set_tempo"]
    base_tempo = min(tempos)[1] if tempos else 500000              # microseconds per quarter
    ticks_per_ms = tpq * 1000 / base_tempo
    end_tick = max(n.end for n in notes)
    last_bar, _ = shape.where(end_tick - 1)
    n_bars = last_bar + 1
    n_phrases = max(1, math.ceil(n_bars / phrase_bars))
    melody_pitches = sorted(n.pitch for n in notes if role.get(n.track) == "melody")
    median = melody_pitches[len(melody_pitches) // 2] if melody_pitches else 60

    # Dynamics
    for n in sorted(notes, key=lambda n: (n.start, n.track, n.pitch)):
        r = role.get(n.track, "other")
        bar, pos = shape.where(n.start)
        x = 0.0 if bar < 0 else ((bar % phrase_bars) + pos / shape.bar_q) / phrase_bars
        phrase = max(0, bar) // phrase_bars
        song_arc = 1 + 0.06 * math.sin(math.pi * (phrase + 0.5) / n_phrases)
        arc = phrase_arc(x) * song_arc
        if r in BAND_ROLES:
            arc *= form_build(bar, n_bars)
        metric = METRIC[shape.strength(n.start)]
        v = float(n.velocity)
        if r == "drums":
            v *= metric ** 1.5 * math.sqrt(arc)
            v += rng.gauss(0, 5)
        else:
            v *= metric * arc
            if r == "melody":
                v += (n.pitch - median) * 0.8
            v += rng.gauss(0, 3)
        n.velocity = max(1, min(127, round(v)))

    # Timing: human variation, the melody's lead, rolled piano chords
    def ms(x: float) -> int:
        return round(x * ticks_per_ms)

    # Notes that start together in one track move together (a chord is one gesture).
    groups: dict[tuple[int, int], list[Note]] = {}
    for n in notes:
        groups.setdefault((n.track, n.start), []).append(n)
    for (track, _), group in sorted(groups.items()):
        r = role.get(track, "other")
        sigma = SIGMA_MS.get(r, 5.0)
        shift = max(-2.5 * sigma, min(2.5 * sigma, rng.gauss(0, sigma)))
        if r == "melody":
            shift -= MELODY_LEAD_MS
        roll = r == "piano_rh" and len(group) > 1
        for k, m in enumerate(sorted(group, key=lambda m: m.pitch)):
            d = ms(shift + (ROLL_MS * k if roll else 0))
            m.start = max(0, m.start + d)
            m.end = max(m.start + ms(30), m.end + d)

    # Touch: legato melody (or a clean release on piano), tighter bass, the last chord rings
    melody_fix = "legato" if melody_legato else "piano"
    for r, fix in (("melody", melody_fix), ("bass", "tight")):
        line = sorted((n for n in notes if role.get(n.track) == r), key=lambda n: n.start)
        for a, b in zip(line, line[1:]):
            gap = b.start - a.end
            if fix == "legato" and -ms(10) < gap < ms(40):
                # overlap into the next note, except on a repeated pitch, which the overlap would cut off
                a.end = b.start + ms(15) if a.pitch != b.pitch else b.start - ms(5)
            elif fix == "piano" and gap < ms(40):
                # release just before the next hammer; no overlap
                a.end = max(a.start + ms(40), b.start - ms(8))
            elif fix == "tight":
                a.end = min(a.end, b.start - ms(10))
                a.end = max(a.start + ms(40), a.start + round((a.end - a.start) * 0.92))
    final_end = max(n.end for n in notes if role.get(n.track) != "drums") if any(
        role.get(n.track) != "drums" for n in notes) else end_tick
    ring = round(shape.beat_q * tpq)
    for n in notes:
        if role.get(n.track) != "drums" and n.end >= final_end - ms(60):
            n.end += ring

    # Sustain pedal on the piano, changed when the left hand moves
    pedal: list[tuple[int, int]] = []
    piano_tracks = [ti for ti, r in role.items() if r in ("piano_rh", "piano_lh")]
    if piano_tracks:
        lh = sorted((n for n in notes if role.get(n.track) == "piano_lh"), key=lambda n: n.start) or \
            sorted((n for n in notes if n.track in piano_tracks), key=lambda n: n.start)
        changes, last = [], None
        for n in lh:
            bar, pos = shape.where(n.start)
            if last is None or n.pitch != last.pitch or shape.strength(n.start) == "down":
                if not changes or n.start - changes[-1] > ms(50):
                    changes.append(n.start)
            last = n
        for i, t in enumerate(changes):
            if i:
                pedal.append((max(0, t - ms(15)), 0))
            pedal.append((t + ms(25), 127))
        pedal.append((max(n.end for n in notes if n.track in piano_tracks), 0))
        pedal_track = next((ti for ti in piano_tracks if role[ti] == "piano_rh"), piano_tracks[0])
        pedal_channel = next(n.channel for n in notes if n.track == pedal_track)

    # Tempo: a breath at each phrase end, and a ritardando over the last two bars
    tempo_events: list[tuple[int, int]] = []
    beat_ticks = round(shape.beat_q * tpq)
    first_full = round(shape.pickup_q * tpq)
    bar_ticks = round(shape.bar_q * tpq)
    rit_bars = 2 if n_bars >= 6 else 1
    rit_start = first_full + (n_bars - rit_bars) * bar_ticks
    for p in range(1, n_phrases):
        last_beat = first_full + p * phrase_bars * bar_ticks - beat_ticks
        if last_beat < rit_start:
            tempo_events += [(last_beat, round(base_tempo / BREATH)), (last_beat + beat_ticks, base_tempo)]
    beats = max(1, round((end_tick - rit_start) / beat_ticks))
    for k in range(beats + 1):
        factor = 1 - (1 - RIT_TO) * min(1, k / beats)
        tempo_events.append((rit_start + k * beat_ticks, round(base_tempo / factor)))

    # Writing
    def extra(ti, events):
        if ti == 0:
            events = [e for e in events if e[2].type != "set_tempo" or e[0] < rit_start] + \
                     [(t, 0, mido.MetaMessage("set_tempo", tempo=v)) for t, v in tempo_events]
        if piano_tracks and ti == pedal_track:
            events += [(t, 1, mido.Message("control_change", channel=pedal_channel, control=64, value=v))
                       for t, v in pedal]
        return events
    write(mid, notes, others, midi_out, extra)
    return {"notes": len(notes), "seed": seed, "phrases": n_phrases, "pedal_changes": len(pedal) // 2,
            "ritardando_bars": rit_bars, "timing_ms": max(SIGMA_MS.values()) * 2.5 + MELODY_LEAD_MS,
            "swing": swing if swung else 0.5, "swung_notes": swung, "form_build": True}


def pickup_of(song) -> Fraction:
    from .yue import tune_events
    return tune_events(song)[3]
