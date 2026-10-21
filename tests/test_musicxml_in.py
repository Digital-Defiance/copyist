"""MusicXML → song file (first slice of import)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from music21 import converter, harmony, key, meter, note, stream

from copyist import engrave, musicxml_in
from copyist.song import load_song
from copyist.validate import is_finished, validate

ROOT = Path(__file__).resolve().parents[1]


class MusicxmlImportTests(unittest.TestCase):
    def test_round_trip_amazing_grace_keeps_key_meter_and_note_count(self):
        song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        out = Path(tempfile.mkdtemp(prefix="copyist-mxl-"))
        paths = engrave.engrave(song.score, out, "lead-sheet", song.title, song.credits)
        data = musicxml_in.song_data_from_musicxml(paths["musicxml"], style="waltz")
        self.assertEqual(data["key"], "G")
        self.assertEqual(data["meter"], "3/4")
        self.assertEqual(data["title"], "Amazing Grace")
        self.assertEqual(data["style"], "waltz")
        # Same number of pitched notes (ties may differ in spelling).
        imported = Path(tempfile.mkdtemp(prefix="copyist-song-")) / "ag.yaml"
        musicxml_in.import_musicxml(paths["musicxml"], imported, style="waltz")
        again = load_song(imported)
        n_orig = sum(1 for n in song.melody.flatten().notes if n.isNote)
        n_imp = sum(1 for n in again.melody.flatten().notes if n.isNote)
        self.assertEqual(n_imp, n_orig)
        # Every verse comes back on the same notes, holds included ("A-maz-ing_ grace").
        self.assertEqual(len(again.verses), 4)
        self.assertTrue(all(f.fits for f in again.lyric_fits))
        self.assertEqual([" ".join(v.split()) for v in again.verses],
                         [" ".join(v.split()) for v in song.verses])

    def test_picks_the_vocal_part_in_a_piano_vocal_score(self):
        score = stream.Score()
        piano = stream.Part(id="P1")
        piano.partName = "Piano"
        piano.append(note.Note("C4", quarterLength=4))
        vocal = stream.Part(id="P2")
        vocal.partName = "Voice"
        vocal.append(note.Note("G4", quarterLength=1))
        vocal.append(note.Note("A4", quarterLength=1))
        vocal.append(note.Note("B4", quarterLength=1))
        vocal.append(note.Note("C5", quarterLength=1))
        score.insert(0, piano)
        score.insert(0, vocal)
        path = Path(tempfile.mkdtemp(prefix="copyist-pv-")) / "pv.musicxml"
        score.write("musicxml", fp=str(path))
        part = musicxml_in.pick_melody_part(converter.parse(str(path)))
        self.assertTrue("Voice" in (part.partName or "") or "voice" in (part.id or "").lower())
        data = musicxml_in.song_data_from_musicxml(path, title="Demo")
        # Voice has four quarter notes; piano's single whole note must not be chosen.
        self.assertGreaterEqual(data["melody"].count("G") + data["melody"].count("A")
                                + data["melody"].count("B") + data["melody"].count("c"), 4)

    def test_picks_the_part_with_the_words_whatever_its_name(self):
        # A vocal part is often named for its character; the words say which part is sung.
        score = stream.Score()
        flute = stream.Part(id="P1")
        flute.partName = "Melody (flute)"
        flute.append([note.Note(p, quarterLength=1) for p in ("C5", "D5", "E5", "F5")])
        sung = stream.Part(id="P2")
        sung.partName = "Captain Hook"
        for p, word in (("G4", "Yo"), ("A4", "ho"), ("B4", "yo"), ("C5", "ho")):
            n = note.Note(p, quarterLength=1)
            n.lyric = word
            sung.append(n)
        score.insert(0, flute)
        score.insert(0, sung)
        path = Path(tempfile.mkdtemp(prefix="copyist-hook-")) / "hook.musicxml"
        score.write("musicxml", fp=str(path))
        part = musicxml_in.pick_melody_part(converter.parse(str(path)))
        self.assertEqual(part.partName, "Captain Hook")

    def test_a_choir_scores_melody_is_the_top_voice(self):
        # Every part has words; the bass has the most. The tune is the soprano's.
        score = stream.Score()
        for name, pitches in (("Soprano", ("E5", "D5", "C5", "D5")), ("Alto", ("C5", "B4", "A4", "B4")),
                              ("Bass", ("C3", "G2", "A2", "G2", "G2"))):
            p = stream.Part(id=name)
            p.partName = name
            for pitch, word in zip(pitches, ("Lift", "ev", "ry", "voice", "now")):
                n = note.Note(pitch, quarterLength=1)
                n.lyric = word
                p.append(n)
            score.insert(0, p)
        path = Path(tempfile.mkdtemp(prefix="copyist-satb-")) / "satb.musicxml"
        score.write("musicxml", fp=str(path))
        self.assertEqual(musicxml_in.pick_melody_part(converter.parse(str(path))).partName, "Soprano")

    def test_words_stay_on_their_notes(self):
        # Verse 1 holds "home" over two notes; after a rest, verse 2 starts a note late (a skip);
        # verse 2 is silent for the last bar, a refrain printed once under verse 1.
        part = stream.Part()
        m1, m2, m3 = stream.Measure(number=1), stream.Measure(number=2), stream.Measure(number=3)
        m1.append(meter.TimeSignature("4/4"))

        def sung(pitch, *words, length=1.0):
            n = note.Note(pitch, quarterLength=length)
            for k, w in enumerate(words, start=1):
                if w:
                    text, _, syllabic = w.partition("|")
                    n.addLyric(text, lyricNumber=k)
                    if syllabic:
                        n.lyrics[-1].syllabic = syllabic
            return n

        m1.append([sung("C4", "Car|begin", "Sing|begin"), sung("D4", "ry|end", "ing|end"),
                   sung("E4", "me", "out"), sung("F4", "home,", "loud,")])
        m2.append([sung("G4"), note.Rest(quarterLength=1), sung("A4", "oh", None), sung("G4", "go", "and")])
        m3.append([sung("F4", "now", None), sung("E4", "to", None), sung("D4", "the", None), sung("C4", "sea.", None)])
        part.append([m1, m2, m3])
        score = stream.Score()
        score.insert(0, part)
        folder = Path(tempfile.mkdtemp(prefix="copyist-mxl-words-"))
        score.write("musicxml", fp=str(folder / "words.musicxml"))
        musicxml_in.import_musicxml(folder / "words.musicxml", folder / "words.yaml", title="Words")
        song = load_song(folder / "words.yaml")
        self.assertEqual([" ".join(v.split()) for v in song.verses],
                         ["Car-ry me home,_ oh go now to the sea.",
                          "Sing-ing out loud,_ * and now to the sea."])
        self.assertTrue(all(f.fits for f in song.lyric_fits))

    def test_chord_symbols_become_quoted_abc(self):
        part = stream.Part()
        m = stream.Measure(number=1)
        m.append(harmony.ChordSymbol("G"))
        m.append(note.Note("G4", quarterLength=2))
        m.append(harmony.ChordSymbol("D7"))
        m.append(note.Note("A4", quarterLength=2))
        part.append(m)
        score = stream.Score()
        score.insert(0, part)
        path = Path(tempfile.mkdtemp(prefix="copyist-ch-")) / "ch.musicxml"
        score.write("musicxml", fp=str(path))
        data = musicxml_in.song_data_from_musicxml(path, title="Chords")
        self.assertIn('"G"', data["melody"])
        self.assertIn('"D7"', data["melody"])

    def test_a_key_change_keeps_every_pitch(self):
        # Bar 1 in D, bar 2 in C: the song keeps D's signature, so bar 2's naturals must say so.
        part = stream.Part()
        first = stream.Measure(number=1)
        first.append([key.KeySignature(2), meter.TimeSignature("4/4")])
        first.append([note.Note(p, quarterLength=1) for p in ("D4", "E4", "F#4", "G4")])
        second = stream.Measure(number=2)
        second.append(key.KeySignature(0))
        second.append([note.Note(p, quarterLength=1) for p in ("C4", "F4", "C5", "B4")])
        part.append([first, second])
        score = stream.Score()
        score.insert(0, part)
        folder = Path(tempfile.mkdtemp(prefix="copyist-mxl-key-"))
        score.write("musicxml", fp=str(folder / "change.musicxml"))
        musicxml_in.import_musicxml(folder / "change.musicxml", folder / "change.yaml", title="Key change")
        data = yaml.safe_load((folder / "change.yaml").read_text(encoding="utf-8"))
        self.assertEqual(data["key"], "D")
        song = load_song(folder / "change.yaml")
        self.assertEqual([n.pitch.midi for n in song.melody.recurse().notes if n.isNote],
                         [62, 64, 66, 67, 60, 65, 72, 71])

    def test_missing_file_is_readable(self):
        with self.assertRaises(musicxml_in.MusicxmlImportError) as ctx:
            musicxml_in.song_data_from_musicxml(ROOT / "no-such.musicxml")
        self.assertIn("No file", str(ctx.exception))

    def test_major_general_song_is_finished(self):
        song = load_song(ROOT / "songs" / "major-general.yaml")
        self.assertTrue(is_finished(validate(song)))
        notes = sum(1 for n in song.melody.flatten().notes if n.isNote)
        self.assertGreaterEqual(notes, 100)


if __name__ == "__main__":
    unittest.main()
