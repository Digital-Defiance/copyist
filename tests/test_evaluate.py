"""The transcription scorer (scripts/transcribe/evaluate.py, docs/transcribing.md): what it reads, and how
it lines a draft up with the true score."""
import importlib.util
import unittest
from pathlib import Path

from helpers import KEY_CHANGE_VOCAL

ROOT = Path(__file__).resolve().parents[1]
TRUTH = ROOT / "tests" / "data" / "key-change-truth.yaml"      # the same music in one key, at the draft's pitch
DRAFT_PATH = ROOT / "tests" / "data" / "plans" / "key-change.abc"
DRAFT = DRAFT_PATH.read_text(encoding="utf-8")


def load_evaluate():
    """evaluate.py as roundtrip.py loads it (it's a script, not part of the package)."""
    spec = importlib.util.spec_from_file_location("tr_eval", ROOT / "scripts/transcribe/evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = load_evaluate()


class ReadingTests(unittest.TestCase):
    def test_chords_and_notes_keep_every_bar_across_key_changes(self):
        tn, tc, spq = ev.truth(TRUTH)
        self.assertEqual([m for _, _, m in tn], KEY_CHANGE_VOCAL)          # the two data files agree
        notes, chords, _ = ev.transcribed(DRAFT)
        self.assertEqual([m for _, _, m in notes], KEY_CHANGE_VOCAL)
        self.assertEqual(len(ev.parse_any(DRAFT).vocal), 6)
        self.assertEqual(chords, tc)
        self.assertEqual([round(t, 6) for t, _, _ in chords], [0, 2.4, 4.8, 7.2, 9.0, 9.6, 10.8, 12.0, 13.2])
        end = tn[-1][0] + tn[-1][1]
        self.assertEqual(ev.chord_accuracy(tc, chords, 0.0, 1.0, end), 1.0)


if __name__ == "__main__":
    unittest.main()
