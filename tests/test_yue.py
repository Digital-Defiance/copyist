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

    BATCH_SYNTH = (
        "#!/usr/bin/env python3\n"
        "# Stands in for yue-synth: one track per song of the batch, numbered as yue2.cpp numbers them.\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "req = json.loads(Path(args[args.index('--request') + 1]).read_text())\n"
        "with open(Path(sys.argv[0]).with_name('calls.txt'), 'a') as f:\n"
        "    f.write(json.dumps({'lm_batch_size': req.get('lm_batch_size', 1), 'lm_seed': req['lm_seed']}) + '\\n')\n"
        "out = Path(args[args.index('--out') + 1])\n"
        "if req.get('semantic_tokens'):\n"
        "    out.write_bytes(b'RIFF' + f\"replay-{req['semantic_tokens']}/s{req.get('steps', 32)}\".encode())\n"
        "    out.with_suffix('.json').write_text(json.dumps(dict(req)))\n"
        "    sys.exit(0)\n"
        "n = req.get('lm_batch_size', 1)\n"
        "if n > 1 and os.environ.get('FAKE_BATCH_FAILS'):\n"
        "    sys.exit(3)\n"
        "for i in range(n):\n"
        "    track = out.with_name(out.stem + f'{i}0' + out.suffix) if n > 1 else out\n"
        "    steps = f\"/s{req['steps']}\" if 'steps' in req else ''\n"
        "    track.write_bytes(b'RIFF' + (str(req['lm_seed'] + i) + steps).encode())\n"
        "    track.with_suffix('.json').write_text(json.dumps({'lm_seed': req['lm_seed'] + i, 'seed': req['seed'],\n"
        "        'steps': req.get('steps', 32), 'semantic_tokens': f\"codes-{req['lm_seed'] + i}\"}))\n"
    )

    def batch_env(self) -> tuple[Path, dict]:
        tmp = Path(tempfile.mkdtemp(prefix="copyist-yue-batch-"))
        binary = tmp / "yue-synth"
        binary.write_text(self.BATCH_SYNTH, encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
        (tmp / "model.gguf").write_bytes(b"m")
        (tmp / "vae.gguf").write_bytes(b"v")
        return tmp, {"COPYIST_YUE_SYNTH": str(binary), "COPYIST_YUE_MODEL": str(tmp / "model.gguf"),
                     "COPYIST_YUE_VAE": str(tmp / "vae.gguf")}

    def calls(self, tmp: Path) -> list[dict]:
        return [json.loads(line) for line in (tmp / "calls.txt").read_text().splitlines()]

    def test_several_takes_are_drawn_in_one_run(self):
        tmp, env = self.batch_env()
        out = tmp / "out"
        with mock.patch.dict(os.environ, env):
            code = main(["produce", str(ROOT / "songs" / "amazing-grace.yaml"), "--takes", "3", "--take", "t",
                         "--seed", "100", "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(tmp), [{"lm_batch_size": 3, "lm_seed": 100}])
        takes = out / "amazing-grace" / "takes"
        self.assertEqual(sorted(p.name for p in takes.iterdir()), ["t-1", "t-2", "t-3"])
        for k in (1, 2, 3):
            folder = takes / f"t-{k}"
            self.assertEqual((folder / "production.wav").read_bytes(), b"RIFF" + str(99 + k).encode())
            req = json.loads((folder / "yue-request.json").read_text())
            self.assertEqual((req["lm_seed"], req["seed"]), (99 + k, 100))   # rendered alone, the same take
            self.assertNotIn("lm_batch_size", req)
            self.assertTrue((folder / "replay.json").is_file())

    def test_a_batch_that_fails_renders_each_take_alone_with_the_same_seeds(self):
        tmp, env = self.batch_env()
        out = tmp / "out"
        with mock.patch.dict(os.environ, dict(env, FAKE_BATCH_FAILS="1")):
            code = main(["produce", str(ROOT / "songs" / "amazing-grace.yaml"), "--takes", "2", "--seed", "7",
                         "--out", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(tmp), [{"lm_batch_size": 2, "lm_seed": 7}, {"lm_batch_size": 1, "lm_seed": 7},
                                           {"lm_batch_size": 1, "lm_seed": 8}])
        takes = out / "amazing-grace" / "takes"
        self.assertEqual(sorted(p.name for p in takes.iterdir()), ["seed-7-1", "seed-7-2"])
        self.assertEqual((takes / "seed-7-2" / "production.wav").read_bytes(), b"RIFF8")

    def test_drafts_then_finishing_the_one_you_like(self):
        from copyist import yue
        from copyist.web.server import Project, job_args
        tmp, env = self.batch_env()
        root = tmp / "project"
        (root / "songs").mkdir(parents=True)
        (root / "songs" / "amazing-grace.yaml").write_text((ROOT / "songs" / "amazing-grace.yaml").read_text())
        out = root / "out"
        with mock.patch.dict(os.environ, env):
            code = main(["produce", str(root / "songs" / "amazing-grace.yaml"), "--takes", "2", "--draft",
                         "--take", "d", "--seed", "5", "--out", str(out)])
        self.assertEqual(code, 0)
        takes = out / "amazing-grace" / "takes"
        self.assertEqual(self.calls(tmp), [{"lm_batch_size": 2, "lm_seed": 5}])
        for k in (1, 2):
            folder = takes / f"d-{k}"
            self.assertEqual(json.loads((folder / "yue-request.json").read_text())["steps"], yue.DRAFT_STEPS)
            self.assertEqual(json.loads((folder / yue.TAKE_INFO).read_text())["steps"], yue.DRAFT_STEPS)
            self.assertTrue(yue.is_draft(folder))
        project = Project(root)
        listed = {r["name"]: r for r in project.recordings("amazing-grace") if r["kind"] == "take"}
        self.assertTrue(listed["d-2"]["draft"])
        label, _, args = job_args(project, {"action": "produce", "song": "amazing-grace", "takes": 4, "draft": True})
        self.assertEqual(label, "Making 4 drafts")
        self.assertIn("--draft", args)
        label, _, args = job_args(project, {"action": "finish", "song": "amazing-grace", "take": "d-2"})
        self.assertEqual((label, args[0], args[2]), ("Finishing the take", "finish", "d-2"))

        with mock.patch.dict(os.environ, env):
            code = main(["finish", str(root / "songs" / "amazing-grace.yaml"), "d-2", "--out", str(out)])
        self.assertEqual(code, 0)
        folder = takes / "d-2"
        # The same performance (take 2's codes), all 32 steps; the draft kept beside it.
        self.assertEqual((folder / "production.wav").read_bytes(), b"RIFFreplay-codes-6/s32")
        self.assertEqual((folder / "draft.wav").read_bytes(), b"RIFF6/s12")
        self.assertFalse(yue.is_draft(folder))
        self.assertNotIn("steps", json.loads((folder / "yue-request.json").read_text()))
        self.assertFalse(any(p.name.startswith(".finish") for p in takes.iterdir()))
        with self.assertRaises(ValueError):       # finished now: nothing left to finish
            job_args(Project(root), {"action": "finish", "song": "amazing-grace", "take": "d-2"})

    def test_a_take_without_codes_cant_be_finished(self):
        from copyist import yue
        folder = Path(tempfile.mkdtemp(prefix="copyist-nofinish-"))
        (folder / "replay.json").write_text("{}")
        with self.assertRaises(SongError):
            yue.finish_take(folder)

    def test_the_page_asks_for_up_to_four_takes(self):
        from copyist.web.server import Project, job_args
        root = Path(tempfile.mkdtemp(prefix="copyist-takes-web-"))
        (root / "songs").mkdir()
        (root / "songs" / "amazing-grace.yaml").write_text((ROOT / "songs" / "amazing-grace.yaml").read_text())
        project = Project(root)
        label, _, args = job_args(project, {"action": "produce", "song": "amazing-grace", "takes": 3})
        self.assertEqual(label, "Making 3 takes")
        self.assertEqual(args[args.index("--takes") + 1], "3")
        self.assertNotIn("--takes", job_args(project, {"action": "produce", "song": "amazing-grace"})[2])
        with self.assertRaises(ValueError):
            job_args(project, {"action": "produce", "song": "amazing-grace", "takes": 5})

    def test_a_missing_lora_is_refused(self):
        with self.assertRaises(SongError):
            yue.lora_adapters(["/nowhere/voice.safetensors"])
