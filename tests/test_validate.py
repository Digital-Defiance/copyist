import unittest
from pathlib import Path

from copyist.song import load_song
from copyist.validate import FAIL, PASS, WARN, is_finished, report_markdown, validate
from helpers import severities, song_from

ROOT = Path(__file__).resolve().parents[1]


class AmazingGraceTests(unittest.TestCase):
    def test_everything_passes(self):
        song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        findings = validate(song)
        self.assertTrue(is_finished(findings))
        self.assertEqual({f.severity for f in findings}, {PASS})
        self.assertIn("Finished", report_markdown(song, findings))


class BarsTests(unittest.TestCase):
    def test_overfull_bar_fails(self):
        findings = validate(song_from(melody='"C"C4 | D4 E2 | F4 |', lyrics=["a b c d"]))
        bad = [f for f in findings if f.check == "bars" and f.severity == FAIL]
        self.assertEqual([f.bar for f in bad], [2])

    def test_pickup_and_final_bar_are_fine_together(self):
        findings = validate(song_from(melody='G | "C"c4 | c3 |', lyrics=["a b c"]))
        self.assertEqual(severities(findings, "bars"), {PASS})


class LyricsFitTests(unittest.TestCase):
    def test_too_many_syllables_fails(self):
        findings = validate(song_from(melody='"C"C D E F |', lyrics=["one two three four five"]))
        self.assertIn(FAIL, severities(findings, "lyrics-fit"))

    def test_too_few_syllables_reports_where(self):
        findings = validate(song_from(melody='"C"C D E F | G4 |', lyrics=["one two three"]))
        bad = [f for f in findings if f.check == "lyrics-fit" and f.severity == FAIL]
        self.assertEqual((bad[0].bar, bad[0].beat), (1, 4.0))


class RangeTests(unittest.TestCase):
    def test_far_out_of_range_fails(self):
        findings = validate(song_from(melody='"C"C D E e |', lyrics=["a b c d"]))
        self.assertIn(FAIL, severities(findings, "range"))

    def test_a_step_out_only_warns(self):
        findings = validate(song_from(melody='"C"C D E d |', lyrics=["a b c d"]))
        self.assertEqual(severities(findings, "range"), {WARN})


class ChordToneTests(unittest.TestCase):
    def test_non_chord_tone_on_downbeat_warns(self):
        findings = validate(song_from(melody='"C"D2 E2 | "G"G4 |', lyrics=["a b c"]))
        warns = [f for f in findings if f.check == "chord-tones" and f.severity == WARN]
        self.assertEqual([(f.bar, f.beat) for f in warns], [(1, 1.0)])


class ProsodyTests(unittest.TestCase):
    def test_stress_on_weak_beat_warns(self):
        # "a-MAZ-ing": the stressed syllable on beat 3 and "a" on the downbeat.
        findings = validate(song_from(melody='"C"C2 D E | F4 |', lyrics=["a-maz-ing time"]))
        self.assertIn(WARN, severities(findings, "prosody"))

    def test_stress_on_strong_beat_passes(self):
        findings = validate(song_from(melody='C | "C"D2 E F | G4 |', lyrics=["a-maz-ing grace now"]))
        self.assertEqual(severities(findings, "prosody"), {PASS})


class KeyTests(unittest.TestCase):
    def test_note_outside_key_warns(self):
        findings = validate(song_from(melody='"C"C D E ^F |', lyrics=["a b c d"]))
        self.assertIn(WARN, severities(findings, "key"))


if __name__ == "__main__":
    unittest.main()
