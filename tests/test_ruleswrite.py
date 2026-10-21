"""Rule-based melody writer (no YuE2)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import ruleswrite, write
from copyist.song import load_song

LYRICS = """[Verse]
Morning comes across the hill
Rivers running home to the sea

[Chorus]
Carry me home, carry me home
Carry me over the water home
"""


class ComposeTests(unittest.TestCase):
    def test_draft_loads_and_fits(self):
        draft = ruleswrite.compose(LYRICS, "waltz", "alto", seed=1)
        self.assertEqual(draft.meter, "3/4")
        self.assertGreaterEqual(len(draft.bars), 4)
        cand = write.song_from_bars(
            draft.bars, unit=draft.unit, meter=draft.meter, key=draft.key, tempo=draft.tempo,
            lyrics=LYRICS, title="Carry Me Home", voice="alto", style="waltz",
            written_with={"planner": "rules", "seed": 1}, notes=draft.notes)
        path = Path(tempfile.mkdtemp(prefix="copyist-rules-")) / "song.yaml"
        path.write_text(write.song_yaml(cand.data), encoding="utf-8")
        song = load_song(path)
        self.assertTrue(song.lyric_fits[0].fits)
        self.assertEqual([s["name"] for s in song.sections], ["verse", "chorus"])
        self.assertEqual(song.written_with["planner"], "rules")

    def test_seed_changes_the_melody(self):
        a = ruleswrite.compose(LYRICS, "folk", "alto", 1)
        b = ruleswrite.compose(LYRICS, "folk", "alto", 2)
        self.assertNotEqual(
            [t.step + str(t.octave) for bar in a.bars for t in bar.toks if t.kind == "note"],
            [t.step + str(t.octave) for bar in b.bars for t in bar.toks if t.kind == "note"])

    def test_compound_meter_tempo_counts_dotted_quarters(self):
        # A jig's 96-132 BPM is dotted quarters; written as a bare number it played at
        # quarter = N, two-thirds of the speed.
        draft = ruleswrite.compose(LYRICS, "celtic-jig", "alto", seed=1)
        self.assertEqual(draft.meter, "6/8")
        self.assertRegex(str(draft.tempo), r"^3/8=\d+$")
        bpm = int(str(draft.tempo).split("=")[1])
        self.assertTrue(96 <= bpm <= 132, bpm)
        self.assertIn(f"Q:3/8={bpm}", ruleswrite.plan_abc(draft))
        cand = write.song_from_bars(
            draft.bars, unit=draft.unit, meter=draft.meter, key=draft.key, tempo=draft.tempo,
            lyrics=LYRICS, title="Jig", voice="alto", style="celtic-jig",
            written_with={"planner": "rules", "seed": 1}, notes=draft.notes)
        path = Path(tempfile.mkdtemp(prefix="copyist-rules-jig-")) / "song.yaml"
        path.write_text(write.song_yaml(cand.data), encoding="utf-8")
        mark = load_song(path).score.recurse().getElementsByClass("MetronomeMark").first()
        self.assertEqual((mark.referent.quarterLength, mark.number), (1.5, bpm))
        waltz = ruleswrite.compose(LYRICS, "waltz", "alto", seed=1)
        self.assertIsInstance(waltz.tempo, int)

    def test_empty_lyrics_refused(self):
        with self.assertRaises(write.WriteError):
            ruleswrite.compose("   ", "waltz", "alto", 1)

    def test_melody_stays_diatonic(self):
        # Chromatic sharps against flats made Hope candidate 1 sound sharp and flat at once.
        from copyist import abcplan
        for seed in (1, 2, 3, 7, 11):
            draft = ruleswrite.compose(LYRICS, "folk", "alto", seed)
            scale = set(ruleswrite._scale_pcs(draft.key))
            midis = abcplan.pitches(draft.bars, draft.key)
            off = [m for m in midis if (m % 12) not in scale]
            self.assertEqual(off, [], f"seed {seed} key {draft.key}: off-scale {off}")
            melody = abcplan.write(draft.bars, draft.unit, draft.unit)
            self.assertNotRegex(melody, r"[=^_]", f"seed {seed}: chromatic mark in {melody!r}")


class WriteCommandRulesTests(unittest.TestCase):
    def setUp(self):
        from copyist import render
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-rules-cmd-"))
        self.lyrics = self.tmp / "lyrics.txt"
        self.lyrics.write_text(LYRICS, encoding="utf-8")
        self.out = self.tmp / "out"
        def fake_band(midi, wav, style=None, cache=None, stems_dir=None):
            wav.write_bytes(b"RIFF")
            return render.BandAudio(wav, "sampled")
        self.patch = mock.patch.object(render, "render_band", fake_band)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_write_engine_rules(self):
        from copyist.cli import main
        self.assertEqual(main(["write", str(self.lyrics), "--title", "Carry Me Home", "--style", "waltz",
                               "--engine", "rules", "--candidates", "2", "--out", str(self.out),
                               "--no-preview"]), 0)
        folder = self.out / "carry-me-home" / "write"
        index = json.loads((folder / write.INDEX).read_text())
        self.assertEqual(index["engine"], "rules")
        self.assertEqual(sum(1 for e in index["candidates"] if e.get("ok")), 2)
        song = load_song(folder / index["candidates"][0]["song"])
        self.assertTrue(song.lyric_fits[0].fits)
        self.assertEqual(song.written_with["planner"], "rules")
        self.assertTrue((folder / "candidate-1" / write.PLAN_FILE).is_file())


if __name__ == "__main__":
    unittest.main()
