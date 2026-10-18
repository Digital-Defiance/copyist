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

HAVE_AUDIO = all(importlib.util.find_spec(m) for m in ("librosa", "soundfile", "scipy"))
if HAVE_AUDIO:
    import soundfile as sf
NEEDS_AUDIO = unittest.skipUnless(HAVE_AUDIO, "transcribing needs librosa (pip install copyist[transcribe])")
from copyist.song import load_song

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
        sung = [self.note(1.0, 1.5, 60), self.note(1.5, 2.0, 60.2, attack=True)]
        self.assertEqual(len(tr.clean_notes(sung, self.times, self.midi, self.rms)), 2)

    def test_the_lyrics_fix_the_count(self):
        notes = []
        t = 1.0
        for k in range(12):                            # six sung notes, each with a scoop before it
            notes.append(self.note(t, t + 0.2, 60 + k // 2 * 2 - 1 + (k % 2)))
            t += 0.2 if k % 2 == 0 else 0.6
            notes[-1].end = t
        kept = tr.clean_notes(notes, self.times, self.midi, self.rms, target=6)
        self.assertLessEqual(len(kept), int(6 * 1.25))


class RhythmTests(unittest.TestCase):
    def test_the_plainest_rhythm_wins(self):
        self.assertEqual(tr.snap_rhythm([0.02, 0.47, 1.05]), [Fraction(0), Fraction(1, 2), Fraction(1)])
        self.assertEqual(tr.snap_rhythm([0.0, 0.70]), [Fraction(0), Fraction(3, 4)])
        self.assertEqual(tr.snap_rhythm([0.0, 0.35, 0.68], tr.COMPOUND_PATTERNS), [Fraction(0), Fraction(1, 3), Fraction(2, 3)])


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

    @NEEDS_AUDIO
    def test_sheetsage_through_a_fake_runner_is_moved_down_an_octave(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-sheetsage-"))
        runner = tmp / "yue-transcribe"
        runner.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\na = sys.argv[1:]\n"
                          f"Path(a[a.index('--out') + 1]).write_text({self.SHEETSAGE!r})\n")
        runner.chmod(runner.stat().st_mode | stat.S_IEXEC)
        (tmp / "ss.gguf").write_bytes(b"x")
        sf.write(tmp / "song.wav", np.zeros(SR), SR)
        with mock.patch.dict(os.environ, {"COPYIST_YUE_TRANSCRIBE": str(runner), "COPYIST_SHEETSAGE": str(tmp / "ss.gguf")}):
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
