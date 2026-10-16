import unittest

from copyist.lyrics import EXTEND_MARK, HOLD, SKIP, SYL, tokenize
from helpers import song_from


class TokenizeTests(unittest.TestCase):
    def test_hyphenated_word_and_melisma(self):
        toks = tokenize("A-maz-ing_ grace")
        self.assertEqual([t.kind for t in toks], [SYL, SYL, SYL, HOLD, SYL])
        self.assertEqual([t.syllabic for t in toks if t.kind == SYL], ["begin", "middle", "end", "single"])
        self.assertEqual([t.word for t in toks if t.kind == SYL], [0, 0, 0, 1])

    def test_word_continues_across_hyphen_at_chunk_end(self):
        toks = [t for t in tokenize("al-_ read-y come") if t.kind == SYL]
        self.assertEqual([(t.text, t.syllabic, t.word) for t in toks],
                         [("al", "begin", 0), ("read", "middle", 0), ("y", "end", 0), ("come", "single", 1)])

    def test_skip(self):
        self.assertEqual([t.kind for t in tokenize("la * la")], [SYL, SKIP, SYL])


class AlignTests(unittest.TestCase):
    def test_ties_and_rests_take_no_syllable(self):
        song = song_from(melody='C2 D2- | D2 z E2 |', lyrics=["one two three"])
        fit = song.lyric_fits[0]
        self.assertTrue(fit.fits)
        self.assertEqual([p.note.nameWithOctave for p in fit.placed], ["C4", "D4", "E4"])

    def test_verses_get_their_own_lyric_numbers(self):
        song = song_from(melody="C D E F |", lyrics=["a b c d", "e f g h"])
        first = song.lyric_fits[0].placed[0].note
        self.assertEqual([(l.number, l.text) for l in first.lyrics], [(1, "a"), (2, "e")])


class HeldSyllableTests(unittest.TestCase):
    def test_word_final_hold_gets_an_extender_mid_word_hold_does_not(self):
        song = song_from(melody='"C"C D E F | G4 |', lyrics=["grace_ al-_ read-y"])
        placed = {p.text: p for p in song.lyric_fits[0].placed}
        self.assertEqual(len(placed["grace"].held), 1)
        self.assertEqual(placed["grace"].note.lyrics[0].identifier, EXTEND_MARK)
        self.assertEqual(len(placed["al"].held), 1)
        self.assertNotEqual(placed["al"].note.lyrics[0].identifier, EXTEND_MARK)

    def test_slur_only_where_every_verse_holds(self):
        both = song_from(melody='"C"C D E F |', lyrics=["one_ two three", "four_ five six"])
        self.assertEqual(len(both.melody.getElementsByClass("Slur")), 1)
        one = song_from(melody='"C"C D E F |', lyrics=["one_ two three", "four five six sev"])
        self.assertEqual(len(one.melody.getElementsByClass("Slur")), 0)


if __name__ == "__main__":
    unittest.main()
