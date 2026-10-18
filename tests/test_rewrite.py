"""Section rewriting: again, higher, simpler."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import abcplan, rewrite, write
from copyist.song import load_song

PLANS = Path(__file__).resolve().parent / "data" / "plans"


def plan_text(name: str) -> str:
    return (PLANS / f"{name}.abc").read_text(encoding="utf-8")


def plan_lyrics(name: str) -> str:
    return (PLANS / f"{name}.txt").read_text(encoding="utf-8")


def make_song(tmp: Path, title: str = "Carry Me Home", plan: str = "alto-waltz") -> Path:
    cand = write.song_from_plan(plan_text(plan), plan_lyrics(plan), title, "alto", "waltz",
                                {"planner": "yue-plan", "seed": 1})
    path = tmp / f"{write.slug(title)}.yaml"
    path.write_text(write.song_yaml(cand.data), encoding="utf-8")
    return path


class BarHelpersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-rewrite-"))
        self.path = make_song(self.tmp)
        self.data = rewrite.load_data(self.path)

    def test_bars_and_section_bounds(self):
        bars = rewrite.bars_from_melody(self.data["melody"], self.data["sections"])
        self.assertEqual(len(bars), 18)
        self.assertEqual(rewrite.section_bounds(self.data["sections"], "verse", 18), (0, 10))
        self.assertEqual(rewrite.section_bounds(self.data["sections"], "chorus", 18), (10, 18))
        self.assertEqual({b.section for b in bars[10:]}, {"chorus"})

    def test_unknown_section_is_refused(self):
        with self.assertRaises(write.WriteError) as e:
            rewrite.section_bounds(self.data["sections"], "bridge", 18)
        self.assertIn("bridge", str(e.exception))

    def test_transpose_notes_raises_pitch_keeps_chords(self):
        bars = rewrite.section_slice(self.data, "chorus")
        before = abcplan.pitches(bars, self.data["key"])
        chords = [t.text for b in bars for t in b.toks if t.kind == "chord"]
        abcplan.transpose_notes(bars, self.data["key"], 3)
        after = abcplan.pitches(bars, self.data["key"])
        self.assertEqual([a - b for a, b in zip(after, before)], [3] * len(before))
        self.assertEqual([t.text for b in bars for t in b.toks if t.kind == "chord"], chords)

    def test_raise_section_moves_chords_with_notes(self):
        bars, new_key = rewrite.raise_section(self.data, "chorus", 3)
        # Partial section: song key stays; chorus chords move with the pitches.
        self.assertEqual(new_key, self.data["key"])
        chorus = bars[10:]
        chords = [t.text for b in chorus for t in b.toks if t.kind == "chord"]
        self.assertTrue(any(c in ("Bb", "A#") or c.startswith("Bb") or c.startswith("A#")
                            for c in chords))                     # G + 3
        self.assertTrue(any(c.startswith("F") for c in chords))   # D + 3 → F


class HigherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-rewrite-hi-"))
        self.path = make_song(self.tmp)
        self.out = self.tmp / "out"
        (self.out / "carry-me-home" / "write").mkdir(parents=True)
        (self.out / "carry-me-home" / "write" / "lyrics.txt").write_text(
            plan_lyrics("alto-waltz"), encoding="utf-8")

    def test_higher_raises_chorus_and_keeps_verse(self):
        with mock.patch.object(write, "band_preview", return_value="fake"):
            index = rewrite.rewrite_section(self.path, "chorus", "higher", self.out,
                                            candidates=2, previews=True, plan_more=False)
        self.assertTrue(any(e.get("ok") for e in index["candidates"]))
        base = rewrite.load_data(self.path)
        base_bars = rewrite.bars_from_melody(base["melody"], base["sections"])
        verse_before = abcplan.pitches(base_bars[:10], base["key"])
        chorus_before = abcplan.pitches(base_bars[10:], base["key"])
        best = next(e for e in index["candidates"] if e.get("ok"))
        raised = rewrite.load_data(self.out / "carry-me-home" / "rewrite" / "higher" / best["song"])
        bars = rewrite.bars_from_melody(raised["melody"], raised["sections"])
        self.assertEqual(abcplan.pitches(bars[:10], raised["key"]), verse_before)
        self.assertGreater(rewrite.mean_pitch(bars[10:], raised["key"]),
                           sum(chorus_before) / len(chorus_before))
        # Chorus chords moved with the notes (not left in the old key against a raised tune).
        chorus_chords = [t.text for b in bars[10:] for t in b.toks if t.kind == "chord"]
        base_chorus = [t.text for b in base_bars[10:] for t in b.toks if t.kind == "chord"]
        self.assertNotEqual(chorus_chords, base_chorus)
        song = load_song(self.out / "carry-me-home" / "rewrite" / "higher" / best["song"])
        self.assertTrue(song.lyric_fits[0].fits)

    def test_cli_higher(self):
        from copyist.cli import main
        with mock.patch.object(write, "band_preview", return_value="fake"):
            self.assertEqual(main(["rewrite", str(self.path), "--section", "verse", "--how", "higher",
                                   "--candidates", "1", "--out", str(self.out), "--no-preview"]), 0)
        folder = self.out / "carry-me-home" / "rewrite" / "higher"
        index = json.loads((folder / write.INDEX).read_text())
        self.assertEqual(index["how"], "higher")
        self.assertTrue(index["candidates"][0]["ok"])


class AgainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-rewrite-again-"))
        self.out = self.tmp / "out"
        write_folder = self.out / "carry-me-home" / "write"
        write_folder.mkdir(parents=True)
        lyrics = plan_lyrics("alto-waltz")
        (write_folder / "lyrics.txt").write_text(lyrics, encoding="utf-8")

        base_cand = write.song_from_plan(plan_text("alto-waltz"), lyrics, "Carry Me Home", "alto", "waltz",
                                         {"planner": "yue-plan", "seed": 1})
        # Donor: same form, chorus raised so the swap is audible and leaps differ.
        donor_data = dict(base_cand.data)
        donor_bars, donor_key = rewrite.raise_section(donor_data, "chorus", 5)
        donor_cand = rewrite.candidate_from_bars(
            donor_bars, unit=__import__("fractions").Fraction(donor_data["unit"]),
            meter=donor_data["meter"], key=donor_key, tempo=donor_data["tempo"],
            lyrics=lyrics, title="Carry Me Home", voice="alto", style="waltz",
            written_with={"planner": "yue-plan", "seed": 2})

        self.base_path = write_folder / "candidate-1" / "carry-me-home.yaml"
        self.base_path.parent.mkdir(parents=True)
        self.base_path.write_text(write.song_yaml(base_cand.data), encoding="utf-8")
        donor_path = write_folder / "candidate-2" / "carry-me-home.yaml"
        donor_path.parent.mkdir(parents=True)
        donor_path.write_text(write.song_yaml(donor_cand.data), encoding="utf-8")

        write.write_index(write_folder, {
            "title": "Carry Me Home", "slug": "carry-me-home", "lyrics_id": "x",
            "candidates": [
                {"seed": 1, "folder": "candidate-1", "ok": True,
                 "song": "candidate-1/carry-me-home.yaml",
                 "key": base_cand.data["key"], "meter": base_cand.data["meter"]},
                {"seed": 2, "folder": "candidate-2", "ok": True,
                 "song": "candidate-2/carry-me-home.yaml",
                 "key": donor_cand.data["key"], "meter": donor_cand.data["meter"]},
            ],
        })
        # Song file outside write/ (as if kept).
        self.song = self.tmp / "songs" / "carry-me-home.yaml"
        self.song.parent.mkdir()
        self.song.write_text(self.base_path.read_text(), encoding="utf-8")

    def test_again_swaps_chorus_from_donor(self):
        with mock.patch.object(write, "band_preview", return_value="fake"):
            index = rewrite.rewrite_section(self.song, "chorus", "again", self.out,
                                            candidates=1, previews=False, plan_more=False)
        self.assertTrue(index["candidates"][0]["ok"])
        self.assertEqual(index["candidates"][0]["donor"], 2)
        base = rewrite.load_data(self.song)
        out = rewrite.load_data(self.out / "carry-me-home" / "rewrite" / "again" /
                                index["candidates"][0]["song"])
        self.assertEqual(abcplan.pitches(rewrite.section_slice(out, "verse"), out["key"]),
                         abcplan.pitches(rewrite.section_slice(base, "verse"), base["key"]))
        self.assertNotEqual(abcplan.pitches(rewrite.section_slice(out, "chorus"), out["key"]),
                            abcplan.pitches(rewrite.section_slice(base, "chorus"), base["key"]))

    def test_simpler_prefers_smaller_leaps(self):
        # Candidate 2's raised chorus has larger leaps on average; seed a third with a flat chorus.
        write_folder = self.out / "carry-me-home" / "write"
        base = rewrite.load_data(self.base_path)
        bars = rewrite.bars_from_melody(base["melody"], base["sections"])
        # Flatten chorus pitches toward the first note (small leaps).
        chorus = bars[10:]
        first = abcplan.pitches(chorus, base["key"])[0]
        midis = abcplan._note_midis(chorus, base["key"])
        flat = []
        for row in midis:
            flat.append([None if m is None else first + (0 if abs(m - first) < 3 else (1 if m > first else -1))
                         for m in row])
        abcplan._set_note_pitches(chorus, base["key"], flat)
        merged = bars[:10] + chorus
        lyrics = plan_lyrics("alto-waltz")
        flat_cand = rewrite.candidate_from_bars(
            merged, unit=__import__("fractions").Fraction(base["unit"]),
            meter=base["meter"], key=base["key"], tempo=base["tempo"],
            lyrics=lyrics, title="Carry Me Home", voice="alto", style="waltz",
            written_with={"planner": "yue-plan", "seed": 3})
        path = write_folder / "candidate-3" / "carry-me-home.yaml"
        path.parent.mkdir()
        path.write_text(write.song_yaml(flat_cand.data), encoding="utf-8")
        index = write.read_index(write_folder)
        index["candidates"].append({
            "seed": 3, "folder": "candidate-3", "ok": True, "song": "candidate-3/carry-me-home.yaml",
            "key": flat_cand.data["key"], "meter": flat_cand.data["meter"],
        })
        write.write_index(write_folder, index)

        with mock.patch.object(write, "band_preview", return_value="fake"):
            result = rewrite.rewrite_section(self.song, "chorus", "simpler", self.out,
                                             candidates=1, previews=False, plan_more=False)
        self.assertEqual(result["candidates"][0]["donor"], 3)

    def test_keep_rewrite(self):
        with mock.patch.object(write, "band_preview", return_value="fake"):
            rewrite.rewrite_section(self.song, "chorus", "again", self.out,
                                    candidates=1, previews=False, plan_more=False)
        songs = self.tmp / "kept"
        target = rewrite.keep(self.out, "Carry Me Home", "again", 1, songs, replace=False)
        self.assertTrue(target.is_file())
        self.assertTrue(load_song(target).lyric_fits[0].fits)


if __name__ == "__main__":
    unittest.main()
