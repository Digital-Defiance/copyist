"""Editing by ear: every change lands where it should, and nothing else in the song file moves."""
from __future__ import annotations

import difflib
import shutil
import tempfile
import unittest
from pathlib import Path

from music21 import harmony, note

from copyist import abcplan, edit, lyrics as lyr, write
from copyist.song import load_song

ROOT = Path(__file__).resolve().parent.parent
PLANS = Path(__file__).resolve().parent / "data" / "plans"
SONGS = sorted((ROOT / "songs").glob("*.yaml")) + [ROOT / "tests" / "data" / "key-change-truth.yaml"]


def sounds(path: Path) -> list[tuple[int, float]]:
    """(MIDI pitch, quarter notes) of every note as Copyist's loader reads the file."""
    song = load_song(path)
    return [(n.pitch.midi, float(n.duration.quarterLength)) for n in song.melody.recurse().notes
            if isinstance(n, note.Note)]


def fits(path: Path) -> list[bool]:
    return [f.fits for f in load_song(path).lyric_fits]


def changed_lines(before: str, after: str) -> list[str]:
    return [l for l in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
            if l[:1] in "+-" and not l.startswith(("+++", "---"))]


class EditCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def copy(self, src: Path) -> Path:
        dest = self.tmp / src.name
        shutil.copyfile(src, dest)
        return dest

    def ids(self, path: Path, kind: str = "note") -> list[str]:
        return [e["id"] for b in edit.view(path)["bars"] for e in b["events"] if e["kind"] == kind]


class ViewTest(EditCase):
    def test_every_song_reads_as_the_loader_does(self):
        for src in SONGS:
            with self.subTest(song=src.name):
                v = edit.view(src)
                notes = [e for b in v["bars"] for e in b["events"] if e["kind"] == "note"]
                self.assertEqual([(e["midi"], e["length"]) for e in notes], sounds(src))
                for e in notes:
                    if not e["held_over"]:
                        self.assertEqual(len(e["words"]), v["verses"])

    def test_chord_tones_match_the_loaders_chords(self):
        for src in SONGS:
            song = load_song(src)
            for cs in song.melody.recurse().getElementsByClass(harmony.ChordSymbol):
                symbol = cs.figure.replace("-", "b")
                with self.subTest(song=src.name, chord=symbol):
                    self.assertEqual({p % 12 for p in edit.chord_tones(symbol)},
                                     {p.pitch.midi % 12 if hasattr(p, "pitch") else p.midi % 12
                                      for p in cs.pitches})

    def test_flat_chords_play(self):
        for symbol, pcs in (("Bb", {10, 2, 5}), ("Abmaj7", {8, 0, 3, 7}), ("Ebm7", {3, 6, 10, 1}),
                            ("Bbm", {10, 1, 5}), ("G/B", {7, 11, 2}), ("Bb/Ab", {10, 2, 5, 8})):
            with self.subTest(symbol=symbol):
                self.assertEqual({p % 12 for p in edit.chord_tones(symbol)}, pcs)
        self.assertEqual(edit.chord_tones("H7"), [])

    def test_words_line_up_with_their_notes(self):
        v = edit.view(ROOT / "songs" / "amazing-grace.yaml")
        first = v["bars"][0]["events"][0]
        self.assertEqual(first["words"][0], "A-")
        self.assertEqual(v["bars"][1]["events"][0]["words"][0], "maz-")
        self.assertEqual(v["bars"][1]["events"][2]["words"][0], "_")

    def test_bars_are_numbered_as_on_the_score(self):
        self.assertEqual([b["number"] for b in edit.view(ROOT / "songs" / "amazing-grace.yaml")["bars"]][:2], [0, 1])
        self.assertEqual(edit.view(ROOT / "songs" / "silent-night.yaml")["bars"][0]["number"], 1)

    def test_tempo(self):
        self.assertEqual(edit.tempo_qpm({"tempo": 80}), 80)
        self.assertEqual(edit.tempo_qpm({"tempo": "3/8=56"}), 56 * 1.5)


class PitchTest(EditCase):
    def test_a_nudge_moves_only_that_note(self):
        for src in SONGS:
            before = sounds(src)
            for i, at in enumerate(self.ids(src)):
                if src.name not in ("key-change-truth.yaml", "amazing-grace.yaml") and i % 7:
                    continue
                with self.subTest(song=src.name, at=at):
                    path = self.copy(src)
                    old = path.read_text(encoding="utf-8")
                    edit.apply(path, "up-half", at)
                    after = sounds(path)
                    self.assertEqual([d for _, d in after], [d for _, d in before])
                    moved = [k for k, (a, b) in enumerate(zip(before, after)) if a != b]
                    self.assertTrue(moved)
                    self.assertTrue(all(after[k][0] == before[k][0] + 1 for k in moved))
                    self.assertEqual(moved, list(range(moved[0], moved[0] + len(moved))))  # one tied run
                    # The ABC rule (accidentals last the bar) reads the edited bars the same way.
                    data = edit.load(path)[1]
                    bars = edit.bars_of(data)
                    carry = [m for row in abcplan._note_midis(bars, data["key"]) for m in row if m is not None]
                    self.assertEqual(carry, [m for m, _ in after])
                    for line in changed_lines(old, path.read_text(encoding="utf-8")):
                        self.assertNotIn("lyrics", line)

    def test_scale_steps_stay_in_the_key(self):
        self.assertEqual(edit.moved(64, "up", "C"), 65)        # E -> F
        self.assertEqual(edit.moved(65, "up", "G"), 66)        # F -> F#: G major has F#
        self.assertEqual(edit.moved(62, "down", "F"), 60)
        self.assertEqual(edit.moved(70, "up", "F"), 72)        # Bb -> C

    def test_a_tied_note_moves_with_its_tie(self):
        path = self.copy(ROOT / "songs" / "amazing-grace.yaml")
        edit.apply(path, "down", "b9.0")                        # the d held over from bar 8
        self.assertIn('"D"c3- | "D7"c2 B', path.read_text(encoding="utf-8"))

    def test_naturals_are_added_where_the_abc_rule_would_misread(self):
        bar = abcplan.Bar(abcplan.tokenize_bar("F G F A")[0], "verse")
        edit.respell_bar(bar, "C", {0: 66})                    # the first F becomes F#
        self.assertEqual(edit.bar_text(bar), "^F G =F A")

    def test_range_edges(self):
        path = self.copy(ROOT / "songs" / "silent-night.yaml")
        with self.assertRaises(edit.EditError):
            for _ in range(40):
                edit.apply(path, "up", "b1.0")


class RhythmTest(EditCase):
    def bar_lengths(self, path: Path) -> list:
        return load_song(path).written_bars()

    def test_longer_and_shorter_keep_bars_and_words(self):
        for src in SONGS:
            lengths, fit = self.bar_lengths(src), fits(src)
            for op in ("longer", "shorter"):
                for at in self.ids(src)[:12]:
                    path = self.copy(src)
                    with self.subTest(song=src.name, op=op, at=at):
                        try:
                            edit.apply(path, op, at)
                        except edit.EditError:
                            continue
                        self.assertEqual(self.bar_lengths(path), lengths)
                        self.assertEqual(fits(path), fit)

    def test_longer_moves_the_next_note(self):
        path = self.copy(ROOT / "songs" / "when-the-saints.yaml")
        edit.apply(path, "longer", "b1.1")
        self.assertIn('"C"z C3/2 E/ F | G4', path.read_text(encoding="utf-8"))
        edit.apply(path, "longer", "b1.2")
        self.assertIn('"C"z C3/2 E F/ | G4', path.read_text(encoding="utf-8"))
        edit.apply(path, "longer", "b1.2")                      # an eighth would leave nothing: a sixteenth
        self.assertIn('"C"z C3/2 E5/4 F/4 | G4', path.read_text(encoding="utf-8"))

    def test_longer_holds_over_the_bar_line(self):
        path = self.copy(ROOT / "songs" / "amazing-grace.yaml")
        edit.apply(path, "longer", "b1.0")
        self.assertIn('D- | "G"D/ G3/2 B/G/', path.read_text(encoding="utf-8"))
        self.assertEqual(fits(path), [True] * 4)

    def test_shorter_at_the_end_leaves_a_rest(self):
        path = self.copy(ROOT / "songs" / "amazing-grace.yaml")
        edit.apply(path, "shorter", "b17.0")
        self.assertIn('"G"G3- | G3/2 z/ |]', path.read_text(encoding="utf-8"))

    def test_shorter_then_longer_is_where_it_started(self):
        src = ROOT / "songs" / "silent-night.yaml"
        path = self.copy(src)
        edit.apply(path, "shorter", "b3.0")
        edit.apply(path, "longer", "b3.0")
        self.assertEqual(path.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))


class SplitJoinTest(EditCase):
    def test_split_holds_the_syllable_over_the_new_note(self):
        src = ROOT / "songs" / "amazing-grace.yaml"
        path = self.copy(src)
        old = path.read_text(encoding="utf-8")
        edit.apply(path, "split", "b2.0")
        new = path.read_text(encoding="utf-8")
        self.assertIn('"G"G G B/G/', new)
        self.assertIn("A-maz-_ ing_ grace", new)
        self.assertIn("\"'Twas grace_ that_ taught", new)             # a quoted verse stays quoted
        self.assertEqual(fits(path), [True] * 4)
        self.assertEqual(len(changed_lines(old, new)), 2 * 5)        # the melody line and four verses

    def test_split_and_join_on_every_song(self):
        for src in SONGS:
            fit = fits(src)
            n = len(sounds(src))
            for at in self.ids(src)[:10]:
                path = self.copy(src)
                with self.subTest(song=src.name, at=at):
                    try:
                        edit.apply(path, "split", at)
                    except edit.EditError:
                        continue
                    self.assertEqual(len(sounds(path)), n + 1)
                    self.assertEqual(fits(path), fit)
                    edit.apply(path, "join", at)                    # the two halves join again
                    self.assertEqual(fits(path), fit)
                    self.assertEqual([m for m, _ in sounds(path)], [m for m, _ in sounds(src)])

    def test_join_keeps_syllables_on_their_notes(self):
        path = self.copy(ROOT / "songs" / "amazing-grace.yaml")
        with self.assertRaisesRegex(edit.EditError, "own syllable"):
            edit.apply(path, "join", "b2.0")
        edit.apply(path, "join", "b2.1")                            # "ing" and its hold
        text = path.read_text(encoding="utf-8")
        self.assertIn('"G"G2 B |', text)
        self.assertIn("A-maz-ing grace", text)
        self.assertEqual(fits(path), [True] * 4)

    def test_dotted_notes_split_into_note_and_dot(self):
        q = edit.split_lengths(abcplan.Fraction(3, 2), abcplan.Fraction(1, 4))
        self.assertEqual(q, (1, abcplan.Fraction(1, 2)))
        self.assertIsNone(edit.split_lengths(abcplan.Fraction(1, 4), abcplan.Fraction(1, 4)))

    def test_lyric_lines_render_back_as_they_read(self):
        for src in SONGS:
            for verse in edit.verses_of(edit.load(src)[1]):
                for line in verse.split("\n"):
                    toks = lyr.tokenize(line)
                    with self.subTest(song=src.name, line=line[:30]):
                        self.assertEqual(lyr.tokenize(edit.render_line(toks)), toks)


class ChordTest(EditCase):
    def test_set_replace_and_remove(self):
        src = ROOT / "songs" / "amazing-grace.yaml"
        path = self.copy(src)
        edit.apply(path, "chord", "b2.1", "Em")
        self.assertIn('"G"G2 "Em"B/G/', path.read_text(encoding="utf-8"))
        edit.apply(path, "chord", "b2.1", "Bm")
        self.assertIn('"G"G2 "Bm"B/G/', path.read_text(encoding="utf-8"))
        edit.apply(path, "chord", "b2.1", "")
        self.assertIn('"G"G2 B/G/', path.read_text(encoding="utf-8"))
        with self.assertRaises(edit.EditError):
            edit.apply(path, "chord", "b2.1", "Q7")

    def test_chord_roots_are_spelled_from_the_key(self):
        for key, semitones, root in (("C", 10, "Bb"), ("Am", 7, "E"), ("F#m", 3, "A"), ("Bb", 9, "G"),
                                     ("Eb", 11, "D"), ("D", 11, "C#"), ("G#", 11, "G")):
            with self.subTest(key=key, semitones=semitones):
                self.assertEqual(edit.degree_root(key, semitones), root)

    def test_options_put_the_fitting_chord_first(self):
        options = edit.chord_options(ROOT / "songs" / "amazing-grace.yaml", "b2.0")
        self.assertEqual(options[0]["symbol"], "G")              # G B G | B A, until the C chord
        self.assertEqual(options[0]["fit"], 0.83)
        self.assertTrue(any(o["now"] for o in options))
        minor = edit.best_chords(edit.events_of([abcplan.Bar(abcplan.tokenize_bar("A c e c")[0], "")],
                                                abcplan.Fraction(1, 4), "Am"), edit.Event("b1.0", 0, 0, "note", 0, 1),
                                 "Am")
        self.assertEqual(minor[0]["symbol"], "Am")


class FileTest(EditCase):
    def test_only_the_changed_bar_is_written(self):
        src = ROOT / "songs" / "silent-night.yaml"
        path = self.copy(src)
        edit.apply(path, "up", "b3.0")
        diff = changed_lines(src.read_text(encoding="utf-8"), path.read_text(encoding="utf-8"))
        self.assertEqual(len(diff), 2)
        self.assertIn('"G7"e2 d B3', diff[1])

    def test_a_written_song_can_be_edited(self):
        cand = write.song_from_plan((PLANS / "alto-waltz.abc").read_text(encoding="utf-8"),
                                    (PLANS / "alto-waltz.txt").read_text(encoding="utf-8"),
                                    "Carry Me Home", "alto", "waltz", {"planner": "yue-plan", "seed": 1})
        path = self.tmp / "carry-me-home.yaml"
        path.write_text(write.song_yaml(cand.data), encoding="utf-8")
        fit = fits(path)
        ids = self.ids(path)
        for op in ("up", "split", "longer", "chord"):
            edit.apply(path, op, ids[3], "C" if op == "chord" else None)
        self.assertEqual(fits(path), fit)

    def test_an_edit_that_would_break_the_song_changes_nothing(self):
        src = ROOT / "songs" / "amazing-grace.yaml"
        path = self.copy(src)
        with self.assertRaises(edit.EditError):
            edit.apply(path, "join", "b2.0")
        self.assertEqual(path.read_text(encoding="utf-8"), src.read_text(encoding="utf-8"))

    def test_a_song_that_already_doesnt_fit_can_still_be_edited(self):
        path = self.copy(ROOT / "songs" / "amazing-grace.yaml")
        text = path.read_text(encoding="utf-8").replace("I see.", "I see a-gain.")
        path.write_text(text, encoding="utf-8")
        edit.apply(path, "up", "b3.0")

    def test_undo_and_redo(self):
        src = ROOT / "songs" / "when-the-saints.yaml"
        path = self.copy(src)
        hist = self.tmp / "edits"
        original = path.read_text(encoding="utf-8")
        edit.apply(path, "up", "b2.0", history=hist)
        once = path.read_text(encoding="utf-8")
        edit.apply(path, "split", "b2.0", history=hist)
        twice = path.read_text(encoding="utf-8")
        self.assertTrue(edit.view(path, hist)["can_undo"])
        edit.step_back(path, hist)
        self.assertEqual(path.read_text(encoding="utf-8"), once)
        edit.step_back(path, hist)
        self.assertEqual(path.read_text(encoding="utf-8"), original)
        with self.assertRaises(edit.EditError):
            edit.step_back(path, hist)
        edit.step_back(path, hist, redo=True)
        self.assertEqual(path.read_text(encoding="utf-8"), once)
        edit.step_back(path, hist, redo=True)
        self.assertEqual(path.read_text(encoding="utf-8"), twice)
        edit.step_back(path, hist)
        edit.apply(path, "down", "b4.0", history=hist)          # a new edit drops what could be redone
        self.assertFalse(edit.view(path, hist)["can_redo"])
        self.assertEqual(len(list((hist / "versions").iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
