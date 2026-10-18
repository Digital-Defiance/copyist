import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from copyist.web.server import make_server

ROOT = Path(__file__).resolve().parents[1]

TRAINING = """device mps; artist 39 (+2 held out), minted 4516
LoRA rank 32: 34.9M parameters
EVAL step 0 {'artist_held_out': 4.767, 'artist_trained': 5.0268, 'minted_val': 3.6086}
step 1/800 loss 3.420 21.4 s/step, about 4.7 h to go
step 100/800 loss 4.396 15.4 s/step, about 3.0 h to go
EVAL step 100 {'artist_held_out': 4.0061, 'artist_trained': 4.2534, 'minted_val': 3.5809}
step 180/800 loss 3.112 15.3 s/step, about 2.6 h to go
"""


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="copyist-web-"))
        (cls.root / "songs").mkdir()
        shutil.copy(ROOT / "songs" / "amazing-grace.yaml", cls.root / "songs")
        out = cls.root / "out" / "amazing-grace"
        (out / "takes" / "take-1").mkdir(parents=True)
        (out / "report.md").write_text("**Finished:** 0 failing, 0 warnings.\n\n| Check | Result | Where | Details |\n"
                                       "|---|---|---|---|\n| bars | pass |  | All 17 bars add up. |\n", encoding="utf-8")
        import pymupdf
        with pymupdf.open() as doc:
            doc.new_page(width=200, height=100).insert_text((20, 50), "Amazing Grace")
            doc.new_page(width=200, height=100)
            doc.save(out / "lead-sheet.pdf")
        (out / "takes" / "take-1" / "production.wav").write_bytes(bytes(range(256)) * 4)
        (out / "amazing-grace.wav").write_bytes(bytes(range(256)) * 4)
        (out / "stems").mkdir()
        (out / "stems" / "piano.wav").write_bytes(b"RIFF")
        (out / "audio.json").write_text(json.dumps({
            "engine": "sampled", "credits": ["Salamander Grand Piano V3 by Alexander Holm (CC BY 3.0)"], "note": "",
            "parts": [{"part": "piano", "instrument": "piano", "label": "Salamander Grand Piano V3",
                       "licence": "CC BY 3.0", "stem": "piano.wav"},
                      {"part": "bass", "instrument": "upright-bass", "label": "Meatbass", "licence": "CC0",
                       "stem": "bass.wav"}]}))
        (out / "takes" / "take-1" / "yue-request.json").write_text(json.dumps(
            {"style": "lightson, a waltz", "seed": 7, "adapters": [{"name": "step-300.safetensors", "scale": 1}]}))
        run = cls.root / ".cache" / "lora" / "lights-on"
        (run / "lora").mkdir(parents=True)
        (run / "train-output.txt").write_text(TRAINING, encoding="utf-8")
        (run / "lora" / "step-300.safetensors").write_bytes(b"x")
        (run / "songs.jsonl").write_text(
            json.dumps({"style": "lightson, in the style of lightson. Female lead. Banjo."}) + "\n"
            + json.dumps({"style": "lightson, in the style of lightson. Female lead. Strings."}) + "\n", encoding="utf-8")
        cls.server = make_server(cls.root, port=0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": f"127.0.0.1:{self.port}", **(headers or {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r, data

    def post(self, body, **headers):
        return self.request("POST", "/api/jobs", body, {"Content-Type": "application/json", "X-Copyist": "1", **headers})

    def test_page_and_songs(self):
        r, data = self.request("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn(b"<title>Copyist</title>", data)
        r, data = self.request("GET", "/static/fonts/shantell-sans.woff2")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "font/woff2"))
        r, data = self.request("GET", "/api/songs")
        self.assertEqual([s["title"] for s in json.loads(data)], ["Amazing Grace"])

    def test_song_detail(self):
        r, data = self.request("GET", "/api/songs/amazing-grace")
        song = json.loads(data)
        self.assertEqual(song["report"]["checks"][0]["check"], "bars")
        self.assertEqual(song["sheets"], [{"label": "Lead sheet", "path": "out/amazing-grace/lead-sheet.pdf"}])
        take = song["recordings"][0]
        self.assertEqual((take["kind"], take["seed"], take["voice"]), ("take", 7, ["step-300.safetensors"]))
        self.assertIn("waltz", song["default_style"])
        self.assertEqual(self.request("GET", "/api/songs/nope")[0].status, 404)

    def test_sheets_come_as_page_images(self):
        r, data = self.request("GET", "/api/pages?file=out/amazing-grace/lead-sheet.pdf")
        pages = json.loads(data)["pages"]
        self.assertEqual(len(pages), 2)
        r, png = self.request("GET", "/files/" + pages[0])
        self.assertEqual((r.status, r.getheader("Content-Type"), png[:4]), (200, "image/png", b"\x89PNG"))
        self.assertEqual(self.request("GET", "/api/pages?file=songs/amazing-grace.yaml")[0].status, 404)

    def test_audio_can_seek(self):
        r, data = self.request("GET", "/files/out/amazing-grace/takes/take-1/production.wav", headers={"Range": "bytes=10-19"})
        self.assertEqual(r.status, 206)
        self.assertEqual(data, bytes(range(10, 20)))
        self.assertEqual(r.getheader("Content-Range"), "bytes 10-19/1024")

    def test_only_out_is_served(self):
        for path in ("/files/songs/amazing-grace.yaml", "/files/out/../songs/amazing-grace.yaml",
                     "/files/out/%2e%2e/songs/amazing-grace.yaml", "/static/../server.py"):
            self.assertEqual(self.request("GET", path)[0].status, 404, path)

    def test_other_hosts_and_sites_are_refused(self):
        self.assertEqual(self.request("GET", "/api/songs", headers={"Host": "evil.example"})[0].status, 403)
        self.assertEqual(self.request("POST", "/api/jobs", {"action": "build", "song": "amazing-grace"},
                                      {"Content-Type": "application/json"})[0].status, 403)
        self.assertEqual(self.post({"action": "build", "song": "amazing-grace"}, Origin="https://evil.example")[0].status, 403)

    def test_bad_requests_say_why(self):
        r, data = self.post({"action": "erase", "song": "amazing-grace"})
        self.assertEqual((r.status, json.loads(data)["error"]), (400, "Unknown action."))
        r, data = self.post({"action": "produce", "song": "amazing-grace", "voice": "../../etc/passwd"})
        self.assertEqual((r.status, json.loads(data)["error"]), (400, "No such voice."))
        r, data = self.post({"action": "build", "song": "../songs/x"})
        self.assertEqual(r.status, 400)

    def test_a_job_runs_and_reports(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("COPYIST_")}
        env["PYTHONPATH"] = str(ROOT)
        env["COPYIST_HOME"] = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, env, clear=True):
            r, data = self.post({"action": "produce", "song": "amazing-grace", "voice": ".cache/lora/lights-on/lora/step-300.safetensors"})
            self.assertEqual(r.status, 202, data)
            job = json.loads(data)
            self.assertEqual(self.post({"action": "produce", "song": "amazing-grace"})[0].status, 400)  # one at a time
            for _ in range(120):
                job = json.loads(self.request("GET", f"/api/jobs/{job['id']}")[1])
                if job["status"] != "running":
                    break
                time.sleep(0.5)
        self.assertEqual(job["status"], "failed")       # no YuE2 here; the output says what to set
        self.assertIn("yue-synth) isn't installed here", job["output"])
        self.assertIn("--lora .cache/lora/lights-on/lora/step-300.safetensors:1", job["output"])

    def test_health_and_models(self):
        health = json.loads(self.request("GET", "/api/health")[1])
        self.assertTrue(health["ok"])
        self.assertEqual(set(health["models"]), {"singer", "voices"})
        listing = json.loads(self.request("GET", "/api/models")[1])
        self.assertIn("CC BY-NC 4.0", listing["licence"])
        singer = next(g for g in listing["groups"] if g["id"] == "singer")
        self.assertEqual([m["id"] for m in singer["models"]], ["yue2", "yue2-vae"])

    def test_instruments_are_listed_in_packs(self):
        health = json.loads(self.request("GET", "/api/health")[1])
        self.assertEqual(set(health["instruments"]), {"band", "keys", "bells", "folk", "electric", "winds"})
        listing = json.loads(self.request("GET", "/api/models")[1])
        band = next(g for g in listing["instruments"] if g["id"] == "instruments-band")
        self.assertEqual([i["id"] for i in band["models"]],
                         ["piano", "electric-bass", "upright-bass", "drums", "clarinet"])
        self.assertGreater(band["size"], 500_000_000)
        keys = next(g for g in listing["instruments"] if g["id"] == "instruments-keys")
        self.assertEqual([i["id"] for i in keys["models"]], ["organ", "harp", "tonewheel"])
        bells = next(g for g in listing["instruments"] if g["id"] == "instruments-bells")
        self.assertEqual([i["id"] for i in bells["models"]], ["musicbox"])
        folk = next(g for g in listing["instruments"] if g["id"] == "instruments-folk")
        self.assertEqual([i["id"] for i in folk["models"]], ["nylon-guitar", "steel-guitar", "fiddle"])
        electric = next(g for g in listing["instruments"] if g["id"] == "instruments-electric")
        self.assertEqual([i["id"] for i in electric["models"]], ["electric-guitar"])
        winds = next(g for g in listing["instruments"] if g["id"] == "instruments-winds")
        self.assertEqual([i["id"] for i in winds["models"]], ["flute", "sax"])
        self.assertIn("sfizz", listing)

    def test_the_band_recording_says_what_played_it(self):
        song = json.loads(self.request("GET", "/api/songs/amazing-grace")[1])
        band = song["band"]
        self.assertEqual((band["engine"], band["path"]), ("sampled", "out/amazing-grace/amazing-grace.wav"))
        self.assertEqual([(p["part"], p["path"]) for p in band["parts"]],
                         [("piano", "out/amazing-grace/stems/piano.wav"), ("bass", None)])   # no bass stem on disk

    def test_styles_for_the_songs_meter_and_the_actions_that_use_them(self):
        from copyist.web.server import job_args
        song = json.loads(self.request("GET", "/api/songs/amazing-grace")[1])
        self.assertIn("waltz", [s["id"] for s in song["styles"]])
        self.assertNotIn("rock", [s["id"] for s in song["styles"]])              # rock is 4/4; this is 3/4
        self.assertEqual(song["style_in_use"], "waltz")
        project = self.server.RequestHandlerClass.project
        self.assertEqual(job_args(project, {"action": "gallery", "song": "amazing-grace"})[2],
                         ["gallery", "songs/amazing-grace.yaml"])
        self.assertEqual(job_args(project, {"action": "use-style", "song": "amazing-grace", "style": "hymn",
                                            "tempo": 72})[2],
                         ["use-style", "songs/amazing-grace.yaml", "hymn", "--tempo", "72"])
        self.assertEqual(job_args(project, {"action": "gallery-takes", "song": "amazing-grace",
                                            "voice": ".cache/lora/lights-on/lora/step-300.safetensors"})[2],
                         ["gallery", "songs/amazing-grace.yaml", "--takes",
                          "--lora", ".cache/lora/lights-on/lora/step-300.safetensors:1",
                          "--prefix", "lightson, in the style of lightson. Female lead."])
        for bad in ({"style": "rock"}, {"style": "no-such-style"}, {"style": "hymn", "tempo": 900}):
            with self.assertRaises(ValueError):
                job_args(project, {"action": "use-style", "song": "amazing-grace", **bad})

    def test_writing_a_song_from_the_page(self):
        from copyist.web.server import job_args
        project = self.server.RequestHandlerClass.project
        label, slug, args = job_args(project, {"action": "write", "title": "Carry Me Home", "style": "waltz",
                                               "voice": "tenor", "candidates": 3,
                                               "lyrics": "[Verse]\nMorning comes across the hill"})
        self.assertEqual(slug, "carry-me-home")
        self.assertEqual(args, ["write", "out/carry-me-home/write/lyrics.txt", "--title", "Carry Me Home",
                                "--voice", "tenor", "--candidates", "3", "--seed", "1", "--style", "waltz"])
        self.assertEqual((self.root / "out/carry-me-home/write/lyrics.txt").read_text(),
                         "[Verse]\nMorning comes across the hill\n")
        for bad in ({"title": ""}, {"lyrics": ""}, {"style": "no-such-style"}, {"voice": "mezzo"},
                    {"candidates": 40}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                job_args(project, {"action": "write", "title": "T", "lyrics": "la la", **bad})
        # Candidates as `copyist write` leaves them; the page lists them and plays the previews.
        folder = self.root / "out" / "carry-me-home" / "write"
        (folder / "candidate-1").mkdir(parents=True, exist_ok=True)
        (folder / "candidate-1" / "preview.wav").write_bytes(b"RIFF")
        (folder / "candidate-1" / "carry-me-home.yaml").write_text("title: Carry Me Home\n")
        (folder / "candidates.json").write_text(json.dumps({"title": "Carry Me Home", "slug": "carry-me-home",
            "style": "waltz", "voice": "tenor", "candidates": [
                {"seed": 1, "folder": "candidate-1", "ok": True, "rank": 1, "song": "candidate-1/carry-me-home.yaml",
                 "preview": "candidate-1/preview.wav", "key": "D", "meter": "3/4", "tempo": 86, "scores": {}},
                {"seed": 2, "folder": "candidate-2", "ok": False, "reason": "tuplets"}]}))
        listed = json.loads(self.request("GET", "/api/writing")[1])
        self.assertEqual([(w["slug"], w["candidates"], w["usable"]) for w in listed], [("carry-me-home", 2, 1)])
        d = json.loads(self.request("GET", "/api/writing/carry-me-home")[1])
        self.assertEqual(d["candidates"][0]["preview_path"], "out/carry-me-home/write/candidate-1/preview.wav")
        self.assertEqual((d["next_seed"], d["song_exists"]), (3, False))
        self.assertIn("Morning comes", d["lyrics"])
        self.assertEqual(self.request("GET", "/files/out/carry-me-home/write/candidate-1/preview.wav")[0].status, 200)
        self.assertEqual(self.request("GET", "/api/writing/nothing-here")[0].status, 404)
        self.assertEqual(job_args(project, {"action": "write-more", "slug": "carry-me-home", "candidates": 2})[2],
                         ["write", "out/carry-me-home/write/lyrics.txt", "--title", "Carry Me Home", "--voice",
                          "tenor", "--candidates", "2", "--seed", "3", "--style", "waltz"])
        self.assertEqual(job_args(project, {"action": "keep", "slug": "carry-me-home", "seed": 1})[2],
                         ["write", "--title", "Carry Me Home", "--keep", "1", "--build"])
        for bad in ({"seed": 2}, {"seed": 9}, {"slug": "../songs"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                job_args(project, {"action": "keep", "slug": "carry-me-home", **bad})
        styles = json.loads(self.request("GET", "/api/styles")[1])
        self.assertIn("waltz", [s["id"] for s in styles])

    def test_transcribing_a_recording_from_the_page(self):
        from copyist.web.server import job_args
        project = self.server.RequestHandlerClass.project
        r, data = self.request("POST", "/api/upload?name=My%20Song.wav", None,
                               {"X-Copyist": "1", "Content-Type": "application/octet-stream"})
        self.assertEqual(r.status, 400)                                          # empty
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request("POST", "/api/upload?name=My%20Song.wav", body=b"RIFF" + bytes(1000),
                  headers={"Host": f"127.0.0.1:{self.port}", "X-Copyist": "1"})
        resp = c.getresponse()
        up = json.loads(resp.read())
        c.close()
        self.assertEqual(resp.status, 201)
        self.assertTrue(up["upload"].startswith("out/uploads/") and up["upload"].endswith("-My-Song.wav"))
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request("POST", "/api/upload?name=notes.txt", body=b"hello", headers={"Host": f"127.0.0.1:{self.port}", "X-Copyist": "1"})
        self.assertEqual(c.getresponse().status, 400)
        c.close()
        self.assertEqual(self.request("POST", "/api/upload?name=a.wav", None, {"Content-Type": "x"})[0].status, 403)
        label, slug, args = job_args(project, {"action": "transcribe", "upload": up["upload"], "title": "My Song",
                                               "lyrics": "la la la"})
        self.assertEqual(slug, "my-song")
        self.assertEqual(args, ["transcribe", up["upload"], "--title", "My Song", "--engine", "open",
                                "--lyrics", "out/my-song/transcribe/lyrics-given.txt"])
        for bad in ({"upload": "songs/amazing-grace.yaml"}, {"upload": "out/uploads/nothing.wav"}, {"title": ""},
                    {"engine": "sheetsage", "accept_licence": True}, {"engine": "magic"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                job_args(project, {"action": "transcribe", "upload": up["upload"], "title": "T", **bad})
        folder = self.root / "out" / "my-song" / "transcribe"
        self.assertEqual(json.loads(self.request("GET", "/api/transcriptions/my-song")[1])["pending"], True)
        (folder / "source.wav").write_bytes(b"RIFF")
        (folder / "my-song.yaml").write_text("title: My Song\n")
        (folder / "transcription.json").write_text(json.dumps({"title": "My Song", "slug": "my-song", "engine": "open",
            "recording": "My Song.wav", "source": "source.wav", "song": "my-song.yaml", "key": "C", "meter": "4/4",
            "tempo": "100", "doubts": ["Bar 2, beat 1: between E4 and F4; wrote E4"], "notes": [], "fails": 0,
            "warnings": 1}))
        d = json.loads(self.request("GET", "/api/transcriptions/my-song")[1])
        self.assertEqual((d["source_path"], d["preview_path"], d["kept"]), ("out/my-song/transcribe/source.wav", None, False))
        listed = json.loads(self.request("GET", "/api/transcriptions")[1])
        self.assertEqual([t["slug"] for t in listed["items"]], ["my-song"])
        self.assertEqual(job_args(project, {"action": "keep-transcription", "slug": "my-song"})[2],
                         ["transcribe", "--title", "My Song", "--keep", "--build"])

    def test_an_instrument_download_needs_no_licence_box(self):
        from copyist import instruments

        def fake_pack(pack, progress=None, opener=None):
            progress(5, 5)
            return [Path("/tmp/instruments/piano")]
        with mock.patch.object(instruments, "download_pack", fake_pack):
            r, data = self.post({"action": "download", "group": "instruments-band"})
            self.assertEqual(r.status, 202, data)
            job = json.loads(data)
            for _ in range(50):
                job = json.loads(self.request("GET", f"/api/jobs/{job['id']}")[1])
                if job["status"] != "running":
                    break
                time.sleep(0.1)
        self.assertEqual((job["status"], job["progress"]), ("done", [5, 5]))
        r, _ = self.post({"action": "download", "group": "instruments-everything"})
        self.assertEqual(r.status, 400)

    def test_downloads_need_the_licence_accepted(self):
        r, data = self.post({"action": "download", "group": "singer"})
        self.assertEqual((r.status, json.loads(data)["error"]), (400, "Accept the licence first."))
        r, data = self.post({"action": "download", "group": "everything", "accept_licence": True})
        self.assertEqual(r.status, 400)

    def test_a_download_job_reports_progress(self):
        from copyist import models
        calls = []

        def fake_group(group, progress=None, opener=None):
            for done in (10, 20):
                progress(done, 20)
                calls.append(done)
            return [Path("/tmp/model.gguf")]
        with mock.patch.object(models, "download_group", fake_group):
            r, data = self.post({"action": "download", "group": "voices", "accept_licence": True})
            self.assertEqual(r.status, 202, data)
            job = json.loads(data)
            for _ in range(50):
                job = json.loads(self.request("GET", f"/api/jobs/{job['id']}")[1])
                if job["status"] != "running":
                    break
                time.sleep(0.1)
        self.assertEqual((job["status"], job["progress"]), ("done", [20, 20]))
        self.assertIn("Ready: /tmp/model.gguf", job["output"])

    def test_training_and_voices(self):
        run = json.loads(self.request("GET", "/api/training")[1])[0]
        self.assertEqual((run["step"], run["steps"], run["hours_left"]), (180, 800, 2.6))
        self.assertEqual([e["step"] for e in run["evals"]], [0, 100])
        self.assertEqual(run["checkpoints"], ["step-300"])
        voices = json.loads(self.request("GET", "/api/voices")[1])
        self.assertEqual(voices, [{"id": ".cache/lora/lights-on/lora/step-300.safetensors", "label": "lights-on, step 300",
                                   "style": "lightson, in the style of lightson. Female lead."}])


class LibraryTests(unittest.TestCase):
    def test_a_new_library_gets_a_demo_song(self):
        root = Path(tempfile.mkdtemp(prefix="copyist-lib-")) / "Copyist"
        server = make_server(root, port=0, demo=True)
        server.server_close()
        self.assertTrue((root / "songs" / "amazing-grace.yaml").is_file())
        self.assertTrue((root / "out").is_dir())

    def test_the_demo_song_matches_the_test_song(self):
        self.assertEqual((ROOT / "copyist" / "demo" / "amazing-grace.yaml").read_text(encoding="utf-8"),
                         (ROOT / "songs" / "amazing-grace.yaml").read_text(encoding="utf-8"))

    def test_serve_for_the_app_prints_where_it_is(self):
        import subprocess
        import sys
        root = tempfile.mkdtemp(prefix="copyist-lib-")
        p = subprocess.Popen([sys.executable, "-m", "copyist", "serve", "--root", root, "--port", "0", "--machine"],
                             cwd=ROOT, stdout=subprocess.PIPE, text=True)
        try:
            line = json.loads(p.stdout.readline())
            self.assertEqual(line["copyist"], "ready")
            c = http.client.HTTPConnection("127.0.0.1", line["port"], timeout=10)
            c.request("GET", "/api/health")
            self.assertTrue(json.loads(c.getresponse().read())["ok"])
            c.close()
        finally:
            p.terminate()
            p.wait(timeout=10)
            p.stdout.close()


if __name__ == "__main__":
    unittest.main()
