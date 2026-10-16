import tempfile
import unittest
from pathlib import Path

import pymupdf
from music21 import harmony, stream

from copyist import arrange, engrave
from copyist.song import load_song

ROOT = Path(__file__).resolve().parents[1]


def bar_lengths(part):
    return [sum(e.quarterLength for e in m.notesAndRests if not isinstance(e, harmony.ChordSymbol))
            for m in part.getElementsByClass(stream.Measure)]


class ArrangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        cls.band = arrange.arrange_band(cls.song)

    def test_style_and_parts(self):
        self.assertEqual(self.band.style, "waltz")
        self.assertEqual(set(self.band.parts), {"voice", "piano", "bass", "drums"})

    def test_every_part_lines_up_with_the_melody(self):
        expected = bar_lengths(self.song.melody)
        for part in self.band.score.parts:
            if part.partName == "Drums":
                continue  # written in two voices; checked in test_drums
            self.assertEqual(bar_lengths(part), expected, part.partName)

    def test_piano_plays_the_written_chords(self):
        timeline = arrange.chord_timeline(self.song.melody)
        rh = self.band.score.parts[1]
        for ch in rh.recurse().getElementsByClass("Chord"):
            if isinstance(ch, harmony.ChordSymbol):
                continue
            cs = arrange.chord_at(timeline, float(ch.getOffsetInHierarchy(rh)))
            self.assertTrue({p.name for p in ch.pitches} <= {p.name for p in cs.pitches},
                            f"{ch} doesn't fit {cs.figure}")

    def test_bass_sounds_an_octave_below_written(self):
        perf = self.band.performance()
        bass = [p for p in perf.parts if p.partName == "Bass"][0]
        pitches = [n.pitch.midi for n in bass.recurse().notes]
        self.assertTrue(28 <= min(pitches) and max(pitches) <= 50)  # E1 to D3


class EngraveTests(unittest.TestCase):
    def test_lead_sheet_pdf_is_letter_and_has_music(self):
        song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        out = Path(tempfile.mkdtemp(prefix="copyist-engrave-"))
        paths = engrave.engrave(song.score, out, "lead-sheet", song.title, song.credits)
        doc = pymupdf.open(paths["pdf"])
        self.assertEqual(tuple(round(x) for x in doc[0].rect[2:]), (612, 792))
        text = doc[0].get_text()
        for expected in ("Amazing Grace", "John Newton", "maz", "♩"):
            self.assertIn(expected, text)
        xml = paths["musicxml"].read_text(encoding="utf-8")
        self.assertEqual(xml.count("<extend"), 15)   # held word endings across the 4 verses
        self.assertNotIn("copyist-extend", xml)
        pix = doc[0].get_pixmap(dpi=30)
        dark = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 128)
        self.assertGreater(dark, 500)  # the page isn't blank


if __name__ == "__main__":
    unittest.main()
