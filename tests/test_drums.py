import dataclasses
import unittest
from pathlib import Path

from music21 import harmony, note, percussion, stream

from copyist import arrange, drums
from copyist.song import SongError, load_song
from helpers import song_from

ROOT = Path(__file__).resolve().parents[1]


def hits_in(measure):
    """Written drum hits in a bar: (offset, set of display pitches)."""
    out = []
    for v in measure.voices:
        for el in v.notesAndRests:
            if isinstance(el, percussion.PercussionChord):
                out.append((float(el.offset), {u.displayName for u in el.notes}))
            elif isinstance(el, note.Unpitched):
                out.append((float(el.offset), {el.displayName}))
    return out


class DrumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Country waltz keeps the kit; the default waltz is piano-vocal without drums.
        cls.song = dataclasses.replace(load_song(ROOT / "songs" / "amazing-grace.yaml"), style="country-waltz")
        cls.band = arrange.arrange_band(cls.song)
        cls.kit = [p for p in cls.band.score.parts if p.partName == "Drums"][0]
        cls.bars = {m.number: m for m in cls.kit.getElementsByClass(stream.Measure)}

    def test_drum_bars_line_up_with_the_melody(self):
        def lengths(part):
            out = []
            for m in part.getElementsByClass(stream.Measure):
                if m.voices:
                    out.append(max(sum(e.quarterLength for e in v.notesAndRests) for v in m.voices))
                else:
                    out.append(sum(e.quarterLength for e in m.notesAndRests
                                   if not isinstance(e, harmony.ChordSymbol)))
            return out
        self.assertEqual(lengths(self.kit), lengths(self.song.melody))

    def test_crash_on_bar_one_and_after_the_fill(self):
        crash = drums.KIT["crash"][0] + str(drums.KIT["crash"][1])
        for bar in (1, 9):
            self.assertIn(crash, hits_in(self.bars[bar])[0][1], f"bar {bar}")
        self.assertNotIn(crash, hits_in(self.bars[2])[0][1])

    def test_fill_in_bar_eight(self):
        snare = drums.KIT["snare"][0] + str(drums.KIT["snare"][1])
        offsets = [off for off, pieces in hits_in(self.bars[8]) if pieces == {snare}]
        self.assertEqual(offsets, [2.0, 2.5])

    def test_performance_uses_the_gm_drum_channel(self):
        perf = self.band.performance()
        kit = [p for p in perf.parts if p.partName == "Drums"][0]
        inst = kit.getElementsByClass("Instrument").first()
        self.assertEqual(inst.midiChannel, 9)
        self.assertEqual({n.pitch.midi for n in kit.recurse().notes} - {36, 37, 38, 42, 49}, set())


class InstrumentChoiceTests(unittest.TestCase):
    def test_excluded_instruments_get_no_part(self):
        song = song_from(melody='"C"C D E F | "G"G4 |', lyrics=["a b c d e"],
                         instruments=["voice", "piano"])
        band = arrange.arrange_band(song)
        self.assertEqual(set(band.parts), {"voice", "piano"})
        self.assertEqual(band.excluded, ["guitar", "bass", "drums"])
        names = {p.partName for p in band.performance().parts}
        self.assertNotIn("Drums", names)
        self.assertNotIn("Bass", names)

    def test_unknown_instrument_is_an_error(self):
        with self.assertRaises(SongError):
            song_from(melody="C D E F |", instruments=["voice", "theremin"])


if __name__ == "__main__":
    unittest.main()
