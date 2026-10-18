"""Melody writing (docs/melody-writing.md): syllables, reading planner scores, fitting lyrics, song files."""
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from music21 import pitch

from copyist import abcplan, fit, lyrics, syllables, write, yue
from copyist.song import SongError, load_song
from helpers import song_from

PLANS = Path(__file__).resolve().parent / "data" / "plans"

# word, how it's printed under the notes, stress weight of each syllable
SYLLABLE_TABLE = [
    ("feathers", "fea-thers", [2, 0]),
    ("perches", "per-ches", [2, 0]),
    ("sweetest", "sweet-est", [2, 0]),
    ("extremity", "ex-tre-mi-ty", [0, 2, 0, 0]),
    ("alleluia", "al-le-lu-ia", [1, 0, 2, 0]),
    ("hallelujah", "hal-le-lu-jah", [1, 0, 2, 0]),
    ("being", "be-ing", [2, 0]),
    ("fire", "fire", [1.5]),
    ("hour", "hour", [1.5]),
    ("every", "ev-ery", [2, 0]),
    ("heaven", "hea-ven", [2, 0]),
    ("quiet", "qui-et", [2, 0]),
    ("believed", "be-lieved", [0, 2]),
    ("table", "ta-ble", [2, 0]),
    ("little", "lit-tle", [2, 0]),
    ("children", "chil-dren", [2, 0]),
    ("darkness", "dark-ness", [2, 0]),
    ("lightning", "light-ning", [2, 0]),
    ("window", "win-dow", [2, 0]),
    ("open", "o-pen", [2, 0]),
    ("lion", "li-on", [2, 0]),
    ("morning", "morn-ing", [2, 0]),
    ("running", "run-ning", [2, 0]),
    ("singing", "sing-ing", [2, 0]),
    ("without", "with-out", [0, 2]),
    ("evening", "eve-ning", [2, 0]),
    ("remember", "re-mem-ber", [0, 2, 0]),
    ("tomorrow", "to-mor-row", [0, 2, 1]),
    ("beautiful", "beau-ti-ful", [2, 0, 0]),
    ("mountain", "moun-tain", [2, 0]),
    ("amazing", "a-maz-ing", [0, 2, 0]),
    ("across", "a-cross", [0, 2]),
    ("dangers", "dan-gers", [2, 0]),
    ("angel", "an-gel", [2, 0]),
    ("kitchen", "kitch-en", [2, 0]),
    ("flower", "flow-er", [2, 0]),
    ("sister", "sis-ter", [2, 0]),
    ("secret", "se-cret", [2, 0]),
    ("hope", "hope", [1.5]),
    ("the", "the", [0.3]),
]


def plan_text(name: str) -> str:
    return (PLANS / f"{name}.abc").read_text(encoding="utf-8")


def plan_lyrics(name: str) -> str:
    return (PLANS / f"{name}.txt").read_text(encoding="utf-8")


def load_data(data: dict):
    path = Path(tempfile.mkdtemp(prefix="copyist-write-")) / "song.yaml"
    path.write_text(write.song_yaml(data), encoding="utf-8")
    return load_song(path)


SMALL = """X:1
M:4/4
L:1/32
Q:1/4=96
K:C
% verse
V: Vocal
"C"c8c8c8c8|"G"d16z16|"C"e8e8e8e8|"G"c16z16|
"""


def small_fit(lyrics: str):
    plan = abcplan.parse(SMALL)
    bars = abcplan.trim(plan)
    sylls = syllables.all_syllables(syllables.parse_lyrics(lyrics))
    return fit.fit(bars, plan.unit, plan.meter, sylls), sylls, bars, plan


class SyllableTests(unittest.TestCase):
    def test_table(self):
        for word, printed, stresses in SYLLABLE_TABLE:
            with self.subTest(word=word):
                got = syllables.syllabify_word(word)
                self.assertEqual("-".join(s for s, _ in got), printed)
                self.assertEqual([w for _, w in got], stresses)

    def test_punctuation_stays_on_the_last_syllable(self):
        self.assertEqual(syllables.syllabify_word("feathers,"), [("fea", 2.0), ("thers,", 0.0)])
        self.assertEqual(syllables.syllabify_word("Hope"), [("Hope", 1.5)])

    def test_unknown_word_counts_vowel_groups_and_stresses_the_first(self):
        got = syllables.syllabify_word("blorpentine")
        self.assertGreater(len(got), 1)
        self.assertEqual(got[0][1], 2.0)

    def test_lyrics_sections_and_lines(self):
        sections = syllables.parse_lyrics(plan_lyrics("alto-waltz"))
        self.assertEqual([s.name for s in sections], ["verse", "chorus"])
        self.assertEqual([len(line.syllables) for s in sections for line in s.lines], [7, 8, 8, 9])
        first = sections[0].lines[0].syllables
        self.assertTrue(first[0].line_start)
        self.assertTrue(first[-1].line_end)

    def test_untagged_lyrics_are_a_verse(self):
        sections = syllables.parse_lyrics("Climbing up the stairs\n\nand down again")
        self.assertEqual([s.name for s in sections], ["verse"])
        self.assertEqual(len(sections[0].lines), 2)


class PlanReadingTests(unittest.TestCase):
    def test_sections_whole_bar_rests_ties_and_chords(self):
        plan = abcplan.parse(plan_text("alto-waltz"))
        self.assertEqual((plan.meter, plan.unit, plan.tempo, plan.key), ("3/4", Fraction(1, 32), "1/4=86", "D"))
        bars = abcplan.trim(plan)
        self.assertEqual(len(bars), 18)                      # intro and outro dropped; Z2 kept as two bars
        self.assertFalse(bars[8].sung or bars[9].sung)
        self.assertEqual(abcplan.sections_of(bars), [{"name": "verse", "bar": 1}, {"name": "chorus", "bar": 11}])
        self.assertEqual(bars[0].toks[0].kind, "chord")      # a chord on a rest is kept
        self.assertTrue(any(t.tie for t in bars[13].toks))

    def test_tuplets_are_refused(self):
        with self.assertRaises(abcplan.PlanError) as e:
            abcplan.parse(plan_text("tuplet"))
        self.assertIn("(", str(e.exception))

    def test_bar_length_is_checked(self):
        with self.assertRaises(abcplan.PlanError):
            abcplan.parse(SMALL.replace("d16z16", "d16z8"))

    def test_accidentals_carry_through_the_bar_by_letter(self):
        plan = abcplan.parse(SMALL.replace('"C"c8c8c8c8', '"C"^c8C8c8=c8'))
        self.assertEqual(abcplan.pitches(abcplan.trim(plan), "C")[:4], [73, 61, 73, 72])

    def test_key_signatures(self):
        self.assertEqual(abcplan.key_accidentals("Bm"), {"F": 1, "C": 1})
        self.assertEqual(abcplan.key_accidentals("Bb"), {"B": -1, "E": -1})
        self.assertEqual(abcplan.key_accidentals("D dorian"), {})
        self.assertEqual(abcplan.transpose_key("D", 1), "Eb")
        self.assertEqual(abcplan.transpose_key("C", 5), "F")
        self.assertEqual(abcplan.transpose_key("Am", 2), "Bm")
        self.assertEqual(abcplan.transpose_chord("G/D", 5, "C"), "C/G")
        self.assertEqual(abcplan.transpose_chord("E7", 1, "F"), "F7")

    def test_units(self):
        plan = abcplan.parse(plan_text("alto-waltz"))
        self.assertEqual(abcplan.best_unit(abcplan.trim(plan), plan.unit), Fraction(1, 4))
        plan = abcplan.parse(plan_text("tenor-march"))
        self.assertEqual(abcplan.best_unit(abcplan.trim(plan), plan.unit), Fraction(1, 8))
        plan = abcplan.parse(plan_text("wide-range"))
        self.assertEqual(abcplan.best_unit(abcplan.trim(plan), plan.unit), Fraction(1, 16))

    def test_two_four_is_written_in_four_four(self):
        text = SMALL.replace("M:4/4", "M:2/4").replace(
            '"C"c8c8c8c8|"G"d16z16|"C"e8e8e8e8|"G"c16z16|', '"C"c8c8|e8e8|"G"d16|z16|"C"e8e8|g8g8|"G"c16|z16|')
        plan = abcplan.parse(text)
        bars, meter = abcplan.pair_bars(abcplan.trim(plan), plan.meter)
        self.assertEqual((meter, len(bars)), ("4/4", 4))
        self.assertTrue(all(b.length == 32 for b in bars))
        self.assertTrue(all(b.toks[0].kind == "chord" for b in bars))      # chords on the new downbeats
        # A plan whose chords change on its even bars gets a bar of rest in front, so they still land on beat 1.
        shifted = text.replace('"C"c8c8|', 'c8c8|"C"c8c8|', 1).replace('"C"c8c8|e8e8|', '"C"c8c8|e8e8|', 1)
        plan = abcplan.parse(shifted)
        bars, meter = abcplan.pair_bars(abcplan.trim(plan), plan.meter)
        self.assertEqual(len(bars), 5)
        self.assertTrue(all(any(t.kind == "chord" for t in b.toks[:1]) for b in bars[1:]))
        cand = write.song_from_plan(text, "Sing it to me now\nsing it to me", "Two", "alto")
        self.assertEqual(cand.data["meter"], "4/4")
        self.assertTrue(load_data(cand.data).lyric_fits[0].fits)

    def test_a_chord_isnt_repeated_while_it_lasts(self):
        plan = abcplan.parse(SMALL.replace('"C"e8e8e8e8', '"G"e8e8e8e8'))
        bars = abcplan.trim(plan)
        text = abcplan.write(bars, plan.unit, abcplan.best_unit(bars, plan.unit))
        self.assertEqual(text.count('"G"'), 1)

    def test_tempo(self):
        self.assertEqual(abcplan.tempo_field("1/4=86"), 86)
        self.assertEqual(abcplan.tempo_field("3/8=60"), "3/8=60")


class FitTests(unittest.TestCase):
    def test_exact_count(self):
        f, sylls, _, _ = small_fit("Hold me close to night\nLight the can dle now")
        self.assertEqual(f.splits, 0)
        self.assertTrue(all(a == b for a, b in f.spans))

    def test_one_extra_note_is_held_at_the_end_of_a_line(self):
        f, sylls, _, _ = small_fit("Hold me close tonight\nLight the candle")
        held = [s for s, (a, b) in zip(sylls, f.spans) if b > a]
        self.assertEqual(len(held), 1)
        self.assertTrue(held[0].line_end)
        self.assertTrue(f.lyrics.endswith("can-dle_"))

    def test_a_line_ends_on_the_rest(self):
        f, sylls, bars, plan = small_fit("Light the candle\nHold me close tonight")
        notes = fit.slots(bars, plan.unit, plan.meter)
        end_of_line_one = f.spans[3][1]                   # "dle"
        self.assertTrue(notes[end_of_line_one].rest_after)

    def test_one_missing_note_is_made_by_a_split(self):
        f, sylls, bars, plan = small_fit("Hold me close tonight, my love\nLight the candle")
        self.assertEqual(f.splits, 1)
        self.assertEqual(len(fit.slots(bars, plan.unit, plan.meter)), len(sylls))

    def test_too_many_syllables_reject_the_melody(self):
        with self.assertRaises(ValueError):
            small_fit("Hold me close tonight, my love, my dear\nLight the candle")

    def test_stress_inside_a_word(self):
        # "a-bash" must not put "a" on the downbeat and "bash" off it.
        plan = abcplan.parse(SMALL)
        bars = abcplan.trim(plan)
        sylls = syllables.all_syllables(syllables.parse_lyrics("Don't abash me\nnow or then my dear"))
        f = fit.fit(bars, plan.unit, plan.meter, sylls)
        notes = fit.slots(bars, plan.unit, plan.meter)
        a, bash = (k for k, s in enumerate(sylls) if s.text in ("a", "bash"))
        self.assertGreaterEqual(notes[f.spans[bash][0]].strength, notes[f.spans[a][0]].strength)

    def test_lyric_syntax_round_trips(self):
        sylls = syllables.all_syllables(syllables.parse_lyrics("already soul"))
        text = fit.lyric_text(sylls, [(0, 1), (2, 2), (3, 3), (4, 6)])
        self.assertEqual(text, "al-_ rea-dy soul__")
        tokens = lyrics.tokenize(text)
        self.assertEqual([t.kind for t in tokens], ["syl", "hold", "syl", "syl", "syl", "hold", "hold"])
        self.assertEqual([t.word for t in tokens if t.kind == "syl"], [0, 0, 0, 1])


class SongFromPlanTests(unittest.TestCase):
    def check(self, name: str, voice: str):
        cand = write.song_from_plan(plan_text(name), plan_lyrics(name), "Test", voice, style="waltz",
                                    written_with={"planner": "yue-plan", "seed": 3})
        song = load_data(cand.data)
        self.assertTrue(song.lyric_fits[0].fits)
        low, high = (pitch.Pitch(p).midi for p in write.VOICES[voice][:2])
        midis = [n.pitch.midi for n in song.melody.recurse().notes if hasattr(n, "pitch")]
        self.assertTrue(all(low <= m <= high for m in midis), (name, min(midis), max(midis)))
        return cand, song

    def test_alto_waltz(self):
        cand, song = self.check("alto-waltz", "alto")
        self.assertEqual((song.key, song.meter, song.unit, song.tempo), ("D", "3/4", "1/4", "86"))
        self.assertEqual(song.sections, [{"name": "verse", "bar": 1}, {"name": "chorus", "bar": 11}])
        self.assertEqual(song.written_with, {"planner": "yue-plan", "seed": 3})
        self.assertEqual(len(song.written_bars()), 18)
        # The plan's G# carries through its bar (to the low G); the song file writes both.
        self.assertIn('"E7"^G B ^G,', cand.data["melody"])
        names = [n.pitch.nameWithOctave for n in song.melody.recurse().notes if hasattr(n, "pitch")]
        self.assertEqual(names[-4:-1], ["G#4", "B4", "G#3"])

    def test_tenor(self):
        cand, song = self.check("tenor-march", "tenor")
        self.assertEqual((song.key, song.unit), ("G", "1/8"))
        self.assertEqual(cand.data["voice"]["clef"], "treble-8vb")

    def test_transposed_when_no_octave_fits(self):
        cand, song = self.check("wide-range", "alto")
        self.assertEqual((cand.placement.transposed, song.key, song.unit), (5, "F", "1/16"))
        self.assertTrue(any("Transposed +5" in n for n in cand.notes))
        self.assertNotIn("^", cand.data["melody"])
        self.assertNotIn("_", cand.data["melody"])

    def test_a_bad_plan_is_a_write_error(self):
        with self.assertRaises(write.WriteError):
            write.song_from_plan(plan_text("tuplet"), "la la la", "Test")
        with self.assertRaises(write.WriteError):
            write.song_from_plan(plan_text("alto-waltz"), "la", "Test", voice="mezzo")


class SectionTests(unittest.TestCase):
    MELODY = '"C"C D E F | G4 | "F"A G F E | "C"C4 |'

    def test_sections_load_and_label_yue2_requests(self):
        song = song_from(melody=self.MELODY, lyrics=["one two three four five six sev-en eight nine"],
                         sections=[{"name": "verse", "bar": 1}, {"name": "chorus", "bar": 3}])
        self.assertEqual(song.section_at(1), "verse")
        self.assertEqual(song.section_at(4), "chorus")
        abc, labels = yue.score_abc(song, 1, intro_bars=0)
        self.assertIn("% chorus", abc)
        text = yue.lyrics_text(song, 1, intro=False)
        self.assertIn("[Verse]", text)
        self.assertIn("[Chorus]", text)
        self.assertLess(text.index("[Verse]"), text.index("[Chorus]"))

    def test_songs_without_sections_are_unchanged(self):
        song = song_from(melody=self.MELODY, lyrics=["one two three four five six sev-en eight nine"])
        self.assertEqual(song.sections, [])
        self.assertNotIn("[Chorus]", yue.lyrics_text(song, 1))

    def test_hook_counts_the_chorus_opening_coming_back(self):
        melody = '"C"C D E F | G4 | "F"A G F E | "C"C4 | "C"C D E F | G4 | "G"B A G F | "C"C4 |'
        song = song_from(melody=melody, sections=[{"name": "verse", "bar": 1}, {"name": "chorus", "bar": 5}])
        self.assertEqual(write.hook_count(song), 1)            # bars 1-2 have bars 5-6's rhythm and contour
        self.assertIsNone(write.hook_count(song_from(melody=melody)))

    def test_bad_sections_are_refused(self):
        for bad in ([{"name": "verse"}], [{"name": "verse", "bar": 3}, {"name": "chorus", "bar": 2}], "verse"):
            with self.subTest(bad=bad), self.assertRaises(SongError):
                song_from(melody=self.MELODY, sections=bad)


if __name__ == "__main__":
    unittest.main()


FAKE_PLANNER = """#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
seed = int(args[args.index('--lm-seed') + 1])
plans = Path(os.environ['FAKE_PLANS'])
name = {2: 'tuplet'}.get(seed, 'alto-waltz')
Path(args[args.index('--out') + 1]).write_text((plans / (name + '.abc')).read_text())
with open(os.environ['FAKE_LOG'], 'a') as log:
    log.write(str(seed) + '\\n')
"""


class StyleLineTests(unittest.TestCase):
    def test_waltz_keeps_meter_and_tempo_as_their_own_tags(self):
        # Production already says "gentle 3/4 waltz"; the planner still needs a
        # trailing "3/4" and "N BPM" or it wanders into 4/4 and 6/8 (Mac trial).
        line = write.style_line("waltz", None, "alto")
        parts = [p.strip() for p in line.split(",")]
        self.assertIn("3/4", parts)
        self.assertTrue(any(p.endswith("BPM") for p in parts), line)

    def test_rank_prefers_the_style_meter(self):
        a = {"fails": 0, "meter_miss": 1, "fit_cost": 0.4, "prosody": 0, "range": 0, "leap": 5,
             "chord_tones": 0, "hook": 0}
        b = {"fails": 0, "meter_miss": 0, "fit_cost": 0.5, "prosody": 0, "range": 0, "leap": 5,
             "chord_tones": 0, "hook": 0}
        self.assertLess(write.rank_key(b), write.rank_key(a))


class WriteCommandTests(unittest.TestCase):
    def setUp(self):
        import os
        import stat
        from unittest import mock
        from copyist import render
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-write-cmd-"))
        planner = self.tmp / "yue-plan"
        planner.write_text(FAKE_PLANNER)
        planner.chmod(planner.stat().st_mode | stat.S_IEXEC)
        (self.tmp / "m.gguf").write_bytes(b"m")
        self.log = self.tmp / "planner-calls.txt"
        env = {"COPYIST_YUE_PLAN": str(planner), "COPYIST_YUE_MODEL": str(self.tmp / "m.gguf"),
               "FAKE_PLANS": str(PLANS), "FAKE_LOG": str(self.log)}
        self.patches = [mock.patch.dict(os.environ, env)]

        def fake_band(midi, wav, style=None, cache=None, stems_dir=None):
            wav.write_bytes(b"RIFF")
            return render.BandAudio(wav, "sampled")
        self.patches.append(mock.patch.object(render, "render_band", fake_band))
        for p in self.patches:
            p.start()
        self.lyrics = self.tmp / "carry-me-home.txt"
        self.lyrics.write_text(plan_lyrics("alto-waltz"), encoding="utf-8")
        self.out, self.songs = self.tmp / "out", self.tmp / "songs"

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def run_write(self, *extra):
        from copyist.cli import main
        return main(["write", str(self.lyrics), "--style", "waltz", "--candidates", "3", "--out", str(self.out),
                     "--songs", str(self.songs), *extra])

    def test_candidates_are_written_checked_previewed_and_ranked(self):
        self.assertEqual(self.run_write(), 0)
        folder = self.out / "carry-me-home" / "write"
        index = json.loads((folder / write.INDEX).read_text())
        self.assertEqual(index["title"], "Carry Me Home")
        self.assertIn("waltz", index["style_line"])
        entries = index["candidates"]
        self.assertEqual([e["seed"] for e in entries], [1, 3, 2])         # usable ones ranked first
        self.assertEqual([e.get("rank") for e in entries], [1, 2, None])
        self.assertIn("(", entries[2]["reason"])
        for e in entries[:2]:
            song = load_song(folder / e["song"])
            self.assertTrue(song.lyric_fits[0].fits)
            self.assertEqual(song.style, "waltz")
            self.assertEqual(song.written_with["seed"], e["seed"])
            self.assertTrue((folder / e["preview"]).is_file())
            self.assertTrue((folder / e["folder"] / write.REPORT_FILE).is_file())
            self.assertEqual(e["scores"]["fails"], 0)
            self.assertEqual(e["scores"]["hook"], 0)                      # the chorus's opening doesn't come back
        request = json.loads((folder / "candidate-1" / write.REQUEST_FILE).read_text())
        self.assertEqual((request["cot"], request["abc"], request["lm_seed"]), ("full", "", 1))
        self.assertIn("[chorus]", request["lyrics"])

    def test_plans_are_reused_and_more_candidates_follow_on(self):
        self.run_write()
        self.run_write("--seed", "3", "--no-preview")                      # seeds 3, 4, 5: 3 is already planned
        calls = self.log.read_text().split()
        self.assertEqual(sorted(calls), ["1", "2", "3", "4", "5"])
        index = json.loads((self.out / "carry-me-home" / "write" / write.INDEX).read_text())
        self.assertEqual(sorted(e["seed"] for e in index["candidates"]), [1, 2, 3, 4, 5])

    def test_new_words_start_a_fresh_list(self):
        self.run_write()
        self.lyrics.write_text(plan_lyrics("alto-waltz").replace("Morning comes", "Evening falls"), encoding="utf-8")
        self.run_write("--candidates", "1", "--seed", "1")
        index = json.loads((self.out / "carry-me-home" / "write" / write.INDEX).read_text())
        self.assertEqual([e["seed"] for e in index["candidates"]], [1])
        self.assertEqual(self.log.read_text().split(), ["1", "2", "3", "1"])         # planned again for the new words

    def test_keep_copies_one_song_and_nothing_else(self):
        self.run_write()
        self.songs.mkdir()
        (self.songs / "other.yaml").write_text("untouched\n")
        from copyist.cli import main
        self.assertEqual(main(["write", "--title", "Carry Me Home", "--keep", "1", "--out", str(self.out),
                               "--songs", str(self.songs)]), 0)
        self.assertEqual(sorted(p.name for p in self.songs.iterdir()), ["carry-me-home.yaml", "other.yaml"])
        self.assertEqual((self.songs / "other.yaml").read_text(), "untouched\n")
        self.assertTrue(load_song(self.songs / "carry-me-home.yaml").lyric_fits[0].fits)
        # Keeping a different candidate under the same name needs --replace.
        self.assertEqual(main(["write", "--title", "Carry Me Home", "--keep", "3", "--out", str(self.out),
                               "--songs", str(self.songs)]), 2)
        self.assertEqual(main(["write", "--title", "Carry Me Home", "--keep", "3", "--replace",
                               "--out", str(self.out), "--songs", str(self.songs)]), 0)
        self.assertIn("seed: 3", (self.songs / "carry-me-home.yaml").read_text())
        self.assertEqual(main(["write", "--title", "Carry Me Home", "--keep", "2", "--out", str(self.out),
                               "--songs", str(self.songs)]), 2)          # the unusable one can't be kept
