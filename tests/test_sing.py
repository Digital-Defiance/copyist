import math
import tempfile
import unittest
import wave
from pathlib import Path

from copyist import sing
from copyist.song import SongError, load_song
from helpers import song_from

ROOT = Path(__file__).resolve().parents[1]

import importlib.util

HAVE_LIBROSA = importlib.util.find_spec("librosa") is not None


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = load_song(ROOT / "songs" / "amazing-grace.yaml")

    def test_words_span_their_notes(self):
        notes = sing.sung_notes(self.song, 1, (0, 1))
        self.assertEqual([(n.word, n.kind) for n in notes],
                         [("Amazing", 2), ("Amazing", 3), ("Amazing", 3), ("Amazing", 3)])
        self.assertEqual(notes[0].phones, "en_AH0-M-EY1-Z-IH0-NG")
        self.assertEqual([n.midi for n in notes], [62, 67, 71, 67])

    def test_ties_merge_and_timing_follows_tempo(self):
        notes = sing.sung_notes(self.song, 1)
        me = [n for n in notes if n.word == "me"][0]   # d3- | d2: five beats at 80 bpm
        self.assertAlmostEqual(me.dur, 5 * 60 / 80)
        self.assertAlmostEqual(notes[1].start, 60 / 80)

    def test_old_contractions_have_pronunciations(self):
        notes = sing.sung_notes(self.song, 2, (0, 0))
        self.assertEqual((notes[0].word, notes[0].phones), ("'Twas", "en_T-W-AH1-Z"))

    def test_segments_are_soulx_shaped(self):
        segs = sing.soulx_segments(sing.sung_notes(self.song, 1))
        self.assertEqual(len(segs), 4)               # one per four-bar phrase
        for seg in segs:
            counts = {len(seg[k].split()) for k in ("duration", "text", "phoneme", "note_pitch", "note_type")}
            self.assertEqual(len(counts), 1)
            self.assertTrue(seg["text"].startswith("<SP>") and seg["text"].endswith("<SP>"))
            start, end = seg["time"]
            self.assertAlmostEqual((end - start) / 1000, sum(map(float, seg["duration"].split())), places=2)

    def test_short_last_phrase_folds_in(self):
        segs = sing.soulx_segments(sing.sung_notes(self.song, 1, (0, 4)))
        self.assertEqual(len(segs), 1)

    def test_unknown_word_asks_for_a_pronunciation(self):
        song = song_from(melody='"C"C D E F |', lyrics=["zorblax is my friend"])
        with self.assertRaises(SongError):
            sing.sung_notes(song, 1)
        song = song_from(melody='"C"C D E F |', lyrics=["zorblax is my friend"],
                         pronunciations={"zorblax": "Z AO1 R B L AE0 K S"})
        self.assertEqual(sing.sung_notes(song, 1, pronunciations=song.pronunciations)[0].phones,
                         "en_Z-AO1-R-B-L-AE0-K-S")


def tone_file(notes, offset=0.5, detune_cents=0.0, sr=22050):
    import numpy as np
    total = offset + notes[-1].start + notes[-1].dur + 0.5
    y = np.zeros(int(total * sr), dtype=np.float32)
    for n in notes:
        if not n.midi:
            continue
        hz = 440 * 2 ** ((n.midi - 69) / 12) * 2 ** (detune_cents / 1200)
        a, b = int((offset + n.start) * sr), int((offset + n.start + n.dur) * sr)
        t = np.arange(b - a) / sr
        y[a:b] = 0.3 * np.sin(2 * math.pi * hz * t) + 0.1 * np.sin(4 * math.pi * hz * t)
    path = Path(tempfile.mkdtemp(prefix="copyist-pitch-")) / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    return path


@unittest.skipUnless(HAVE_LIBROSA, "pitch checking needs librosa (pip install copyist[sing])")
class PitchCheckTests(unittest.TestCase):
    def setUp(self):
        self.notes = sing.sung_notes(load_song(ROOT / "songs" / "amazing-grace.yaml"), 1, (0, 4))

    def test_in_tune_passes(self):
        from copyist import pitch
        results = pitch.check(tone_file(self.notes), self.notes, offset=0.5)
        self.assertTrue(results and all(r.ok for r in results), [r.describe() for r in results if not r.ok])

    def test_a_semitone_sharp_fails(self):
        from copyist import pitch
        results = pitch.check(tone_file(self.notes, detune_cents=100), self.notes, offset=0.5)
        self.assertFalse(any(r.ok for r in results))
        self.assertIn("sharp", results[0].describe())


class HearTests(unittest.TestCase):
    def test_compare_counts_words_in_order(self):
        from copyist import hear
        share, missed = hear.compare(["Amazing", "grace,", "how", "sweet"], ["amazing", "Grace", "how", "neat"])
        self.assertAlmostEqual(share, 0.75)
        self.assertEqual(missed, ["sweet"])


if __name__ == "__main__":
    unittest.main()
