"""YuE2 score export: the header, durations, bars, the pickup and the intro."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import yue
from copyist.cli import main
from copyist.song import SongError, load_song
from helpers import song_from

ROOT = Path(__file__).resolve().parents[1]

NOTE = __import__("re").compile(r'"[^"]*"')
DUR = __import__("re").compile(r"[A-Ga-gz][,']*(\d*)")


def vocal_lines(abc: str) -> list[str]:
    lines = abc.splitlines()
    return [lines[i + 1] for i, line in enumerate(lines) if line == "V: Vocal"]


def durations(music: str) -> list[int]:
    return [int(m.group(1) or "1") for m in DUR.finditer(NOTE.sub("", music))]


class AmazingGraceExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        cls.abc, cls.labels = yue.score_abc(cls.song, 1, 4)

    def test_header(self):
        self.assertEqual(self.abc.splitlines()[:8], [
            "X:1",
            "T:",
            "M:3/4",
            "L:1/16",
            "Q:1/4=80",
            'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
            'V: Ins clef=treble name="Ins Melody" snm="Inst."',
            "K:G",
        ])

    def test_only_allowed_durations(self):
        found = [n for line in vocal_lines(self.abc) for n in durations(line)]
        self.assertTrue(found)
        self.assertTrue(all(n in yue.ALLOWED for n in found), found)

    def test_bar_count(self):
        # 4 intro bars, then the pickup bar and the tune's 16 bars.
        self.assertEqual(sum(line.count("|") for line in vocal_lines(self.abc)), 21)
        self.assertEqual(self.labels.count("intro"), 1)
        self.assertEqual(self.labels.count("verse"), 5)   # 17 verse bars, four to a block

    def test_pickup_is_padded_with_a_rest(self):
        verse = self.abc.split("% verse", 1)[1]
        first = next(line for line in verse.splitlines() if line and not line.startswith(("V:", "%")))
        self.assertTrue(first.startswith("z8d4|"), first)  # an octave up: see SUNG_OCTAVE_BELOW

    def test_intro_chords_are_the_tunes_first_full_bars(self):
        intro = self.abc.split("% intro", 1)[1].split("% verse", 1)[0]
        vocal = next(line for line in intro.splitlines() if line and not line.startswith(("V:", "%")))
        self.assertEqual(vocal, '"G"z12|"G"z12|"C"z12|"G"z12|')

    def test_request_is_deterministic_and_as_long_as_the_score(self):
        req = yue.request(self.song, verses=1, seed=831001)
        self.assertEqual(req["seed"], 831001)
        self.assertEqual(req["lm_seed"], 831001)
        self.assertEqual(req["abc"], self.abc)
        self.assertAlmostEqual(req["duration"], 21 * 3 * 60 / 80)
        self.assertAlmostEqual(yue.vocal_offset(self.song, 4), (4 * 3 + 2) * 60 / 80)

    def test_melody_is_written_an_octave_above_where_it_sounds(self):
        written, _ = yue.score_abc(self.song, 1, 4, octave=0)
        self.assertEqual(yue.SUNG_OCTAVE_BELOW, 1)
        self.assertIn("z8D4|", written)
        self.assertIn("z8d4|", self.abc)

    def test_each_verse_starts_one_tune_later(self):
        self.assertAlmostEqual(yue.verse_offset(self.song, 1, 4), yue.vocal_offset(self.song, 4))
        # 16 bars of 3/4 at 80 BPM, the pickup sharing a bar with the last bar
        self.assertAlmostEqual(yue.verse_offset(self.song, 2, 4) - yue.verse_offset(self.song, 1, 4), 16 * 3 * 60 / 80)


class DurationTests(unittest.TestCase):
    def test_a_length_yu_e_cant_write_is_tied(self):
        # Two bars: music21 leaves a one-bar tune unmeasured, and the exporter reads bars.
        song = song_from(meter="4/4", melody='"C"C5/4 z11/4 | C D E F |',
                         lyrics=["one two three four five"])
        abc, _ = yue.score_abc(song, 1, intro_bars=0)
        music = "".join(vocal_lines(abc))
        self.assertIn("c4-c", music)
        self.assertTrue(all(n in yue.ALLOWED for n in durations(music)), music)

    def test_a_triplet_is_snapped_to_sixteenths(self):
        # YuE2's dialect has no tuplets; productions approximate them on the binary grid.
        song = song_from(meter="4/4", melody="(3CDE F2 z | C D E F |",
                         lyrics=["one two three four five six seven eight"])
        abc, _ = yue.score_abc(song, 1, intro_bars=0)
        music = "".join(vocal_lines(abc))
        self.assertTrue(music)
        self.assertTrue(all(n in yue.ALLOWED for n in durations(music)), music)


class RuntimeTests(unittest.TestCase):
    def test_missing_runtime_points_at_the_docs(self):
        here = os.getcwd()
        os.chdir(tempfile.mkdtemp())    # no .cache/ copies here either
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                for key in ("COPYIST_YUE_SYNTH", "COPYIST_YUE_MODEL", "COPYIST_YUE_VAE"):
                    os.environ.pop(key, None)
                with self.assertRaises(SongError) as caught:
                    yue.run_yue2cpp({"style": "x"}, Path(tempfile.mkdtemp()))
        finally:
            os.chdir(here)
        self.assertIn("docs/production.md", str(caught.exception))

    def test_produce_calls_yue_synth(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-yue-"))
        binary = tmp / "yue-synth"
        binary.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from pathlib import Path\n"
            "args = sys.argv[1:]\n"
            "Path(sys.argv[0]).with_name('args.txt').write_text('\\n'.join(args))\n"
            "out = args[args.index('--out') + 1]\n"
            "Path(out).write_bytes(b'RIFF')\n",
            encoding="utf-8",
        )
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
        model, vae = tmp / "model.gguf", tmp / "vae.gguf"
        model.write_bytes(b"m")
        vae.write_bytes(b"v")
        out = tmp / "out"
        env = {
            "COPYIST_YUE_SYNTH": str(binary),
            "COPYIST_YUE_MODEL": str(model),
            "COPYIST_YUE_VAE": str(vae),
            "COPYIST_YUE_DEVICE": "MTL0",
        }
        with mock.patch.dict(os.environ, env):
            code = main(["produce", str(ROOT / "songs" / "amazing-grace.yaml"),
                         "--verses", "1", "--seed", "831001", "--out", str(out)])
        self.assertEqual(code, 0)
        audio = out / "amazing-grace" / "production" / "production.wav"
        self.assertTrue(audio.is_file())
        args = (tmp / "args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(args[args.index("--device") + 1], "MTL0")
        self.assertEqual(args[args.index("--model") + 1], str(model))
        request = json.loads((out / "amazing-grace" / "production" / "yue-request.json").read_text(encoding="utf-8"))
        self.assertIn('"G"z12|"G"z12|"C"z12|"G"z12|', request["abc"])
        self.assertEqual(request["output_format"], "wav16")
        self.assertNotIn("--adapters", args)

        loras = tmp / "loras"
        loras.mkdir()
        (loras / "voice.safetensors").write_bytes(b"x")
        with mock.patch.dict(os.environ, env):
            code = main(["produce", str(ROOT / "songs" / "amazing-grace.yaml"), "--out", str(out),
                         "--lora", str(loras / "voice.safetensors") + ":0.8", "--style", "lightson, a waltz"])
        self.assertEqual(code, 0)
        args = (tmp / "args.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(args[args.index("--adapters") + 1], str(loras.resolve()))
        request = json.loads((out / "amazing-grace" / "production" / "yue-request.json").read_text(encoding="utf-8"))
        self.assertEqual(request["adapters"], [{"name": "voice.safetensors", "scale": 0.8}])
        self.assertEqual(request["style"], "lightson, a waltz")

    def test_a_missing_lora_is_refused(self):
        with self.assertRaises(SongError):
            yue.lora_adapters(["/nowhere/voice.safetensors"])
