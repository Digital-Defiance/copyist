import importlib.util
import unittest

from copyist import voiceprompt

HAVE_SCIPY = importlib.util.find_spec("scipy") is not None and importlib.util.find_spec("numpy") is not None


class HintTests(unittest.TestCase):
    def test_keeps_lyrics_and_drops_markdown_and_directions(self):
        text = ("# June Snow\n\n**Act One** · Sung by JENNIFER\n\nEvery day when I go out,\n"
                "*(She stops on the footbridge and looks up.)*\n[Chorus]\nThe cottonwoods dance for me!\n")
        hint = voiceprompt.clean_hint(text)
        self.assertIn("Every day when I go out,", hint)
        self.assertIn("The cottonwoods dance for me!", hint)
        for gone in ("#", "*", "(", "footbridge", "[Chorus]", "Chorus"):
            self.assertNotIn(gone, hint)

    def test_nothing_left_means_no_hint(self):
        self.assertIsNone(voiceprompt.clean_hint("[Intro]\n(instrumental)\n"))

    def test_word_text(self):
        self.assertEqual(voiceprompt.word_text(" I’m,"), "I'm")
        self.assertEqual(voiceprompt.word_text("'twas"), "twas")


@unittest.skipUnless(HAVE_SCIPY, "needs numpy and scipy")
class ContourTests(unittest.TestCase):
    def test_octave_slip_is_folded_back(self):
        import numpy as np
        f0 = np.full(60, 440.0)
        f0[20:26] = 880.0          # the tracker jumped an octave
        m = voiceprompt.smooth_contour(f0)
        self.assertTrue(np.allclose(m, 69.0, atol=0.01), m)

    def test_unvoiced_frames_stay_unvoiced(self):
        import numpy as np
        f0 = np.full(40, 440.0)
        f0[10:20] = 0.0
        m = voiceprompt.smooth_contour(f0)
        self.assertTrue(np.isnan(m[10:20]).all())
        self.assertFalse(np.isnan(m[:10]).any())

    def test_split_notes_ignores_vibrato_and_absorbs_blips(self):
        import numpy as np
        vibrato = 0.3 * np.sin(np.arange(60) * 0.8)
        contour = np.concatenate([np.full(30, 60.0), np.full(30, 62.0)]) + vibrato
        contour[44:46] = 65.0      # a two-frame blip inside the second note
        notes = voiceprompt.split_notes(contour, 0, 60)
        self.assertEqual([(s, e, p) for s, e, p in notes], [(0, 30, 60), (30, 60, 62)])


if __name__ == "__main__":
    unittest.main()
