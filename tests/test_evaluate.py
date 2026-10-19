"""The transcription scorer (scripts/transcribe/evaluate.py, docs/transcribing.md): what it reads, and how
it lines a draft up with the true score."""
import contextlib
import importlib.util
import io
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


def _search_as_before(truth_notes, notes, spq, octave_free, search=14.0):
    """best_alignment as it was on 2026-10-19, before the identity rule and the search past ±14 s,
    kept to show that inside the window nothing changed."""
    best = (-1, 0, 1.0)
    for ratio in [x / 1000 for x in range(900, 1101, 5)] + [0.5, 2.0, 2 / 3, 1.5]:
        for step in range(int(-search * 20), int(search * 20) + 1):
            shift = step / 20
            f = ev.match(truth_notes, notes, spq, octave_free, shift, ratio)[0]
            if f > best[0]:
                best = (f, shift, ratio)
    # refine
    f0, s0, r0 = best
    for dr in [x / 2000 for x in range(-10, 11)]:
        for ds in [x / 100 for x in range(-10, 11)]:
            f = ev.match(truth_notes, notes, spq, octave_free, s0 + ds, r0 + dr)[0]
            if f > best[0]:
                best = (f, s0 + ds, r0 + dr)
    return best


class AlignmentTests(unittest.TestCase):
    def test_identical_key_changing_truth_and_draft_score_one(self):
        tn, tc, spq = ev.truth(TRUTH)
        notes, chords, _ = ev.transcribed(DRAFT)
        self.assertEqual(ev.best_alignment(tn, notes, spq, False), (1.0, 0.0, 1.0))
        self.assertEqual(ev.chord_accuracy(tc, chords, 0.0, 1.0, tn[-1][0] + tn[-1][1]), 1.0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ev.main([str(TRUTH), str(DRAFT_PATH)]), 0)
        self.assertIn("notes F1 1.00", out.getvalue())
        self.assertIn("chords (root and maj/min, by time): 1.00", out.getvalue())

    def test_a_draft_more_than_20_s_late_still_scores_one(self):
        intro = '% intro\nV: Vocal\n' + '"C"z16|' * 9 + '\nV: Ins\nZ9|\n'        # 21.6 s at 100 bpm
        late = DRAFT.replace("% verse\n", intro + "% verse\n")
        tn, _, spq = ev.truth(TRUTH)
        notes, _, _ = ev.transcribed(late)
        self.assertAlmostEqual(notes[0][0], 21.6)
        f, shift, ratio = ev.best_alignment(tn, notes, spq, False)
        self.assertEqual(f, 1.0)
        self.assertLessEqual(abs(notes[0][0] * ratio + shift - tn[0][0]), 0.25 * spq)

    def test_long_offsets_align_both_ways(self):
        tn, _, spq = ev.truth(TRUTH)
        later = [[s + 23.0, d, m] for s, d, m in tn]
        self.assertEqual(ev.best_alignment(tn, later, spq, False)[0], 1.0)      # a draft with a long intro
        self.assertEqual(ev.best_alignment(later, tn, spq, False)[0], 1.0)      # a recording's intro (--sung)

    def test_inside_the_window_the_search_is_unchanged(self):
        tn, _, spq = ev.truth(TRUTH)
        notes, _, _ = ev.transcribed(DRAFT)
        late = [[s + 3.0, d, m] for s, d, m in notes[:-1]]
        wrong = [list(n) for n in late]
        wrong[5][2] += 2
        for draft in (late, wrong):
            with self.subTest(wrong_pitch=draft is wrong):
                self.assertEqual(ev.best_alignment(tn, draft, spq, True), _search_as_before(tn, draft, spq, True))


if __name__ == "__main__":
    unittest.main()
