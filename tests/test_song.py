import unittest
from pathlib import Path

from music21 import harmony

from copyist.song import SongError, load_song, parse_key
from helpers import song_from

ROOT = Path(__file__).resolve().parents[1]


class KeyTests(unittest.TestCase):
    def test_keys(self):
        self.assertEqual(str(parse_key("G")), "G major")
        self.assertEqual(str(parse_key("Em")), "e minor")
        self.assertEqual(str(parse_key("Bb")), "B- major")
        self.assertEqual(str(parse_key("F#m")), "f# minor")
        self.assertEqual(str(parse_key("D dorian")), "D dorian")

    def test_bad_key(self):
        with self.assertRaises(SongError):
            parse_key("H")


class LoadTests(unittest.TestCase):
    def test_amazing_grace_loads(self):
        song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        self.assertEqual(song.title, "Amazing Grace")
        self.assertEqual(len(song.verses), 4)
        self.assertTrue(all(f.fits for f in song.lyric_fits))
        chords = [cs.figure for cs in song.melody.recurse().getElementsByClass(harmony.ChordSymbol)]
        self.assertEqual(chords[:4], ["G", "C", "G", "D"])

    def test_missing_fields(self):
        with self.assertRaises(SongError):
            song_from(melody="")

    def test_wrong_format_version(self):
        with self.assertRaises(SongError):
            song_from(format="copyist-song/99", melody="C D E F |")


if __name__ == "__main__":
    unittest.main()
