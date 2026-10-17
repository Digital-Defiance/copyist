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
        import fitz
        with fitz.open() as doc:
            doc.new_page(width=200, height=100).insert_text((20, 50), "Amazing Grace")
            doc.new_page(width=200, height=100)
            doc.save(out / "lead-sheet.pdf")
        (out / "takes" / "take-1" / "production.wav").write_bytes(bytes(range(256)) * 4)
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
        env = {k: v for k, v in os.environ.items() if not k.startswith("COPYIST_YUE")}
        env["PYTHONPATH"] = str(ROOT)
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
        self.assertIn("YuE2 isn't set up here", job["output"])
        self.assertIn("--lora .cache/lora/lights-on/lora/step-300.safetensors:1", job["output"])

    def test_training_and_voices(self):
        run = json.loads(self.request("GET", "/api/training")[1])[0]
        self.assertEqual((run["step"], run["steps"], run["hours_left"]), (180, 800, 2.6))
        self.assertEqual([e["step"] for e in run["evals"]], [0, 100])
        self.assertEqual(run["checkpoints"], ["step-300"])
        voices = json.loads(self.request("GET", "/api/voices")[1])
        self.assertEqual(voices, [{"id": ".cache/lora/lights-on/lora/step-300.safetensors", "label": "lights-on, step 300",
                                   "style": "lightson, in the style of lightson. Female lead."}])


if __name__ == "__main__":
    unittest.main()
