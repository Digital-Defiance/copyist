"""Transcribing a recording into a lead sheet (`copyist transcribe`, SPEC section 12, docs/transcribing.md).

Copyist's own transcriber, all open code: beats and bars from the accompaniment, chords from its
chroma, the sung melody from the vocal's pitch track. Wherever the audio leaves a doubt, the music
around it decides (SPEC 12.2a): the key and the chord underneath, the beat, and the shape of the line.
What it can't settle is kept as a doubt for the person to choose by ear.

The result is written as a score in the planner's ABC dialect (`abcplan`), so the same path as melody
writing (`write.song_from_plan`) turns it into a Copyist song file with the lyrics fitted under it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np

SR = 22050
HOP = 512                       # chroma and onsets
PITCH_HOP = 256                 # the vocal's pitch track
NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
# Chord qualities: intervals above the root, and how they're written.
QUALITIES = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "sus4": (0, 5, 7),
    "dim": (0, 3, 6),
}
# Krumhansl-Kessler key profiles.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)


# ---------------------------------------------------------------- audio

def load(path: Path, sr: int = SR) -> np.ndarray:
    import librosa
    y, _ = librosa.load(str(path), sr=sr, mono=True)
    return y


@dataclass
class Stems:
    """The recording, split. `accompaniment` is everything but the voice; `bass` may be None."""
    mix: np.ndarray
    vocals: np.ndarray
    accompaniment: np.ndarray
    bass: np.ndarray | None = None


def stems_from_files(mix: Path, vocals: Path, accompaniment: Path | None = None, bass: Path | None = None) -> Stems:
    y = load(mix)
    v = load(vocals)
    n = min(len(y), len(v))
    acc = load(accompaniment)[:n] if accompaniment else y[:n] - v[:n]
    b = load(bass) if bass else None
    return Stems(y[:n], v[:n], acc, b[:n] if b is not None else None)


# ---------------------------------------------------------------- beats and bars

@dataclass
class Grid:
    beats: np.ndarray              # beat times, seconds
    beats_per_bar: int
    first_downbeat: int            # index into `beats`
    tempo: float                   # beats a minute

    def position(self, t: float) -> float:
        """Time in seconds -> beats from the first downbeat (fractional; extrapolated outside)."""
        b = self.beats
        period = 60.0 / self.tempo
        if t <= b[0]:
            idx = (t - b[0]) / period
        elif t >= b[-1]:
            idx = len(b) - 1 + (t - b[-1]) / period
        else:
            k = int(np.searchsorted(b, t) - 1)
            idx = k + (t - b[k]) / (b[k + 1] - b[k])
        return idx - self.first_downbeat


def beat_times(acc: np.ndarray, vocals: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Beats from the band's onsets and the singer's together, with a steady tempo (songs rarely
    drift much, and a tight tracker won't wander onto the off-beats in a sparse intro)."""
    import librosa
    env = librosa.onset.onset_strength(y=acc, sr=SR, hop_length=HOP)
    env = env / (env.max() + 1e-9)
    if vocals is not None:
        ev = librosa.onset.onset_strength(y=vocals, sr=SR, hop_length=HOP)
        n = min(len(env), len(ev))
        env = env[:n] + ev[:n] / (ev.max() + 1e-9)
    tempo, frames = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP, start_bpm=100, tightness=400)
    tempo = float(np.atleast_1d(tempo)[0])
    times = librosa.frames_to_time(frames, sr=SR, hop_length=HOP)
    return times, tempo


def beat_chroma(y: np.ndarray, beats: np.ndarray, low: bool = False) -> np.ndarray:
    """Chroma averaged between beats: shape (n_beats, 12). `low` looks only below middle C (the bass)."""
    import librosa
    if low:
        c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, fmin=librosa.note_to_hz("C1"), n_octaves=3)
    else:                       # above the bass, so a walking or alternating bass doesn't rename the chord
        c = librosa.feature.chroma_cqt(y=y, sr=SR, hop_length=HOP, fmin=librosa.note_to_hz("C3"), n_octaves=4)
    frames = librosa.time_to_frames(beats, sr=SR, hop_length=HOP)
    frames = np.append(frames, c.shape[1])
    out = np.zeros((len(beats), 12))
    for k in range(len(beats)):
        a, b = frames[k], max(frames[k] + 1, frames[k + 1])
        out[k] = c[:, a:b].mean(axis=1) if a < c.shape[1] else 0
    return out


# ---------------------------------------------------------------- key

def key_of(chroma_total: np.ndarray) -> tuple[int, bool, float]:
    """(tonic pitch class, minor?, confidence) by correlation with the Krumhansl profiles."""
    scores = []
    for tonic in range(12):
        for minor, prof in ((False, MAJOR_PROFILE), (True, MINOR_PROFILE)):
            scores.append((np.corrcoef(chroma_total, np.roll(prof, tonic))[0, 1], tonic, minor))
    scores.sort(reverse=True)
    best, second = scores[0], scores[1]
    return best[1], best[2], float(best[0] - second[0])


def key_name(tonic: int, minor: bool) -> str:
    flats = {"major": {5, 10, 3, 8, 1}, "minor": {2, 7, 0, 5, 10, 3}}       # keys spelled with flats
    names_sharp = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    names_flat = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
    use_flat = tonic in flats["minor" if minor else "major"]
    name = (names_flat if use_flat else names_sharp)[tonic]
    return name + ("m" if minor else "")


def scale_of(tonic: int, minor: bool) -> set[int]:
    return {(tonic + i) % 12 for i in (MINOR_SCALE if minor else MAJOR_SCALE)}


# ---------------------------------------------------------------- chords

@dataclass
class Chord:
    root: int                      # pitch class, -1 for no chord
    quality: str
    bass: int = -1                 # slash bass pitch class, -1 if the root

    def tones(self) -> set[int]:
        return {(self.root + i) % 12 for i in QUALITIES[self.quality]} if self.root >= 0 else set()

    def name(self, key_tonic: int = 0, minor: bool = False) -> str:
        if self.root < 0:
            return ""
        flat_key = key_name(key_tonic, minor).replace("m", "")[1:2] == "b" or key_name(key_tonic, minor) in ("F", "Dm")
        spell = (lambda pc: ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"][pc]) if flat_key else \
            (lambda pc: ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][pc])
        text = spell(self.root) + self.quality
        if self.bass >= 0 and self.bass != self.root:
            text += "/" + spell(self.bass)
        return text


CHORDS = [Chord(r, q) for r in range(12) for q in QUALITIES]


def _template(ch: Chord) -> np.ndarray:
    t = np.zeros(12)
    for i, iv in enumerate(QUALITIES[ch.quality]):
        t[(ch.root + iv) % 12] = 1.0 if i < 3 else 0.6
    t[ch.root] += 0.3
    return t / np.linalg.norm(t)


TEMPLATES = np.array([_template(c) for c in CHORDS])
# Plain triads unless the audio clearly says otherwise.
QUALITY_PRIOR = {"": 0.0, "m": 0.0, "7": -0.03, "m7": -0.04, "maj7": -0.08, "sus4": -0.12, "dim": -0.1}
PRIOR = np.array([QUALITY_PRIOR[c.quality] for c in CHORDS])


@dataclass
class ChordReading:
    chords: list[Chord]            # one per beat
    margin: list[float]            # how far the chosen chord beat the runner-up (small = doubtful)
    runner_up: list[Chord]


def read_chords(chroma: np.ndarray, bass_chroma: np.ndarray | None, key: tuple[int, bool],
                beat_cost: list[float] | None = None, change_cost: float = 0.25,
                downbeats: list[bool] | None = None) -> ChordReading:
    """A chord for every beat: chroma against chord templates, the bass's note favouring roots, the
    key favouring its own chords, and a Viterbi path that only changes chord when it pays. `beat_cost`
    gives the cost of a change on each beat (cheap on downbeats, dear in the middle of a bar)."""
    norm = chroma / (np.linalg.norm(chroma, axis=1, keepdims=True) + 1e-9)
    emit = norm @ TEMPLATES.T + PRIOR                           # (beats, chords) cosine similarity
    tonic, minor = key
    diatonic = scale_of(tonic, minor)
    in_key = np.array([1.0 if c.tones() <= diatonic else 0.0 for c in CHORDS])
    emit = emit + 0.08 * in_key
    if bass_chroma is not None:
        bnorm = bass_chroma / (bass_chroma.max(axis=1, keepdims=True) + 1e-9)
        roots = np.array([c.root for c in CHORDS])
        # The bass on a downbeat is usually the root; between them it walks or alternates.
        weight = np.array([0.25 if downbeats and downbeats[t] else 0.08 for t in range(len(chroma))])
        emit = emit + weight[:, None] * bnorm[:, roots]
    n, m = emit.shape
    score = np.full((n, m), -np.inf)
    back = np.zeros((n, m), dtype=int)
    score[0] = emit[0]
    for t in range(1, n):
        cost = beat_cost[t] if beat_cost else change_cost
        best_prev = int(np.argmax(score[t - 1]))
        stay = score[t - 1]
        move = score[t - 1, best_prev] - cost
        take_move = move > stay
        score[t] = np.where(take_move, move, stay) + emit[t]
        back[t] = np.where(take_move, best_prev, np.arange(m))
    path = [int(np.argmax(score[-1]))]
    for t in range(n - 1, 0, -1):
        path.append(int(back[t, path[-1]]))
    path.reverse()
    chords, margins, runners = [], [], []
    for t, k in enumerate(path):
        order = np.argsort(-emit[t])
        other = next(j for j in order if j != k)
        chords.append(CHORDS[k])
        margins.append(float(emit[t, k] - emit[t, other]))
        runners.append(CHORDS[other])
    # A slash bass where the bass clearly plays another chord tone.
    if bass_chroma is not None:
        for t, ch in enumerate(chords):
            starts = t == 0 or (chords[t - 1].root, chords[t - 1].quality) != (ch.root, ch.quality)
            b = int(np.argmax(bass_chroma[t]))
            if starts and b != ch.root and b in ch.tones() and bass_chroma[t, b] > 1.5 * bass_chroma[t, ch.root]:
                chords[t] = Chord(ch.root, ch.quality, b)
    return ChordReading(chords, margins, runners)


# ---------------------------------------------------------------- meter and downbeats

# ---------------------------------------------------------------- the sung melody

@dataclass
class HeardNote:
    start: float                   # seconds
    end: float
    midi: float                    # median pitch, fractional
    candidates: list[int] = field(default_factory=list)
    attack: bool = False           # it starts with a new syllable on the same pitch as the note before
    spread: float = 0.0            # how much the pitch wanders inside it, in semitones (a slide wanders)


def vocal_track(vocals: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import librosa
    f0, voiced, prob = librosa.pyin(vocals, fmin=70.0, fmax=1000.0, sr=SR, frame_length=2048, hop_length=PITCH_HOP)
    times = librosa.frames_to_time(np.arange(len(f0)), sr=SR, hop_length=PITCH_HOP)
    midi = np.where(voiced, librosa.hz_to_midi(np.where(voiced, f0, 440.0)), np.nan)
    rms = librosa.feature.rms(y=vocals, frame_length=2048, hop_length=PITCH_HOP)[0][:len(midi)]
    return times, midi, rms


def vocal_notes(times: np.ndarray, midi: np.ndarray, rms: np.ndarray, onsets: np.ndarray,
                min_len: float = 0.08, jump: float = 0.7) -> list[HeardNote]:
    """Voiced runs of the pitch track, split where the pitch moves to a new note and holds there, or
    where a new syllable starts on the same pitch (an onset with a dip in loudness before it)."""
    from scipy.ndimage import median_filter
    voiced = ~np.isnan(midi)
    smooth = midi.copy()
    smooth[voiced] = median_filter(np.nan_to_num(midi, nan=0.0), size=5)[voiced]
    dt = times[1] - times[0]
    hold = max(2, int(0.05 / dt))
    notes: list[HeardNote] = []
    onset_frames = set(np.round(onsets / dt).astype(int).tolist())
    k, n = 0, len(midi)
    attack = False
    while k < n:
        if not voiced[k]:
            k += 1
            attack = False
            continue
        start = k
        cur = [smooth[k]]
        k += 1
        split_by_attack = False
        while k < n and voiced[k]:
            ref = float(np.median(cur[-max(1, min(len(cur), 12)):]))
            ahead = smooth[k:k + hold]
            moved = len(ahead) == hold and np.all(~np.isnan(ahead)) and np.all(np.abs(ahead - ref) > jump)
            # A new syllable on the same pitch: an onset (backtracked to the dip before it) that the
            # loudness climbs out of again.
            new_syllable = k in onset_frames and len(cur) * dt > min_len and \
                rms[k:k + 8].max() > 1.25 * rms[max(start, k - 2):k + 1].min()
            if moved or new_syllable:
                split_by_attack = new_syllable and not moved
                break
            cur.append(smooth[k])
            k += 1
        if (k - start) * dt >= min_len:
            core = np.array(cur[len(cur) // 5: max(len(cur) // 5 + 1, len(cur) - len(cur) // 5)])
            notes.append(HeardNote(times[start], times[min(k, n - 1)], float(np.median(core)), attack=attack,
                                   spread=float(np.std(cur))))
        attack = split_by_attack
    return notes


def clean_notes(notes: list[HeardNote], times: np.ndarray, midi: np.ndarray, rms: np.ndarray,
                target: int | None = None, gate: float = 0.12, short: float = 0.15) -> list[HeardNote]:
    """Tidy what the pitch track heard into sung notes.

    1. Drop quiet notes: other instruments bleeding into the vocal stem (the intro, mostly).
    2. Drop notes far outside the body of the line (octave errors and stray partials).
    3. Fold short fragments into the neighbour nearest in pitch: scoops, slides and vibrato that the
       tracker cut into pieces.
    4. Join neighbours on the same pitch with no gap: one note the tracker split.
    5. If the number of sung syllables is known (`target`, from the lyrics), keep folding the most
       doubtful fragments until the notes are within reach of it: the words fix the count.
    """
    if not notes:
        return notes
    voiced = ~np.isnan(midi)
    loud = float(np.percentile(rms[voiced], 95)) if voiced.any() else 1.0

    def level(n):
        a, b = np.searchsorted(times, [n.start, n.end])
        return float(rms[a:max(a + 1, b)].mean()) / (loud + 1e-9)

    kept = [n for n in notes if level(n) >= gate]
    if not kept:
        return kept
    body = np.array([n.midi for n in kept])
    lo, hi = np.percentile(body, 5) - 7, np.percentile(body, 95) + 7
    kept = [n for n in kept if lo <= n.midi <= hi]

    def merge(i, j):
        """Join neighbours i and j; the joined note keeps the longer one's pitch (the other was a
        scoop, a slide or a wobble on the way)."""
        a, b = kept[min(i, j)], kept[max(i, j)]
        pitch = a.midi if (a.end - a.start) >= (b.end - b.start) else b.midi
        kept[min(i, j)] = HeardNote(a.start, b.end, pitch, attack=a.attack, spread=max(a.spread, b.spread))
        del kept[max(i, j)]

    def neighbours(i):
        for j in (i - 1, i + 1):
            if 0 <= j < len(kept) and kept[max(i, j)].start - kept[min(i, j)].end < 0.08:
                yield j

    def fold_best(allowed, score):
        best = None
        for i, n in enumerate(kept):
            for j in neighbours(i):
                if allowed(n, kept[j]):
                    sc = score(n, kept[j])
                    if best is None or sc < best[0]:
                        best = (sc, i, j)
        if best is None:
            return False
        merge(best[2], best[1])
        return True

    length = lambda n: n.end - n.start                                    # noqa: E731
    # Fragments: too short to be a sung note at all.
    while fold_best(lambda n, m: length(n) < short, lambda n, m: (length(n), abs(m.midi - n.midi))):
        pass
    # Slides: a short note a semitone or so from a much longer neighbour, on the way in or out.
    while fold_best(lambda n, m: length(n) < 0.35 and abs(m.midi - n.midi) <= 1.2 and length(m) >= 2 * length(n)
                    and n.spread > 0.25,
                    lambda n, m: (length(n) * (1 + abs(m.midi - n.midi)),)):
        pass
    k = 0
    while k + 1 < len(kept):
        a, b = kept[k], kept[k + 1]
        if abs(a.midi - b.midi) < 0.5 and b.start - a.end < 0.03 and not b.attack:
            merge(k, k + 1)
        else:
            k += 1
    # The words fix the count: fold the likeliest leftovers (short, near in pitch) while there are
    # many more notes than syllables, leaving real melismas (a run of distinct pitches) alone.
    if target:
        while len(kept) > target * 1.25 and fold_best(
                lambda n, m: length(n) < 0.45 and abs(m.midi - n.midi) <= 2.5,
                lambda n, m: (length(n) * (1 + abs(m.midi - n.midi)),)):
            pass
    return kept


def syllable_hints(notes: list[HeardNote], times: np.ndarray, rms: np.ndarray) -> list[float]:
    """For each note, how surely a new syllable starts on it (0..1): after a silence or a breath
    almost surely; after a dip in loudness (a consonant) likely; when the voice only glides to a new
    pitch, probably not (a melisma)."""
    out = []
    for i, n in enumerate(notes):
        if i == 0 or n.start - notes[i - 1].end > 0.06:
            out.append(1.0)
            continue
        a, b = np.searchsorted(times, [n.start - 0.06, n.start + 0.03])
        dip = float(rms[a:max(a + 1, b)].min())
        pa, pb = np.searchsorted(times, [notes[i - 1].start, notes[i - 1].end])
        ca, cb = np.searchsorted(times, [n.start, n.end])
        around = min(float(rms[pa:max(pa + 1, pb)].mean()), float(rms[ca:max(ca + 1, cb)].mean()))
        depth = max(0.0, 1 - dip / (around + 1e-9))
        h = min(1.0, 0.15 + 1.5 * depth)
        if n.attack:
            h = max(h, 0.85)
        out.append(round(h, 2))
    return out


def candidates_for(m: float) -> list[int]:
    """The nearest semitone, and the other neighbour when the pitch sits near halfway."""
    near = int(round(m))
    other = near + (1 if m > near else -1)
    return [near, other] if abs(m - near) > 0.3 else [near]


# ---------------------------------------------------------------- deciding notes by context

def choose_pitches(notes: list[HeardNote], strengths: list[float], chord_tones: list[set[int]],
                   scale: set[int]) -> tuple[list[int], list[int]]:
    """Each note's pitch: what the audio says, and where it's close, what the music says (in the key,
    a chord tone on a strong beat, near the note before). Returns the pitches and the indexes of the
    notes still in doubt."""
    import itertools
    cands = [candidates_for(n.midi) for n in notes]
    if not notes:
        return [], []

    def emit(i, p):
        c = -abs(notes[i].midi - p) * 4.0
        if p % 12 not in scale:
            c -= 0.6
        if strengths[i] >= 0.5 and chord_tones[i] and p % 12 not in chord_tones[i]:
            c -= 0.4
        return c

    def step(a, b):
        leap = abs(a - b)
        return -0.05 * leap - (0.8 if leap > 12 else 0)

    best = [{p: (emit(0, p), None) for p in cands[0]}]
    for i in range(1, len(notes)):
        row = {}
        for p in cands[i]:
            prev = max(best[-1].items(), key=lambda kv: kv[1][0] + step(kv[0], p))
            row[p] = (prev[1][0] + step(prev[0], p) + emit(i, p), prev[0])
        best.append(row)
    p = max(best[-1].items(), key=lambda kv: kv[1][0])[0]
    path = [p]
    for i in range(len(notes) - 1, 0, -1):
        p = best[i][p][1]
        path.append(p)
    path.reverse()
    doubts = [i for i, c in enumerate(cands) if len(c) > 1 and abs(emit(i, c[0]) - emit(i, c[1])) < 0.5]
    del itertools
    return path, doubts


# ---------------------------------------------------------------- the draft score

@dataclass
class Draft:
    abc: str
    key: str
    meter: str
    tempo: int
    doubts: list[str]
    notes: list[str]
    octave_above: int = 0          # how many octaves above the singing the draft is written
    hints: list[float] | None = None   # per sung note: how surely a new syllable starts on it


def grid_shift(positions: list[float], lengths: list[float], per_beat: int = 2) -> float:
    """The small time shift (in beats) that puts the sung onsets nearest the eighth-note grid, longer
    notes counting more: singers sit a little ahead of or behind the band, and the simplest
    notation is the likeliest reading."""
    best = (float("inf"), 0.0)
    for step in range(-24, 25):
        d = step / 100
        cost = sum(min(1.0, max(0.25, ln)) * abs((p + d) * per_beat - round((p + d) * per_beat))
                   for p, ln in zip(positions, lengths))
        if cost < best[0] - 1e-9 or (abs(cost - best[0]) < 1e-9 and abs(d) < abs(best[1])):
            best = (cost, d)
    return best[1]


# Rhythms within one beat, with what each costs to read: plain ones are likelier.
F = Fraction
BEAT_PATTERNS = [
    ((F(0),), 0.0), ((F(1, 2),), 0.05), ((F(0), F(1, 2)), 0.05),
    ((F(1, 4),), 0.25), ((F(3, 4),), 0.2),
    ((F(0), F(3, 4)), 0.15), ((F(0), F(1, 4)), 0.25), ((F(1, 2), F(3, 4)), 0.2), ((F(1, 4), F(1, 2)), 0.3),
    ((F(0), F(1, 4), F(1, 2)), 0.25), ((F(0), F(1, 2), F(3, 4)), 0.2), ((F(0), F(1, 4), F(3, 4)), 0.3),
    ((F(1, 4), F(1, 2), F(3, 4)), 0.35), ((F(0), F(1, 4), F(1, 2), F(3, 4)), 0.3),
    ((F(0), F(1, 3), F(2, 3)), 0.3), ((F(0), F(2, 3)), 0.25),
]


COMPOUND_PATTERNS = [
    ((F(0),), 0.0), ((F(1, 3),), 0.15), ((F(2, 3),), 0.1),
    ((F(0), F(2, 3)), 0.05), ((F(0), F(1, 3)), 0.15), ((F(1, 3), F(2, 3)), 0.15),
    ((F(0), F(1, 3), F(2, 3)), 0.05), ((F(0), F(1, 2), F(2, 3)), 0.15), ((F(0), F(1, 6), F(1, 3)), 0.3),
    ((F(0), F(1, 3), F(1, 2), F(2, 3)), 0.25), ((F(0), F(1, 6), F(1, 3), F(2, 3)), 0.3),
]


def snap_rhythm(positions: list[float], patterns=None) -> list[Fraction]:
    """Onsets (in beats) onto the plainest rhythm that fits them, beat by beat: each beat's onsets
    take the pattern (two eighths, a dotted eighth and a sixteenth, ...) with the least timing error
    plus reading cost. Error is in beats; a quarter beat off costs about as much as a sixteenth."""
    out: list[Fraction | None] = [None] * len(positions)
    beats: dict[int, list[int]] = {}
    for i, p in enumerate(positions):
        beats.setdefault(int(math.floor(p + 0.125)), []).append(i)
    for b, idx in beats.items():
        local = [positions[i] - b for i in idx]
        best = None
        for pattern, cost in (patterns or BEAT_PATTERNS):
            if len(pattern) != len(local):
                continue
            err = sum(abs(x - float(q)) for x, q in zip(local, pattern))
            total = err + cost
            if best is None or total < best[0]:
                best = (total, pattern)
        if best is None or best[0] > 0.6:
            for i in idx:
                out[i] = quantize(positions[i])
        else:
            for i, q in zip(idx, best[1]):
                out[i] = b + q
    # Keep them in order and distinct.
    for i in range(1, len(out)):
        if out[i] <= out[i - 1]:
            out[i] = out[i - 1] + Fraction(1, 4)
    return out


def snap(pos: float) -> Fraction:
    """A beat position on the grid: the nearest eighth when it's close, else the nearest sixteenth."""
    eighth = Fraction(round(pos * 2), 2)
    return eighth if abs(pos - float(eighth)) < 0.15 else quantize(pos)


def quantize(pos: float, grid: Fraction = Fraction(1, 4)) -> Fraction:
    """Beats -> the nearest grid point (sixteenths by default)."""
    return Fraction(round(pos / float(grid))) * grid


@dataclass
class Meter:
    per_beat: int                  # eighths in a beat: 2 (simple: 3/4, 4/4) or 3 (compound: 6/8, 12/8)
    beats_per_bar: int
    phase: int                     # the eighth (in the eighth grid) where a bar starts
    confidence: float

    @property
    def compound(self) -> bool:
        return self.per_beat == 3

    @property
    def text(self) -> str:
        return f"{3 * self.beats_per_bar}/8" if self.compound else f"{self.beats_per_bar}/4"



def eighth_grid(beats: np.ndarray) -> np.ndarray:
    """Each tracked beat split in two (the tracker counts quarters, or eighth pairs in 6/8)."""
    mids = (beats[:-1] + beats[1:]) / 2
    grid = np.empty(len(beats) + len(mids))
    grid[0::2], grid[1::2] = beats, mids
    return grid


def choose_meter_eighths(acc: np.ndarray, bass: np.ndarray, heard: list[HeardNote], eighths: np.ndarray) -> Meter:
    """Which eighths start beats and bars: the grouping (3/4, 4/4, 6/8 or 12/8, any phase) that puts
    the most harmonic change, bass notes, accents and long sung notes on bar and beat starts."""
    import librosa
    frames = np.clip(librosa.time_to_frames(eighths, sr=SR, hop_length=HOP), 0, None)
    env = librosa.onset.onset_strength(y=acc, sr=SR, hop_length=HOP)
    benv = librosa.onset.onset_strength(y=bass, sr=SR, hop_length=HOP, fmax=300)
    accent = env[np.clip(frames, 0, len(env) - 1)]
    low = benv[np.clip(frames, 0, len(benv) - 1)]
    chroma = beat_chroma(acc, eighths)
    norm = chroma / (np.linalg.norm(chroma, axis=1, keepdims=True) + 1e-9)
    novelty = np.zeros(len(eighths))
    for e in range(2, len(eighths) - 2):
        before, after = norm[e - 2:e].mean(axis=0), norm[e:e + 2].mean(axis=0)
        novelty[e] = 1 - float(before @ after / (np.linalg.norm(before) * np.linalg.norm(after) + 1e-9))
    melody = np.zeros(len(eighths))
    step = float(np.median(np.diff(eighths)))
    for n in heard:
        if n.end - n.start >= 1.5 * step:
            k = int(np.argmin(np.abs(eighths - n.start)))
            if abs(eighths[k] - n.start) < 0.35 * step:
                melody[k] += min(4.0, (n.end - n.start) / step)
    unit = lambda f: f / (f.max() + 1e-9)                               # noqa: E731
    idx = np.arange(len(eighths))
    # 1. The beat: every 2 eighths or every 3? Beats carry the accents, bass notes and sung onsets;
    #    the eighths between them don't.
    pulse = unit(accent) + unit(low) + unit(melody)
    beat_scores = []
    for per_beat in (2, 3):
        for off in range(per_beat):
            on = (idx - off) % per_beat == 0
            beat_scores.append((pulse[on].mean() - pulse[~on].mean() + (0.02 if per_beat == 2 else 0), per_beat, off))
    beat_scores.sort(reverse=True)
    _, per_beat, off = beat_scores[0]
    beat_conf = beat_scores[0][0] - next(b[0] for b in beat_scores if b[1] != per_beat)
    # 2. The bar: which beats start bars? Harmony changes, long sung notes and the bass say so.
    bar_feat = 2.0 * unit(novelty) + 1.5 * unit(melody) + unit(low) + 0.5 * unit(accent)
    beat_idx = idx[(idx - off) % per_beat == 0]
    options = [(3, 0.0), (4, 0.02)] if per_beat == 2 else [(2, 0.06), (4, -0.06)]
    bar_scores = []
    for per_bar, prior in options:
        for ph in range(per_bar):
            starts = beat_idx[ph::per_bar]
            rest = np.setdiff1d(beat_idx, starts)
            if len(starts) < 2:
                continue
            bar_scores.append((bar_feat[starts].mean() - bar_feat[rest].mean() + prior, per_bar, int(starts[0])))
    bar_scores.sort(reverse=True)
    best = bar_scores[0]
    rival = next((b for b in bar_scores if b[1] != best[1]), best)
    phase = best[2] % (per_beat * best[1])
    return Meter(per_beat, best[1], phase, float(min(beat_conf, best[0] - rival[0] if rival is not best else 1.0)))


def draft(stems: Stems, syllables: int | None = None) -> Draft:
    """The open engine: the recording's lead sheet as planner-dialect ABC. `syllables`, when the
    lyrics are known, is how many sung syllables to expect."""
    import librosa
    acc = stems.accompaniment
    tracked, tracked_tempo = beat_times(acc, stems.vocals)
    if len(tracked) < 8:
        raise ValueError("Couldn't find a steady beat in the recording.")
    # The melody first: it also says where the beats and bars really are.
    times, midi, rms = vocal_track(stems.vocals)
    v_on = librosa.onset.onset_detect(y=stems.vocals, sr=SR, hop_length=PITCH_HOP, units="time", backtrack=True)
    heard = clean_notes(vocal_notes(times, midi, rms, v_on), times, midi, rms, target=syllables)
    for nt in heard:                  # a syllable starts with its consonant, before the pitch settles
        before = v_on[(v_on >= nt.start - 0.15) & (v_on <= nt.start + 0.03)]
        if len(before):
            nt.start = float(before[0])
    bass_src = stems.bass if stems.bass is not None else acc
    eighths = eighth_grid(tracked)
    meter = choose_meter_eighths(acc, bass_src, heard, eighths)
    g, per_bar = meter.per_beat, meter.beats_per_bar
    first = meter.phase % g
    beats = eighths[first::g]
    downbeat_index = (meter.phase - first) // g          # the beat where the first full bar starts
    tempo = 60.0 / float(np.median(np.diff(beats)))
    chroma = beat_chroma(acc, beats)
    bass_chroma = beat_chroma(bass_src, beats, low=True)
    tonic, minor, key_conf = key_of(chroma.sum(axis=0))

    def cost_at(k):
        pos = (k - downbeat_index) % per_bar
        return 0.08 if pos == 0 else 0.2 if per_bar == 4 and pos == 2 else 0.45
    reading = read_chords(chroma, bass_chroma, (tonic, minor), [cost_at(k) for k in range(len(beats))],
                          downbeats=[(k - downbeat_index) % per_bar == 0 for k in range(len(beats))])
    grid = Grid(beats, per_bar, downbeat_index, tempo)

    raw = [grid.position(n.start) for n in heard]
    raw_ends = [grid.position(n.end) for n in heard]
    patterns = COMPOUND_PATTERNS if meter.compound else BEAT_PATTERNS
    shift = grid_shift(raw, [e - s for s, e in zip(raw, raw_ends)], 3 if meter.compound else 2)
    positions = snap_rhythm([p + shift for p in raw], patterns)
    finest = Fraction(1, 6) if meter.compound else Fraction(1, 4)
    ends = [quantize(e + shift, finest) for e in raw_ends]
    beat_index = [int(math.floor(float(p))) + downbeat_index for p in positions]
    chord_at = [reading.chords[min(max(b, 0), len(beats) - 1)] for b in beat_index]
    strengths = [1.0 if p % per_bar == 0 else 0.5 if p.denominator == 1 else 0.25 for p in positions]
    pitches, doubtful = choose_pitches(heard, strengths, [c.tones() for c in chord_at], scale_of(tonic, minor))

    # Note lengths on the grid: to the next note, or the heard end when a rest follows.
    hint_of = syllable_hints(heard, times, rms)
    events, hints = [], []
    for i, (p, e, m) in enumerate(zip(positions, ends, pitches)):
        nxt = positions[i + 1] if i + 1 < len(positions) else None
        end = e if e > p else p + finest
        if nxt is not None and (nxt - end) < Fraction(1, 2):
            end = nxt                                   # legato: a short gap is articulation, not a rest
        if nxt is not None:
            end = min(end, nxt)
        if end > p:
            events.append((p, end, m))
            hints.append(hint_of[i])
    if not events:
        raise ValueError("Couldn't hear a sung melody in the vocal.")

    tempo_text = f"3/8={round(tempo)}" if meter.compound else f"1/4={round(tempo)}"
    abc = to_abc(events, reading, per_bar, downbeat_index, tempo_text, key_name(tonic, minor), meter)
    doubts = [f"Bar {int(positions[i] // per_bar) + 1}, beat {float(positions[i] % per_bar) + 1:g}: "
              f"heard between {pitch_name(int(math.floor(heard[i].midi)))} and "
              f"{pitch_name(int(math.ceil(heard[i].midi)))}; wrote {pitch_name(pitches[i])}"
              for i in doubtful]
    beat_word = "dotted-quarter beats" if meter.compound else "beats"
    notes = [f"Tempo about {tempo:.0f} {beat_word} a minute; {meter.text} "
             f"({'sure' if meter.confidence > 0.1 else 'not sure'}); key {key_name(tonic, minor)} "
             f"({'sure' if key_conf > 0.05 else 'not sure'}).",
             f"{len(events)} sung notes; {len(doubtful)} decided by the music around them."]
    return Draft(abc, key_name(tonic, minor), meter.text, round(tempo), doubts, notes, hints=hints)


def pitch_name(m: int) -> str:
    return f"{NOTE_NAMES[m % 12]}{m // 12 - 1}"


def to_abc(events, reading: ChordReading, per_bar: int, downbeat_index: int, tempo: str, key: str,
           meter: Meter) -> str:
    """Events (start, end in beats from the first downbeat; MIDI) and the chords -> planner ABC at L:1/16."""
    from music21 import pitch as m21pitch
    unit = Fraction(1, 6) if meter.compound else Fraction(1, 4)      # a sixteenth, in beats
    first_bar = int(math.floor(float(events[0][0]) / per_bar))
    last_bar = int(math.floor(float(events[-1][1] - Fraction(1, 64)) / per_bar))
    lines = ["X:1", "T:", f"M:{meter.text}", "L:1/16", f"Q:{tempo}",
             'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"', f"K:{key}", "% verse", "V: Vocal"]
    bars = []
    last_chord = None
    for b in range(first_bar, last_bar + 1):
        start, end = Fraction(b * per_bar), Fraction((b + 1) * per_bar)
        cuts = {start, end}
        for s, e, _ in events:
            for t in (s, e):
                if start < t < end:
                    cuts.add(t)
        chord_marks = {}
        for beat in range(per_bar):
            idx = b * per_bar + beat + downbeat_index
            if 0 <= idx < len(reading.chords):
                ch = reading.chords[idx].name()
                if ch and ch != last_chord:
                    chord_marks[start + beat] = ch
                    cuts.add(start + beat)
                    last_chord = ch
        out = []
        cuts = sorted(cuts)
        for a, z in zip(cuts, cuts[1:]):
            mark = f'"{chord_marks[a]}"' if a in chord_marks else ""
            ev = next((e for e in events if e[0] <= a < e[1]), None)
            n = (z - a) / unit
            length = str(n.numerator) if n.denominator == 1 else f"{n.numerator}/{n.denominator}"
            if ev is None:
                out.append(f"{mark}z{length}")
            else:
                p = m21pitch.Pitch(midi=ev[2])
                acc = {1: "^", -1: "_"}.get(int(p.alter), "=") if p.alter else "="
                octave = p.octave
                text = p.step if octave <= 4 else p.step.lower()
                text += "," * (4 - octave) if octave < 4 else "'" * (octave - 5) if octave > 5 else ""
                tie = "-" if z < ev[1] else ""
                out.append(f"{mark}{acc}{text}{length}{tie}")
        bars.append("".join(out))
    for k in range(0, len(bars), 4):
        lines.append("|".join(bars[k:k + 4]) + "|")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- SheetSage2 (optional)

SHEETSAGE_LICENCE = ("SheetSage2's weights are licensed CC BY-NC 4.0: non-commercial use only, with no added "
                     "permission for creators to sell what they make. Use the open engine for anything you'll sell.")
SHEETSAGE_OCTAVE_ABOVE = 1           # it writes YuE2's way, an octave above the singing


def sheetsage_draft(recording: Path, folder: Path, binary: str | None = None, model: str | None = None,
                    device: str | None = None) -> Draft:
    """SheetSage2 through yue2.cpp's `yue-transcribe`: the whole mix in, a lead sheet out."""
    import os
    import subprocess
    from . import paths
    binary = binary or (str(p) if (p := paths.find_program("yue-transcribe", "COPYIST_YUE_TRANSCRIBE")) else None)
    model = model or os.environ.get("COPYIST_SHEETSAGE") or \
        (str(p) if (p := paths.find_model("SheetSage2-Q8_0.gguf", "COPYIST_SHEETSAGE")) else None)
    if not binary:
        raise ValueError("SheetSage2's runner (yue-transcribe) isn't installed: run scripts/setup-yue.sh.")
    if not model:
        raise ValueError("SheetSage2 isn't downloaded. " + SHEETSAGE_LICENCE)
    out = folder / "draft.abc"
    cmd = [binary, "--model", model, "--audio", str(recording), "--out", str(out)]
    if device or os.environ.get("COPYIST_YUE_DEVICE"):
        cmd += ["--device", device or os.environ["COPYIST_YUE_DEVICE"]]
    with open(folder / "sheetsage.log", "w", encoding="utf-8") as log:
        r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    if r.returncode != 0 or not out.is_file():
        raise ValueError(f"yue-transcribe failed (exit {r.returncode}); see {folder / 'sheetsage.log'}.")
    text = out.read_text(encoding="utf-8")
    from . import abcplan
    try:
        plan = abcplan.parse(text)
    except abcplan.PlanError:
        # An instrumental lead goes in the Ins voice; take it, with the Vocal voice's chords.
        text = lead_from_ins(text)
        plan = abcplan.parse(text)
    return Draft(text, plan.key, plan.meter, int(abcplan.tempo_field(plan.tempo)) if
                 isinstance(abcplan.tempo_field(plan.tempo), int) else 90, [],
                 ["Transcribed by SheetSage2 (non-commercial licence)."], octave_above=SHEETSAGE_OCTAVE_ABOVE)


def lead_from_ins(text: str) -> str:
    """Swap the Vocal and Ins voices, keeping the chord symbols where they were written (in Vocal)."""
    return text.replace("V: Vocal", "V: _tmp").replace("V: Ins", "V: Vocal").replace("V: _tmp", "V: Ins")


# ---------------------------------------------------------------- the command

INDEX = "transcription.json"
ENGINES = ("open", "sheetsage")


def heard_lyrics(vocals: Path) -> str:
    """The words, as Whisper hears them on the vocal, one phrase a line (when the person gave none)."""
    from . import hear
    if not hear.available():
        raise ValueError("Without the lyrics, Copyist listens for the words with Whisper (pip install faster-whisper); "
                         "or give the lyrics with --lyrics.")
    import librosa
    from faster_whisper import WhisperModel
    audio, _ = librosa.load(str(vocals), sr=16000, mono=True)
    segments, _ = WhisperModel("base.en", device="cpu", compute_type="int8").transcribe(audio, beam_size=5)
    lines = [s.text.strip() for s in segments if s.text.strip()]
    if not lines:
        raise ValueError("Whisper heard no words in the vocal; give the lyrics with --lyrics.")
    return "\n".join(lines) + "\n"


def transcribe(recording: Path, title: str, out_root: Path = Path("out"), lyrics: str | None = None,
               engine: str = "open", voice: str | None = None, vocals: Path | None = None,
               accompaniment: Path | None = None, device: str | None = None, cache: Path = Path(".cache"),
               preview: bool = True) -> dict:
    """A recording -> a Copyist song file and a report in out/<slug>/transcribe/; returns the index."""
    import json
    import shutil
    from . import stems as stems_mod, syllables, validate, write
    from .song import load_song
    if engine not in ENGINES:
        raise ValueError(f"Unknown engine {engine!r}: choose {', '.join(ENGINES)}.")
    recording = Path(recording)
    if not recording.is_file():
        raise ValueError(f"There's no recording at {recording}.")
    name = write.slug(title)
    folder = out_root / name / "transcribe"
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / f"source{recording.suffix.lower()}"
    if recording.resolve() != source.resolve():
        shutil.copy(recording, source)
    if lyrics:
        (folder / "lyrics.txt").write_text(lyrics.strip() + "\n", encoding="utf-8")
    if vocals is None or accompaniment is None:
        vocals, accompaniment = stems_mod.split_vocals(source, folder / "stems", device=device)
    if lyrics is None:
        lyrics = heard_lyrics(vocals)
        (folder / "lyrics-heard.txt").write_text(lyrics, encoding="utf-8")
    count = len(syllables.all_syllables(syllables.parse_lyrics(lyrics)))
    if engine == "open":
        d = draft(stems_from_files(source, vocals, accompaniment), syllables=count)
    else:
        d = sheetsage_draft(source, folder, device=device)
    (folder / "draft.abc").write_text(d.abc, encoding="utf-8")
    import re
    shown = re.sub(r"^\d{8}-\d{6}-", "", recording.name)          # the page's upload stamp
    written_with = {"transcriber": f"copyist-{engine}", "recording": shown}
    cand = write.song_from_plan(d.abc, lyrics, title, voice, None, written_with, None, as_sung=d.octave_above,
                                hints=d.hints)
    song_path = folder / f"{name}.yaml"
    song_path.write_text(write.song_yaml(cand.data), encoding="utf-8")
    song = load_song(song_path)
    findings = validate.validate(song)
    report = [f"# {title}: transcription", "", f"From {shown}, by the {engine} engine.", ""] + \
        [f"- {n}" for n in d.notes + cand.notes]
    if d.doubts:
        report += ["", "## Doubts", "", "Decided by the music around them; listen to these first.", ""] + \
            [f"- {x}" for x in d.doubts]
    if engine == "sheetsage":
        report += ["", SHEETSAGE_LICENCE]
    report += ["", validate.report_markdown(song, findings)]
    (folder / "report.md").write_text("\n".join(report), encoding="utf-8")
    index = {"title": title, "slug": name, "engine": engine, "recording": shown,
             "source": source.name, "song": song_path.name, "key": song.key, "meter": song.meter,
             "tempo": song.tempo, "voice": cand.data["voice"], "sections": song.sections,
             "doubts": d.doubts, "notes": d.notes + cand.notes,
             "fails": sum(f.severity == "fail" for f in findings),
             "warnings": sum(f.severity == "warn" for f in findings)}
    if preview:
        try:
            index["engine_used"] = write.band_preview(song, folder / "preview.wav", cache)
            index["preview"] = "preview.wav"
        except Exception as e:                       # the song file stands without its preview
            index["preview_error"] = str(e)
    (folder / INDEX).write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def keep(out_root: Path, title_or_slug: str, songs_dir: Path = Path("songs"), replace: bool = False) -> Path:
    """Copy a transcription's song file into songs/."""
    from . import write
    name = write.slug(title_or_slug)
    folder = out_root / name / "transcribe"
    source = folder / f"{name}.yaml"
    if not source.is_file():
        raise ValueError(f"There's no transcription of {name} in {folder}.")
    target = songs_dir / f"{name}.yaml"
    text = source.read_text(encoding="utf-8")
    if target.exists() and target.read_text(encoding="utf-8") != text and not replace:
        raise ValueError(f"{target} already exists; keep it under another title, or pass --replace.")
    songs_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
