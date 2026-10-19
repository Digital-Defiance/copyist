"""Transcribing recordings (docs/transcribing.md): the open engine on recordings made in the test, where
every note, chord, key and meter is known."""
import importlib.util
import json
import os
import stat
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import numpy as np

from copyist import abcplan, transcribe as tr
from helpers import KEY_CHANGE_INS, KEY_CHANGE_VOCAL, la

HAVE_AUDIO = all(importlib.util.find_spec(m) for m in ("librosa", "soundfile", "scipy"))
if HAVE_AUDIO:
    import soundfile as sf
NEEDS_AUDIO = unittest.skipUnless(HAVE_AUDIO, "transcribing needs librosa (pip install copyist[transcribe])")
from copyist.song import load_song

KEY_CHANGE = Path(__file__).resolve().parent / "data" / "plans" / "key-change.abc"   # SheetSage2's layout

SR = tr.SR
BPM = 100
BEAT = 60 / BPM
# (start beat, length in beats, MIDI) for a little tune in C, 4/4, with a pickup-free start and a
# repeated note (bar 2) that only an attack separates.
TUNE = [(0, 1, 60), (1, 1, 62), (2, 1, 64), (3, 1, 65),
        (4, 1, 67), (5, 1, 67), (6, 2, 69),
        (8, 1, 67), (9, 1, 65), (10, 1, 64), (11, 1, 62),
        (12, 4, 60)]
CHORDS = [(0, (48, 52, 55)), (4, (53, 57, 60)), (8, (55, 59, 62)), (12, (48, 52, 55))]   # C F G C
LYRICS = "Here we go around\nthe mountain\nevery day\nsing"     # 12 syllables, 12 notes


def tone(midi: float, seconds: float, amp: float = 0.3, partials=(1.0, 0.5, 0.3, 0.15)) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    f = 440.0 * 2 ** ((midi - 69) / 12)
    y = sum(a * np.sin(2 * np.pi * f * (k + 1) * t) for k, a in enumerate(partials))
    env = np.minimum(1, np.minimum(t / 0.02, (seconds - t) / 0.04).clip(0))
    return amp * y * env


def render_tune(lead_in: float = 1.0, bars: int = 4):
    total = lead_in + bars * 4 * BEAT + 1.0
    n = int(total * SR)
    vocals, acc = np.zeros(n), np.zeros(n)
    for start, length, m in TUNE:
        a = int((lead_in + start * BEAT) * SR)
        y = tone(m, length * BEAT - 0.06)              # a short breath between notes: an attack each time
        vocals[a:a + len(y)] += y
    rng = np.random.default_rng(1)
    for bar_start, chord in CHORDS:
        for beat in range(4):
            a = int((lead_in + (bar_start + beat) * BEAT) * SR)
            pad = sum(tone(c, BEAT * 0.9, 0.08, (1.0, 0.3)) for c in chord)
            acc[a:a + len(pad)] += pad
            bass = tone(chord[0] - 12, BEAT * 0.9, 0.25 if beat in (0, 2) else 0.12, (1.0, 0.4))
            acc[a:a + len(bass)] += bass
            click = rng.normal(0, 0.25 if beat == 0 else 0.12, int(0.03 * SR)) * np.linspace(1, 0, int(0.03 * SR))
            acc[a:a + len(click)] += click
    return vocals, acc


@NEEDS_AUDIO
class SyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="copyist-transcribe-"))
        cls.vocals, cls.acc = render_tune()
        sf.write(cls.tmp / "vocals.wav", cls.vocals, SR)
        sf.write(cls.tmp / "acc.wav", cls.acc, SR)
        sf.write(cls.tmp / "mix.wav", cls.vocals + cls.acc, SR)
        cls.draft = tr.draft(tr.Stems(cls.vocals + cls.acc, cls.vocals, cls.acc))
        cls.plan = abcplan.parse(cls.draft.abc)

    def test_key_meter_and_tempo(self):
        self.assertEqual(self.draft.key, "C")
        self.assertEqual(self.draft.meter, "4/4")
        self.assertLess(abs(self.draft.tempo - BPM), 4)

    def test_every_note_with_the_repeated_one(self):
        bars = abcplan.trim(self.plan)
        self.assertEqual(abcplan.pitches(bars, self.plan.key), [m for _, _, m in TUNE])

    def test_rhythm_on_the_grid(self):
        bars = abcplan.trim(self.plan)
        onsets, pos, tied = [], Fraction(0), False
        for bar in bars:
            for t in bar.toks:
                if t.kind == "chord":
                    continue
                if t.kind == "note" and not tied:
                    onsets.append(pos)
                tied = t.kind == "note" and t.tie
                pos += t.length * self.plan.unit * 4
        first = onsets[0]
        self.assertEqual([o - first for o in onsets], [Fraction(s) for s, _, _ in TUNE])

    def test_chords(self):
        names = [t.text for b in self.plan.vocal for t in b.toks if t.kind == "chord"]
        self.assertEqual(names[:4], ["C", "F", "G", "C"])

    def test_the_command_end_to_end(self):
        out = self.tmp / "out"
        (self.tmp / "tune.txt").write_text(LYRICS)
        from copyist.cli import main
        code = main(["transcribe", str(self.tmp / "mix.wav"), "--title", "Mountain", "--lyrics", str(self.tmp / "tune.txt"),
                     "--vocals", str(self.tmp / "vocals.wav"), "--accompaniment", str(self.tmp / "acc.wav"),
                     "--out", str(out), "--no-preview"])
        self.assertEqual(code, 0)
        folder = out / "mountain" / "transcribe"
        index = json.loads((folder / tr.INDEX).read_text())
        self.assertEqual((index["key"], index["meter"], index["engine"]), ("C", "4/4", "open"))
        song = load_song(folder / index["song"])
        self.assertTrue(song.lyric_fits[0].fits)
        self.assertEqual(song.written_with["transcriber"], "copyist-open")
        onsets = [n.pitch.midi for n in song.melody.recurse().notes
                  if hasattr(n, "pitch") and not (n.tie is not None and n.tie.type in ("stop", "continue"))]
        self.assertEqual(onsets, [m for _, _, m in TUNE])          # sung where it was sung: no octave moved
        self.assertIn("0 note(s) split", (folder / "report.md").read_text())
        self.assertTrue((folder / "source.wav").is_file())
        songs = self.tmp / "songs"
        self.assertEqual(main(["transcribe", "--title", "Mountain", "--keep", "--out", str(out), "--songs", str(songs)]), 0)
        self.assertTrue((songs / "mountain.yaml").is_file())


class EngineListTests(unittest.TestCase):
    def test_neural_is_a_known_engine(self):
        self.assertIn("neural", tr.ENGINES)
        self.assertIn("open", tr.ENGINES)


class CleaningTests(unittest.TestCase):
    def setUp(self):
        self.times = np.arange(0, 10, 0.01)
        self.midi = np.full(len(self.times), 60.0)
        self.rms = np.full(len(self.times), 1.0)

    def note(self, a, b, m, **kw):
        return tr.HeardNote(a, b, m, **kw)

    def test_quiet_notes_are_bleed(self):
        self.rms[:100] = 0.01
        kept = tr.clean_notes([self.note(0.2, 0.8, 62), self.note(1.2, 2.0, 60)], self.times, self.midi, self.rms)
        self.assertEqual([n.midi for n in kept], [60])

    def test_a_stray_partial_far_from_the_line_is_dropped(self):
        # A bass bleed more than a seventh below the sung line.
        kept = tr.clean_notes(
            [self.note(1.0, 1.5, 60), self.note(1.5, 1.7, 48), self.note(1.7, 2.2, 64)],
            self.times, self.midi, self.rms)
        self.assertEqual([n.midi for n in kept], [60, 64])

    def test_a_high_note_a_seventh_above_the_median_is_kept(self):
        # Silent Night's F5 sits ~8 semitones above a G4 median — not a partial.
        kept = tr.clean_notes(
            [self.note(1.0, 1.5, 67), self.note(1.5, 2.0, 69), self.note(2.0, 2.5, 67),
             self.note(2.5, 3.2, 77), self.note(3.2, 3.8, 72)],
            self.times, self.midi, self.rms)
        self.assertIn(77, [round(n.midi) for n in kept])
        # A true stray more than a major sixth below still drops.
        kept = tr.clean_notes(
            [self.note(1.0, 1.5, 67), self.note(1.5, 1.7, 48), self.note(1.7, 2.2, 69)],
            self.times, self.midi, self.rms)
        self.assertNotIn(48, [round(n.midi) for n in kept])

    def test_grid_rearticulations_merge_short_echoes(self):
        events = [(Fraction(0), Fraction(2), 67), (Fraction(2), Fraction(2) + Fraction(1, 4), 67),
                  (Fraction(3), Fraction(4), 60)]
        folded, _ = tr.fold_grid_rearticulations(events)
        self.assertEqual(folded, [(Fraction(0), Fraction(2) + Fraction(1, 4), 67), (Fraction(3), Fraction(4), 60)])

    def test_grid_rearticulations_keep_equal_eighth_patter(self):
        # Eight same-pitch eighths (Major-General) must not cascade-merge.
        eighth = Fraction(1, 2)
        events = [(i * eighth, (i + 1) * eighth, 70) for i in range(8)]
        folded, _ = tr.fold_grid_rearticulations(events, floor=8)
        self.assertEqual(len(folded), 8)

    def test_fragments_fold_into_the_nearest_pitch(self):
        kept = tr.clean_notes([self.note(1.0, 1.5, 60), self.note(1.5, 1.58, 61), self.note(1.58, 2.2, 64)],
                              self.times, self.midi, self.rms)
        self.assertEqual([(round(n.start, 2), round(n.end, 2), n.midi) for n in kept], [(1.0, 1.58, 60), (1.58, 2.2, 64)])

    def test_a_wandering_slide_folds_but_a_steady_passing_note_stays(self):
        slide = [self.note(1.0, 2.0, 71), self.note(2.0, 2.25, 72, spread=0.6), self.note(2.4, 3.0, 69)]
        self.assertEqual(len(tr.clean_notes(slide, self.times, self.midi, self.rms)), 2)
        steady = [self.note(1.0, 2.0, 72), self.note(2.0, 2.2, 71, spread=0.05), self.note(2.2, 3.0, 69)]
        self.assertEqual([n.midi for n in tr.clean_notes(steady, self.times, self.midi, self.rms)], [72, 71, 69])

    def test_a_split_on_one_pitch_joins_unless_a_syllable_starts_it(self):
        split = [self.note(1.0, 1.5, 60), self.note(1.5, 2.0, 60.2)]
        self.assertEqual(len(tr.clean_notes(split, self.times, self.midi, self.rms)), 1)
        # Two equal-weight syllables on one pitch stay (real repeated notes in the tune).
        sung = [self.note(1.0, 1.5, 60), self.note(1.5, 2.0, 60.2, attack=True)]
        self.assertEqual(len(tr.clean_notes(sung, self.times, self.midi, self.rms)), 2)

    def test_a_short_same_pitch_rearticulation_folds_even_with_an_onset(self):
        # YuE2 / Broadway: "G, G" for one written G — short echo after a long note.
        long_short = [self.note(1.0, 2.5, 67), self.note(2.5, 2.7, 67.1, attack=True)]
        self.assertEqual(len(tr.clean_notes(long_short, self.times, self.midi, self.rms)), 1)
        # Same across a brief rest; two equal-weight syllables on one pitch still stay (below).
        with_rest = [self.note(1.0, 1.8, 65), self.note(1.95, 2.15, 65, attack=True)]
        self.assertEqual(len(tr.clean_notes(with_rest, self.times, self.midi, self.rms)), 1)

    def test_two_syllable_length_notes_on_one_pitch_are_kept(self):
        # Tyger "Ty-ger Ty-ger": both notes syllable-length — not a grace-note re-hit.
        pair = [self.note(1.0, 1.38, 69), self.note(1.38, 2.13, 69.1, attack=True)]
        self.assertEqual(len(tr.clean_notes(pair, self.times, self.midi, self.rms)), 2)

    def test_undershoot_keeps_short_steady_passing_tones(self):
        # Silent Night pattern: G A G with a short steady A. Aggressive fold drops A and
        # undershoots the lyric count; the retry with gentler fragments keeps it.
        notes = [
            self.note(1.0, 1.5, 67), self.note(1.5, 1.62, 69, spread=0.05), self.note(1.62, 2.2, 67),
            self.note(2.2, 2.7, 64), self.note(2.7, 2.82, 65, spread=0.05), self.note(2.82, 3.4, 64),
        ]
        kept = tr.clean_notes(notes, self.times, self.midi, self.rms, target=6)
        self.assertGreaterEqual(len(kept), 5)
        self.assertIn(69, [round(n.midi) for n in kept])

    def test_the_lyrics_fix_the_count(self):
        notes = []
        t = 1.0
        for k in range(12):                            # six sung notes, each with a scoop before it
            notes.append(self.note(t, t + 0.2, 60 + k // 2 * 2 - 1 + (k % 2)))
            t += 0.2 if k % 2 == 0 else 0.6
            notes[-1].end = t
        kept = tr.clean_notes(notes, self.times, self.midi, self.rms, target=6)
        self.assertLessEqual(len(kept), max(6 + 2, int(6 * 1.08)))

    def test_overshoot_folds_short_scoops_to_target(self):
        # Saints: E, short D scoop, C — lyrics want two notes, not three.
        notes = [
            self.note(1.0, 1.8, 64), self.note(1.8, 2.0, 62, spread=0.25), self.note(2.0, 3.0, 60),
            self.note(3.0, 3.8, 64), self.note(3.8, 3.95, 62, spread=0.14), self.note(3.95, 5.0, 60),
        ]
        kept = tr.clean_notes(notes, self.times, self.midi, self.rms, target=4)
        self.assertEqual(len(kept), 4)

    def test_split_toward_target_cuts_long_patter_holds(self):
        # Continuous Bb patter heard as one long note; lyrics want eight syllables.
        long = [self.note(1.0, 3.0, 70)]               # ~2 s at allegro ≈ eight eighths
        onsets = np.array([1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75])
        split = tr.split_toward_target(long, target=8, onsets=onsets, bpm=132)
        self.assertGreaterEqual(len(split), 6)
        self.assertLessEqual(len(split), 9)
        self.assertTrue(all(abs(n.midi - 70) < 0.1 for n in split))


class KeyChoiceTests(unittest.TestCase):
    def test_choose_key_prefers_the_confident_source(self):
        # Flat noise (no key) vs a clear Eb-major profile — take the clear one.
        flat = np.ones(12)
        strong_eb = np.roll(tr.MAJOR_PROFILE, 3).astype(float)
        tonic, minor, conf = tr.choose_key(flat, strong_eb)
        self.assertEqual((tonic, minor), (3, False))
        self.assertGreater(conf, 0.05)

    def test_melody_chroma_weights_by_duration(self):
        notes = [tr.HeardNote(0, 1.0, 63), tr.HeardNote(1.0, 1.2, 70)]  # Eb4 long, Bb4 short
        h = tr.melody_chroma(notes)
        self.assertGreater(h[3], h[10])


class ChordReadingTests(unittest.TestCase):
    def test_smooth_chroma_averages_similar_neighbours_only(self):
        chroma = np.zeros((5, 12))
        chroma[:, 0] = 1.0                         # same C harmony
        chroma[2, 0] = 2.0
        sm = tr.smooth_chroma(chroma, radius=1, min_cos=0.55)
        self.assertGreater(float(sm[1, 0]), 1.0)   # pulled toward the peak
        # A sudden F chord must not bleed into the C before it.
        jump = np.zeros((4, 12))
        jump[:2, 0] = 1.0                          # C
        jump[2:, 5] = 1.0                          # F
        sm = tr.smooth_chroma(jump, radius=2, min_cos=0.55)
        self.assertGreater(float(sm[1, 0]), float(sm[1, 5]))
        self.assertGreater(float(sm[2, 5]), float(sm[2, 0]))

    def test_tonal_boost_favours_I_IV_V_in_major(self):
        boost = tr.tonal_boost(0, False)  # C major
        by_name = {c.name(0, False): float(boost[i]) for i, c in enumerate(tr.CHORDS)}
        self.assertGreater(by_name["C"], by_name["Dm"])
        self.assertGreater(by_name["F"], by_name["Em"])
        self.assertGreater(by_name["G7"], by_name["Bdim"])

    def test_read_chords_holds_I_through_passing_tones_in_compound(self):
        # C triad with a little E/G wobble — Silent Night's band was renaming every bar.
        chroma = np.zeros((6, 12))
        chroma[:, [0, 4, 7]] = 1.0
        chroma[1, 2] = 0.4   # D passing
        chroma[3, 4] = 1.3   # E louder briefly
        bass = np.zeros((6, 12))
        bass[:, 0] = 1.0
        reading = tr.read_chords(chroma, bass, (0, False),
                                 beat_cost=[0.05, 0.40, 0.40, 0.05, 0.40, 0.40],
                                 smooth_radius=3)
        names = [c.name(0, False) for c in reading.chords]
        self.assertGreaterEqual(names.count("C"), 4)


class OnsetPullTests(unittest.TestCase):
    def test_pull_onset_start_caps_how_far_back(self):
        onsets = np.array([1.00, 2.00])
        # 0.12 s before pitch settle — uncapped would take 1.00; cap keeps 1.04.
        self.assertAlmostEqual(tr.pull_onset_start(1.12, onsets, cap=0.08), 1.04)
        self.assertAlmostEqual(tr.pull_onset_start(1.05, onsets, cap=0.08), 1.00)
        self.assertAlmostEqual(tr.pull_onset_start(1.50, onsets, cap=0.08), 1.50)


class RhythmTests(unittest.TestCase):
    def test_the_plainest_rhythm_wins(self):
        self.assertEqual(tr.snap_rhythm([0.02, 0.47, 1.05]), [Fraction(0), Fraction(1, 2), Fraction(1)])
        self.assertEqual(tr.snap_rhythm([0.0, 0.70]), [Fraction(0), Fraction(3, 4)])
        self.assertEqual(tr.snap_rhythm([0.0, 0.35, 0.68], tr.COMPOUND_PATTERNS), [Fraction(0), Fraction(1, 3), Fraction(2, 3)])

    def test_a_late_lone_onset_snaps_to_the_downbeat(self):
        # Sung ~0.35 into the beat: a late downbeat, not an intentional eighth (Saints take).
        self.assertEqual(tr.snap_rhythm([0.35]), [Fraction(0)])
        self.assertEqual(tr.snap_rhythm([1.32]), [Fraction(1)])
        # A real off-beat still lands on the half when it's clearly there.
        self.assertEqual(tr.snap_rhythm([0.52]), [Fraction(1, 2)])

    def test_double_tempo_rebuilds_a_compound_eighth_grid(self):
        # Tracker at 108 BPM, true pulse 54 (half): every other beat, trisected → true eighths.
        tracked = np.arange(0.0, 10.0, 60.0 / 108.0)
        self.assertTrue(tr.double_tempo(108.0, 54.0))
        self.assertFalse(tr.double_tempo(112.0, 112.0))
        self.assertFalse(tr.double_tempo(83.0, 56.0))          # eighth-pair 6/8, not a double lock
        eighths, compound = tr.eighths_for_meter(tracked, 108.0, 54.0)
        self.assertTrue(compound)
        step = float(np.median(np.diff(eighths)))
        self.assertAlmostEqual(60.0 / step, 162.0, delta=2)   # three eighths per 54 BPM beat
        plain, compound = tr.eighths_for_meter(tracked, 112.0, 112.0)
        self.assertFalse(compound)
        self.assertEqual(len(plain), len(tr.eighth_grid(tracked)))

    def test_waltz_guard_skips_compound_when_simple_meter_is_sure(self):
        # Double-tempo shape: skip 6/8 rebuild only when the plain grid is sure it's simple.
        tracked = np.arange(0.0, 10.0, 60.0 / 108.0)
        acc = np.zeros(8)
        with mock.patch.object(tr, "choose_meter_eighths") as choose:
            choose.return_value = tr.Meter(2, 4, 0, 0.50)          # Tyger-like
            _, compound = tr.meter_eighths(tracked, 108.0, 54.0, acc, acc, [])
            self.assertFalse(compound)
            choose.return_value = tr.Meter(2, 4, 0, 0.21)          # Silent Night-like
            _, compound = tr.meter_eighths(tracked, 108.0, 54.0, acc, acc, [])
            self.assertTrue(compound)


def _fake_sheetsage(tmp: Path, abc_text: str) -> dict:
    """A stand-in for yue-transcribe that writes `abc_text`, with SheetSage2's model files beside it in
    `tmp`; returns the environment that points Copyist at them."""
    runner = tmp / "yue-transcribe"
    runner.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\na = sys.argv[1:]\n"
                      f"Path(a[a.index('--out') + 1]).write_text({abc_text!r})\n")
    runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
    (tmp / "ss.gguf").write_bytes(b"x")
    (tmp / "MERT-v2-FullSong-Q8_0.gguf").write_bytes(b"x")  # yue-transcribe loads MERT beside the head
    return {"COPYIST_YUE_TRANSCRIBE": str(runner), "COPYIST_SHEETSAGE": str(tmp / "ss.gguf")}


def _onsets(song) -> list[int]:
    """MIDI pitch of each sung note's onset (tie continuations left out)."""
    return [n.pitch.midi for n in song.melody.recurse().notes
            if hasattr(n, "pitch") and not (n.tie is not None and n.tie.type in ("stop", "continue"))]


class DraftReadingTests(unittest.TestCase):
    SHEETSAGE = """X:1
T:
M:3/4
L:1/32
Q:1/4=79
V: Vocal clef=treble name="Vocal Melody" snm="Vocal"
V: Ins clef=treble name="Ins Melody" snm="Inst."
K:G
% intro
V: Vocal
"G"z24|
V: Ins
G,8B,8D8|
V: Vocal
M:3/8
"C"z4D8|
V: Ins
z12|
% verse
V: Vocal
M:3/4
"G"G16B8|"D"A24|
V: Ins
Z2|
"""

    def test_a_pickup_bar_in_another_meter(self):
        plan = abcplan.parse(self.SHEETSAGE)
        bars = abcplan.trim(plan)
        self.assertEqual(len(bars), 3)
        self.assertEqual(bars[0].units, Fraction(12))
        with self.assertRaises(abcplan.PlanError):              # a meter change mid-song isn't a pickup
            abcplan.parse(self.SHEETSAGE.replace('"G"G16B8|"D"A24|', '"G"G16B8|\nM:2/4\n"D"A16|'))

    # SheetSage sometimes puts the sung line on Ins (with chords) and leaves Vocal as Z rests.
    SHEETSAGE_INS_LEAD = """X:1
T:
M:4/4
L:1/32
Q:1/4=100
V: Ins clef=treble name="Vocal Melody" snm="Vocal"
V: Vocal clef=treble name="Ins Melody" snm="Inst."
K:C
% verse
V: Ins
"C"C8D8E8F8|"G"G8A8B8c8|
V: Vocal
Z2|
V: Ins
M:1/4
"C"C8|
V: Vocal
M:1/4
Z|
V: Ins
M:4/4
"C"E8E8E8E8|
V: Vocal
M:4/4
Z|
"""

    def test_sheetsage_ins_lead_is_taken_and_short_bars_join(self):
        text, notes = tr.sheetsage_lead_sheet(self.SHEETSAGE_INS_LEAD)
        self.assertTrue(any("Ins voice" in n for n in notes))
        self.assertTrue(any("short mid-song" in n for n in notes))
        plan = abcplan.parse(text)
        self.assertEqual(plan.meter, "4/4")
        bars = abcplan.trim(plan)
        self.assertTrue(all(b.units is None for b in bars))
        from copyist import fit as fitting
        slots = fitting.slots(bars, plan.unit, plan.meter)
        self.assertGreaterEqual(len(slots), 9)   # the Ins tune, not the empty Vocal Zs

    def test_the_ins_voice_reads_its_own_key_changes(self):
        text = KEY_CHANGE.read_text(encoding="utf-8")
        self.assertEqual((tr.voice_note_count(text, "Vocal"), tr.voice_note_count(text, "Ins")), (22, 12))
        plan = abcplan.parse(tr.lead_from_ins(text))
        self.assertEqual(abcplan.pitches(plan.vocal, plan.key), KEY_CHANGE_INS)
        self.assertEqual([b.new_key for b in plan.vocal], [None, None, "D", None, "Bb", None])

    def test_sheetsage_key_changes_through_a_fake_runner_keep_every_bar(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-sheetsage-"))
        text = KEY_CHANGE.read_text(encoding="utf-8")
        (tmp / "song.wav").write_bytes(b"")                     # the fake runner never reads it
        with mock.patch.dict(os.environ, _fake_sheetsage(tmp, text)):
            d = tr.sheetsage_draft(tmp / "song.wav", tmp)
        plan = abcplan.parse(d.abc)
        self.assertEqual(len(plan.vocal), 6)
        self.assertEqual(abcplan.pitches(plan.vocal, plan.key), KEY_CHANGE_VOCAL)
        self.assertEqual((d.key, d.octave_above), ("C", 1))
        self.assertEqual(d.abc, text)                           # SheetSage's own text, unchanged

    @NEEDS_AUDIO
    def test_sheetsage_key_change_transcription_end_to_end(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-sheetsage-"))
        sf.write(tmp / "song.wav", np.zeros(SR), SR)
        with mock.patch.dict(os.environ, _fake_sheetsage(tmp, KEY_CHANGE.read_text(encoding="utf-8"))):
            index = tr.transcribe(tmp / "song.wav", "Key change", tmp / "out", lyrics=la(22), engine="sheetsage",
                                  vocals=tmp / "song.wav", accompaniment=tmp / "song.wav", preview=False)
        folder = tmp / "out" / "key-change" / "transcribe"
        song = load_song(folder / index["song"])
        self.assertEqual(_onsets(song), [m - 12 for m in KEY_CHANGE_VOCAL])
        self.assertEqual(song.key, "C")
        self.assertTrue(song.lyric_fits[0].fits)
        report = (folder / "report.md").read_text()
        self.assertIn("bar 3 (C to D)", report)
        self.assertIn("non-commercial", report)
        self.assertTrue(any("bar 5 (D to Bb)" in n for n in index["notes"]))

    def test_short_bars_and_a_key_change_keep_pitches_and_say_where(self):
        src = KEY_CHANGE.read_text(encoding="utf-8").replace(
            "% chorus\nV: Vocal\nK:D\n",
            'V: Vocal\nM:2/4\n"F"a8|\nV: Ins\nM:2/4\nz8|\n% chorus\nV: Vocal\nM:4/4\nK:D\n').replace(
            "V: Ins\nK:D\n", "V: Ins\nM:4/4\nK:D\n")
        text, notes = tr.sheetsage_lead_sheet(src)
        self.assertTrue(any("short mid-song" in n for n in notes))
        plan = abcplan.parse(text)
        bars = abcplan.trim(plan)
        expected = KEY_CHANGE_VOCAL[:8] + [81] + KEY_CHANGE_VOCAL[8:]             # the short bar's A
        self.assertEqual(abcplan.pitches(bars, plan.key), expected)
        self.assertEqual(abcplan.key_changes(bars, plan.key), [(2, "C", "D"), (4, "D", "Bb")])
        from copyist import write
        cand = write.song_from_plan(text, la(23), "Short bar", None, as_sung=1)
        self.assertTrue(any("bar 3 (C to D)" in n and "bar 5 (D to Bb)" in n for n in cand.notes), cand.notes)
        path = Path(tempfile.mkdtemp(prefix="copyist-short-bar-")) / "short-bar.yaml"
        path.write_text(write.song_yaml(cand.data), encoding="utf-8")
        self.assertEqual(_onsets(load_song(path)), [m - 12 for m in expected])

    @NEEDS_AUDIO
    def test_sheetsage_through_a_fake_runner_is_moved_down_an_octave(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-sheetsage-"))
        sf.write(tmp / "song.wav", np.zeros(SR), SR)
        with mock.patch.dict(os.environ, _fake_sheetsage(tmp, self.SHEETSAGE)):
            index = tr.transcribe(tmp / "song.wav", "Pickup", tmp / "out", lyrics="A-maz-ing grace",
                                  engine="sheetsage", vocals=tmp / "song.wav", accompaniment=tmp / "song.wav",
                                  preview=False)
        song = load_song(tmp / "out" / "pickup" / "transcribe" / index["song"])
        self.assertEqual([n.pitch.nameWithOctave for n in song.melody.recurse().notes if hasattr(n, "pitch")],
                         ["D3", "G3", "B3", "A3"])
        self.assertTrue(song.lyric_fits[0].fits)
        self.assertIn("non-commercial", (tmp / "out" / "pickup" / "transcribe" / "report.md").read_text())


if __name__ == "__main__":
    unittest.main()
