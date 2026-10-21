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
        self.assertEqual(set(self.band.parts), {"voice", "piano", "bass"})
        self.assertIn("The waltz style has no drums", " ".join(self.band.notes))
        self.assertIn("right hand rests", " ".join(self.band.notes))

    def test_every_part_lines_up_with_the_melody(self):
        expected = bar_lengths(self.song.melody)
        for part in self.band.score.parts:
            if part.partName == "Drums":
                continue  # written in two voices; checked in test_drums
            self.assertEqual(bar_lengths(part), expected, part.partName)

    def test_piano_left_hand_plays_chord_tones(self):
        timeline = arrange.chord_timeline(self.song.melody)
        lh = self.band.score.parts[2]
        for n in lh.recurse().getElementsByClass("Note"):
            cs = arrange.chord_at(timeline, float(n.getOffsetInHierarchy(lh)))
            self.assertIn(n.pitch.name, {p.name for p in cs.pitches}, f"{n} doesn't fit {cs.figure}")

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

    def test_flat_and_sharp_chords_keep_their_signs(self):
        # Verovio draws the flat in "Bb" with a music-font glyph; unmapped, the PDF lost it
        # and printed "B", a different chord.
        out = Path(tempfile.mkdtemp(prefix="copyist-chords-"))
        (out / "chords.yaml").write_text(
            "format: copyist-song/0\ntitle: Chord Signs\nkey: F\nmeter: 4/4\ntempo: 100\n"
            "voice: {name: Melody, range: [C4, F5]}\n"
            'melody: |\n  "F"F2 A2 | "Bb"B2 d2 | "Eb"e2 c2 | "F#m"f2 A2 | "C#dim"c4 |]\n'
            "lyrics:\n  - one two three four five six sev-en eight\n", encoding="utf-8")
        song = load_song(out / "chords.yaml")
        paths = engrave.engrave(song.score, out, "lead-sheet", song.title, song.credits)
        text = pymupdf.open(paths["pdf"])[0].get_text()
        for chord in ("B♭", "E♭", "F♯m", "C♯dim"):
            self.assertIn(chord, text)
        unprintable = [hex(ord(c)) for c in text if c == "\x00" or 0xE000 <= ord(c) <= 0xF8FF]
        self.assertEqual(unprintable, [])


if __name__ == "__main__":
    unittest.main()
