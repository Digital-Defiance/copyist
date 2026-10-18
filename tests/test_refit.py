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
