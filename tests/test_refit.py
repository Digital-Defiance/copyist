"""Refitting new lyrics under an existing melody."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from copyist import refit, write
from copyist.song import load_song

PLANS = Path(__file__).resolve().parent / "data" / "plans"


def plan_lyrics(name: str) -> str:
    return (PLANS / f"{name}.txt").read_text(encoding="utf-8")


def plan_text(name: str) -> str:
    return (PLANS / f"{name}.abc").read_text(encoding="utf-8")


class RefitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-refit-"))
        cand = write.song_from_plan(plan_text("alto-waltz"), plan_lyrics("alto-waltz"),
                                    "Carry Me Home", "alto", "waltz",
                                    {"planner": "yue-plan", "seed": 1})
        self.path = self.tmp / "carry-me-home.yaml"
        self.path.write_text(write.song_yaml(cand.data), encoding="utf-8")

    def test_refit_changes_words_keeps_pitches(self):
        before = load_song(self.path)
        before_midi = [n.pitch.midi for n in before.melody.recurse().notes if hasattr(n, "pitch")]
        new = """[Verse]
Evening falls across the hill
Rivers running home to the sea

[Chorus]
Carry me home, carry me home
Carry me over the water home
"""
        refit.refit(self.path, new)
        after = load_song(self.path)
        self.assertTrue(after.lyric_fits[0].fits)
        self.assertIn("Eve-ning", after.verses[0])
        self.assertNotIn("Morn-ing", after.verses[0])
        self.assertNotIn("Morning", after.verses[0])
        after_midi = [n.pitch.midi for n in after.melody.recurse().notes if hasattr(n, "pitch")]
        # Same contour when syllable counts match (no splits needed).
        self.assertEqual(before_midi, after_midi)
        self.assertTrue(after.written_with.get("refit"))

    def test_plain_for_edit(self):
        text = refit.plain_for_edit(["Hope is the thing with fea-thers\nThat per-ches in the soul"])
        self.assertEqual(text, "Hope is the thing with feathers\nThat perches in the soul")

    def test_empty_refused(self):
        with self.assertRaises(write.WriteError):
            refit.refit(self.path, "   ")

    def amazing_grace(self) -> Path:
        path = self.tmp / "amazing-grace.yaml"
        path.write_text((PLANS.parents[2] / "songs" / "amazing-grace.yaml").read_text(encoding="utf-8"),
                        encoding="utf-8")
        return path

    def test_each_verse_fits_the_whole_melody(self):
        # Two verses used to be fitted as one: "32 notes for 56 syllables".
        path = self.amazing_grace()
        before = [n.pitch.midi for n in load_song(path).melody.recurse().notes if hasattr(n, "pitch")]
        refit.refit(path, "Amazing grace, how sweet the sound\nThat saved a wretch like me\n"
                          "I once was lost, but now am found\nWas blind, but now I see\n\n"
                          "When we've been there ten thousand years\nBright shining as the sun\n"
                          "We've no less days to sing God's praise\nThan when we'd first begun\n")
        after = load_song(path)
        self.assertEqual(len(after.verses), 2)
        self.assertTrue(all(f.fits for f in after.lyric_fits))
        self.assertIn("thou-sand", after.verses[1])
        self.assertEqual(before, [n.pitch.midi for n in after.melody.recurse().notes if hasattr(n, "pitch")])

    def test_all_verses_from_the_page_round_trip(self):
        path = self.amazing_grace()
        verses = load_song(path).verses
        refit.refit(path, refit.plain_for_edit(verses))
        after = load_song(path)
        self.assertEqual(len(after.verses), 4)
        self.assertTrue(all(f.fits for f in after.lyric_fits))

    def test_half_a_verse_is_not_stretched_over_the_melody(self):
        with self.assertRaisesRegex(write.WriteError, "too few to be a verse"):
            refit.refit(self.amazing_grace(),
                        "Amazing grace how sweet the sound that saved a wretch like me\n\n"
                        "I once was lost but now am found was blind but now I see "
                        "and more and more words here to sing")   # 36 syllables, 14 in the first block


class RefitPageTests(unittest.TestCase):
    def test_job_args_refit(self):
        # Light check via job_args without the full web fixture when possible.
        from copyist.web.server import Project, job_args
        root = Path(tempfile.mkdtemp(prefix="copyist-refit-web-"))
        songs = root / "songs"
        songs.mkdir()
        (songs / "amazing-grace.yaml").write_text(
            Path(__file__).resolve().parents[1].joinpath("songs/amazing-grace.yaml").read_text(),
            encoding="utf-8")
        project = Project(root)
        label, slug, args = job_args(project, {
            "action": "refit", "song": "amazing-grace",
            "lyrics": "Amazing grace how sweet the sound\nThat saved a wretch like me",
        })
        self.assertEqual(slug, "amazing-grace")
        self.assertEqual(label, "Fitting the new lyrics")
        self.assertEqual(args[:2], ["refit", "songs/amazing-grace.yaml"])
        self.assertIn("--build", args)
        self.assertTrue((root / "out/amazing-grace/refit-lyrics.txt").is_file())


if __name__ == "__main__":
    unittest.main()
