"""Transcription lyric fit: a long libretto against fewer heard notes must not abort."""
from __future__ import annotations

import unittest

from copyist import fit as fitting, syllables


class TranscriptionLyricTests(unittest.TestCase):
    def test_drops_spoken_and_trims_to_the_note_budget(self):
        text = """[Verse]
Every day when I go out,
the cottonwoods dance for me.

[Chorus]
The cottonwoods dance for me!

[Verse]
A second verse with many more words here today.

[Spoken Word]
I spend an hour every day watching the dance.

[Chorus]
The cottonwoods dance for me again and again.
"""
        sections = syllables.parse_lyrics(text)
        total = len(syllables.all_syllables(sections))
        self.assertGreater(total, 40)
        kept, notes = fitting.syllables_for_transcription(sections, n_notes=20)
        self.assertLessEqual(len(kept), 20 + int(fitting.SPLIT_LIMIT * 20))
        self.assertTrue(any("spoken" in n.lower() for n in notes))
        self.assertTrue(any("left the rest off" in n for n in notes))
        # Spoken syllables are not in the kept set.
        spoken = next(s for s in sections if s.name == "spoken")
        spoken_bits = {sy.text.lower() for line in spoken.lines for sy in line.syllables}
        kept_bits = {sy.text.lower() for sy in kept}
        self.assertIn("watch", spoken_bits)
        self.assertNotIn("watch", kept_bits)

    def test_short_lyrics_pass_through(self):
        sections = syllables.parse_lyrics("Hope is the thing with feathers\n")
        kept, notes = fitting.syllables_for_transcription(sections, n_notes=20)
        self.assertEqual(len(kept), len(syllables.all_syllables(sections)))
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
